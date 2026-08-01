import asyncio
import unittest
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.tenant_context import TenantContext
from app.models.base import Base
from app.models.coupon_template import CouponTemplate
from app.models.entrance_code import EntranceCode
from app.services.entrance_code_service import EntranceCodeService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


class EntranceCodeCouponTemplateTenantIsolationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        start_time = datetime(2026, 1, 1)
        end_time = datetime(2026, 12, 31, 23, 59, 59)
        self.db.add_all(
            [
                CouponTemplate(
                    id=101,
                    tenant_id=TENANT_A,
                    name="A coupon",
                    type="FIXED",
                    value=5,
                    min_amount=20,
                    total_stock=100,
                    used_stock=0,
                    start_time=start_time,
                    end_time=end_time,
                    status=1,
                ),
                CouponTemplate(
                    id=202,
                    tenant_id=TENANT_B,
                    name="B coupon",
                    type="FIXED",
                    value=8,
                    min_amount=30,
                    total_stock=100,
                    used_stock=0,
                    start_time=start_time,
                    end_time=end_time,
                    status=1,
                ),
            ]
        )
        await self.db.commit()
        TenantContext.set_tenant_id(TENANT_A)

    async def asyncTearDown(self):
        TenantContext.clear()
        await self.db.close()
        await self.engine.dispose()

    def _service(self):
        service = EntranceCodeService(self.db)
        service.set_tenant_id(TENANT_A)

        async def fake_generate_code_image(*args, **kwargs):
            return {
                "image_url": "/static/entrance-codes/test.png",
                "code_type": "QR",
                "generation_status": "SUCCESS",
                "generation_error": None,
            }

        service._generate_code_image = fake_generate_code_image
        return service

    async def test_create_entrance_code_rejects_coupon_template_from_other_tenant(self):
        service = self._service()

        with self.assertRaisesRegex(ValueError, "优惠券模板不存在"):
            await service.create_entrance_code(
                name="bad entrance",
                channel="STORE",
                coupon_template_id=202,
            )

        result = await self.db.execute(select(EntranceCode))
        self.assertEqual(result.scalars().all(), [])

    async def test_create_entrance_code_allows_coupon_template_from_same_tenant(self):
        service = self._service()

        entrance_code = await service.create_entrance_code(
            name="good entrance",
            channel="STORE",
            coupon_template_id=101,
        )

        self.assertEqual(entrance_code.tenant_id, TENANT_A)
        self.assertEqual(entrance_code.coupon_template_id, 101)


if __name__ == "__main__":
    unittest.main()