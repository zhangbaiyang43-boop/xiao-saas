import asyncio
import unittest
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.consumption import Consumption
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.models.customer_identity import CustomerIdentity
from app.models.member_account import MemberAccount
from app.models.point_ledger import PointLedger
from app.models.tenant import Tenant
from app.services.customer_service import CustomerService
from app.services.membership_service import MembershipService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


class CustomerMergeAssetsTest(unittest.IsolatedAsyncioTestCase):
    """merge_customers used to only reassign the login identity (CustomerIdentity),
    silently leaving points, stored balance, consumption totals, coupons, consumption
    history, and point ledger entries all behind on the now-disabled source customer --
    a merge that looked successful actually erased the customer's assets."""

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(tenant_id=TENANT_A, name="Test Restaurant", password_hash="x", status=True, is_open=True)
        self.db.add(self.tenant)
        await self.db.flush()

        now = datetime.utcnow()
        self.source = Customer(id=generate_snowflake_id(), tenant_id=TENANT_A, openid="source-openid", phone="13800000001", created_at=now)
        self.target = Customer(id=generate_snowflake_id(), tenant_id=TENANT_A, openid="target-openid", phone="13800000002", created_at=now)
        self.db.add_all([self.source, self.target])
        await self.db.flush()

        self.db.add(CustomerIdentity(
            tenant_id=TENANT_A, customer_id=self.source.id, channel="MINIAPP",
            channel_user_id="source-openid", bind_time=now,
        ))

        self.source_account = MemberAccount(
            tenant_id=TENANT_A, customer_id=self.source.id, member_id="13800000001",
            level_code="LV2", level_name="银卡会员", total_consumption=300, yearly_consumption=300,
            points_balance=150, balance=20,
        )
        self.db.add(self.source_account)

        template = CouponTemplate(
            id=generate_snowflake_id(), tenant_id=TENANT_A, name="老客券", type="FIXED",
            value=10, min_amount=20, total_stock=100, used_stock=0,
            start_time=now - timedelta(days=1), end_time=now + timedelta(days=30), status=1,
        )
        self.db.add(template)
        await self.db.flush()

        self.db.add(Coupon(
            id=generate_snowflake_id(), tenant_id=TENANT_A, template_id=template.id,
            customer_id=self.source.id, code="MERGE-TEST-1", status="UNUSED",
            expire_time=now + timedelta(days=30),
        ))
        self.db.add(Consumption(
            tenant_id=TENANT_A, customer_id=self.source.id, project="老客消费",
            amount=88.0, consume_time=now,
        ))
        self.db.add(PointLedger(
            tenant_id=TENANT_A, customer_id=self.source.id, member_id="13800000001",
            event_type="consumption", points=30, balance_after=150, ref_id="old-order-1",
        ))
        await self.db.commit()

        self.service = CustomerService(self.db)
        self.service.set_tenant_id(TENANT_A)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_merge_migrates_member_account_totals_into_target(self):
        # Pre-create target's account with a known-zero baseline so ensure_account() inside
        # merge_customers doesn't implicitly grant it a fresh register bonus that would
        # couple this assertion to POINT_RULES' exact value.
        membership_service = MembershipService(self.db)
        membership_service.set_tenant_id(TENANT_A)
        target_account = await membership_service.ensure_account(self.target)
        target_account.points_balance = 0
        await self.db.commit()

        result = await self.service.merge_customers(self.source.id, self.target.id)

        self.assertIsNotNone(result)
        target_account = await membership_service.get_account_by_customer(self.target.id)

        self.assertEqual(int(target_account.points_balance), 150)
        self.assertEqual(float(target_account.balance), 20.0)
        self.assertEqual(float(target_account.total_consumption), 300.0)
        self.assertEqual(float(target_account.yearly_consumption), 300.0)
        self.assertEqual(target_account.level_code, "LV2")  # recomputed from merged consumption

    async def test_merge_deletes_the_now_orphaned_source_account_row(self):
        await self.service.merge_customers(self.source.id, self.target.id)

        result = await self.db.execute(
            select(MemberAccount).filter(MemberAccount.tenant_id == TENANT_A, MemberAccount.customer_id == self.source.id)
        )
        self.assertIsNone(result.scalar_one_or_none())

    async def test_merge_adds_to_targets_existing_balance_not_overwrites_it(self):
        # Target already has its own account with its own assets before the merge.
        membership_service = MembershipService(self.db)
        membership_service.set_tenant_id(TENANT_A)
        target_account = await membership_service.ensure_account(self.target)
        target_account.points_balance = 40
        target_account.total_consumption = 100
        target_account.yearly_consumption = 100
        await self.db.commit()

        await self.service.merge_customers(self.source.id, self.target.id)

        merged = await membership_service.get_account_by_customer(self.target.id)
        self.assertEqual(int(merged.points_balance), 190)  # 40 + 150
        self.assertEqual(float(merged.total_consumption), 400.0)  # 100 + 300

    async def test_merge_reassigns_coupon_to_target(self):
        await self.service.merge_customers(self.source.id, self.target.id)

        result = await self.db.execute(select(Coupon).filter(Coupon.tenant_id == TENANT_A, Coupon.code == "MERGE-TEST-1"))
        coupon = result.scalar_one_or_none()
        self.assertEqual(coupon.customer_id, self.target.id)

    async def test_merge_reassigns_consumption_history_to_target(self):
        await self.service.merge_customers(self.source.id, self.target.id)

        result = await self.db.execute(
            select(Consumption).filter(Consumption.tenant_id == TENANT_A, Consumption.project == "老客消费")
        )
        consumption = result.scalar_one_or_none()
        self.assertEqual(consumption.customer_id, self.target.id)

    async def test_merge_reassigns_point_ledger_history_to_target(self):
        await self.service.merge_customers(self.source.id, self.target.id)

        result = await self.db.execute(
            select(PointLedger).filter(PointLedger.tenant_id == TENANT_A, PointLedger.ref_id == "old-order-1")
        )
        ledger = result.scalar_one_or_none()
        self.assertEqual(ledger.customer_id, self.target.id)

    async def test_merge_still_disables_source_and_reassigns_identity(self):
        await self.service.merge_customers(self.source.id, self.target.id)

        await self.db.refresh(self.source)
        self.assertEqual(self.source.status, -1)

        result = await self.db.execute(
            select(CustomerIdentity).filter(CustomerIdentity.channel_user_id == "source-openid")
        )
        identity = result.scalar_one_or_none()
        self.assertEqual(identity.customer_id, self.target.id)

    async def test_merge_when_source_has_no_member_account_does_not_crash(self):
        # Cover the case where source never got a MemberAccount at all.
        no_account_source = Customer(
            id=generate_snowflake_id(), tenant_id=TENANT_A, openid="bare-source-openid",
            phone="13800000003", created_at=datetime.utcnow(),
        )
        self.db.add(no_account_source)
        await self.db.commit()

        result = await self.service.merge_customers(no_account_source.id, self.target.id)

        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
