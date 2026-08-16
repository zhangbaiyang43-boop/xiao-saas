"""P0-16 Phase B1 -- T10: a failure in the NEW observability logging must
never change a business result. Telemetry is best-effort by design (Section
27/83/84 of the B1 brief); this forces the logging subsystem itself to raise
(not just a malformed argument, which Python's own logging module already
isolates via Handler.handleError) and proves order creation still succeeds.
"""

import asyncio
import unittest
from unittest.mock import patch

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
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
    if target.id is None:
        target.id = generate_snowflake_id()


def make_request():
    return Request(
        {
            "type": "http", "method": "POST", "path": "/api/v1/orders",
            "headers": [], "query_string": b"", "server": ("testserver", 80),
            "scheme": "http", "client": ("testclient", 50000),
        }
    )


class LoggingFailureDoesNotBreakOrderCreationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.tenant = Tenant(tenant_id=TENANT_A, name="Restaurant A", password_hash="x", status=True, is_open=True, payment_mode="postpay")
        self.dish = MenuItem(tenant_id=TENANT_A, name="宫保鸡丁", price="28.00", available=True)
        self.db.add_all([self.tenant, self.dish])
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_order_still_created_when_the_logging_subsystem_itself_raises(self):
        body = OrderCreate(
            shop=TENANT_A, table="", items=[OrderItemIn(dish_id=self.dish.id, name="宫保鸡丁", price=28, qty=1)],
            total=28, request_id="K-TELEMETRY-1",
        )
        # Force the logging call itself to raise -- simulates the logging
        # subsystem (not just a malformed argument) failing outright.
        with patch("app.api.v1.orders.logger.info", side_effect=RuntimeError("disk full")):
            result = await create_order(body, make_request(), db=self.db)

        self.assertEqual(result.code, 200, "order creation must succeed even if its own trace logging fails")
        self.assertTrue(result.data.get("order_id"))


if __name__ == "__main__":
    unittest.main()
