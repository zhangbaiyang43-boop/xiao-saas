import asyncio
import unittest
from datetime import datetime, timedelta

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.services.statistics_service import StatisticsService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    # Same SQLite-only workaround used elsewhere in this suite: OrderItem.id relies
    # on native BIGINT AUTO_INCREMENT (correct on production MySQL); SQLite only
    # aliases autoincrement to rowid for a column declared literally as INTEGER.
    if target.id is None:
        target.id = generate_snowflake_id()


class OrderOverviewStatsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(tenant_id=TENANT_A, name="Test Restaurant", password_hash="x", status=True, is_open=True)
        self.other_tenant = Tenant(tenant_id=TENANT_B, name="Other Restaurant", password_hash="x", status=True, is_open=True)
        self.db.add_all([self.tenant, self.other_tenant])
        await self.db.commit()

        self.svc = StatisticsService(self.db)
        self.svc.set_tenant_id(TENANT_A)

        # "今天" in UTC+8 local time, expressed as the UTC instant used by the
        # service's own day-boundary math, so orders land inside "today" regardless
        # of what wall-clock time this test happens to run at.
        utc8_now = datetime.utcnow() + timedelta(hours=8)
        today_local = utc8_now.date()
        self.today_start_utc = datetime(today_local.year, today_local.month, today_local.day) - timedelta(hours=8)
        self.yesterday_start_utc = self.today_start_utc - timedelta(days=1)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_order(self, tenant_id, created_at, total, status="done", payment_status="paid", items=None):
        order = Order(
            tenant_id=tenant_id, total=str(total), status=status, payment_status=payment_status,
            payment_mode="prepay", table_no="A1",
        )
        self.db.add(order)
        await self.db.flush()
        order.created_at = created_at
        for name, qty in (items or []):
            self.db.add(OrderItem(order_id=order.id, name=name, price="10.00", qty=qty))
        await self.db.commit()
        return order

    async def test_revenue_only_counts_paid_orders(self):
        await self._make_order(TENANT_A, self.today_start_utc + timedelta(hours=2), 100, payment_status="paid")
        await self._make_order(TENANT_A, self.today_start_utc + timedelta(hours=3), 999, payment_status="unpaid")

        data = await self.svc.order_overview()
        self.assertEqual(data["today_revenue"], 100.0)

    async def test_cancelled_and_rejected_orders_excluded_from_order_count(self):
        await self._make_order(TENANT_A, self.today_start_utc + timedelta(hours=2), 50, status="done", payment_status="paid")
        await self._make_order(TENANT_A, self.today_start_utc + timedelta(hours=2), 999, status="cancelled", payment_status="paid")
        await self._make_order(TENANT_A, self.today_start_utc + timedelta(hours=2), 999, status="rejected", payment_status="unpaid")

        data = await self.svc.order_overview()
        self.assertEqual(data["today_order_count"], 1)

    async def test_settled_orders_are_counted_not_dropped(self):
        # This is exactly the bug being fixed: the old frontend logic excluded
        # 'settled' orders from revenue, silently losing money that was actually
        # collected once a table got checked out.
        await self._make_order(TENANT_A, self.today_start_utc + timedelta(hours=2), 88, status="settled", payment_status="paid")

        data = await self.svc.order_overview()
        self.assertEqual(data["today_revenue"], 88.0)
        self.assertEqual(data["today_order_count"], 1)

    async def test_cross_tenant_isolation(self):
        await self._make_order(TENANT_A, self.today_start_utc + timedelta(hours=2), 100, payment_status="paid")
        await self._make_order(TENANT_B, self.today_start_utc + timedelta(hours=2), 5000, payment_status="paid")

        data = await self.svc.order_overview()
        self.assertEqual(data["today_revenue"], 100.0)

    async def test_yesterday_comparison_and_percent_change(self):
        await self._make_order(TENANT_A, self.yesterday_start_utc + timedelta(hours=2), 100, payment_status="paid")
        await self._make_order(TENANT_A, self.today_start_utc + timedelta(hours=2), 150, payment_status="paid")

        data = await self.svc.order_overview()
        self.assertEqual(data["yesterday_revenue"], 100.0)
        self.assertEqual(data["today_revenue"], 150.0)
        self.assertEqual(data["revenue_change_pct"], 50.0)

    async def test_percent_change_is_none_when_yesterday_had_no_revenue(self):
        await self._make_order(TENANT_A, self.today_start_utc + timedelta(hours=2), 150, payment_status="paid")

        data = await self.svc.order_overview()
        self.assertIsNone(data["revenue_change_pct"])

    async def test_average_order_value(self):
        await self._make_order(TENANT_A, self.today_start_utc + timedelta(hours=1), 100, payment_status="paid")
        await self._make_order(TENANT_A, self.today_start_utc + timedelta(hours=2), 200, payment_status="paid")

        data = await self.svc.order_overview()
        self.assertEqual(data["today_aov"], 150.0)

    async def test_trend_7d_has_exactly_seven_days_ending_today(self):
        data = await self.svc.order_overview()
        self.assertEqual(len(data["trend_7d"]), 7)
        today_local = (datetime.utcnow() + timedelta(hours=8)).date()
        self.assertEqual(data["trend_7d"][-1]["date"], today_local.isoformat())

    async def test_top_dishes_7d_ranked_by_quantity(self):
        await self._make_order(
            TENANT_A, self.today_start_utc + timedelta(hours=2), 100, payment_status="paid",
            items=[("宫保鸡丁", 3), ("米饭", 5)],
        )
        await self._make_order(
            TENANT_A, self.today_start_utc + timedelta(hours=3), 50, payment_status="paid",
            items=[("宫保鸡丁", 2)],
        )

        data = await self.svc.order_overview()
        top = data["top_dishes_7d"]
        self.assertEqual(top[0], {"name": "米饭", "qty": 5})
        self.assertEqual(top[1], {"name": "宫保鸡丁", "qty": 5})

    async def test_unpaid_order_items_do_not_count_toward_top_dishes(self):
        await self._make_order(
            TENANT_A, self.today_start_utc + timedelta(hours=2), 100, payment_status="unpaid",
            items=[("秘制烤鱼", 10)],
        )

        data = await self.svc.order_overview()
        self.assertEqual(data["top_dishes_7d"], [])


if __name__ == "__main__":
    unittest.main()
