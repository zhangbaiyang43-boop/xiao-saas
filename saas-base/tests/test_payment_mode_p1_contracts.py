import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ORDERS_SOURCE = (ROOT / "app" / "api" / "v1" / "orders.py").read_text(encoding="utf-8-sig")
LIFECYCLE_SERVICE_SOURCE = (
    ROOT / "app" / "services" / "order_lifecycle_service.py"
).read_text(encoding="utf-8-sig")
PRINT_SERVICE_SOURCE = (ROOT / "app" / "services" / "order_print_service.py").read_text(encoding="utf-8-sig")
MINIAPP_MENU_SOURCE = (
    ROOT.parent / "member-mini-client" / "src" / "subpkg-order" / "pages" / "menu.vue"
).read_text(encoding="utf-8-sig")
MINIAPP_CHECKOUT_SOURCE = (
    ROOT.parent / "member-mini-client" / "src" / "subpkg-order" / "composables" / "useCheckout.js"
).read_text(encoding="utf-8-sig")


def function_source(source: str, name: str) -> str:
    lines = source.splitlines()
    start = next(
        (idx for idx, line in enumerate(lines) if line.startswith(f"async def {name}(") or line.startswith(f"def {name}(") ),
        None,
    )
    assert start is not None, f"{name} source not found"
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if line.startswith("@router.") or line.startswith("class ") or line.startswith("async def ") or line.startswith("def "):
            end = idx
            break
    return "\n".join(lines[start:end])


def lifecycle_method_source(name: str) -> str:
    lines = LIFECYCLE_SERVICE_SOURCE.splitlines()
    start = next(
        (idx for idx, line in enumerate(lines) if line.startswith(f"    async def {name}(")),
        None,
    )
    assert start is not None, f"{name} source not found"
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if line.startswith("    async def ") or line.startswith("    def "):
            end = idx
            break
    return "\n".join(lines[start:end])


class PaymentModeP1ContractsTest(unittest.TestCase):
    def test_create_order_returns_order_id_and_backend_next_action(self):
        create_source = function_source(ORDERS_SOURCE, "_persist_create_order_and_build_response")
        action_source = function_source(ORDERS_SOURCE, "build_order_next_action")
        self.assertIn('"prepay": "pay"', ORDERS_SOURCE)
        self.assertIn('"postpay": "order_success"', ORDERS_SOURCE)
        self.assertIn('"table_account": "table_order_success"', ORDERS_SOURCE)
        self.assertIn('"order_id": order_data["id"]', create_source)
        self.assertIn('"next_action": build_order_next_action(payment_mode)', create_source)
        self.assertIn('raise ValueError("unsupported payment mode")', action_source)

    def test_miniapp_keeps_id_compatibility_and_accepts_order_id_fallback(self):
        self.assertIn("import { useCheckout } from '../composables/useCheckout.js'", MINIAPP_MENU_SOURCE)
        self.assertIn("} = useCheckout({", MINIAPP_MENU_SOURCE)
        self.assertIn("pendingOrderId,", MINIAPP_MENU_SOURCE)
        self.assertIn("pendingOrderId.value = String(data.id || data.order_id || '')", MINIAPP_CHECKOUT_SOURCE)
        self.assertIn("if (data.need_payment !== false)", MINIAPP_CHECKOUT_SOURCE)
        self.assertLess(
            MINIAPP_CHECKOUT_SOURCE.index("pendingOrderId.value = String(data.id || data.order_id || '')"),
            MINIAPP_CHECKOUT_SOURCE.index("if (data.need_payment !== false)"),
        )

    def test_postpay_settlement_marks_offline_paid_only_at_settled_transition(self):
        source = lifecycle_method_source("update_order_status")
        self.assertIn('just_settled = body.status == "settled"', source)
        self.assertIn('getattr(order, "payment_mode", "prepay") == "postpay"', source)
        self.assertIn('_mark_order_offline_paid(order)', source)
        self.assertIn('"payment_status": getattr(order, "payment_status", None)', source)
        self.assertIn('"payment_time": getattr(order, "payment_time", None)', source)
        self.assertNotIn('body.status == "done" and getattr(order, "payment_mode", "prepay") == "postpay"', source)

    def test_table_account_settlement_syncs_child_orders_paid_in_same_flow(self):
        source = lifecycle_method_source("settle_table")
        self.assertIn('.with_for_update()', source)
        self.assertIn('paid_synced_count = 0', source)
        self.assertIn('getattr(o, "payment_mode", "prepay") in ("table_account", "postpay")', source)
        self.assertIn('_mark_order_offline_paid(o)', source)
        self.assertIn('"payment_status": "paid"', source)
        self.assertIn('"payment_method": "offline"', source)

    def test_offline_paid_helper_is_idempotent_and_preserves_existing_payment_time(self):
        source = function_source(LIFECYCLE_SERVICE_SOURCE, "_mark_order_offline_paid")
        self.assertIn('if getattr(order, "payment_status", None) == "paid":', source)
        self.assertIn('return False', source)
        self.assertIn('order.payment_status = "paid"', source)
        self.assertIn('order.payment_method = payment_method', source)
        self.assertIn('order.payment_time = datetime.now(timezone.utc).isoformat()', source)

    def test_reprint_rules_allow_pay_later_kitchen_but_keep_receipt_paid_only(self):
        rule_source = function_source(PRINT_SERVICE_SOURCE, "can_reprint_order")
        route_source = function_source(ORDERS_SOURCE, "reprint_order_ticket")
        print_source = function_source(PRINT_SERVICE_SOURCE, "_print_paid_order_ticket")
        self.assertIn('if print_type == "receipt":', rule_source)
        self.assertIn('payment_status == "paid"', rule_source)
        self.assertIn('if print_type == "kitchen":', rule_source)
        self.assertIn('payment_mode in ("postpay", "table_account")', rule_source)
        self.assertIn('status in ("cancelled", "rejected")', rule_source)
        self.assertIn('allowed, reason = can_reprint_order(order, print_type=print_type)', route_source)
        self.assertIn('evaluate_print_eligibility', print_source)
        eligibility_source = function_source(PRINT_SERVICE_SOURCE, "evaluate_print_eligibility")
        self.assertIn('payment_mode == "prepay"', eligibility_source)
        self.assertIn('payment_mode in ("postpay", "table_account")', rule_source)


if __name__ == "__main__":
    unittest.main()
