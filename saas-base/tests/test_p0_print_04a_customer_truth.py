"""P0-PRINT-04A: customers see only what the system really knows.

- print bookkeeping stored after PRINT_META_MARKER in Order.merchant_note never reaches a
  customer-facing payload (order read, same-table order list, order submission response)
- kitchen_notice is a two-word derivation: sent only when the print provider accepted
  the ticket, otherwise submitted
- pending is never "waiting to be accepted"; done is never "served"
- no state machine, merchant wording or merchant payload changes
"""
from __future__ import annotations

import inspect
import json
import unittest
from decimal import Decimal
from types import SimpleNamespace

from app.api.v1 import orders as orders_module
from app.api.v1.orders import ORDER_ALLOWED_TRANSITIONS, order_status_text, serialize_order
from app.models.order import Order
from app.services import dining_session_service as dining_module
from app.services import order_lifecycle_service as lifecycle
from app.services.dining_session_service import DiningSessionService
from app.services.order_lifecycle_service import (
    OrderLifecycleService,
    customer_order_view,
    customer_status_text,
    customer_visible_merchant_note,
    derive_kitchen_notice,
)
from app.services.order_print_service import PRINT_META_MARKER, _compose_merchant_note_with_print_meta

SECRETS = ("SN-SECRET-001", "TASK-999", "provider exploded", "PRINT_META", "printer_identifier", "provider_task_id")
HUMAN_NOTE = "少辣，不要香菜"


def _meta() -> dict:
    return {
        "version": 2,
        "initial_print": {
            "status": "FAILED",
            "attempts": 2,
            "provider_task_id": "TASK-999",
            "last_error": "provider exploded",
            "route": {"provider": "feieyun", "printer_identifier": "SN-SECRET-001"},
        },
        "manual_reprints": [{"operator": "account-42", "status": "SUCCESS"}],
    }


def _order(*, status="pending", print_status="PENDING", note=None, payment_mode="prepay") -> Order:
    order = Order(
        tenant_id="t-1", table_no="A1", total=Decimal("20.00"), status=status,
        payment_status="paid", payment_mode=payment_mode, source="miniprogram",
        print_status=print_status, merchant_note=note,
    )
    order.id = 90001234
    return order


class CustomerNoteSanitizationTest(unittest.TestCase):
    def test_b1_plain_note_is_unchanged(self):
        self.assertEqual(customer_visible_merchant_note(HUMAN_NOTE), HUMAN_NOTE)
        self.assertIsNone(customer_visible_merchant_note(None))
        self.assertIsNone(customer_visible_merchant_note(""))

    def test_b2_only_the_human_part_survives(self):
        raw = _compose_merchant_note_with_print_meta(HUMAN_NOTE, _meta())
        self.assertIn(PRINT_META_MARKER, raw)
        visible = customer_visible_merchant_note(raw)
        self.assertEqual(visible, HUMAN_NOTE)
        for secret in SECRETS:
            self.assertNotIn(secret, visible)

    def test_b3_print_bookkeeping_alone_becomes_nothing(self):
        raw = _compose_merchant_note_with_print_meta(None, _meta())
        self.assertTrue(raw.startswith(PRINT_META_MARKER))
        self.assertIsNone(customer_visible_merchant_note(raw))

    def test_b3b_a_corrupt_meta_tail_still_leaks_nothing(self):
        raw = HUMAN_NOTE + PRINT_META_MARKER + '{"route": {"printer_identifier": "SN-SECRET-001"'
        self.assertEqual(customer_visible_merchant_note(raw), HUMAN_NOTE)

    def test_b3c_non_string_input_is_not_trusted(self):
        self.assertIsNone(customer_visible_merchant_note(object()))


class CustomerPayloadsLeakNothingTest(unittest.TestCase):
    def _assert_clean(self, payload):
        blob = json.dumps(payload, ensure_ascii=False, default=str)
        for secret in SECRETS:
            self.assertNotIn(secret, blob, secret)
        self.assertFalse([key for key in payload if str(key).startswith("print_")])
        self.assertNotIn("print_status", blob)

    def test_b4_submission_response_view(self):
        order = _order(note=_compose_merchant_note_with_print_meta(HUMAN_NOTE, _meta()), print_status="FAILED")
        raw = serialize_order(order, [])
        # the raw serializer is the merchant/staff shape and still carries print internals
        self.assertIn("print_status", raw)
        self._assert_clean(customer_order_view(raw, order))

    def test_b4_same_table_order_list_item(self):
        order = _order(note=_compose_merchant_note_with_print_meta(HUMAN_NOTE, _meta()), print_status="FAILED")
        item = DiningSessionService(None)._serialize_order(order, [])
        self._assert_clean(item)
        self.assertEqual(item["merchant_note"], HUMAN_NOTE)

    def test_b4_print_bookkeeping_only_note_is_null_in_the_list_item(self):
        order = _order(note=_compose_merchant_note_with_print_meta(None, _meta()))
        self.assertIsNone(DiningSessionService(None)._serialize_order(order, [])["merchant_note"])

    def test_b7_legacy_fields_are_kept(self):
        order = _order(note=None)
        view = customer_order_view(serialize_order(order, []), order)
        for key in ("id", "table_no", "total", "status", "status_text", "payment_status", "payment_mode",
                    "pickup_no", "created_at", "items", "order_type", "dining_session_id"):
            self.assertIn(key, view, key)
        self.assertEqual(view["status"], "pending")  # raw status token is unchanged

        item = DiningSessionService(None)._serialize_order(order, [])
        for key in ("id", "order_no", "table_no", "total", "status", "payment_status", "payment_mode",
                    "pickup_no", "items", "participant_no"):
            self.assertIn(key, item, key)


