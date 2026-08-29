"""BUG: 店铺整体选桌台账单,但顾客扫的桌码属于简餐区(zone_type=quick),
/shop/info 只返回店铺默认 → 小程序按钮写「提交桌台」,点了却建成 prepay 单跳微信支付。

修复:/shop/info 和建单共用 resolve_effective_payment_mode,按「这张桌」算。
"""

import asyncio
import unittest

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.menu import get_shop_info
from app.models.base import Base
from app.models.entrance_code import EntranceCode
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.services.entrance_code_service import resolve_effective_payment_mode
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TEN = "tenant-shopinfo-zone"


def _req():
    return Request({
        "type": "http", "method": "GET", "path": "/api/v1/shop/info", "headers": [],
        "query_string": b"", "server": ("t", 80), "scheme": "http", "client": ("c", 1), "state": {},
    })


class ShopInfoZonePaymentModeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        # 整店默认桌台账单
        self.db.add(Tenant(tenant_id=TEN, name="羊肉馆", password_hash="x", status=True, payment_mode="table_account"))
        self.db.add(TenantConfig(tenant_id=TEN, member_rules={}, coupon_rules={}, business_info={}, plugin_settings={}))
        for table_no, zone in [("A01", "quick"), ("B02", "full"), ("C03", None)]:
            self.db.add(EntranceCode(
                id=generate_snowflake_id(), tenant_id=TEN,
                name=f"{table_no}桌", channel="TABLE", scene=f"Z-{table_no}",
                entry_type="table", table_no=table_no, zone_type=zone, status=1,
            ))
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def test_resolver_zone_overrides_store_default(self):
        async def run():
            return (
                await resolve_effective_payment_mode(self.db, TEN, "table_account", "A01"),
                await resolve_effective_payment_mode(self.db, TEN, "table_account", "B02"),
                await resolve_effective_payment_mode(self.db, TEN, "table_account", "C03"),
                await resolve_effective_payment_mode(self.db, TEN, "table_account", ""),
                await resolve_effective_payment_mode(self.db, TEN, "table_account", "NOPE"),
            )

        a01, b02, c03, empty, nope = asyncio.run(run())
        self.assertEqual(a01, "prepay")          # 简餐区 → 先付款(BUG 场景)
        self.assertEqual(b02, "table_account")   # 正餐区 → 桌台账单
        self.assertEqual(c03, "table_account")   # 没分区 → 跟随店铺默认
        self.assertEqual(empty, "table_account")  # 没传桌号 → 店铺默认
        self.assertEqual(nope, "table_account")   # 桌号查不到 → 店铺默认

    def test_shop_info_returns_zone_aware_payment_mode(self):
        async def run(table):
            resp = await get_shop_info(shop=TEN, request=_req(), table=table, db=self.db)
            data = resp.data if hasattr(resp, "data") else resp["data"]
            return data["payment_mode"]

        # 扫简餐区桌码 → shop/info 就返回 prepay,小程序按钮显示「立即支付」而不是「提交桌台」
        self.assertEqual(asyncio.run(run("A01")), "prepay")
        self.assertEqual(asyncio.run(run("B02")), "table_account")
        self.assertEqual(asyncio.run(run("")), "table_account")


if __name__ == "__main__":
    unittest.main()
