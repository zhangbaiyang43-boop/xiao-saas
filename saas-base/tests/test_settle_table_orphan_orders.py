"""Bug fix: orders with no dining_session_id (e.g. the demo/test data the
super-admin "填充测试数据" tool seeds -- see test_data_seed.py, which never
attaches a session) are still grouped and shown as checkout-ready by admin-h5's
table view, but settle_table()'s lookup only ever finds sessions via a JOIN on
DiningSession -- so these orders could never be settled, no matter how many
times the merchant retried, refreshed, or opened the page in a private window.
The 404 "本桌没有进行中的会话" was not a cache/staleness problem; it was a real
gap: there was no settlement path at all for a table's worth of orphan orders."""

import asyncio
import unittest
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.api.v1.orders import settle_table
from app.models.base import Base
from app.models.dining import DiningSession
from app.models.order import Order, OrderItem
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT = "tenant-orphan-settle"


class FakeRequest:
    def __init__(self, **state):
        self.state = SimpleNamespace(**state)


def make_merchant_request(tenant_id=TENANT):
    # get_request_principal() requires role=="owner" for an account_id-less
    # merchant request -- matches what real AuthMiddleware sets for an owner
    # JWT (app/middleware/auth_middleware.py:127-142).
    return FakeRequest(tenant_id=tenant_id, token_type="merchant", role="owner", account_id=None)


class SettleTableOrphanOrdersTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_orphan_order(self, table_no="A05", status="done", total="25.00"):
        # Mirrors exactly what test_data_seed.py produces: dining_session_id is
        # never set at all.
        order = Order(
            tenant_id=TENANT,
            dining_session_id=None,
            table_no=table_no,
            total=total,
            status=status,
            payment_status="paid",
            payment_method="mock",
            source="h5",
        )
        self.db.add(order)
        await self.db.flush()
        self.db.add(OrderItem(id=generate_snowflake_id(), order_id=order.id, name="牛肉汤", price=total, qty=1))
        await self.db.commit()
        return order

    async def test_orphan_orders_can_be_settled_without_a_dining_session(self):
        o1 = await self._make_orphan_order()
        o2 = await self._make_orphan_order()

        res = await settle_table({"table_no": "A05"}, make_merchant_request(), self.db)

        self.assertEqual(res.code, 200, res.msg)
        self.assertEqual(res.data["settled_count"], 2)
        self.assertIsNone(res.data["dining_session_id"])

        for order_id in (o1.id, o2.id):
            reloaded = await self.db.get(Order, order_id)
            self.assertEqual(reloaded.status, "settled")

    async def test_orphan_settle_does_not_touch_unrelated_tables(self):
        await self._make_orphan_order(table_no="A05")
        other = await self._make_orphan_order(table_no="A06")

        res = await settle_table({"table_no": "A05"}, make_merchant_request(), self.db)

        self.assertEqual(res.code, 200, res.msg)
        reloaded_other = await self.db.get(Order, other.id)
        self.assertEqual(reloaded_other.status, "done")

    async def test_orphan_settle_still_blocks_on_unfinished_orders(self):
        await self._make_orphan_order(status="preparing")

        res = await settle_table({"table_no": "A05"}, make_merchant_request(), self.db)

        self.assertEqual(res.code, 409)
        self.assertIn("本桌还有未完成的订单", res.msg)

    async def test_retrying_a_permanently_stuck_table_now_succeeds_instead_of_404_forever(self):
        # This is the exact reported symptom: refresh, retry, private-window --
        # none of it used to help, because the 404 wasn't about staleness.
        await self._make_orphan_order()

        first = await settle_table({"table_no": "A05"}, make_merchant_request(), self.db)
        self.assertEqual(first.code, 200, first.msg)

        # A second settle attempt on the now-fully-settled table correctly
        # reports "no session" again -- there's nothing left to close, not a bug.
        second = await settle_table({"table_no": "A05"}, make_merchant_request(), self.db)
        self.assertEqual(second.code, 404)

    async def test_session_based_table_is_unaffected_by_the_orphan_fallback(self):
        from datetime import datetime

        now = datetime.utcnow()
        session = DiningSession(
            tenant_id=TENANT, table_no="B01", status="OPEN", active_key=f"{TENANT}:B01",
            started_at=now, last_activity_at=now,
        )
        self.db.add(session)
        await self.db.flush()
        order = Order(
            tenant_id=TENANT, dining_session_id=session.id, table_no="B01",
            total="30.00", status="done", payment_status="paid", payment_mode="table_account",
        )
        self.db.add(order)
        await self.db.commit()

        res = await settle_table({"table_no": "B01"}, make_merchant_request(), self.db)

        self.assertEqual(res.code, 200, res.msg)
        self.assertEqual(res.data["dining_session_id"], str(session.id))
        session_result = await self.db.execute(select(DiningSession).where(DiningSession.id == session.id))
        self.assertEqual(session_result.scalar_one().status, "CLOSED")


if __name__ == "__main__":
    unittest.main()
