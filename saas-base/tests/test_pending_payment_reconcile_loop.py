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


class PendingPaymentReconcileLoopTest(unittest.IsolatedAsyncioTestCase):
    """P0 audit finding: the only reconciliation for a paid-but-webhook-lost order used to be
    the 15-minute stale-order cancellation sweep, so the kitchen could wait up to 15 minutes
    for a ticket despite the customer having already paid. _pending_payment_reconcile_once
    runs on a much shorter cycle (see app/main.py) and must ONLY recover paid orders --
    never cancel or touch stock, since that's still _stale_order_cleanup_once's job."""

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
        self.dish = MenuItem(tenant_id=TENANT_A, name="牛肉汤", price="18.00", available=True, stock=5)
        db.add(self.dish)
        await db.flush()

        self.old_order = Order(
            tenant_id=TENANT_A, table_no="A1", status="pending_payment",
            payment_status="unpaid", payment_mode="prepay", total=18.0,
            created_at=datetime.utcnow() - timedelta(seconds=200),
        )
        self.fresh_order = Order(
            tenant_id=TENANT_A, table_no="A2", status="pending_payment",
            payment_status="unpaid", payment_mode="prepay", total=18.0,
            created_at=datetime.utcnow(),
        )
        db.add(self.old_order)
        db.add(self.fresh_order)
        await db.commit()
        await db.close()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_recovers_paid_order_past_the_short_threshold(self):
        from app.main import _pending_payment_reconcile_once
        from app.services.order_payment_service import OrderPaymentService

        with patch("app.core.database.AsyncSessionLocal", self.SessionLocal), \
             patch.object(OrderPaymentService, "_recover_wxpay_order_if_paid", new=AsyncMock(return_value=True)) as mock_recover:
            await _pending_payment_reconcile_once()

        # Only the order past PENDING_PAYMENT_RECONCILE_AFTER_SECONDS should even be checked --
        # the fresh order (just created) hasn't crossed the threshold yet.
        checked_ids = {call.args[0].id for call in mock_recover.call_args_list}
        self.assertEqual(checked_ids, {self.old_order.id})

    async def test_never_cancels_or_touches_stock_itself(self):
        from app.main import _pending_payment_reconcile_once
        from app.services.order_payment_service import OrderPaymentService

        with patch("app.core.database.AsyncSessionLocal", self.SessionLocal), \
             patch.object(OrderPaymentService, "_recover_wxpay_order_if_paid", new=AsyncMock(return_value=False)):
            await _pending_payment_reconcile_once()

        verify_db = self.SessionLocal()
        try:
            order = await verify_db.get(Order, self.old_order.id)
            dish = await verify_db.get(MenuItem, self.dish.id)
            # Still pending_payment -- this loop must never cancel; that stays
            # _stale_order_cleanup_once's job at the 15-minute threshold.
            self.assertEqual(order.status, "pending_payment")
            self.assertEqual(dish.stock, 5)
        finally:
            await verify_db.close()


if __name__ == "__main__":
    unittest.main()
