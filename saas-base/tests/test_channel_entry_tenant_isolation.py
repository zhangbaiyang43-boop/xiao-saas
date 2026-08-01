import asyncio
import unittest
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.channel_entries import get_entry, list_entries
from app.core.tenant_context import TenantContext
from app.models.base import Base
from app.models.channel_entry import ChannelEntry
from app.models.coupon_template import CouponTemplate
from app.services.channel_entry_service import ChannelEntryService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


def make_request(tenant_id=TENANT_A):
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/channel-entries",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    request.state.tenant_id = tenant_id
    request.state.token_type = "merchant"
    return request


class ChannelEntryTenantIsolationTest(unittest.IsolatedAsyncioTestCase):
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
                    name="B secret coupon",
                    type="FIXED",
                    value=88,
                    min_amount=188,
                    total_stock=100,
                    used_stock=0,
                    start_time=start_time,
                    end_time=end_time,
                    status=1,
                    description="B private discount",
                ),
                ChannelEntry(
                    id=301,
                    tenant_id=TENANT_A,
                    name="dirty entry",
                    channel_code="custom",
                    coupon_template_id=202,
                    h5_url="https://example.test/h5/301",
                    status=1,
                    visit_count=0,
                    scan_count=0,
                ),
            ]
        )
        await self.db.commit()
        TenantContext.set_tenant_id(TENANT_A)

    async def asyncTearDown(self):
        TenantContext.clear()
        await self.db.close()
        await self.engine.dispose()

    async def test_create_entry_rejects_coupon_template_from_other_tenant(self):
        service = ChannelEntryService(self.db)
        service.set_tenant_id(TENANT_A)

        with self.assertRaises(ValueError):
            await service.create_entry(
                name="bad link",
                channel_code="custom",
                coupon_template_id=202,
            )

    async def test_update_entry_rejects_coupon_template_from_other_tenant(self):
        service = ChannelEntryService(self.db)
        service.set_tenant_id(TENANT_A)

        with self.assertRaises(ValueError):
            await service.update_entry(301, coupon_template_id=202)
    async def test_public_entry_does_not_expose_cross_tenant_coupon_template(self):
        data = await ChannelEntryService(self.db).get_entry_with_coupon(301)

        self.assertIsNotNone(data)
        self.assertEqual(data["tenant_id"], TENANT_A)
        self.assertIsNone(data["coupon"])

    async def test_admin_list_and_detail_do_not_expose_cross_tenant_coupon_name(self):
        request = make_request(TENANT_A)

        list_result = await list_entries(request=request, db=self.db)
        self.assertEqual(list_result.code, 200)
        self.assertIsNone(list_result.data["items"][0]["coupon_name"])

        detail_result = await get_entry(request=request, entry_id=301, db=self.db)
        self.assertEqual(detail_result.code, 200)
        self.assertIsNone(detail_result.data["coupon_name"])


if __name__ == "__main__":
    unittest.main()


