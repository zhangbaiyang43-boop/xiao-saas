import asyncio
import unittest
from datetime import datetime, timedelta

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.api.v1.orders import (
    OrderCreate,
    OrderItemIn,
    OrderStatusUpdate,
    _restore_order_stock,
    cancel_order,
    create_order,
    update_order_status,
)
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_request(customer_id=None, tenant_id=None, token_type=None, path="/api/v1/orders"):
    req = Request(
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
    if customer_id is not None:
        req.state.customer_id = customer_id
    if tenant_id is not None:
        req.state.tenant_id = tenant_id
    if token_type is not None:
        req.state.token_type = token_type
    if token_type == "merchant":
        req.state.role = "owner"
        req.state.account_id = None
    return req


class OrderStockRestorationTestBase(unittest.IsolatedAsyncioTestCase):
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
        # P0-01: this suite is about stock restoration, not table validity.
        self.db.add(EntranceCode(
            id=generate_snowflake_id(),
            tenant_id=TENANT_A, name="B2", scene="E000000000B2",
            table_no="B2", entry_type="table", status=1,
        ))
        await self.db.flush()
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_dish(self, stock=5, **overrides):
        defaults = dict(tenant_id=TENANT_A, name="宫保鸡丁", price="28.00", available=True, stock=stock)
        defaults.update(overrides)
        dish = MenuItem(**defaults)
        self.db.add(dish)
        await self.db.flush()
        return dish

    async def _make_order_with_items(self, items: list, **order_overrides):
        """items: list of (dish, qty) tuples."""
        defaults = dict(
            tenant_id=TENANT_A, table_no="A1", status="pending_payment",
            payment_status="unpaid", payment_mode="prepay", total=0,
            created_at=datetime.utcnow(),
        )
        defaults.update(order_overrides)
        order = Order(**defaults)
        self.db.add(order)
        await self.db.flush()
        for dish, qty in items:
            self.db.add(OrderItem(order_id=order.id, dish_id=dish.id, name=dish.name, price=dish.price, qty=qty))
        await self.db.commit()
        await self.db.refresh(order)
        return order


class RestoreOrderStockHelperTest(OrderStockRestorationTestBase):
    async def test_restores_stock_for_each_item(self):
        dish = await self._make_dish(stock=2)  # already deducted down from e.g. 5 to 2
        order = await self._make_order_with_items([(dish, 3)])

        await _restore_order_stock(order, self.db)
        await self.db.commit()
        await self.db.refresh(dish)

        self.assertEqual(dish.stock, 5)

    async def test_sums_multiple_line_items_of_the_same_dish(self):
        # Same dish split into two rows (e.g. two different spec selections), as happens
        # when a customer orders the same base dish with different spice levels.
        dish = await self._make_dish(stock=0)
        order = await self._make_order_with_items([(dish, 2), (dish, 3)])

        await _restore_order_stock(order, self.db)
        await self.db.commit()
        await self.db.refresh(dish)

        self.assertEqual(dish.stock, 5)

    async def test_does_not_touch_dishes_without_stock_tracking(self):
        dish = await self._make_dish(stock=None)
        order = await self._make_order_with_items([(dish, 2)])

        await _restore_order_stock(order, self.db)
        await self.db.commit()
        await self.db.refresh(dish)

        self.assertIsNone(dish.stock)

    async def test_tolerates_orders_with_no_items(self):
        order = await self._make_order_with_items([])
        await _restore_order_stock(order, self.db)  # must not raise


class CancelOrderRestoresStockTest(OrderStockRestorationTestBase):
    async def test_cancel_order_restores_stock(self):
        dish = await self._make_dish(stock=0)
        order = await self._make_order_with_items([(dish, 1)])

        result = await cancel_order(str(order.id), make_request(), db=self.db)

        self.assertEqual(result.code, 200)
        await self.db.refresh(dish)
        self.assertEqual(dish.stock, 1)


class UpdateOrderStatusRestoresStockTest(OrderStockRestorationTestBase):
    async def test_merchant_reject_restores_stock(self):
        # "rejected" is only a valid transition from "pending" (i.e. already paid, kitchen
        # hasn't started yet), not from "pending_payment" -- see ORDER_ALLOWED_TRANSITIONS.
        dish = await self._make_dish(stock=0)
        order = await self._make_order_with_items([(dish, 2)], status="pending")

        result = await update_order_status(
            str(order.id),
            OrderStatusUpdate(status="rejected"),
            make_request(tenant_id=TENANT_A, token_type="merchant"),
            db=self.db,
        )

        self.assertEqual(result.code, 200)
        await self.db.refresh(dish)
        self.assertEqual(dish.stock, 2)

    async def test_merchant_cancel_restores_stock(self):
        dish = await self._make_dish(stock=1)
        order = await self._make_order_with_items([(dish, 4)])

        result = await update_order_status(
            str(order.id),
            OrderStatusUpdate(status="cancelled"),
            make_request(tenant_id=TENANT_A, token_type="merchant"),
            db=self.db,
        )

        self.assertEqual(result.code, 200)
        await self.db.refresh(dish)
        self.assertEqual(dish.stock, 5)


class StaleOrderTimeoutRestoresStockTest(OrderStockRestorationTestBase):
    async def test_create_order_timeout_cleanup_restores_stale_orders_stock(self):
        dish = await self._make_dish(stock=0)
        stale_order = await self._make_order_with_items(
            [(dish, 2)],
            created_at=datetime.utcnow() - timedelta(minutes=30),
        )

        body = OrderCreate(
            shop=TENANT_A, table="B2",
            items=[OrderItemIn(dish_id=dish.id, name=dish.name, price=28.0, qty=1)],
            total=28.0,
        )
        result = await create_order(body, make_request(), db=self.db)

        self.assertEqual(result.code, 200)
        await self.db.refresh(stale_order)
        self.assertEqual(stale_order.status, "cancelled")
        await self.db.refresh(dish)
        # +2 restored from the stale order, then -1 deducted for the new order just created
        self.assertEqual(dish.stock, 1)


if __name__ == "__main__":
    unittest.main()
