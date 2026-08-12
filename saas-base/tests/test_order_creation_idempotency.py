import asyncio
import unittest

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.api.v1.orders import create_order, OrderCreate, OrderItemIn
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    # Same SQLite-only workaround as test_order_entry_security.py: OrderItem.id relies
    # on native BIGINT AUTO_INCREMENT (fine on production MySQL), which SQLite only
    # aliases to rowid for a column declared literally as INTEGER, not BIGINT.
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


class OrderCreationIdempotencyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
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
        await self.db.flush()

        self.dish = MenuItem(tenant_id=TENANT_A, name="Kung Pao Chicken", price="28.00", available=True)
        self.db.add(self.dish)
        # P0-01: this suite is about idempotency, not table validity.
        self.db.add(EntranceCode(
            id=generate_snowflake_id(),
            tenant_id=TENANT_A, name="A12", scene="E00000000012",
            table_no="A12", entry_type="table", status=1,
        ))
        await self.db.flush()
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _order_body(self, request_id=None):
        return OrderCreate(
            shop=TENANT_A,
            table="A12",
            items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=28.0, qty=1)],
            total=28.0,
            request_id=request_id,
        )

    async def _order_count(self):
        result = await self.db.execute(select(func.count()).select_from(Order))
        return int(result.scalar() or 0)

    async def test_retrying_the_same_request_id_does_not_create_a_second_order(self):
        first = await create_order(self._order_body(request_id="retry-abc-1"), make_request(), db=self.db)
        self.assertEqual(first.code, 200)
        second = await create_order(self._order_body(request_id="retry-abc-1"), make_request(), db=self.db)
        self.assertEqual(second.code, 200)

        self.assertEqual(first.data["order_id"], second.data["order_id"])
        self.assertEqual(await self._order_count(), 1)

    async def test_a_new_request_id_creates_a_genuinely_new_order(self):
        first = await create_order(self._order_body(request_id="submit-1"), make_request(), db=self.db)
        second = await create_order(self._order_body(request_id="submit-2"), make_request(), db=self.db)

        self.assertEqual(first.code, 200)
        self.assertEqual(second.code, 200)
        self.assertNotEqual(first.data["order_id"], second.data["order_id"])
        self.assertEqual(await self._order_count(), 2)

    async def test_omitting_request_id_keeps_legacy_behavior_of_always_creating_a_new_order(self):
        # 旧客户端/没升级的调用方不传 request_id 时，行为必须和修复前完全一样——
        # 这个字段是可选加固，不能变成强制要求，否则会破坏现有调用方。
        first = await create_order(self._order_body(request_id=None), make_request(), db=self.db)
        second = await create_order(self._order_body(request_id=None), make_request(), db=self.db)

        self.assertEqual(first.code, 200)
        self.assertEqual(second.code, 200)
        self.assertNotEqual(first.data["order_id"], second.data["order_id"])
        self.assertEqual(await self._order_count(), 2)

    async def test_concurrent_duplicate_already_committed_by_another_request_is_returned_not_duplicated(self):
        # 模拟"几乎同一时刻"的真正并发重复提交：另一路请求已经把订单提交并落库了，
        # 这次请求带着同样的 request_id 进来时，即便没赶上前面那次早查重的检查窗口，
        # 唯一索引冲突兜底也必须让它拿到同一张订单，而不是报错或者建出第二张。
        pre_existing = Order(
            tenant_id=TENANT_A, total="28.00", status="pending",
            payment_status="unpaid", payment_mode="postpay",
            client_request_id="race-key-1",
        )
        self.db.add(pre_existing)
        await self.db.commit()

        result = await create_order(self._order_body(request_id="race-key-1"), make_request(), db=self.db)
        self.assertEqual(result.code, 200)
        self.assertEqual(result.data["order_id"], str(pre_existing.id))
        self.assertEqual(await self._order_count(), 1)


if __name__ == "__main__":
    unittest.main()
