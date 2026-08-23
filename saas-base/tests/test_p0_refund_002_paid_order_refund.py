"""P0-REFUND-002: paid fulfillable orders can refund in-system; paid cancel stays 409."""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.orders import OrderStatusUpdate, refund_paid_order
from app.models.base import Base
from app.models.order import Order
from app.models.tenant import Tenant
from app.services.order_lifecycle_service import OrderLifecycleService
from app.services.order_payment_service import OrderPaymentService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "p0-refund-002-a"
TENANT_B = "p0-refund-002-b"


def make_merchant_request(tenant_id=TENANT_A, role="owner", account_id=None):
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/orders/1/refund",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    request.state.tenant_id = tenant_id
    request.state.token_type = "merchant"
    request.state.role = role
    request.state.account_id = account_id
    return request


class P0Refund002PaidOrderRefundTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        for tid in (TENANT_A, TENANT_B):
            self.db.add(
                Tenant(
                    tenant_id=tid,
                    name=f"Shop {tid}",
                    password_hash="x",
                    status=True,
                    is_open=True,
                    payment_mode="prepay",
                    wx_pay_enabled=True,
                    wx_mchid="1900000001",
                )
            )
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_order(self, tenant_id=TENANT_A, **overrides) -> Order:
        values = dict(
            tenant_id=tenant_id,
            table_no="A1",
            status="pending",
            payment_status="paid",
            payment_mode="prepay",
            payment_method="wxpay",
            total=58.0,
            created_at=datetime.utcnow(),
        )
        values.update(overrides)
        order = Order(**values)
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def test_paid_pending_refund_success_cancels_and_refunds_once(self):
        order = await self._make_order()
        fake = AsyncMock()
        fake.enabled = True
        with patch("app.services.wxpay_service.WxPayService", return_value=fake):
            result = await refund_paid_order(str(order.id), make_merchant_request(), self.db)

        self.assertEqual(result.code, 200, result.msg)
        await self.db.refresh(order)
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.refund_status, "success")
        self.assertEqual(float(order.refund_amount), 58.0)
        self.assertIsNotNone(order.refunded_at)
        fake.refund.assert_awaited_once()
        _, kwargs = fake.refund.call_args
        self.assertEqual(kwargs["out_refund_no"], f"RF{order.id}")

    async def test_paid_preparing_refund_success_cancels(self):
        order = await self._make_order(status="preparing")
        fake = AsyncMock()
        fake.enabled = True
        with patch("app.services.wxpay_service.WxPayService", return_value=fake):
            result = await refund_paid_order(str(order.id), make_merchant_request(), self.db)

        self.assertEqual(result.code, 200, result.msg)
        await self.db.refresh(order)
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(order.refund_status, "success")

    async def test_refund_success_is_idempotent(self):
        order = await self._make_order()
        fake = AsyncMock()
        fake.enabled = True
        with patch("app.services.wxpay_service.WxPayService", return_value=fake):
            first = await refund_paid_order(str(order.id), make_merchant_request(), self.db)
            second = await refund_paid_order(str(order.id), make_merchant_request(), self.db)

        self.assertEqual(first.code, 200)
        self.assertEqual(second.code, 200)
        self.assertTrue((second.data or {}).get("idempotent"))
        await self.db.refresh(order)
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(order.refund_status, "success")
        fake.refund.assert_awaited_once()

    async def test_refund_failure_keeps_order_status(self):
        order = await self._make_order()
        fake = AsyncMock()
        fake.enabled = True
        fake.refund.side_effect = RuntimeError("wxpay gateway timeout")
        with patch("app.services.wxpay_service.WxPayService", return_value=fake):
            result = await refund_paid_order(str(order.id), make_merchant_request(), self.db)

        self.assertEqual(result.code, 502)
        await self.db.refresh(order)
        self.assertEqual(order.status, "pending")
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.refund_status, "failed")
        self.assertIn("timeout", order.refund_error or "")

    async def test_unpaid_order_cannot_refund(self):
        order = await self._make_order(payment_status="unpaid", payment_method=None)
        result = await refund_paid_order(str(order.id), make_merchant_request(), self.db)
        self.assertEqual(result.code, 400)
        await self.db.refresh(order)
        self.assertEqual(order.status, "pending")
        self.assertIsNone(order.refund_status)

    async def test_paid_cancel_and_status_still_409(self):
        order = await self._make_order(customer_id=909)
        refund = AsyncMock(return_value={"success": True, "amount": 58.0, "error": None})
        svc = OrderLifecycleService(self.db)
        svc.set_tenant_id(TENANT_A)
        with patch.object(OrderPaymentService, "_refund_order_payment", new=refund):
            status = await svc.update_order_status(
                int(order.id), OrderStatusUpdate(status="cancelled")
            )
            cancel_by_customer = await OrderLifecycleService(self.db).cancel_order(
                int(order.id), customer_id=909, participant_token=None
            )

        self.assertEqual(cancel_by_customer.code, 409)
        self.assertEqual((cancel_by_customer.data or {}).get("code"), "PAID_ORDER_CANCEL_REQUIRES_REFUND")
        self.assertEqual(status.code, 409)
        self.assertEqual((status.data or {}).get("code"), "PAID_ORDER_CANCEL_REQUIRES_REFUND")
        refund.assert_not_called()
        await self.db.refresh(order)
        self.assertEqual(order.status, "pending")

    async def test_waiter_cannot_refund(self):
        order = await self._make_order()
        result = await refund_paid_order(
            str(order.id),
            make_merchant_request(role="waiter", account_id=12),
            self.db,
        )
        self.assertEqual(getattr(result, "status_code", None) or getattr(result, "code", None), 403)
        await self.db.refresh(order)
        self.assertEqual(order.status, "pending")
        self.assertIsNone(order.refund_status)

    async def test_tenant_a_refund_does_not_mutate_tenant_b(self):
        order_a = await self._make_order(tenant_id=TENANT_A)
        order_b = await self._make_order(tenant_id=TENANT_B, table_no="B1")
        note_b = order_b.merchant_note
        status_b = order_b.status
        refund_b = order_b.refund_status
        fake = AsyncMock()
        fake.enabled = True
        with patch("app.services.wxpay_service.WxPayService", return_value=fake):
            result = await refund_paid_order(
                str(order_a.id), make_merchant_request(TENANT_A), self.db
            )

        self.assertEqual(result.code, 200)
        await self.db.refresh(order_b)
        self.assertEqual(order_b.status, status_b)
        self.assertEqual(order_b.refund_status, refund_b)
        self.assertEqual(order_b.merchant_note, note_b)
        self.assertEqual(order_b.payment_status, "paid")
