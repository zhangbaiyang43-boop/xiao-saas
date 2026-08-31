"""P0-REFUND-PROCESSING-RECONCILIATION.

Production ¥0.02 canary: WeChat returned the refund as SUCCESS, but Kaixin stayed
at refund_status="processing" forever -- no refund callback, GET /orders is a pure
DB read, no scheduler. This locks the fix:

  POST /api/v1/orders/{id}/refund/reconcile  is QUERY-ONLY. It queries the EXISTING
  refund (out_refund_no = RF{order.id}) and converges local state. It must NEVER
  call WxPayService.refund() -- POST /orders/{id}/refund stays the only command.
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.orders import refund_paid_order, reconcile_order_refund, serialize_order
from app.models.base import Base
from app.models.order import Order
from app.models.tenant import Tenant
from app.services.order_payment_service import OrderPaymentService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "p0-rpr-a"
TENANT_B = "p0-rpr-b"


def make_merchant_request(tenant_id=TENANT_A, role="owner", account_id=None):
    request = Request(
        {
            "type": "http", "method": "POST", "path": "/api/v1/orders/1/refund/reconcile",
            "headers": [], "query_string": b"", "server": ("testserver", 80),
            "scheme": "http", "client": ("testclient", 50000),
        }
    )
    request.state.tenant_id = tenant_id
    request.state.token_type = "merchant"
    request.state.role = role
    request.state.account_id = account_id
    return request


def _wxpay(*, query_status="SUCCESS", query_raises=False, query_none=False):
    fake = AsyncMock()
    fake.enabled = True
    if query_raises:
        fake.query_refund_by_out_refund_no.side_effect = RuntimeError("network down")
    elif query_none:
        fake.query_refund_by_out_refund_no.return_value = None
    else:
        fake.query_refund_by_out_refund_no.return_value = {
            "status": query_status,
            "amount": {"refund": 5800, "total": 5800},
        }
    return fake


class RefundProcessingReconciliationTest(unittest.IsolatedAsyncioTestCase):
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
            tenant_id=tenant_id, table_no="A1", status="rejected",
            payment_status="paid", payment_mode="prepay", payment_method="wxpay",
            total=58.0, refund_status="processing", created_at=datetime.utcnow(),
        )
        values.update(overrides)
        order = Order(**values)
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def _reconcile(self, order, tenant_id=TENANT_A):
        with patch("app.services.wxpay_service.WxPayService", return_value=self.fake):
            return await reconcile_order_refund(str(order.id), make_merchant_request(tenant_id), self.db)

    # ---- eligibility (B01-B06) -----------------------------------------

    async def test_B01_processing_same_tenant_allowed(self):
        self.fake = _wxpay(query_status="SUCCESS")
        order = await self._make_order()
        res = await self._reconcile(order)
        self.assertEqual(res.code, 200, res.msg)

    async def test_B02_cross_tenant_denied(self):
        self.fake = _wxpay()
        order = await self._make_order(tenant_id=TENANT_A)
        res = await self._reconcile(order, tenant_id=TENANT_B)
        self.assertEqual(res.code, 404)
        self.fake.query_refund_by_out_refund_no.assert_not_called()
        self.fake.refund.assert_not_called()

    async def test_B03_unpaid_denied(self):
        self.fake = _wxpay()
        order = await self._make_order(payment_status="unpaid", refund_status="processing")
        res = await self._reconcile(order)
        self.assertEqual(res.code, 400)
        self.fake.query_refund_by_out_refund_no.assert_not_called()

    async def test_B04_non_terminal_denied(self):
        self.fake = _wxpay()
        order = await self._make_order(status="pending")
        res = await self._reconcile(order)
        self.assertEqual(res.code, 409)
        self.fake.query_refund_by_out_refund_no.assert_not_called()

    async def test_B05_already_success_is_idempotent_no_provider_query(self):
        self.fake = _wxpay()
        order = await self._make_order(refund_status="success", refund_amount=58.0,
                                       refunded_at=datetime.now(timezone.utc))
        res = await self._reconcile(order)
        self.assertEqual(res.code, 200)
        self.assertTrue((res.data or {}).get("idempotent"))
        self.fake.query_refund_by_out_refund_no.assert_not_called()
        self.fake.refund.assert_not_called()

    async def test_B06_failed_is_noop_no_refund_created(self):
        self.fake = _wxpay()
        order = await self._make_order(refund_status="failed")
        res = await self._reconcile(order)
        self.assertEqual(res.code, 200)
        self.assertEqual((res.data or {}).get("reconciled"), False)
        self.fake.query_refund_by_out_refund_no.assert_not_called()
        self.fake.refund.assert_not_called()

    # ---- provider status mapping (B07-B21) ---------------------------

    async def test_B07_B13_provider_success_finalizes_locally_without_submit(self):
        self.fake = _wxpay(query_status="SUCCESS")
        order = await self._make_order()
        res = await self._reconcile(order)

        self.assertEqual(res.code, 200)
        self.assertEqual((res.data or {}).get("refund_status"), "success")
        self.fake.query_refund_by_out_refund_no.assert_awaited_with(f"RF{order.id}")  # B07
        self.fake.refund.assert_not_called()                                          # B13 / B15 / B19
        await self.db.refresh(order)
        self.assertEqual(order.refund_status, "success")                              # B08
        self.assertEqual(float(order.refund_amount), 58.0)                            # B09
        self.assertIsNotNone(order.refunded_at)                                       # B10
        self.assertFalse(serialize_order(order, [])["refund_required"])              # B11
        self.assertEqual(order.status, "rejected")                                    # B12

    async def test_B14_provider_processing_stays_processing(self):
        self.fake = _wxpay(query_status="PROCESSING")
        order = await self._make_order()
        res = await self._reconcile(order)
        self.assertEqual((res.data or {}).get("refund_status"), "processing")
        self.fake.refund.assert_not_called()
        await self.db.refresh(order)
        self.assertEqual(order.refund_status, "processing")
        self.assertIsNone(order.refunded_at)

    async def test_B16_provider_closed_marks_failed(self):
        self.fake = _wxpay(query_status="CLOSED")
        order = await self._make_order()
        res = await self._reconcile(order)
        self.assertEqual((res.data or {}).get("refund_status"), "failed")
        self.fake.refund.assert_not_called()
        await self.db.refresh(order)
        self.assertEqual(order.refund_status, "failed")
        self.assertEqual(order.status, "rejected")
        self.assertIsNone(order.refunded_at)

    async def test_B17_provider_abnormal_marks_failed(self):
        self.fake = _wxpay(query_status="ABNORMAL")
        order = await self._make_order()
        res = await self._reconcile(order)
        self.assertEqual((res.data or {}).get("refund_status"), "failed")
        self.fake.refund.assert_not_called()

    async def test_B18_B19_provider_query_none_stays_processing_no_submit(self):
        self.fake = _wxpay(query_none=True)
        order = await self._make_order()
        res = await self._reconcile(order)
        self.assertEqual((res.data or {}).get("refund_status"), "processing")
        self.fake.refund.assert_not_called()                                          # B19
        await self.db.refresh(order)
        self.assertEqual(order.refund_status, "processing")
        self.assertNotEqual(order.refund_status, "failed")

    async def test_B20_provider_unknown_status_stays_processing(self):
        self.fake = _wxpay(query_status="SOME_FUTURE_STATE")
        order = await self._make_order()
        res = await self._reconcile(order)
        self.assertEqual((res.data or {}).get("refund_status"), "processing")
        self.fake.refund.assert_not_called()
        await self.db.refresh(order)
        self.assertEqual(order.refund_status, "processing")

    async def test_B21_provider_query_exception_never_fakes_success_or_failed(self):
        self.fake = _wxpay(query_raises=True)
        order = await self._make_order()
        res = await self._reconcile(order)
        self.assertEqual((res.data or {}).get("refund_status"), "processing")
        self.fake.refund.assert_not_called()
        await self.db.refresh(order)
        self.assertEqual(order.refund_status, "processing")

    async def test_B22_duplicate_reconcile_after_success_is_idempotent(self):
        self.fake = _wxpay(query_status="SUCCESS")
        order = await self._make_order()
        await self._reconcile(order)
        self.fake.query_refund_by_out_refund_no.reset_mock()
        res2 = await self._reconcile(order)
        self.assertEqual(res2.code, 200)
        self.assertTrue((res2.data or {}).get("idempotent"))
        self.fake.query_refund_by_out_refund_no.assert_not_called()  # B23/B24: no re-reversal path re-entered
        self.fake.refund.assert_not_called()
        await self.db.refresh(order)
        self.assertEqual(order.refund_status, "success")
        self.assertEqual(order.status, "rejected")

    # ---- refund COMMAND still behaves as certified (B26-B28) ---------

    async def test_B26_B27_command_still_submits_when_no_existing_refund(self):
        submit_fake = AsyncMock()
        submit_fake.enabled = True
        submit_fake.query_refund_by_out_refund_no.return_value = None
        submit_fake.refund.return_value = {"status": "SUCCESS"}
        order = await self._make_order(refund_status=None)  # never submitted yet
        with patch("app.services.wxpay_service.WxPayService", return_value=submit_fake):
            res = await refund_paid_order(str(order.id), make_merchant_request(), self.db)
        self.assertEqual(res.code, 200)
        submit_fake.refund.assert_awaited_once()  # command DOES create a refund when none exists
        await self.db.refresh(order)
        self.assertEqual(order.refund_status, "success")
        self.assertEqual(order.status, "rejected")

    async def test_B28_command_processing_records_processing_without_finalizing(self):
        proc_fake = AsyncMock()
        proc_fake.enabled = True
        proc_fake.query_refund_by_out_refund_no.return_value = None
        proc_fake.refund.return_value = {"status": "PROCESSING"}
        order = await self._make_order(refund_status=None)
        with patch("app.services.wxpay_service.WxPayService", return_value=proc_fake):
            res = await refund_paid_order(str(order.id), make_merchant_request(), self.db)
        self.assertEqual((res.data or {}).get("refund_status"), "processing")
        await self.db.refresh(order)
        self.assertEqual(order.refund_status, "processing")
        self.assertIsNone(order.refunded_at)

    # ---- reconcile chain never calls WxPayService.refund (B29-guard) --

    async def test_reconcile_source_never_submits_a_provider_refund(self):
        # svc is the WxPayService instance; the only way this method could create a
        # refund is svc.refund(...). Assert that call site does not exist.
        root = Path(__file__).resolve().parents[1]
        src = (root / "app/services/order_payment_service.py").read_text(encoding="utf-8")
        start = src.index("async def _reconcile_existing_refund(")
        end = src.index("async def _refund_orphaned_wxpay_payment(")
        reconcile_src = src[start:end]
        self.assertNotIn("svc.refund(", reconcile_src)
        self.assertNotIn(".refund(\n", reconcile_src)
        self.assertIn("query_refund_by_out_refund_no", reconcile_src)

    async def test_B29_get_orders_does_not_invoke_refund_reconciliation(self):
        root = Path(__file__).resolve().parents[1]
        src = (root / "app/services/order_lifecycle_service.py").read_text(encoding="utf-8")
        start = src.index("async def list_orders(")
        end = src.index("\n    async def ", start + 1)
        list_src = src[start:end]
        for forbidden in (
            "_reconcile_existing_refund",
            "reconcile_refund_status",
            "query_refund_by_out_refund_no",
            "_refund_order_payment",
        ):
            self.assertNotIn(forbidden, list_src)


if __name__ == "__main__":
    unittest.main()
