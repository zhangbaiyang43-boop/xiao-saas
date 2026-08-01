import asyncio
import unittest

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.entrance_code import EntranceCode
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.api.v1.entrance_codes import resolve_entrance_code
from app.services.commission_service import CommissionService
from app.config import settings

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-staff-share"


def make_request(path="/api/v1/entrance-codes/resolve"):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


class StaffShareCodeTest(unittest.IsolatedAsyncioTestCase):
    """员工一键转发小程序卡片：新建员工时自动配一张 entry_type='staff_share'
    的分享码，扫码解析要能带出这位员工的推荐码/姓名，供小程序分享页展示。"""

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
        self.db.add(TenantConfig(tenant_id=TENANT_A, member_rules={}, coupon_rules={}, business_info={}, plugin_settings={}))
        await self.db.commit()

        self.service = CommissionService(self.db)
        self.service.set_tenant_id(TENANT_A)

    async def asyncTearDown(self):
        settings.REDIS_ENABLED = self._original_redis_enabled
        await self.db.close()
        await self.engine.dispose()

    async def test_create_staff_generates_paired_staff_share_entrance_code(self):
        staff = await self.service.create_staff("小王")

        code_result = await self.db.execute(
            select(EntranceCode).filter(
                EntranceCode.tenant_id == TENANT_A,
                EntranceCode.staff_id == staff.id,
            )
        )
        code = code_result.scalar_one_or_none()
        self.assertIsNotNone(code)
        self.assertEqual(code.entry_type, "staff_share")
        self.assertEqual(code.target_page, "subpkg-member/pages/staff-share")
        self.assertEqual(code.status, 1)

    async def test_resolve_staff_share_scene_returns_invite_code_and_name(self):
        staff = await self.service.create_staff("小李")
        code_result = await self.db.execute(
            select(EntranceCode).filter(
                EntranceCode.tenant_id == TENANT_A,
                EntranceCode.staff_id == staff.id,
            )
        )
        code = code_result.scalar_one()

        res = await resolve_entrance_code(code.scene, make_request(), db=self.db)
        self.assertEqual(res.code, 200)
        self.assertEqual(res.data["entry_type"], "staff_share")
        self.assertEqual(res.data["invite_code"], staff.invite_code)
        self.assertEqual(res.data["staff_name"], "小李")
        self.assertEqual(res.data["tenant_id"], TENANT_A)

    async def test_list_staff_exposes_share_code_fields(self):
        await self.service.create_staff("小周")
        rows = await self.service.list_staff()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertIn("share_code_id", row)
        self.assertIn("share_generation_status", row)
        # 测试环境没配微信小程序 APPID/SECRET，生成会失败，但记录本身必须存在
        # 且状态可读，不能因为微信调用失败就让整个员工创建报错。
        self.assertIsNotNone(row["share_code_id"])
        self.assertEqual(row["share_generation_status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
