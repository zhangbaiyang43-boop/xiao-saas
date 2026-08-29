"""P0 ops-alert contracts. Do not hit a real webhook."""
import logging
import unittest
from unittest.mock import patch

from app.core import ops_alert


class OpsAlertContractTest(unittest.TestCase):
    def setUp(self):
        ops_alert.reset_ops_alert_state()
        self.sent = []

        def _capture(text):
            self.sent.append(text)

        self._enqueue_patch = patch.object(ops_alert, "_enqueue_send", side_effect=_capture)
        self._url_patch = patch.object(ops_alert, "_webhook_url", return_value="https://example.invalid/ops-alert")
        self._enqueue_patch.start()
        self._url_patch.start()

    def tearDown(self):
        self._enqueue_patch.stop()
        self._url_patch.stop()
        ops_alert.reset_ops_alert_state()

    def test_candidate_events_are_exactly_the_three_p0s(self):
        self.assertEqual(
            ops_alert.CANDIDATE_EVENTS,
            frozenset(
                {
                    "WXPAY_CALLBACK_ORDER_NOT_FOUND",
                    "UNHANDLED_EXCEPTION",
                    "PRINT_FAILED",
                }
            ),
        )

    def test_wxpay_first_sends_second_is_suppressed(self):
        first = ops_alert.observe_ops_event(
            "WXPAY_CALLBACK_ORDER_NOT_FOUND",
            tenant_id="t-a",
            out_trade_no="1001",
            request_id="req-1",
            reason="ORDER_NOT_FOUND",
        )
        second = ops_alert.observe_ops_event(
            "WXPAY_CALLBACK_ORDER_NOT_FOUND",
            tenant_id="t-a",
            out_trade_no="1002",
            request_id="req-2",
            reason="ORDER_NOT_FOUND",
        )
        self.assertEqual(first, "sent")
        self.assertEqual(second, "suppressed")
        self.assertEqual(len(self.sent), 1)
        body = self.sent[0]
        self.assertIn("[P0] 微信支付订单无法匹配", body)
        self.assertIn("1001", body)
        self.assertIn("req-1", body)
        self.assertNotIn("openid", body.lower())
        self.assertNotIn("paysign", body.lower())

    def test_same_core_exception_fingerprint_sends_once(self):
        kwargs = dict(
            event="UNHANDLED_EXCEPTION",
            method="POST",
            path="/api/v1/orders",
            error_type="RuntimeError",
            stack_top="app/api/v1/orders.py:42",
            request_id="r1",
            tenant_id="t-a",
        )
        results = [ops_alert.observe_ops_event(**kwargs) for _ in range(50)]
        self.assertEqual(results[0], "sent")
        self.assertEqual(set(results[1:]), {"suppressed"})
        self.assertEqual(len(self.sent), 1)

    def test_non_core_exception_path_is_ignored(self):
        result = ops_alert.observe_ops_event(
            "UNHANDLED_EXCEPTION",
            method="GET",
            path="/api/v1/orders/workbench",
            error_type="RuntimeError",
            request_id="r-wb",
        )
        self.assertEqual(result, "ignored")
        self.assertEqual(self.sent, [])

    def test_print_alerts_on_third_failure_only(self):
        results = [
            ops_alert.observe_ops_event(
                "PRINT_FAILED",
                tenant_id="t-a",
                printer_id="p1",
                order_id=n,
            )
            for n in (1, 2, 3)
        ]
        self.assertEqual(results, ["pending", "pending", "sent"])
        self.assertEqual(len(self.sent), 1)
        self.assertIn("厨房连续打印失败", self.sent[0])
        self.assertIn("t-a", self.sent[0])

    def test_print_failures_are_isolated_by_tenant(self):
        for n in (1, 2, 3):
            ops_alert.observe_ops_event("PRINT_FAILED", tenant_id="t-a", printer_id="p1", order_id=n)
        other = ops_alert.observe_ops_event("PRINT_FAILED", tenant_id="t-b", printer_id="p1", order_id=9)
        self.assertEqual(other, "pending")
        self.assertEqual(len(self.sent), 1)

    def test_print_failures_are_isolated_by_printer(self):
        for n in (1, 2, 3):
            ops_alert.observe_ops_event("PRINT_FAILED", tenant_id="t-a", printer_id="p1", order_id=n)
        other = ops_alert.observe_ops_event("PRINT_FAILED", tenant_id="t-a", printer_id="p2", order_id=9)
        self.assertEqual(other, "pending")
        self.assertEqual(len(self.sent), 1)

    def test_print_fourth_failure_is_suppressed(self):
        results = [
            ops_alert.observe_ops_event("PRINT_FAILED", tenant_id="t-a", printer_id="p1", order_id=n)
            for n in (1, 2, 3, 4)
        ]
        self.assertEqual(results, ["pending", "pending", "sent", "suppressed"])
        self.assertEqual(len(self.sent), 1)

    def test_dynamic_pay_route_is_core_and_alerts(self):
        result = ops_alert.observe_ops_event(
            "UNHANDLED_EXCEPTION",
            method="POST",
            path="/api/v1/orders/123456/pay",
            error_type="RuntimeError",
            stack_top="app/api/v1/orders.py:1414",
            request_id="req-pay",
            tenant_id="t-a",
        )
        self.assertEqual(result, "sent")
        self.assertEqual(len(self.sent), 1)

    def test_ops_alert_failed_does_not_reenter_rules(self):
        result = ops_alert.observe_ops_event("OPS_ALERT_FAILED", reason="wecom_rejected")
        self.assertEqual(result, "ignored")
        self.assertEqual(self.sent, [])

    def test_print_skipped_is_not_a_candidate(self):
        result = ops_alert.observe_ops_event(
            "PRINT_SKIPPED",
            tenant_id="t-a",
            printer_id="p1",
            reason="ALREADY_SUCCESS",
        )
        self.assertEqual(result, "ignored")
        self.assertEqual(self.sent, [])

    def test_empty_webhook_is_noop_and_does_not_raise(self):
        self._url_patch.stop()
        with patch.object(ops_alert, "_webhook_url", return_value=""):
            result = ops_alert.observe_ops_event(
                "WXPAY_CALLBACK_ORDER_NOT_FOUND",
                tenant_id="t-a",
                out_trade_no="1",
            )
        self._url_patch.start()
        self.assertEqual(result, "disabled")
        self.assertEqual(self.sent, [])

    def test_enqueue_failure_does_not_raise(self):
        self._enqueue_patch.stop()
        with patch.object(ops_alert, "_enqueue_send", side_effect=RuntimeError("boom")):
            result = ops_alert.observe_ops_event(
                "WXPAY_CALLBACK_ORDER_NOT_FOUND",
                tenant_id="t-a",
                out_trade_no="1",
            )
        self._enqueue_patch.start()
        self.assertEqual(result, "failed")

    def test_filter_never_drops_records_and_is_idempotent(self):
        record = logging.LogRecord("app.services.x", logging.ERROR, __file__, 1, "PRINT_FAILED", (), None)
        record.event = "PRINT_FAILED"
        record.tenant_id = "t-a"
        record.printer_id = "p1"
        record.order_id = 7
        filt = ops_alert.OpsAlertFilter()
        self.assertTrue(filt.filter(record))
        self.assertTrue(filt.filter(record))
        self.assertEqual(len(self.sent), 0)

    def test_core_paths(self):
        self.assertTrue(ops_alert.is_core_exception_path("GET", "/api/v1/menu/items"))
        self.assertTrue(ops_alert.is_core_exception_path("GET", "/api/v1/shop/info"))
        self.assertTrue(ops_alert.is_core_exception_path("POST", "/api/v1/orders"))
        self.assertTrue(ops_alert.is_core_exception_path("POST", "/api/v1/orders/99/pay"))
        self.assertTrue(ops_alert.is_core_exception_path("POST", "/api/v1/orders/wxpay-notify"))
        self.assertFalse(ops_alert.is_core_exception_path("GET", "/api/v1/orders/workbench"))
        self.assertFalse(ops_alert.is_core_exception_path("POST", "/api/v1/orders/99/cancel"))
        self.assertFalse(ops_alert.is_core_exception_path("POST", "/api/v1/orders/99/reprint"))

    def test_sensitive_keys_never_appear_in_payload(self):
        ops_alert.observe_ops_event(
            "UNHANDLED_EXCEPTION",
            method="POST",
            path="/api/v1/orders",
            error_type="RuntimeError",
            stack_top="app/api/v1/orders.py:10",
            request_id="req-safe",
            tenant_id="t-a",
        )
        body = "\n".join(self.sent).lower()
        for forbidden in ("authorization", "cookie", "paysign", "openid", "private_key", "phone"):
            self.assertNotIn(forbidden, body)


if __name__ == "__main__":
    unittest.main()
