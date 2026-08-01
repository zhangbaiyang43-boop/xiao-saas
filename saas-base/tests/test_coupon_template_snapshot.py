import asyncio
import unittest
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.core.exceptions import BusinessException
from app.models.base import Base
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.models.tenant import Tenant
from app.services.coupon_service import CouponService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


class CouponTemplateSnapshotTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._original_redis_enabled = settings.REDIS_ENABLED
        settings.REDIS_ENABLED = False

        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(tenant_id=TENANT_A, name="Test Restaurant", password_hash="x", status=True, is_open=True)
        self.db.add(self.tenant)
        self.customer = Customer(tenant_id=TENANT_A, openid="openid-1")
        self.db.add(self.customer)
        await self.db.commit()

        self.svc = CouponService(self.db)
        self.svc.set_tenant_id(TENANT_A)
        now = datetime.utcnow()
        self.template = CouponTemplate(
            tenant_id=TENANT_A, name="满100减20", type="FIXED", value=20, min_amount=100,
            total_stock=100, used_stock=0, start_time=now - timedelta(days=1), end_time=now + timedelta(days=30),
            status=1,
        )
        self.db.add(self.template)
        await self.db.commit()

    async def asyncTearDown(self):
        settings.REDIS_ENABLED = self._original_redis_enabled
        await self.db.close()
        await self.engine.dispose()

    async def test_unused_template_core_fields_can_still_be_edited(self):
        updated = await self.svc.update_template(self.template.id, value=5, min_amount=200, type="FIXED")
        self.assertEqual(float(updated.value), 5)
        self.assertEqual(float(updated.min_amount), 200)

    async def test_once_issued_value_cannot_be_lowered(self):
        await self.svc.send_coupons_with_result(self.template.id, [self.customer.id])
        await self.db.refresh(self.template)
        self.assertEqual(self.template.used_stock, 1)

        with self.assertRaises(BusinessException):
            await self.svc.update_template(self.template.id, value=1)

        await self.db.refresh(self.template)
        self.assertEqual(float(self.template.value), 20)  # unchanged

    async def test_once_issued_min_amount_cannot_be_changed(self):
        await self.svc.send_coupons_with_result(self.template.id, [self.customer.id])

        with self.assertRaises(BusinessException):
            await self.svc.update_template(self.template.id, min_amount=200)

        await self.db.refresh(self.template)
        self.assertEqual(float(self.template.min_amount), 100)

    async def test_once_issued_type_cannot_be_changed(self):
        await self.svc.send_coupons_with_result(self.template.id, [self.customer.id])

        with self.assertRaises(BusinessException):
            await self.svc.update_template(self.template.id, type="PERCENT")

        await self.db.refresh(self.template)
        self.assertEqual(self.template.type, "FIXED")

    async def test_once_issued_non_core_fields_can_still_be_edited(self):
        await self.svc.send_coupons_with_result(self.template.id, [self.customer.id])

        updated = await self.svc.update_template(
            self.template.id, name="满100减20（限时）", total_stock=500,
        )
        self.assertEqual(updated.name, "满100减20（限时）")
        self.assertEqual(updated.total_stock, 500)

    async def test_once_issued_resubmitting_the_same_core_value_is_not_blocked(self):
        await self.svc.send_coupons_with_result(self.template.id, [self.customer.id])

        # 提交跟当前值完全一样的 value/min_amount/type，不应被误判为"修改"而拒绝
        updated = await self.svc.update_template(self.template.id, value=20, min_amount=100, type="FIXED")
        self.assertEqual(float(updated.value), 20)


if __name__ == "__main__":
    unittest.main()
