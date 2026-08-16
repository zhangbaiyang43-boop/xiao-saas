"""P0-16 Phase B2 -- B2-T05: both real system stale-cleanup paths must write
terminated_at/actor_type=system/actor_id=NULL/actor_role=NULL and their own
distinct termination_source, never a fabricated account_id like 0 or -1.
"""

import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.services.order_payment_service import OrderPaymentService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


class SynchronousStaleCleanupAuditTest(unittest.IsolatedAsyncioTestCase):
    """app/api/v1/orders.py::_cleanup_stale_pending_payment_orders -- runs
    inline inside create_order, opportunistically sweeping OTHER stale orders
    in the same tenant. The actor is never the requester of the current
    create_order call -- it's the system."""

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.tenant = Tenant(
            tenant_id=TENANT_A, name="Restaurant A", password_hash="x",
            status=True, is_open=True, payment_mode="prepay",
        )
        self.db.add(self.tenant)
        self.stale_order = Order(
            tenant_id=TENANT_A, table_no="A1", status="pending_payment",
            payment_status="unpaid", payment_mode="prepay", total=28.0,
            created_at=datetime.utcnow() - timedelta(minutes=30),
        )
        self.db.add(self.stale_order)
        await self.db.commit()
        await self.db.refresh(self.stale_order)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_synchronous_sweep_writes_system_actor_audit(self):
        from app.api.v1.orders import _cleanup_stale_pending_payment_orders

        with patch.object(OrderPaymentService, "_recover_wxpay_order_if_paid", new=AsyncMock(return_value=False)):
            await _cleanup_stale_pending_payment_orders(TENANT_A, self.db)
        await self.db.commit()

        await self.db.refresh(self.stale_order)
        self.assertEqual(self.stale_order.status, "cancelled")
        self.assertIsNotNone(self.stale_order.terminated_at)
        self.assertEqual(self.stale_order.terminated_actor_type, "system")
        self.assertIsNone(self.stale_order.terminated_actor_id)
        self.assertIsNone(self.stale_order.terminated_actor_role)
        self.assertEqual(self.stale_order.termination_source, "synchronous_stale_cleanup")


class BackgroundStaleCleanupLoopAuditTest(unittest.IsolatedAsyncioTestCase):
    """app/main.py::_stale_order_cleanup_once -- the independent 5-minute
    background asyncio task, no Request/principal in scope at all."""

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        db = self.SessionLocal()
        self.tenant = Tenant(
            tenant_id=TENANT_A, name="Restaurant A", password_hash="x",
            status=True, is_open=True, payment_mode="prepay",
        )
        db.add(self.tenant)
        self.stale_order = Order(
            tenant_id=TENANT_A, table_no="A1", status="pending_payment",
            payment_status="unpaid", payment_mode="prepay", total=28.0,
            created_at=datetime.utcnow() - timedelta(minutes=30),
        )
        db.add(self.stale_order)
        await db.commit()
        await db.refresh(self.stale_order)
        await db.close()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_background_loop_iteration_writes_system_actor_audit(self):
        from app.main import _stale_order_cleanup_once

        with patch("app.core.database.AsyncSessionLocal", self.SessionLocal), \
             patch.object(OrderPaymentService, "_recover_wxpay_order_if_paid", new=AsyncMock(return_value=False)):
            await _stale_order_cleanup_once()

        verify_db = self.SessionLocal()
        try:
            order = await verify_db.get(Order, self.stale_order.id)
            self.assertEqual(order.status, "cancelled")
            self.assertIsNotNone(order.terminated_at)
            self.assertEqual(order.terminated_actor_type, "system")
            self.assertIsNone(order.terminated_actor_id)
            self.assertIsNone(order.terminated_actor_role)
            self.assertEqual(order.termination_source, "stale_order_cleanup")
        finally:
            await verify_db.close()

    async def test_two_system_sources_are_distinct_values(self):
        # Regression guard for the completeness lesson from P0-16 B1: two
        # different system-triggered paths must never share one source label.
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[1]
        orders_source = (root / "app/api/v1/orders.py").read_text(encoding="utf-8-sig")
        main_source = (root / "app/main.py").read_text(encoding="utf-8-sig")
        self.assertIn("synchronous_stale_cleanup", orders_source)
        self.assertIn("stale_order_cleanup", main_source)
        self.assertNotIn("synchronous_stale_cleanup", main_source)


if __name__ == "__main__":
    unittest.main()
