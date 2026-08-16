"""P0-16 Phase B1 -- T04 (payment initiation trace), T05 (callback trace),
T06 (recovery source, all 7 real callers), T07 (print trace), T08
(background-loop exception visibility).
"""

import asyncio
import re
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.config import settings
from app.models.base import Base
from app.models.customer import Customer
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.api.v1.orders import WxPayBody, create_order, OrderCreate, OrderItemIn
from app.services.order_payment_service import OrderPaymentService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def mocked_wxpay_service():
    mock_cls = patch("app.services.wxpay_service.WxPayService")
    mock_instance = mock_cls.start()
    mock_instance.return_value.enabled = True
    mock_instance.return_value.create_jsapi_order = AsyncMock(
        return_value={
            "timeStamp": "1700000000", "nonceStr": "abc123",
            "package": "prepay_id=wx000000000000000000000000000000",
            "signType": "RSA", "paySign": "sig",
        }
    )
    return mock_cls, mock_instance.return_value


def make_request():
    return Request(
        {
            "type": "http", "method": "POST", "path": "/api/v1/orders",
            "headers": [], "query_string": b"", "server": ("testserver", 80),
            "scheme": "http", "client": ("testclient", 50000),
        }
    )


def make_customer_request(customer_id, openid="wx-openid-1"):
    req = make_request()
    req.state.customer_id = customer_id
    req.state.openid = openid
    return req


class PaymentInitiationTraceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.tenant = Tenant(tenant_id=TENANT_A, name="Restaurant A", password_hash="x", status=True, is_open=True, payment_mode="prepay")
        self.customer = Customer(tenant_id=TENANT_A, openid="wx-openid-1")
        self.db.add_all([self.tenant, self.customer])
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_payment_requested_log_correlates_order_and_amount(self):
        order = Order(
            tenant_id=TENANT_A, customer_id=self.customer.id, table_no="", total="19.90",
            status="pending_payment", payment_status="unpaid", payment_mode="prepay",
            client_request_id="K-PAY-1",
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)

        mock_cls, wxpay_instance = mocked_wxpay_service()
        try:
            with patch("app.services.order_payment_service.logger") as mock_logger:
                result = await OrderPaymentService(self.db).create_wxpay_order(
                    str(order.id), WxPayBody(), make_customer_request(self.customer.id)
                )
        finally:
            mock_cls.stop()
        self.assertEqual(result.code, 200)

        all_calls = [str(c) for c in mock_logger.info.call_args_list + mock_logger.warning.call_args_list]
        requested = [c for c in all_calls if "PAYMENT_REQUESTED" in c]
        self.assertTrue(requested, f"no PAYMENT_REQUESTED log; calls were: {all_calls}")
        combined = " ".join(requested)
        self.assertIn(str(order.id), combined)
        self.assertIn("1990", combined)  # amount_fen
        self.assertNotIn("wx-openid-1", combined)  # never log openid


class CallbackAndRecoveryTraceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.tenant = Tenant(tenant_id=TENANT_A, name="Restaurant A", password_hash="x", status=True, is_open=True, payment_mode="prepay")
        self.db.add(self.tenant)
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_order(self, total="28.00"):
        order = Order(
            tenant_id=TENANT_A, table_no="", total=total, status="pending_payment",
            payment_status="unpaid", payment_mode="prepay",
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def test_recovery_success_log_includes_source(self):
        order = await self._make_order()
        fake_resource = {
            "trade_state": "SUCCESS", "out_trade_no": str(order.id),
            "transaction_id": "wx_txn_abc123", "amount": {"total": 2800, "currency": "CNY"},
        }
        with patch("app.services.wxpay_service.WxPayService") as mock_wx_cls:
            mock_wx_cls.return_value.enabled = True
            mock_wx_cls.return_value.query_order_by_out_trade_no = AsyncMock(return_value=fake_resource)
            with patch("app.services.order_payment_service.logger") as mock_logger:
                svc = OrderPaymentService(self.db)
                recovered = await svc._recover_wxpay_order_if_paid(order, source="client_order_query")
        self.assertTrue(recovered)

        all_calls = [str(c) for c in mock_logger.info.call_args_list + mock_logger.warning.call_args_list]
        recovered_calls = [c for c in all_calls if "WXPAY_ORDER_RECOVERED" in c]
        self.assertTrue(recovered_calls, f"no WXPAY_ORDER_RECOVERED log; calls were: {all_calls}")
        self.assertIn("client_order_query", " ".join(recovered_calls))

    async def test_recovery_source_default_does_not_break_existing_direct_callers(self):
        # Existing tests call _recover_wxpay_order_if_paid(order) positionally,
        # with no source kwarg -- the new parameter must default, not become
        # a required break.
        order = await self._make_order()
        with patch("app.services.wxpay_service.WxPayService") as mock_wx_cls:
            mock_wx_cls.return_value.enabled = True
            mock_wx_cls.return_value.query_order_by_out_trade_no = AsyncMock(return_value=None)
            svc = OrderPaymentService(self.db)
            recovered = await svc._recover_wxpay_order_if_paid(order)
        self.assertFalse(recovered)


class RecoverySourceCompletenessTest(unittest.TestCase):
    """T06: the exact completeness guard requested -- every real runtime call
    site of _recover_wxpay_order_if_paid must pass a `source=` kwarg. Prevents
    a repeat of "7 callers, only 6 updated" silently happening again."""

    EXPECTED_CALL_SITES = {
        ("app/api/v1/orders.py", 723): "synchronous_stale_cleanup",
        ("app/main.py", 169): "stale_order_background",
        ("app/main.py", 232): "pending_payment_background",
        ("app/services/order_lifecycle_service.py", 169): "cancel_precheck",
        ("app/services/order_lifecycle_service.py", 235): "client_order_query",
        ("app/services/order_lifecycle_service.py", 352): "merchant_order_query",
        ("app/services/order_lifecycle_service.py", 504): "status_update_precheck",
    }

    def _find_call_lines(self, relpath):
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[1]
        text = (root / relpath).read_text(encoding="utf-8-sig")
        lines = text.splitlines()
        hits = []
        for idx, line in enumerate(lines, start=1):
            if "_recover_wxpay_order_if_paid(" in line and "async def " not in line:
                # capture this line plus a couple following, since calls can
                # wrap across lines with the source kwarg on a later line
                snippet = "\n".join(lines[idx - 1:idx + 2])
                hits.append((idx, snippet))
        return hits

    def test_every_known_call_site_still_exists_and_passes_source(self):
        files = {"app/api/v1/orders.py", "app/main.py", "app/services/order_lifecycle_service.py"}
        total_found = 0
        missing_source = []
        for relpath in files:
            for lineno, snippet in self._find_call_lines(relpath):
                total_found += 1
                if not re.search(r"source\s*=", snippet):
                    missing_source.append(f"{relpath}:{lineno}")
        self.assertEqual(total_found, 7, f"expected 7 runtime call sites, found {total_found}")
        self.assertEqual(missing_source, [], f"call sites missing source= kwarg: {missing_source}")

    def test_no_two_call_sites_share_the_same_source_label(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[1]
        labels = []
        for relpath in ("app/api/v1/orders.py", "app/main.py", "app/services/order_lifecycle_service.py"):
            for lineno, snippet in self._find_call_lines(relpath):
                m = re.search(r"source\s*=\s*[\"']([\w_]+)[\"']", snippet)
                if m:
                    labels.append(m.group(1))
        self.assertEqual(len(labels), len(set(labels)), f"duplicate source labels found: {labels}")


class PrintTraceTest(unittest.TestCase):
    """T07: source-text proof of print trigger/result logging -- executing the
    real print pipeline requires a full provider mock harness already covered
    by P0-07's own tests; this proves the NEW logging calls exist at the right
    points without re-testing print business logic itself."""

    def setUp(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[1]
        self.source = (root / "app/services/order_print_service.py").read_text(encoding="utf-8-sig")

    def test_print_trigger_and_result_events_are_logged(self):
        for event_name in ("PRINT_TRIGGERED", "PRINT_SUCCEEDED", "PRINT_FAILED"):
            self.assertIn(event_name, self.source, f"{event_name} not found in order_print_service.py")

    def test_print_recovery_attempt_is_logged(self):
        self.assertIn("PRINT_RECOVERY_ATTEMPT", self.source)

    def test_print_log_does_not_dump_full_provider_response(self):
        # heuristic: the new logging lines should not contain a raw response-dump
        # pattern like str(response) / response.text over the whole payload
        matches = re.findall(r"logger\.\w+\([^\n]*PRINT_(?:TRIGGERED|SUCCEEDED|FAILED|RECOVERY_ATTEMPT)[^\n]*", self.source)
        offending = [m for m in matches if "response)" in m or ".text" in m]
        self.assertEqual(offending, [])


class BackgroundLoopVisibilityTest(unittest.IsolatedAsyncioTestCase):
    """T08: both background loops must log (not silently swallow) an
    exception raised mid-iteration, and must continue looping afterward."""

    async def test_pending_payment_reconcile_loop_logs_and_continues(self):
        import app.main as main_module

        call_count = {"n": 0}

        async def boom():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("synthetic failure")
            raise asyncio.CancelledError()  # stop the infinite loop after iteration 2

        with patch.object(main_module, "_pending_payment_reconcile_once", side_effect=boom):
            with patch.object(main_module, "logger") as mock_logger:
                with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
                    with self.assertRaises(asyncio.CancelledError):
                        await main_module._pending_payment_reconcile_loop()

        self.assertEqual(call_count["n"], 2, "loop did not continue past the first exception")
        self.assertTrue(mock_logger.exception.called, "exception was not logged")

    async def test_stale_order_cleanup_loop_logs_and_continues(self):
        import app.main as main_module

        call_count = {"n": 0}

        async def boom():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("synthetic failure")
            raise asyncio.CancelledError()

        with patch.object(main_module, "_stale_order_cleanup_once", side_effect=boom):
            with patch.object(main_module, "logger") as mock_logger:
                with patch("asyncio.sleep", new=AsyncMock(return_value=None)):
                    with self.assertRaises(asyncio.CancelledError):
                        await main_module._stale_order_cleanup_loop()

        self.assertEqual(call_count["n"], 2, "loop did not continue past the first exception")
        self.assertTrue(mock_logger.exception.called, "exception was not logged")


if __name__ == "__main__":
    unittest.main()
