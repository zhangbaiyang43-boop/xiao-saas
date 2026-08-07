import asyncio
import unittest
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.commission_record import CommissionRecord
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.models.order import Order
from app.models.point_ledger import PointLedger
from app.models.tenant import Tenant
from app.services.statistics_service import StatisticsService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


class StatisticsServiceDashboardTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(tenant_id=TENANT_A, name="Test Restaurant", password_hash="x", status=True, is_open=True)
        self.db.add(self.tenant)
        await self.db.commit()

        self.svc = StatisticsService(self.db)
        self.svc.set_tenant_id(TENANT_A)
        self.now = datetime.utcnow()
        self.month_start = self.now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_customer(self, suffix: str) -> Customer:
        customer = Customer(tenant_id=TENANT_A, openid=f"openid-{suffix}", status=1)
        self.db.add(customer)
        await self.db.flush()
        return customer

    async def _make_paid_order(self, customer_id: int, created_at: datetime, total: str = "30.00") -> Order:
        order = Order(
            tenant_id=TENANT_A,
            customer_id=customer_id,
            table_no="A1",
            total=total,
            status="done",
            payment_status="paid",
            payment_mode="prepay",
        )
        self.db.add(order)
        await self.db.flush()
        order.created_at = created_at
        await self.db.commit()
        return order

    async def test_repeat_customers_7d_counts_returning_not_first_time_buyers(self):
        repeat_customer = await self._make_customer("repeat")
        new_customer = await self._make_customer("new")

        await self._make_paid_order(repeat_customer.id, self.now - timedelta(days=10))
        await self._make_paid_order(repeat_customer.id, self.now - timedelta(days=2))
        await self._make_paid_order(new_customer.id, self.now - timedelta(days=2))

        data = await self.svc.dashboard()
        self.assertEqual(data["repeat_customers_7d"], 1)

    async def test_repeat_customers_7d_ignores_customers_without_recent_paid_orders(self):
        old_only_customer = await self._make_customer("old-only")
        await self._make_paid_order(old_only_customer.id, self.now - timedelta(days=20))

        data = await self.svc.dashboard()
        self.assertEqual(data["repeat_customers_7d"], 0)

    async def test_points_issued_month_sums_positive_ledger_entries(self):
        customer = await self._make_customer("points")
        self.db.add(PointLedger(
            tenant_id=TENANT_A,
            customer_id=customer.id,
            member_id="m-1",
            event_type="consumption",
            points=120,
            balance_after=120,
            source_channel="STORE",
        ))
        self.db.add(PointLedger(
            tenant_id=TENANT_A,
            customer_id=customer.id,
            member_id="m-1",
            event_type="adjustment",
            points=-20,
            balance_after=100,
            source_channel="STORE",
        ))
        await self.db.commit()

        data = await self.svc.dashboard()
        self.assertEqual(data["points_issued_month"], 120)

    async def test_points_redeemed_coupons_month_counts_points_reward_coupon_templates(self):
        customer = await self._make_customer("redeem")
        template = CouponTemplate(
            id=generate_snowflake_id(),
            tenant_id=TENANT_A,
            name="积分兑换券",
            type="FIXED",
            value=10,
            min_amount=0,
            start_time=self.now,
            end_time=self.now + timedelta(days=30),
            description="points_reward_coupon",
        )
        other_template = CouponTemplate(
            id=generate_snowflake_id(),
            tenant_id=TENANT_A,
            name="普通券",
            type="FIXED",
            value=5,
            min_amount=0,
            start_time=self.now,
            end_time=self.now + timedelta(days=30),
            description="consumption_coupon",
        )
        self.db.add_all([template, other_template])
        await self.db.flush()

        current_coupon = Coupon(
            id=generate_snowflake_id(),
            tenant_id=TENANT_A,
            template_id=template.id,
            customer_id=customer.id,
            code="points-reward-current",
            expire_time=self.now + timedelta(days=7),
        )
        old_coupon = Coupon(
            id=generate_snowflake_id(),
            tenant_id=TENANT_A,
            template_id=template.id,
            customer_id=customer.id,
            code="points-reward-old",
            expire_time=self.now + timedelta(days=7),
        )
        other_coupon = Coupon(
            id=generate_snowflake_id(),
            tenant_id=TENANT_A,
            template_id=other_template.id,
            customer_id=customer.id,
            code="other-coupon",
            expire_time=self.now + timedelta(days=7),
        )
        self.db.add_all([current_coupon, old_coupon, other_coupon])
        await self.db.flush()
        old_coupon.created_at = self.month_start - timedelta(days=1)
        await self.db.commit()

        data = await self.svc.dashboard()
        self.assertEqual(data["points_redeemed_coupons_month"], 1)


class MarketingEffectivenessTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(tenant_id=TENANT_A, name="Test Restaurant", password_hash="x", status=True, is_open=True)
        self.db.add(self.tenant)
        await self.db.commit()

        self.svc = StatisticsService(self.db)
        self.svc.set_tenant_id(TENANT_A)
        self.now = datetime.utcnow()
        self.start = self.now - timedelta(days=30)
        self.end = self.now

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_customer(self, suffix: str, **kwargs) -> Customer:
        customer = Customer(tenant_id=TENANT_A, openid=f"openid-{suffix}", status=1, **kwargs)
        self.db.add(customer)
        await self.db.flush()
        return customer

    async def test_entry_coupon_row_counts_issued_coupons_and_gmv(self):
        customer = await self._make_customer("entry")
        template = CouponTemplate(
            id=generate_snowflake_id(),
            tenant_id=TENANT_A,
            name="进店券",
            type="FIXED",
            value=5,
            min_amount=0,
            start_time=self.now,
            end_time=self.now + timedelta(days=7),
            description="entry_coupon",
        )
        self.db.add(template)
        await self.db.flush()

        coupon = Coupon(
            id=generate_snowflake_id(),
            tenant_id=TENANT_A,
            template_id=template.id,
            customer_id=customer.id,
            code="entry-coupon-1",
            status="USED",
            expire_time=self.now + timedelta(days=7),
        )
        self.db.add(coupon)
        await self.db.flush()
        coupon.created_at = self.now - timedelta(days=1)

        order = Order(
            tenant_id=TENANT_A,
            customer_id=customer.id,
            table_no="A1",
            total="88.00",
            status="done",
            payment_status="paid",
            payment_mode="prepay",
            coupon_id=coupon.id,
        )
        self.db.add(order)
        await self.db.commit()

        rows = await self.svc.marketing_effectiveness(self.start, self.now + timedelta(minutes=1))
        entry_row = next(item for item in rows if item["rule_type"] == "entry_coupon")
        self.assertEqual(entry_row["issued_count"], 1)
        self.assertEqual(entry_row["redemption_rate"], 1.0)
        self.assertEqual(entry_row["gmv"], 88.0)
        self.assertIsNone(entry_row["referral_headcount"])

    async def test_staff_referral_row_counts_commission_and_referrals(self):
        invitee = await self._make_customer("invitee", inviter_id=9001, inviter_type="staff")
        record = CommissionRecord(
            tenant_id=TENANT_A,
            user_id=invitee.id,
            order_id="order-1",
            amount="50.00",
            level=1,
            receiver_id=9001,
            receiver_type="staff",
            commission_amount="10.00",
            status="SETTLED",
            source_type="FIRST_VERIFY",
        )
        self.db.add(record)
        await self.db.flush()
        record.created_at = self.now - timedelta(days=1)
        invitee.created_at = self.now - timedelta(days=1)
        await self._make_paid_order(invitee.id, self.now - timedelta(days=2), total="120.00")
        await self.db.commit()

        rows = await self.svc.marketing_effectiveness(self.start, self.now + timedelta(minutes=1))
        staff_row = next(item for item in rows if item["rule_type"] == "staff_referral")
        self.assertEqual(staff_row["metric_kind"], "commission")
        self.assertEqual(staff_row["issued_count"], 1)
        self.assertEqual(staff_row["redemption_rate"], 1.0)
        self.assertEqual(staff_row["referral_headcount"], 1)
        self.assertEqual(staff_row["gmv"], 120.0)

    async def _make_paid_order(self, customer_id: int, created_at: datetime, total: str = "30.00") -> Order:
        order = Order(
            tenant_id=TENANT_A,
            customer_id=customer_id,
            table_no="A1",
            total=total,
            status="done",
            payment_status="paid",
            payment_mode="prepay",
        )
        self.db.add(order)
        await self.db.flush()
        order.created_at = created_at
        await self.db.commit()
        return order


if __name__ == "__main__":
    unittest.main()
