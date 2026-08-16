import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.order import Order
from app.models.tenant import Tenant
from app.api.v1.orders import (
    OrderStatusUpdate,
    cancel_order,
    update_order_status,
    wxpay_notify,
)
from app.services.order_payment_service import OrderPaymentService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


def make_request(customer_id=None, tenant_id=None, token_type=None, path="/api/v1/orders/1/cancel"):
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


class RaceReconciliationTestBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(
            tenant_id=TENANT_A, name="Test Restaurant", password_hash="x",
            status=True, is_open=True, payment_mode="prepay",
            wx_pay_enabled=True, wx_mchid="1900000001",
        )
        self.db.add(self.tenant)
        await self.db.flush()
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_order(self, **overrides):
        defaults = dict(
            tenant_id=TENANT_A, table_no="A1", status="pending_payment",
            payment_status="unpaid", payment_mode="prepay", total=58.0,
            created_at=datetime.utcnow(),
        )
        defaults.update(overrides)
        order = Order(**defaults)
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order


class RefundOrphanedWxpayPaymentTest(RaceReconciliationTestBase):
    async def test_success_refunds_without_touching_order_status(self):
        order = await self._make_order(status="cancelled")
        fake_wxpay = AsyncMock()
        fake_wxpay.enabled = True

        with patch("app.services.wxpay_service.WxPayService", return_value=fake_wxpay):
            result = await OrderPaymentService(self.db)._refund_orphaned_wxpay_payment(order)

        self.assertTrue(result["success"])
        self.assertEqual(order.status, "cancelled")  # must not resurrect the order
        self.assertEqual(order.refund_status, "success")
        self.assertEqual(float(order.refund_amount), 58.0)
        fake_wxpay.refund.assert_awaited_once()
        _, kwargs = fake_wxpay.refund.call_args
        self.assertEqual(kwargs["refund_fen"], 5800)

    async def test_failure_marks_refund_failed_for_manual_follow_up(self):
        order = await self._make_order(status="rejected")
        fake_wxpay = AsyncMock()
        fake_wxpay.enabled = True
        fake_wxpay.refund.side_effect = RuntimeError("wxpay gateway timeout")

        with patch("app.services.wxpay_service.WxPayService", return_value=fake_wxpay):
            result = await OrderPaymentService(self.db)._refund_orphaned_wxpay_payment(order)

        self.assertFalse(result["success"])
        self.assertEqual(order.status, "rejected")
        self.assertEqual(order.refund_status, "failed")
        self.assertIn("timeout", order.refund_error)


class CancelAndRejectRaceCheckTest(RaceReconciliationTestBase):
    async def test_cancel_order_refuses_when_wechat_already_paid(self):
        order = await self._make_order()

        async def recover(order_obj, *args, **kwargs):
            order_obj.payment_status = "paid"
            order_obj.status = "pending"
            await self.db.flush()
            return True

        with patch.object(OrderPaymentService, "_recover_wxpay_order_if_paid", new=AsyncMock(side_effect=recover)):
            result = await cancel_order(str(order.id), make_request(), db=self.db)

        self.assertEqual(result.code, 409)
        self.assertEqual(result.data["code"], "PAID_ORDER_CANCEL_REQUIRES_REFUND")
        await self.db.refresh(order)
        self.assertEqual(order.status, "pending")  # payment won; cancellation is denied

    async def test_cancel_order_proceeds_normally_when_wechat_not_paid(self):
        order = await self._make_order()

        with patch.object(OrderPaymentService, "_recover_wxpay_order_if_paid", new=AsyncMock(return_value=False)):
            result = await cancel_order(str(order.id), make_request(), db=self.db)

        self.assertEqual(result.code, 200)
        await self.db.refresh(order)
        self.assertEqual(order.status, "cancelled")

    async def test_update_order_status_refuses_reject_when_wechat_already_paid(self):
        order = await self._make_order()

        with patch.object(OrderPaymentService, "_recover_wxpay_order_if_paid", new=AsyncMock(return_value=True)):
            result = await update_order_status(
                str(order.id),
                OrderStatusUpdate(status="rejected"),
                make_request(tenant_id=TENANT_A, token_type="merchant"),
                db=self.db,
            )

        self.assertEqual(result.code, 409)
        await self.db.refresh(order)
        self.assertEqual(order.status, "pending_payment")


class WxpayNotifyRaceWithCancelTest(RaceReconciliationTestBase):
    def _fake_request(self, out_trade_no: str):
        req = AsyncMock()
        req.headers = {}
        req.query_params = {"tenant_id": TENANT_A}
        req.body = AsyncMock(return_value=b"{}")
        self._resource = {
            "out_trade_no": out_trade_no,
            "trade_state": "SUCCESS",
            "transaction_id": f"wx-cancel-race-{out_trade_no}",
            "amount": {"total": 5800, "currency": "CNY"},
        }
        return req

    async def test_callback_after_cancel_records_paid_attention_without_auto_refund(self):
        order = await self._make_order(status="cancelled")
        fake_wxpay = AsyncMock()
        fake_wxpay.enabled = True
        fake_wxpay.verify_notify = lambda headers, raw_body: self._resource

        auto_refund = AsyncMock()

        with patch("app.services.wxpay_service.WxPayService", return_value=fake_wxpay), \
             patch.object(OrderPaymentService, "_refund_orphaned_wxpay_payment", new=auto_refund), \
             patch.object(OrderPaymentService, "_on_payment_success", new=AsyncMock()) as on_success:
            response = await wxpay_notify(self._fake_request(str(order.id)), self.db)

        self.assertEqual(response["code"], "SUCCESS")
        auto_refund.assert_not_called()
        on_success.assert_not_called()  # must not run the "fulfil the order" side effects
        await self.db.refresh(order)
        self.assertEqual(order.status, "cancelled")  # not resurrected
        self.assertEqual(order.payment_status, "paid")
        self.assertIsNone(order.refund_status)

    async def test_callback_skips_when_already_reconciled(self):
        order = await self._make_order(status="cancelled", refund_status="success")
        fake_wxpay = AsyncMock()
        fake_wxpay.enabled = True
        fake_wxpay.verify_notify = lambda headers, raw_body: self._resource

        auto_refund = AsyncMock()

        with patch("app.services.wxpay_service.WxPayService", return_value=fake_wxpay), \
             patch.object(OrderPaymentService, "_refund_orphaned_wxpay_payment", new=auto_refund):
            response = await wxpay_notify(self._fake_request(str(order.id)), self.db)

        self.assertEqual(response["code"], "SUCCESS")
        auto_refund.assert_not_called()

    async def test_normal_pending_payment_callback_still_fulfils_the_order(self):
        order = await self._make_order(status="pending_payment")
        fake_wxpay = AsyncMock()
        fake_wxpay.enabled = True
        fake_wxpay.verify_notify = lambda headers, raw_body: self._resource

        async def fake_on_success(order_obj, payment_method="wxpay"):
            order_obj.payment_status = "paid"
            order_obj.status = "pending"
            return None, 0.0

        with patch("app.services.wxpay_service.WxPayService", return_value=fake_wxpay), \
             patch.object(OrderPaymentService, "_on_payment_success", new=AsyncMock(side_effect=fake_on_success)) as on_success:
            response = await wxpay_notify(self._fake_request(str(order.id)), self.db)

        self.assertEqual(response["code"], "SUCCESS")
        on_success.assert_awaited_once()
        await self.db.refresh(order)
        self.assertEqual(order.payment_status, "paid")


if __name__ == "__main__":
    unittest.main()
