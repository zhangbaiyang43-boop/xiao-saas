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

TENANT_A = "tenant-staff-referral"


class StaffReferralCommissionTest(unittest.IsolatedAsyncioTestCase):
    """羊肉馆场景：员工/亲友把新顾客带到店，顾客首次消费核销后，员工记一笔
    待发放现金佣金（不是券），顾客自己的欢迎券照常发放；顾客推荐顾客的老路径不受影响。"""

    async def asyncSetUp(self):
        self._original_redis_enabled = settings.REDIS_ENABLED
        settings.REDIS_ENABLED = False

        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(
            tenant_id=TENANT_A, name="Test Lamb Shop", password_hash="x",
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

    async def _make_verified_coupon_for(self, customer: Customer) -> tuple[Coupon, CouponTemplate]:
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
            customer_id=customer.id, code=f"C{customer.id}", status="USED",
            use_time=now, expire_time=now + timedelta(days=30),
        )
        self.db.add(coupon)
        await self.db.commit()
        await self.db.refresh(coupon)
        return coupon, template

    async def test_staff_referred_customer_gets_own_welcome_coupon_and_staff_gets_pending_cash(self):
        staff = Staff(id=generate_snowflake_id(), tenant_id=TENANT_A, name="小王", invite_code="STAFF01", status=1)
        self.db.add(staff)
        invitee = Customer(
            id=generate_snowflake_id(), tenant_id=TENANT_A, openid="o-invitee-1",
            inviter_id=staff.id, inviter_type="staff",
        )
        self.db.add(invitee)
        await self.db.commit()

        coupon, template = await self._make_verified_coupon_for(invitee)
        created = await self.service.record_after_verify(coupon, template)
        self.assertEqual(len(created), 2)

        records_result = await self.db.execute(
            select(CommissionRecord).filter(CommissionRecord.tenant_id == TENANT_A)
        )
        records = {r.level: r for r in records_result.scalars().all()}

        staff_record = records[1]
        self.assertEqual(staff_record.receiver_type, "staff")
        self.assertEqual(staff_record.receiver_id, staff.id)
        self.assertGreater(float(staff_record.commission_amount), 0)
        # 员工那条只记账不发券，必须一直留 PENDING，不能被误标成 SETTLED。
        self.assertEqual(staff_record.status, "PENDING")

        invitee_record = records[2]
        self.assertEqual(invitee_record.receiver_type, "customer")
        self.assertEqual(invitee_record.receiver_id, invitee.id)
        # 顾客自己的欢迎券走真实发券流程，应该已经结算成功。
        self.assertEqual(invitee_record.status, "SETTLED")

        invitee_coupons = await self.db.execute(
            select(Coupon).filter(Coupon.tenant_id == TENANT_A, Coupon.customer_id == invitee.id)
        )
        # 一张是被核销的原始新客券，一张是新发的到店奖励券
        self.assertEqual(len(list(invitee_coupons.scalars().all())), 2)

    async def test_customer_to_customer_referral_path_unaffected(self):
        inviter = Customer(id=generate_snowflake_id(), tenant_id=TENANT_A, openid="o-inviter-1", short_invite_code="ABC123")
        self.db.add(inviter)
        await self.db.flush()
        invitee = Customer(
            id=generate_snowflake_id(), tenant_id=TENANT_A, openid="o-invitee-2",
            inviter_id=inviter.id, inviter_type="customer",
        )
        self.db.add(invitee)
        await self.db.commit()

        coupon, template = await self._make_verified_coupon_for(invitee)
        created = await self.service.record_after_verify(coupon, template)
        self.assertEqual(len(created), 2)

        records_result = await self.db.execute(
            select(CommissionRecord).filter(CommissionRecord.tenant_id == TENANT_A)
        )
        records = {r.level: r for r in records_result.scalars().all()}
        # 顾客推荐顾客：两条都发券成功，跟改动前行为一致。
        self.assertEqual(records[1].receiver_type, "customer")
        self.assertEqual(records[1].status, "SETTLED")
        self.assertEqual(records[2].status, "SETTLED")

    async def test_bind_inviter_resolves_staff_code(self):
        staff = Staff(id=generate_snowflake_id(), tenant_id=TENANT_A, name="小李", invite_code="STAFF02", status=1)
        self.db.add(staff)
        new_customer = Customer(id=generate_snowflake_id(), tenant_id=TENANT_A, openid="o-new-1")
        self.db.add(new_customer)
        await self.db.commit()

        updated = await self.service.bind_inviter_for_new_customer(new_customer, "staff02")
        self.assertEqual(updated.inviter_id, staff.id)
        self.assertEqual(updated.inviter_type, "staff")

    async def test_bind_inviter_customer_code_still_takes_priority(self):
        # 老路径回归：顾客短码解析行为必须完全不变。
        inviter = Customer(id=generate_snowflake_id(), tenant_id=TENANT_A, openid="o-inviter-3", short_invite_code="XYZ789")
        self.db.add(inviter)
        new_customer = Customer(id=generate_snowflake_id(), tenant_id=TENANT_A, openid="o-new-2")
        self.db.add(new_customer)
        await self.db.commit()

        updated = await self.service.bind_inviter_for_new_customer(new_customer, "xyz789")
        self.assertEqual(updated.inviter_id, inviter.id)
        self.assertEqual(updated.inviter_type, "customer")

    async def test_staff_referral_disabled_still_gives_invitee_coupon_but_no_staff_record(self):
        # 商户只关了"员工推荐"，没关顾客老带新：员工不该拿到任何佣金记录，
        # 但被推荐顾客自己的欢迎券不受影响，两个开关互不捆绑。
        config_result = await self.db.execute(
            select(TenantConfig).filter(TenantConfig.tenant_id == TENANT_A)
        )
        config = config_result.scalar_one()
        config.plugin_settings = {**config.plugin_settings, "staff_referral": {"enabled": False}}
        await self.db.commit()

        staff = Staff(id=generate_snowflake_id(), tenant_id=TENANT_A, name="小周", invite_code="STAFF03", status=1)
        self.db.add(staff)
        invitee = Customer(
            id=generate_snowflake_id(), tenant_id=TENANT_A, openid="o-invitee-3",
            inviter_id=staff.id, inviter_type="staff",
        )
        self.db.add(invitee)
        await self.db.commit()

        coupon, template = await self._make_verified_coupon_for(invitee)
        created = await self.service.record_after_verify(coupon, template)
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].receiver_type, "customer")
        self.assertEqual(created[0].status, "SETTLED")


if __name__ == "__main__":
    unittest.main()
