import asyncio
import unittest
from datetime import datetime

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from sqlalchemy import event

from app.models.base import Base
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import OrderItem
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.api.v1.orders import create_order, OrderCreate, OrderItemIn
from app.api.v1.menu import get_shop_info, list_menu_items
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# OrderItem.id relies on native DB autoincrement (BIGINT AUTO_INCREMENT on production
# MySQL) instead of the app-side snowflake default every other model uses. SQLite only
# aliases autoincrement onto a column declared literally as INTEGER, not BIGINT, so
# inserts through the real create_order() codepath fail here with a NOT NULL violation
# that can never happen against production MySQL. Backfill it in tests only.
@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()

TENANT_A = "tenant-a"


def make_request(path="/api/v1/orders"):
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


class OrderEntrySecurityTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(
            tenant_id=TENANT_A,
            name="Test Restaurant",
            password_hash="x",
            status=True,
            is_open=True,
            payment_mode="postpay",  # no online-payment plumbing needed for these tests
        )
        self.db.add(self.tenant)
        await self.db.flush()

        self.dish = MenuItem(
            tenant_id=TENANT_A,
            name="Kung Pao Chicken",
            price="28.00",
            available=True,
        )
        self.db.add(self.dish)

        # P0-01: these tests exercise tenant-level ordering behavior (suspended/
        # closed-for-business/active), not table validity -- give them a real,
        # active table registry entry for "A12" so the P0-01 table-authority check
        # doesn't interfere with what they're actually testing.
        self.entrance_code = EntranceCode(
            id=generate_snowflake_id(),
            tenant_id=TENANT_A,
            name="A12",
            scene="E00000000012",
            table_no="A12",
            entry_type="table",
            status=1,
        )
        self.db.add(self.entrance_code)
        await self.db.flush()
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _order_body(self):
        return OrderCreate(
            shop=TENANT_A,
            table="A12",
            items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=28.0, qty=1)],
            total=28.0,
        )

    # ---- Finding A: suspended tenant (super-admin disabled) must not keep taking orders ----

    async def test_suspended_tenant_cannot_create_order(self):
        self.tenant.status = False
        await self.db.commit()

        result = await create_order(self._order_body(), make_request(), db=self.db)
        self.assertEqual(result.code, 403)

    async def test_suspended_tenant_menu_items_hidden_from_customers(self):
        self.tenant.status = False
        await self.db.commit()

        result = await list_menu_items(make_request(), shop=TENANT_A, db=self.db)
        # 顾客端菜单接口不应该把已停用商户的菜品继续展示出来
        self.assertEqual(result.data, [])

    async def test_suspended_tenant_shop_info_reports_closed(self):
        self.tenant.status = False
        await self.db.commit()

        result = await get_shop_info(shop=TENANT_A, request=make_request(path="/api/v1/shop/info"), db=self.db)
        self.assertEqual(result.code, 404)

    async def test_active_tenant_can_still_create_order(self):
        result = await create_order(self._order_body(), make_request(), db=self.db)
        self.assertEqual(result.code, 200)

    # ---- Finding B: merchant "closed for business" toggle must block ordering ----

    async def test_closed_for_business_tenant_cannot_create_order(self):
        config = TenantConfig(tenant_id=TENANT_A, business_info={"is_open": False})
        self.db.add(config)
        await self.db.commit()

        result = await create_order(self._order_body(), make_request(), db=self.db)
        self.assertEqual(result.code, 400)

    async def test_open_tenant_without_config_row_can_order(self):
        # No TenantConfig row at all should default to "open" (matches get_shop_info's biz.get("is_open", True))
        result = await create_order(self._order_body(), make_request(), db=self.db)
        self.assertEqual(result.code, 200)


if __name__ == "__main__":
    unittest.main()
