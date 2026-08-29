"""P0-10 Phase B: deterministic interleaving proofs for the settle-vs-create and
close-vs-new-session-resolve races (SQLite cannot prove true concurrent-thread
timing -- see test_dining_session_append_order_locking.py for the same
documented limitation; MySQL row-lock proof is a separate release gate,
MYSQL_SESSION_CONCURRENCY_PROOF=PENDING_RELEASE_GATE). What IS proven here is
the LOCK ORDER CONTRACT: whichever operation actually commits first determines
a single, legal, deterministic outcome -- never a state where settlement
"succeeds" while a stale request still manages to write into the closed
session, and never a state where a legitimately-in-flight order is silently
dropped by a concurrent settlement.
"""

import asyncio
import unittest
from datetime import datetime

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.orders import OrderCreate, OrderItemIn, create_order, settle_table
from app.models.base import Base
from app.models.dining import DiningParticipant, DiningSession
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.services.dining_session_service import DiningSessionService, hash_participant_token
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT = "tenant-p0-10-races"
TABLE = "R01"
GUEST_TOKEN = "guest-token-races"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


class FakeMerchantRequest:
    def __init__(self):
        from types import SimpleNamespace
        self.state = SimpleNamespace(tenant_id=TENANT, token_type="merchant", role="owner", account_id=None)


def make_customer_request():
    return Request({
        "type": "http", "method": "POST", "path": "/api/v1/orders", "headers": [],
        "query_string": b"", "server": ("testserver", 80), "scheme": "http",
        "client": ("testclient", 50000),
    })


class SettlementRacesTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.db.add(Tenant(
            tenant_id=TENANT, name="Race Restaurant", password_hash="x",
            status=True, is_open=True, payment_mode="postpay",
        ))
        self.dish = MenuItem(tenant_id=TENANT, name="宫保鸡丁", price="28.00", available=True)
        self.db.add(self.dish)
        self.db.add(EntranceCode(
            id=generate_snowflake_id(), tenant_id=TENANT, name=TABLE,
            scene="E0000000R01A", table_no=TABLE, entry_type="table", status=1,
        ))
        await self.db.flush()

        now = datetime.utcnow()
        self.sa = DiningSession(
            tenant_id=TENANT, table_no=TABLE, status="OPEN",
            active_key=f"{TENANT}:{TABLE}", started_at=now, last_activity_at=now,
        )
        self.db.add(self.sa)
        await self.db.flush()
        self.participant = DiningParticipant(
            tenant_id=TENANT, session_id=self.sa.id,
            guest_token_hash=hash_participant_token(GUEST_TOKEN),
            joined_at=now, last_active_at=now,
        )
        self.db.add(self.participant)
        await self.db.flush()
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _order_body(self):
        return OrderCreate(
            shop=TENANT, table=TABLE,
            items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=28.0, qty=1)],
            total=28.0, dining_session_id=self.sa.id, participant_token=GUEST_TOKEN,
        )

    async def _existing_done_order(self, session):
        order = Order(
            tenant_id=TENANT, dining_session_id=session.id, table_no=TABLE,
            total="28.00", status="done", payment_status="paid", payment_method="mock",
            payment_mode="postpay", source="h5",
        )
        self.db.add(order)
        await self.db.flush()
        self.db.add(OrderItem(id=generate_snowflake_id(), order_id=order.id, name="宫保鸡丁", price="28.00", qty=1))
        await self.db.commit()
        return order

    # ---- R: settle wins first -> a stale create-order request for SA must be denied ----
    async def test_settle_first_then_stale_create_order_is_denied(self):
        await self._existing_done_order(self.sa)
        settle_res = await settle_table({"table_no": TABLE, "dining_session_id": str(self.sa.id)}, FakeMerchantRequest(), self.db)
        self.assertEqual(settle_res.code, 200, settle_res.msg)

        create_res = await create_order(self._order_body(), make_customer_request(), db=self.db)

        self.assertEqual(create_res.code, 409)  # 会话过期→可恢复码
        self.assertIn("本桌会话已过期", create_res.msg)
        # SA must not have gained a new order after settlement closed it.
        count_result = await self.db.execute(select(Order).where(Order.dining_session_id == self.sa.id))
        self.assertEqual(len({o.id for o in count_result.scalars().all()}), 1)  # only the pre-existing done order

    # ---- R: create wins first -> the new (not-yet-done) order blocks settlement, is never silently dropped ----
    async def test_create_first_then_settle_blocks_on_the_new_pending_order(self):
        create_res = await create_order(self._order_body(), make_customer_request(), db=self.db)
        self.assertEqual(create_res.code, 200, create_res.msg)

        settle_res = await settle_table({"table_no": TABLE, "dining_session_id": str(self.sa.id)}, FakeMerchantRequest(), self.db)

        # the brand-new order is not "done" yet (postpay defaults to pending) --
        # settlement must fail closed rather than silently settling around it.
        self.assertEqual(settle_res.code, 409)
        self.assertIn(create_res.data["order_id"], settle_res.data.get("blocking_order_ids", []))

    # ---- R: create wins first, order already reached done -> settle correctly includes it ----
    async def test_create_first_order_reaches_done_then_settle_includes_it(self):
        create_res = await create_order(self._order_body(), make_customer_request(), db=self.db)
        self.assertEqual(create_res.code, 200)
        order_id = int(create_res.data["order_id"])
        order = await self.db.get(Order, order_id)
        order.status = "done"
        await self.db.commit()

        settle_res = await settle_table({"table_no": TABLE, "dining_session_id": str(self.sa.id)}, FakeMerchantRequest(), self.db)

        self.assertEqual(settle_res.code, 200, settle_res.msg)
        self.assertEqual(settle_res.data["settled_count"], 1)
        snapshot_ids = {o["id"] for o in settle_res.data["settled_orders"]}
        self.assertIn(str(order_id), snapshot_ids)

    # ---- R: close then new-session-resolve -> next scan gets a genuinely NEW session, never SA ----
    async def test_close_then_resolve_creates_a_new_session_not_sa(self):
        await self._existing_done_order(self.sa)
        settle_res = await settle_table({"table_no": TABLE, "dining_session_id": str(self.sa.id)}, FakeMerchantRequest(), self.db)
        self.assertEqual(settle_res.code, 200, settle_res.msg)

        resolved = await DiningSessionService(self.db).resolve_session(tenant_id=TENANT, table_no=TABLE)
        await self.db.commit()

        sb_id = int(resolved["dining_session_id"])
        self.assertNotEqual(sb_id, self.sa.id)
        sb = await self.db.get(DiningSession, sb_id)
        self.assertEqual(sb.status, "OPEN")
        await self.db.refresh(self.sa)
        self.assertEqual(self.sa.status, "CLOSED")

    # ---- R08: old cart's cached session id, submitted after SA is terminal, is denied (never silently attached to SB) ----
    async def test_r08_old_cart_submit_after_session_closed_is_denied_not_remapped(self):
        await self._existing_done_order(self.sa)
        settle_res = await settle_table({"table_no": TABLE, "dining_session_id": str(self.sa.id)}, FakeMerchantRequest(), self.db)
        self.assertEqual(settle_res.code, 200, settle_res.msg)

        # SB now exists and is the table's current session.
        resolved = await DiningSessionService(self.db).resolve_session(tenant_id=TENANT, table_no=TABLE)
        await self.db.commit()
        sb_id = int(resolved["dining_session_id"])

        # a device whose in-memory cart still references SA (never refreshed) submits.
        stale_cart_body = self._order_body()  # dining_session_id=self.sa.id, baked in at setUp
        result = await create_order(stale_cart_body, make_customer_request(), db=self.db)

        self.assertEqual(result.code, 409)  # 会话过期→可恢复码，小程序据此重建会话重试
        self.assertIn("本桌会话已过期", result.msg)
        # must never have silently landed on SB instead.
        sb_orders = await self.db.execute(select(Order).where(Order.dining_session_id == sb_id))
        self.assertEqual(list(sb_orders.scalars().all()), [])


if __name__ == "__main__":
    unittest.main()
