import asyncio
import unittest

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import OrderItem
from app.models.tenant import Tenant
from app.api.v1.orders import create_order, OrderCreate, OrderItemIn
from app.services.dining_session_service import DiningSessionService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-zone-a"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


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


class EntranceCodeZonePaymentRoutingTest(unittest.IsolatedAsyncioTestCase):
    """羊肉馆场景：简餐区桌码永远先付款，正餐区桌码永远桌台账单，
    不看整店的 payment_mode 开关；没配置分区的桌码/柜台下单则完全不受影响（向后兼容）。"""

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        # 整店默认是 postpay——用来验证分区桌码能覆盖这个默认值，
        # 没分区的桌码/柜台单则仍然落回这个默认值。
        self.tenant = Tenant(
            tenant_id=TENANT_A, name="Test Lamb Shop", password_hash="x",
            status=True, is_open=True, payment_mode="postpay",
        )
        self.db.add(self.tenant)

        self.dish = MenuItem(tenant_id=TENANT_A, name="Lamb Soup", price="15.00", available=True)
        self.db.add(self.dish)

        self.db.add(EntranceCode(
            id=generate_snowflake_id(),
            tenant_id=TENANT_A, name="简餐区A桌", channel="TABLE", scene="ZONE-QUICK-A",
            table_no="QUICK-A", entry_type="table", status=1, zone_type="quick",
        ))
        self.db.add(EntranceCode(
            id=generate_snowflake_id(),
            tenant_id=TENANT_A, name="正餐区B桌", channel="TABLE", scene="ZONE-FULL-B",
            table_no="FULL-B", entry_type="table", status=1, zone_type="full",
        ))
        self.db.add(EntranceCode(
            id=generate_snowflake_id(),
            tenant_id=TENANT_A, name="未配置分区C桌", channel="TABLE", scene="ZONE-NONE-C",
            table_no="NONE-C", entry_type="table", status=1, zone_type=None,
        ))
        await self.db.flush()
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _order_body(self, table, request_id, dining_session_id=None, participant_token=None):
        return OrderCreate(
            shop=TENANT_A,
            table=table,
            items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=15.0, qty=1)],
            total=15.0,
            request_id=request_id,
            dining_session_id=dining_session_id,
            participant_token=participant_token,
        )

    async def test_quick_zone_table_always_prepays_regardless_of_tenant_default(self):
        result = await create_order(self._order_body("QUICK-A", "req-quick-1"), make_request(), db=self.db)
        self.assertEqual(result.code, 200)
        self.assertEqual(result.data["payment_mode"], "prepay")

    async def test_full_zone_table_always_uses_table_account_regardless_of_tenant_default(self):
        # 桌台账单模式要求已经扫码建好本桌会话——先走一遍真实的扫码建会话流程，
        # 再带着 dining_session_id/participant_token 下单，跟小程序真实调用路径一致。
        identity = await DiningSessionService(self.db).resolve_session(TENANT_A, "FULL-B")
        await self.db.commit()
        result = await create_order(
            self._order_body(
                "FULL-B", "req-full-1",
                dining_session_id=int(identity["dining_session_id"]),
                participant_token=identity["participant_token"],
            ),
            make_request(), db=self.db,
        )
        self.assertEqual(result.code, 200)
        self.assertEqual(result.data["payment_mode"], "table_account")

    async def test_table_without_zone_config_falls_back_to_tenant_default(self):
        result = await create_order(self._order_body("NONE-C", "req-none-1"), make_request(), db=self.db)
        self.assertEqual(result.code, 200)
        self.assertEqual(result.data["payment_mode"], "postpay")

    async def test_order_without_table_still_uses_tenant_default(self):
        result = await create_order(self._order_body("", "req-counter-1"), make_request(), db=self.db)
        self.assertEqual(result.code, 200)
        self.assertEqual(result.data["payment_mode"], "postpay")


if __name__ == "__main__":
    unittest.main()
