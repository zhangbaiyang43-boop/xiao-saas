"""P0-PAID-PENDING-REJECT-REFUND-HANDOFF.

Production found the gap: a NORMALLY-paid order still sitting in the kitchen
queue (payment_status=paid, status=pending) could not be rejected, so it never
reached a terminal state, so refund_required never became true, so the merchant
never saw the (already certified) refund action -- the customer's money was
stuck.

Fix contract (Option A -- terminate then refund, two explicit steps):

  paid + pending  --merchant reject-->  rejected + paid
    * termination lifecycle only: status change + termination audit + stock
      restore + pickup/table release
    * NO refund: no provider submit, no refund_status=success, no refunded_at,
      no coupon/point/balance reversal
  rejected + paid  -->  refund_required = true  -->  existing 退款 flow
    * money movement + coupon/point/balance reversal happen ONLY after the
      provider reports final SUCCESS (Phase 02A/02B, unchanged)

Everything else stays fail-closed: paid+pending -> cancelled, customer cancel of
a paid order, and any reject once the order left "pending".
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.orders import OrderStatusUpdate, refund_paid_order, serialize_order
from app.models.base import Base
from app.models.order import Order
from app.models.tenant import Tenant
from app.services.order_lifecycle_service import OrderLifecycleService
from app.services.order_payment_service import OrderPaymentService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "p0-ppr-a"
TENANT_B = "p0-ppr-b"


def make_merchant_request(tenant_id=TENANT_A, role="owner", account_id=None):
    # Legacy owner principal: account_id must be None (a present account_id makes
    # get_request_principal load merchant_accounts, which does not exist here).
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


class PaidPendingRejectRefundHandoffTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        for tid in (TENANT_A, TENANT_B):
            self.db.add(
                Tenant(
                    tenant_id=tid, name=f"Shop {tid}", password_hash="x",
                    status=True, is_open=True, payment_mode="prepay",
                    wx_pay_enabled=True, wx_mchid="1900000001",
                )
            )
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_order(self, tenant_id=TENANT_A, **overrides) -> Order:
        values = dict(
            tenant_id=tenant_id, table_no="A1", status="pending",
            payment_status="paid", payment_mode="prepay", payment_method="wxpay",
            total=58.0, created_at=datetime.utcnow(),
        )
        values.update(overrides)
        order = Order(**values)
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    def _svc(self, tenant_id=TENANT_A) -> OrderLifecycleService:
        svc = OrderLifecycleService(self.db)
        svc.set_tenant_id(tenant_id)
        return svc

    def _fake_wxpay(self, *, submit_status="SUCCESS", query_status=None):
        fake = AsyncMock()
        fake.enabled = True
        fake.refund.return_value = {"status": submit_status}
        fake.query_refund_by_out_refund_no.return_value = (
            None if query_status is None else {"status": query_status}
        )
        return fake

    # ---- reject leg (B01-B10, B16-B20) -------------------------------------

    async def test_B01_B09_paid_pending_reject_terminates_without_any_refund_side_effect(self):
        order = await self._make_order()
        refund = AsyncMock(return_value={"success": True, "amount": 58.0, "error": None})
        restore_calls = []
        import app.services.order_stock_service as stock_mod

        async def counting_restore(o, db):
            # spy only -- stock-restore correctness is covered by
            # test_order_stock_restoration.py; here we only prove it runs once.
            restore_calls.append(int(o.id))

        with patch.object(OrderPaymentService, "_refund_order_payment", new=refund), \
             patch.object(stock_mod, "_restore_order_stock", new=counting_restore):
            result = await self._svc().update_order_status(
                int(order.id), OrderStatusUpdate(status="rejected"), account_id=7, role="owner",
            )

        self.assertEqual(result.code, 200)                       # B01
        await self.db.refresh(order)
        self.assertEqual(order.status, "rejected")               # B02
        self.assertEqual(order.payment_status, "paid")           # B03
        self.assertNotEqual(getattr(order, "refund_status", None), "success")  # B04
        self.assertIsNone(getattr(order, "refunded_at", None))   # B05
        refund.assert_not_called()                               # B06 (no provider submit)
        self.assertEqual(restore_calls, [int(order.id)])         # B07 (exactly once)
        self.assertIsNotNone(order.terminated_at)                # B08
        self.assertEqual(order.terminated_actor_type, "account")
        self.assertEqual(order.terminated_actor_id, 7)
        self.assertEqual(order.termination_source, "merchant_reject")  # B09

    async def test_B10_rejected_paid_order_sets_refund_required_true(self):
        order = await self._make_order()
        with patch.object(
            OrderPaymentService, "_refund_order_payment",
            new=AsyncMock(return_value={"success": True, "amount": 58.0, "error": None}),
        ):
            result = await self._svc().update_order_status(
                int(order.id), OrderStatusUpdate(status="rejected"), account_id=7, role="owner",
            )
        self.assertEqual(result.code, 200)
        await self.db.refresh(order)
        self.assertTrue(serialize_order(order, [])["refund_required"])   # B10

    async def test_B16_cross_tenant_merchant_cannot_reject_paid_pending_order(self):
        order = await self._make_order(tenant_id=TENANT_A)
        result = await self._svc(TENANT_B).update_order_status(
            int(order.id), OrderStatusUpdate(status="rejected"), account_id=7, role="owner",
        )
        self.assertIn(result.code, (403, 404))                   # B16 (not found / forbidden)
        await self.db.refresh(order)
        self.assertEqual(order.status, "pending")
        self.assertEqual(order.payment_status, "paid")

    async def test_B17_paid_pending_cancel_still_fails_closed(self):
        order = await self._make_order()
        result = await self._svc().update_order_status(
            int(order.id), OrderStatusUpdate(status="cancelled"), account_id=7, role="owner",
        )
        self.assertEqual(result.code, 409)                       # B17
        self.assertEqual((result.data or {}).get("code"), "PAID_ORDER_CANCEL_REQUIRES_REFUND")
        await self.db.refresh(order)
        self.assertEqual(order.status, "pending")

    async def test_B18_customer_cancel_of_paid_order_still_fails_closed(self):
        order = await self._make_order(customer_id=909)
        result = await self._svc().cancel_order(
            int(order.id), customer_id=909, participant_token=None,
        )
        self.assertEqual(result.code, 409)                       # B18
        self.assertEqual((result.data or {}).get("code"), "PAID_ORDER_CANCEL_REQUIRES_REFUND")
        await self.db.refresh(order)
        self.assertEqual(order.status, "pending")

    async def test_B19_B20_paid_post_pending_reject_stays_denied(self):
        for src in ("preparing", "done", "settled"):
            order = await self._make_order(status=src)
            result = await self._svc().update_order_status(
                int(order.id), OrderStatusUpdate(status="rejected"), account_id=7, role="owner",
            )
            self.assertNotEqual(result.code, 200, f"{src} -> rejected must be denied")  # B19/B20
            await self.db.refresh(order)
            self.assertEqual(order.status, src)

    # ---- refund handoff leg (B11-B15) -----------------------------------

    async def _reject_then(self, order):
        with patch.object(
            OrderPaymentService, "_refund_order_payment",
            new=AsyncMock(return_value={"success": True, "amount": 58.0, "error": None}),
        ):
            r = await self._svc().update_order_status(
                int(order.id), OrderStatusUpdate(status="rejected"), account_id=7, role="owner",
            )
        self.assertEqual(r.code, 200)
        await self.db.refresh(order)
        self.assertEqual((order.status, order.payment_status), ("rejected", "paid"))

    async def test_B11_B15_reject_then_merchant_refund_provider_success(self):
        order = await self._make_order()
        await self._reject_then(order)

        fake = self._fake_wxpay(submit_status="SUCCESS")
        with patch("app.services.wxpay_service.WxPayService", return_value=fake):
            res = await refund_paid_order(str(order.id), make_merchant_request(), self.db)

        self.assertEqual(res.code, 200, res.msg)
        await self.db.refresh(order)
        self.assertEqual(order.refund_status, "success")         # B11
        self.assertEqual(order.status, "rejected")               # B12 (refund never mutates status)
        self.assertIsNotNone(order.refunded_at)
        self.assertFalse(serialize_order(order, [])["refund_required"])  # B13
        fake.refund.assert_awaited_once()
        _, kwargs = fake.refund.call_args
        self.assertEqual(kwargs["out_refund_no"], f"RF{order.id}")       # B15

        # B14: a duplicate merchant refund submits nothing new to the provider.
        fake2 = self._fake_wxpay(submit_status="SUCCESS")
        with patch("app.services.wxpay_service.WxPayService", return_value=fake2):
            res2 = await refund_paid_order(str(order.id), make_merchant_request(), self.db)
        self.assertEqual(res2.code, 200)
        self.assertTrue((res2.data or {}).get("idempotent"))
        fake2.refund.assert_not_called()                          # B14
        await self.db.refresh(order)
        self.assertEqual(order.status, "rejected")
        self.assertEqual(order.refund_status, "success")

    async def test_reject_then_refund_processing_keeps_button_semantics(self):
        order = await self._make_order()
        await self._reject_then(order)

        fake = self._fake_wxpay(submit_status="PROCESSING", query_status="PROCESSING")
        with patch("app.services.wxpay_service.WxPayService", return_value=fake):
            res = await refund_paid_order(str(order.id), make_merchant_request(), self.db)

        self.assertEqual(res.code, 200)
        self.assertEqual((res.data or {}).get("refund_status"), "processing")
        await self.db.refresh(order)
        self.assertEqual(order.status, "rejected")
        self.assertEqual(order.refund_status, "processing")
        self.assertIsNone(order.refunded_at)
        # processing clears the merchant action (Phase 02B contract, unchanged)
        self.assertFalse(serialize_order(order, [])["refund_required"])


if __name__ == "__main__":
    unittest.main()