class KitchenNoticeTest(unittest.TestCase):
    def test_b5_only_an_accepted_print_is_sent(self):
        self.assertEqual(derive_kitchen_notice(_order(print_status="SUCCESS")), "sent")
        self.assertEqual(derive_kitchen_notice(SimpleNamespace(print_status="success")), "sent")

    def test_b6_everything_else_is_submitted(self):
        for value in ("PENDING", "SENDING", "FAILED", "UNKNOWN", "NOT_ELIGIBLE", "", None):
            self.assertEqual(derive_kitchen_notice(_order(print_status=value)), "submitted", value)
        self.assertEqual(derive_kitchen_notice(SimpleNamespace()), "submitted")  # no printer, no intent

    def test_the_field_is_exposed_by_every_customer_payload_with_only_two_values(self):
        for print_status, expected in (("SUCCESS", "sent"), ("FAILED", "submitted")):
            order = _order(print_status=print_status)
            self.assertEqual(customer_order_view(serialize_order(order, []), order)["kitchen_notice"], expected)
            self.assertEqual(DiningSessionService(None)._serialize_order(order, [])["kitchen_notice"], expected)

    def test_postpay_unpaid_order_is_described_without_claiming_payment(self):
        order = _order(payment_mode="postpay", print_status="SUCCESS")
        order.payment_status = "unpaid"
        text = customer_status_text(order)
        self.assertEqual(text, "订单已发送至厨房")
        self.assertNotIn("付款", text)
        self.assertNotIn("已支付", text)


class CustomerStatusWordingTest(unittest.TestCase):
    def test_pending_is_never_waiting_to_be_accepted(self):
        for print_status in ("SUCCESS", "PENDING", "FAILED"):
            text = customer_status_text(_order(status="pending", print_status=print_status))
            self.assertIn(text, ("订单已发送至厨房", "订单已提交"))
            self.assertNotIn("接单", text)

    def test_done_only_claims_what_the_kitchen_clicked(self):
        self.assertEqual(customer_status_text(_order(status="done")), "厨房已出餐")

    def test_legacy_workbench_states_keep_their_real_wording(self):
        self.assertEqual(customer_status_text(_order(status="preparing")), order_status_text("preparing"))
        self.assertEqual(customer_status_text(_order(status="pending_payment")), "待支付")
        self.assertEqual(customer_status_text(_order(status="settled")), "已结账")

    def test_merchant_wording_is_untouched(self):
        self.assertEqual(order_status_text("pending"), "待接单")
        self.assertEqual(order_status_text("done"), "已上餐")


class StaticContractsTest(unittest.TestCase):
    def test_order_state_machine_is_unchanged(self):
        self.assertEqual(
            ORDER_ALLOWED_TRANSITIONS,
            {
                "pending_payment": {"cancelled"},
                "pending": {"preparing", "rejected", "cancelled"},
                "preparing": {"done"},
                "done": {"settled"},
            },
        )

    def test_customer_serializers_never_hand_out_the_raw_note(self):
        for fn in (OrderLifecycleService.get_my_order, DiningSessionService._serialize_order):
            source = inspect.getsource(fn)
            self.assertNotIn('"merchant_note": order.merchant_note', source, fn.__qualname__)
            self.assertIn("customer_visible_merchant_note(order.merchant_note)", source, fn.__qualname__)
            self.assertIn("derive_kitchen_notice(order)", source, fn.__qualname__)
            for forbidden in ("print_status", "printer_sn", "printer_key", "task_id", "print_error", "PRINT_META"):
                self.assertNotIn(forbidden, source, f"{fn.__qualname__}: {forbidden}")

    def test_only_customer_submitted_orders_get_the_customer_view(self):
        source = inspect.getsource(orders_module)
        self.assertEqual(source.count("customer_order_view("), 2)  # replay + create
        self.assertEqual(source.count('.startswith("staff")'), 2)

    def test_helper_module_surface(self):
        self.assertTrue(callable(lifecycle.customer_order_view))
        self.assertEqual({lifecycle.KITCHEN_NOTICE_SENT, lifecycle.KITCHEN_NOTICE_SUBMITTED}, {"sent", "submitted"})
        self.assertIn("customer_visible_merchant_note", inspect.getsource(dining_module.DiningSessionService._serialize_order))


if __name__ == "__main__":
    unittest.main()
