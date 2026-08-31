"""P0-REFUND-001: WeChat SUCCESS on cancelled/rejected must auto-refund after paid fact."""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.orders import build_order_financial_capabilities, wxpay_notify
from app.models.base import Base
from app.models.order import Order
from app.models.tenant import Tenant
from app.services.order_payment_service import OrderPaymentService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_ID = "p0-refund-001-tenant"


def make_notify_request() -> Request:
    async def _body():
        return b"{}"

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/orders/wxpay-notify",
            "headers": [],
            "query_string": f"tenant_id={TENANT_ID}".encode(),
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    request.body = _body
    return request


class P0Refund001TerminalPaymentRefundTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add(
            Tenant(
                tenant_id=TENANT_ID,
                name="Refund 001 Shop",
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

    async def _make_order(self, **overrides) -> Order:
        values = dict(
            tenant_id=TENANT_ID,
            table_no="R1",
            status="pending_payment",
            payment_status="unpaid",
            payment_mode="prepay",
            total=58.0,
            created_at=datetime.utcnow(),
        )
        values.update(overrides)
        order = Order(**values)
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    def _resource(self, order: Order) -> dict:
        return {
            "out_trade_no": str(order.id),
            "trade_state": "SUCCESS",
            "transaction_id": f"wx-p0-refund-001-{order.id}",
            "amount": {"total": 5800, "currency": "CNY"},
        }

    def _wxpay(self, order: Order, *, refund_error: Exception | None = None):
        fake = AsyncMock()
        fake.enabled = True
        fake.verify_notify = lambda headers, raw_body: self._resource(order)
        if refund_error is not None:
            fake.refund.side_effect = refund_error
        else:
            fake.refund.return_value = {"status": "SUCCESS"}
        fake.query_refund_by_out_refund_no.return_value = None
        return fake

    async def _notify(self, order: Order, fake_wxpay):
        with patch("app.services.wxpay_service.WxPayService", return_value=fake_wxpay):
            return await wxpay_notify(make_notify_request(), self.db)

    async def test_case_a_cancelled_success_pays_then_refunds_once(self):
        order = await self._make_order(status="cancelled")
        fake = self._wxpay(order)
        response = await self._notify(order, fake)

        self.assertEqual(response["code"], "SUCCESS")
        await self.db.refresh(order)
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.wx_transaction_id, f"wx-p0-refund-001-{order.id}")
        self.assertEqual(order.refund_status, "success")
        self.assertEqual(float(order.refund_amount), 58.0)
        self.assertIsNotNone(order.refunded_at)
        fake.refund.assert_awaited_once()
        _, kwargs = fake.refund.call_args
        self.assertEqual(kwargs["out_refund_no"], f"RF{order.id}")

    async def test_case_b_rejected_success_refunds(self):
        order = await self._make_order(status="rejected")
        fake = self._wxpay(order)
        response = await self._notify(order, fake)

        self.assertEqual(response["code"], "SUCCESS")
        await self.db.refresh(order)
        self.assertEqual(order.status, "rejected")
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.refund_status, "success")
        fake.refund.assert_awaited_once()

    async def test_case_c_duplicate_notify_refunds_provider_exactly_once(self):
        order = await self._make_order(status="cancelled")
        fake = self._wxpay(order)
        first = await self._notify(order, fake)
        second = await self._notify(order, fake)

        self.assertEqual(first["code"], "SUCCESS")
        self.assertEqual(second["code"], "SUCCESS")
        await self.db.refresh(order)
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.refund_status, "success")
        self.assertEqual(fake.refund.await_count, 1)

    async def test_case_d_refund_failure_records_failed_and_refund_required(self):
        order = await self._make_order(status="cancelled")
        fake = self._wxpay(order, refund_error=RuntimeError("wxpay gateway timeout"))
        response = await self._notify(order, fake)

        self.assertEqual(response["code"], "SUCCESS")
        await self.db.refresh(order)
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(order.refund_status, "failed")
        self.assertIn("timeout", order.refund_error or "")
        caps = build_order_financial_capabilities(order)
        self.assertTrue(caps["refund_required"])

    async def test_case_e_normal_pending_payment_still_fulfils_without_orphaned_refund(self):
        order = await self._make_order(status="pending_payment")
        fake = self._wxpay(order)

        async def fake_on_success(order_obj, payment_method="wxpay"):
            order_obj.payment_status = "paid"
            order_obj.status = "pending"
            return None, 0.0

        with patch("app.services.wxpay_service.WxPayService", return_value=fake), patch.object(
            OrderPaymentService, "_on_payment_success", new=AsyncMock(side_effect=fake_on_success)
        ) as on_success, patch.object(
            OrderPaymentService, "_run_post_commit_payment_effects", new=AsyncMock()
        ) as effects, patch.object(
            OrderPaymentService, "_refund_orphaned_wxpay_payment", new=AsyncMock()
        ) as refund:
            response = await wxpay_notify(make_notify_request(), self.db)

        self.assertEqual(response["code"], "SUCCESS")
        on_success.assert_awaited_once()
        effects.assert_awaited_once()
        refund.assert_not_called()
        await self.db.refresh(order)
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.status, "pending")
        self.assertIsNone(order.refund_status)
        fake.refund.assert_not_called()
