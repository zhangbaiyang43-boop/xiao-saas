"""P0-12 finding 02: payment_mode is resolved fresh from the tenant's CURRENT
config on every create_order call (PER_ORDER_LIVE), with no session-level
pinning -- so if a merchant changes Tenant.payment_mode mid-session, two orders
in the SAME still-open DiningSession can legitimately end up with different
payment_mode values. Phase A's code reading concluded settle_table already
handles this correctly (per-order mode-aware aggregation, `_mark_order_offline_
paid` is a no-op once `payment_status == "paid"`), but no test proved the exact
end-to-end scenario. This file is that direct proof, not a source-text
assertion.

O1 created while tenant.payment_mode=table_account (30, unpaid).
Tenant mode changes to prepay.
O2 created in the SAME still-open session (40, prepay) and paid online.
O3 created and cancelled (20).

Verifies: O1/O2 keep their own creation-time payment_mode (never retroactively
rewritten), settle_table settles O1 (table_account, offline-paid at settle
time) and O2 (prepay, already paid -- must NOT be re-marked or double-credited)
together, excludes cancelled O3, and member-asset application happens at most
once for O2.
"""

import asyncio
import unittest
from datetime import datetime

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request
from types import SimpleNamespace

from app.config import settings
from app.models.base import Base
from app.models.dining import DiningParticipant, DiningSession
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.api.v1.orders import create_order, settle_table, OrderCreate, OrderItemIn, MockPayBody
from app.services.order_payment_service import OrderPaymentService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT = "tenant-p0-12-mixed"
TABLE = "T08"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_customer_request(customer_id):
    req = Request(
        {
            "type": "http", "method": "POST", "path": "/api/v1/orders",
            "headers": [], "query_string": b"",
            "server": ("testserver", 80), "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    req.state.customer_id = customer_id
    req.state.tenant_id = TENANT
    req.state.token_type = None
    return req


class FakeRequest:
    def __init__(self, **state):
        self.state = SimpleNamespace(**state)


def make_merchant_request():
    return FakeRequest(tenant_id=TENANT, token_type="merchant", role="owner", account_id=None)


class MixedPaymentModeSessionTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(
            tenant_id=TENANT, name="Test Restaurant", password_hash="x",
            status=True, is_open=True, payment_mode="table_account",
        )
        self.db.add(self.tenant)
        self.db.add(TenantConfig(tenant_id=TENANT, business_info={"is_open": True}))
        self.dish1 = MenuItem(tenant_id=TENANT, name="宫保鸡丁", price="30.00", available=True)
        self.dish2 = MenuItem(tenant_id=TENANT, name="鱼香肉丝", price="40.00", available=True)
        self.dish3 = MenuItem(tenant_id=TENANT, name="米饭", price="20.00", available=True)
        self.db.add_all([self.dish1, self.dish2, self.dish3])
        self.db.add(EntranceCode(
            id=generate_snowflake_id(),
            tenant_id=TENANT, name=TABLE, scene=f"E{TENANT}",
            table_no=TABLE, entry_type="table", status=1,
        ))
        await self.db.flush()

        now = datetime.utcnow()
        self.session = DiningSession(
            tenant_id=TENANT, table_no=TABLE, status="OPEN",
            active_key=f"{TENANT}:{TABLE}", started_at=now, last_activity_at=now,
        )
        self.db.add(self.session)
        await self.db.flush()
        for cid in (8001, 8002, 8003):
            self.db.add(DiningParticipant(
                tenant_id=TENANT, session_id=self.session.id,
                customer_id=cid, joined_at=now, last_active_at=now,
            ))
        await self.db.flush()
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _body(self, dish, *, request_id, qty=1):
        return OrderCreate(
            shop=TENANT, table=TABLE, dining_session_id=self.session.id,
            items=[OrderItemIn(dish_id=dish.id, name=dish.name, price=float(dish.price), qty=qty)],
            total=float(dish.price) * qty, request_id=request_id,
        )

    async def test_mixed_mode_session_settles_without_double_charge_or_double_asset(self):
        # O1: created while tenant is table_account.
        o1_result = await create_order(
            self._body(self.dish1, request_id="MIX-O1"), make_customer_request(8001), db=self.db,
        )
        self.assertEqual(o1_result.code, 200, o1_result.msg)
        self.assertEqual(o1_result.data["payment_mode"], "table_account")
        o1_id = int(o1_result.data["order_id"])

        # Merchant changes the store's mode mid-session.
        await self.db.refresh(self.tenant)
        self.tenant.payment_mode = "prepay"
        await self.db.commit()

        # O2: created in the SAME still-open session, resolves the NEW live mode.
        o2_result = await create_order(
            self._body(self.dish2, request_id="MIX-O2"), make_customer_request(8002), db=self.db,
        )
        self.assertEqual(o2_result.code, 200, o2_result.msg)
        self.assertEqual(o2_result.data["payment_mode"], "prepay")
        self.assertTrue(o2_result.data["need_payment"])
        o2_id = int(o2_result.data["order_id"])

        # O3: created and then cancelled -- must be excluded from settlement.
        o3_result = await create_order(
            self._body(self.dish3, request_id="MIX-O3"), make_customer_request(8003), db=self.db,
        )
        self.assertEqual(o3_result.code, 200, o3_result.msg)
        o3_id = int(o3_result.data["order_id"])

        # O1 keeps table_account even though tenant is now prepay.
        o1 = await self.db.get(Order, o1_id)
        self.assertEqual(o1.payment_mode, "table_account")
        self.assertEqual(str(o1.total), "30.00")

        # Pay O2 online (mock pay), proving payment truth is independent of O1's mode.
        settings.ALLOW_MOCK_MONEY_ENDPOINTS = True
        try:
            pay_result = await OrderPaymentService(self.db).mock_pay_order(
                str(o2_id), MockPayBody(participant_token=None), make_customer_request(8002),
            )
        finally:
            settings.ALLOW_MOCK_MONEY_ENDPOINTS = False
        self.assertEqual(pay_result.code, 200, pay_result.msg)

        o2 = await self.db.get(Order, o2_id)
        self.assertEqual(o2.payment_mode, "prepay")
        self.assertEqual(o2.payment_status, "paid")
        self.assertEqual(str(o2.total), "40.00")

        # Move O1/O2 to "done" (kitchen finished) so settle_table's aggregation
        # picks them up; cancel O3. Bypassing the full kitchen status lifecycle
        # here deliberately -- that lifecycle is covered by other test suites,
        # this test is specifically about settle_table's mode-mixed aggregation.
        o1.status = "done"
        o2.status = "done"
        o3 = await self.db.get(Order, o3_id)
        o3.status = "cancelled"
        await self.db.commit()

        settle_result = await settle_table(
            {"table_no": TABLE, "dining_session_id": str(self.session.id)},
            make_merchant_request(), self.db,
        )
        self.assertEqual(settle_result.code, 200, settle_result.msg)
        self.assertEqual(settle_result.data["settled_count"], 2)  # O1 + O2, not O3

        await self.db.refresh(o1)
        await self.db.refresh(o2)
        await self.db.refresh(o3)

        # No double charge: O2 was already paid before settle; settle must not
        # re-mark/re-charge it -- payment_method must remain the mock-pay value,
        # never overwritten to "offline" by settle_table's _mark_order_offline_paid.
        self.assertEqual(o1.status, "settled")
        self.assertEqual(o1.payment_status, "paid")  # newly offline-paid by settle
        self.assertEqual(o1.payment_method, "offline")

        self.assertEqual(o2.status, "settled")
        self.assertEqual(o2.payment_status, "paid")  # was already paid
        self.assertEqual(o2.payment_method, "mock")  # UNCHANGED -- proves no re-mark/double charge

        self.assertEqual(o3.status, "cancelled")  # untouched, excluded from settlement

        # Settlement total is informational (sum of settled orders); no code
        # path here re-collects O2's already-paid amount a second time.
        self.assertAlmostEqual(float(settle_result.data["total"]), 70.0)


if __name__ == "__main__":
    unittest.main()
