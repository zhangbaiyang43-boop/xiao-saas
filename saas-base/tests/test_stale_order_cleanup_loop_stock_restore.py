import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


class StaleOrderCleanupLoopRestoresStockTest(unittest.IsolatedAsyncioTestCase):
    """app/main.py runs its own independent background loop (_stale_order_cleanup_loop,
    every 5 minutes) to cancel abandoned pending_payment orders -- this is the real,
    reliable cleanup mechanism (it doesn't depend on someone else happening to place a new
    order at that tenant, unlike create_order's inline cleanup). It restored locked coupons
    but not deducted stock, missing the same fix already applied to the other three
    cancellation paths in orders.py. Drives the loop for exactly one iteration by making
    the end-of-loop asyncio.sleep raise, so it runs its body once and stops."""

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        db = self.SessionLocal()

        self.tenant = Tenant(
            tenant_id=TENANT_A, name="Test Restaurant", password_hash="x",
            status=True, is_open=True, payment_mode="prepay",
        )
        db.add(self.tenant)
        self.dish = MenuItem(tenant_id=TENANT_A, name="牛肉汤", price="18.00", available=True, stock=0)
        db.add(self.dish)
        await db.flush()

        self.stale_order = Order(
            tenant_id=TENANT_A, table_no="A1", status="pending_payment",
            payment_status="unpaid", payment_mode="prepay", total=54.0,
            created_at=datetime.utcnow() - timedelta(minutes=30),
        )
        db.add(self.stale_order)
        await db.flush()
        db.add(OrderItem(order_id=self.stale_order.id, dish_id=self.dish.id, name=self.dish.name, price=18.0, qty=3))
        await db.commit()
        await db.close()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_loop_iteration_restores_stock_for_cancelled_stale_order(self):
        from app.main import _stale_order_cleanup_once
        from app.services.order_payment_service import OrderPaymentService

        with patch("app.core.database.AsyncSessionLocal", self.SessionLocal), \
             patch.object(OrderPaymentService, "_recover_wxpay_order_if_paid", new=AsyncMock(return_value=False)):
            await _stale_order_cleanup_once()

        verify_db = self.SessionLocal()
        try:
            order = await verify_db.get(Order, self.stale_order.id)
            dish = await verify_db.get(MenuItem, self.dish.id)
            self.assertEqual(order.status, "cancelled")
            self.assertEqual(dish.stock, 3)  # restored, not left at 0
        finally:
            await verify_db.close()


if __name__ == "__main__":
    unittest.main()
