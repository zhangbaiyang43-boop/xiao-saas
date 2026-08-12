import asyncio
import inspect
import unittest
from datetime import datetime

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.dining import DiningParticipant, DiningSession
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import OrderItem
from app.models.tenant import Tenant
from app.api.v1.orders import OrderCreate, OrderItemIn, _resolve_create_order_dining_context, create_order
from app.services.dining_session_service import hash_participant_token
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"
GUEST_TOKEN = "guest-token-real-owner"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_request(path="/api/v1/orders"):
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


class AppendOrderReadsDiningSessionUnderLockTest(unittest.IsolatedAsyncioTestCase):
    """settle_table locks the DiningSession row with with_for_update() before closing it.
    The customer append-order path used to read the same row with a plain (unlocked) SELECT,
    so it could act on a stale "still OPEN" snapshot concurrently with settle_table closing
    it -- the new order would land on a session that's already CLOSED and never be picked up
    by any future settle_table call again. This can't be proven with real concurrent
    transactions against SQLite (see test_coupon_redis_fallback_idempotency.py for why --
    same limitation), but MySQL's row lock is the exact mechanism settle_table's own
    with_for_update() already relies on elsewhere in this codebase. What's verified here:
    the read is now a locking read (so it *would* serialize against settle_table on
    production MySQL), and the sequential correctness of that locking read's WHERE clause
    (an already-closed session is never treated as appendable)."""

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(
            tenant_id=TENANT_A, name="Test Restaurant", password_hash="x",
            status=True, is_open=True, payment_mode="postpay",
        )
        self.db.add(self.tenant)
        self.dish = MenuItem(tenant_id=TENANT_A, name="Kung Pao Chicken", price="28.00", available=True)
        self.db.add(self.dish)
        # P0-01: this test is about append-order locking against settle_table, not
        # table validity -- give A12 a real, active registry entry.
        self.db.add(EntranceCode(
            id=generate_snowflake_id(),
            tenant_id=TENANT_A, name="A12", scene="E00000000012",
            table_no="A12", entry_type="table", status=1,
        ))
        await self.db.flush()

        now = datetime.utcnow()
        self.session = DiningSession(
            tenant_id=TENANT_A, table_no="A12", status="OPEN",
            active_key=f"{TENANT_A}:A12", started_at=now, last_activity_at=now,
        )
        self.db.add(self.session)
        await self.db.flush()
        self.participant = DiningParticipant(
            tenant_id=TENANT_A, session_id=self.session.id,
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
            shop=TENANT_A, table="A12",
            items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=28.0, qty=1)],
            total=28.0,
            dining_session_id=self.session.id,
            participant_token=GUEST_TOKEN,
        )

    async def test_append_order_read_is_a_locking_read(self):
        source = inspect.getsource(_resolve_create_order_dining_context)
        # The dining_session_id branch's SELECT must use with_for_update(), same as
        # settle_table's own session lock, so the two serialize against each other on
        # production MySQL instead of racing on a stale snapshot.
        branch_start = source.index("elif body.dining_session_id:")
        branch_source = source[branch_start:source.index("if is_table_account", branch_start)]
        self.assertIn("with_for_update()", branch_source)

    async def test_open_session_still_accepts_the_order(self):
        result = await create_order(self._order_body(), make_request(), db=self.db)
        self.assertEqual(result.code, 200)

    async def test_already_closed_session_rejects_the_append_instead_of_landing_on_a_dead_session(self):
        self.session.status = "CLOSED"
        await self.db.commit()

        result = await create_order(self._order_body(), make_request(), db=self.db)

        self.assertEqual(result.code, 400)
        self.assertIn("dining session not found", result.msg)


if __name__ == "__main__":
    unittest.main()
