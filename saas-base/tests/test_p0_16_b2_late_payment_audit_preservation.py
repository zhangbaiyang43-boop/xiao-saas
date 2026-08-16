"""P0-16 Phase B2 -- B2-T06: a WeChat payment confirmation that arrives AFTER
an order was already cancelled/rejected (T1: terminate: T2: late payment
lands: T3: reconciliation persists payment truth) must never overwrite the
durable termination audit facts recorded at T1.

_reconcile_confirmed_payment_for_terminal_order is explicitly documented as
"does not touch order.status or print anything" -- this test proves the same
non-interference extends to the new B2 audit columns.
"""

import asyncio
import unittest
from datetime import datetime

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.order import Order
from app.models.tenant import Tenant
from app.services.order_payment_service import OrderPaymentService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


class LatePaymentPreservesTerminationAuditTest(unittest.IsolatedAsyncioTestCase):
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
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_late_payment_reconciliation_does_not_overwrite_termination_audit(self):
        # T1: customer cancel already happened and recorded the durable facts.
        t1 = datetime(2026, 8, 1, 12, 0, 0)
        order = Order(
            tenant_id=TENANT_A, table_no="A1", status="cancelled",
            payment_status="unpaid", payment_mode="prepay", total="28.00",
            terminated_at=t1, terminated_actor_type="customer",
            terminated_actor_id=555, terminated_actor_role=None,
            termination_source="customer_cancel",
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)

        # T3: a late WeChat callback proves the money actually landed.
        fake_resource = {
            "trade_state": "SUCCESS", "out_trade_no": str(order.id),
            "transaction_id": "wx_txn_late_001",
            "amount": {"total": 2800, "currency": "CNY"},
        }
        svc = OrderPaymentService(self.db)
        transitioned, binding_changed = await svc._reconcile_confirmed_payment_for_terminal_order(
            order, fake_resource,
        )
        await self.db.commit()
        await self.db.refresh(order)

        self.assertTrue(transitioned)
        self.assertEqual(order.payment_status, "paid")  # payment truth updates
        self.assertEqual(order.status, "cancelled")  # status untouched (pre-existing contract)

        # Durable termination audit is untouched by the late-payment write.
        self.assertEqual(order.terminated_at, t1)
        self.assertEqual(order.terminated_actor_type, "customer")
        self.assertEqual(order.terminated_actor_id, 555)
        self.assertIsNone(order.terminated_actor_role)
        self.assertEqual(order.termination_source, "customer_cancel")


if __name__ == "__main__":
    unittest.main()
