import asyncio
import unittest
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.commission_record import CommissionRecord
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.models.staff import Staff
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.services.commission_service import CommissionService
from app.utils.id_generator import generate_snowflake_id
from app.config import settings

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-commission-dup"

# NOTE: like test_coupon_redis_fallback_idempotency.py, this cannot exercise real
# concurrent-transaction locking against SQLite (readers here don't block on another
# connection's uncommitted write the way MySQL's row locks do). What this test proves
# is the same thing that test proves for CouponService: the check-then-act sequence is
# correct and durable once you actually run it twice, and the new locking statement
# (mirroring CouponService._dedup_issue_lock -- UPDATE the Customer row, which DOES
# take a real row lock on MySQL) doesn't change behavior for the legitimate path.


class CommissionDoublePayoutRegressionTest(unittest.IsolatedAsyncioTestCase):
    """顾客手上有两张已核销的新客券时（正常情况：入会欢迎券 + 到店奖励券都可能未用），
    record_after_verify 对同一个 customer 的"首次核销"奖励只应该发一次，不能因为两笔
    核销前后脚发生就各发一份。"""

    async def asyncSetUp(self):
        self._original_redis_enabled = settings.REDIS_ENABLED
        settings.REDIS_ENABLED = False

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
        self.db.add(TenantConfig(
            tenant_id=TENANT_A,
            member_rules={}, coupon_rules={}, business_info={},
            plugin_settings={
                "distribution": {"invite_reward_enabled": True},
                "staff_referral": {"enabled": True},
            },
        ))
        await self.db.flush()
        await self.db.commit()

        self.service = CommissionService(self.db)
        self.service.set_tenant_id(TENANT_A)

    async def asyncTearDown(self):
        settings.REDIS_ENABLED = self._original_redis_enabled
        await self.db.close()
        await self.engine.dispose()

    async def _make_verified_coupon_for(self, customer: Customer, suffix: str) -> tuple[Coupon, CouponTemplate]:
        now = datetime.utcnow()
        template = CouponTemplate(
            id=generate_snowflake_id(), tenant_id=TENANT_A, name="新客券", type="FIXED",
            value=10, min_amount=20, total_stock=100, used_stock=0,
            start_time=now - timedelta(days=1), end_time=now + timedelta(days=30), status=1,
        )
        self.db.add(template)
        await self.db.flush()
        coupon = Coupon(
            id=generate_snowflake_id(), tenant_id=TENANT_A, template_id=template.id,
            customer_id=customer.id, code=f"C{customer.id}-{suffix}", status="USED",
            use_time=now, expire_time=now + timedelta(days=30),
        )
        self.db.add(coupon)
        await self.db.commit()
        await self.db.refresh(coupon)
        return coupon, template

    async def test_two_verified_coupons_for_same_customer_only_pay_commission_once(self):
        staff = Staff(id=generate_snowflake_id(), tenant_id=TENANT_A, name="小王", invite_code="STAFF01", status=1)
        self.db.add(staff)
        invitee = Customer(
            id=generate_snowflake_id(), tenant_id=TENANT_A, openid="o-invitee-dup",
            inviter_id=staff.id, inviter_type="staff",
        )
        self.db.add(invitee)
        await self.db.commit()

        coupon_1, template_1 = await self._make_verified_coupon_for(invitee, "a")
        coupon_2, template_2 = await self._make_verified_coupon_for(invitee, "b")

        first = await self.service.record_after_verify(coupon_1, template_1)
        self.assertEqual(len(first), 2)  # staff + invitee welcome reward

        second = await self.service.record_after_verify(coupon_2, template_2)
        self.assertEqual(second, [])  # already paid out -- must not create a second round

        records_result = await self.db.execute(
            select(CommissionRecord).filter(
                CommissionRecord.tenant_id == TENANT_A,
                CommissionRecord.user_id == invitee.id,
                CommissionRecord.source_type == "FIRST_VERIFY",
            )
        )
        records = records_result.scalars().all()
        self.assertEqual(len(records), 2)  # exactly one staff record + one invitee record, not four


if __name__ == "__main__":
    unittest.main()
