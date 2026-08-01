import asyncio
import unittest

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.api.v1.orders import OrderCreate, OrderItemIn, create_order
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


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


class SplitLineItemStockOversellTest(unittest.IsolatedAsyncioTestCase):
    """The same dish split into multiple order lines (e.g. one order with two spice-level
    variants of the same base dish) used to check stock availability independently per line
    against the pre-order stock value, then deduct everything in a separate pass afterward --
    so two lines that individually looked fine could together exceed real stock. Regression
    coverage: the check must be against the running (already-partially-deducted-within-this-
    order) value, so an over-limit split order is rejected outright rather than silently
    accepted and stock clamped to zero."""

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
        self.dish = MenuItem(tenant_id=TENANT_A, name="牛肉汤", price="18.00", available=True, stock=5)
        self.db.add(self.dish)
        await self.db.flush()
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _order_count(self):
        result = await self.db.execute(select(Order))
        return len(list(result.scalars().all()))

    async def test_split_lines_exceeding_stock_are_rejected_not_clamped(self):
        body = OrderCreate(
            shop=TENANT_A, table="A1",
            items=[
                OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=18.0, qty=3),
                OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=18.0, qty=3),
            ],
            total=108.0,
        )

        result = await create_order(body, make_request(), db=self.db)

        self.assertEqual(result.code, 400)
        self.assertIn("stock not enough", result.msg)
        # create_order never called db.commit() on this path -- in the real request
        # lifecycle, FastAPI's get_db() closes the session at the end of the request, which
        # implicitly rolls back anything only flushed-not-committed. Do the same here before
        # checking DB state, otherwise this test would be asserting against an uncommitted,
        # same-transaction "read your own writes" view that production never actually persists.
        await self.db.rollback()
        await self.db.refresh(self.dish)
        self.assertEqual(self.dish.stock, 5)  # untouched -- nothing should have been persisted
        self.assertEqual(await self._order_count(), 0)

    async def test_split_lines_exactly_matching_stock_succeed(self):
        body = OrderCreate(
            shop=TENANT_A, table="A1",
            items=[
                OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=18.0, qty=2),
                OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=18.0, qty=3),
            ],
            total=90.0,
        )

        result = await create_order(body, make_request(), db=self.db)

        self.assertEqual(result.code, 200)
        await self.db.refresh(self.dish)
        self.assertEqual(self.dish.stock, 0)

    async def test_single_line_still_respects_stock_as_before(self):
        body = OrderCreate(
            shop=TENANT_A, table="A1",
            items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=18.0, qty=6)],
            total=108.0,
        )

        result = await create_order(body, make_request(), db=self.db)

        self.assertEqual(result.code, 400)
        await self.db.refresh(self.dish)
        self.assertEqual(self.dish.stock, 5)


if __name__ == "__main__":
    unittest.main()
