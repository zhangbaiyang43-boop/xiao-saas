import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ORDERS_SOURCE = (ROOT / "app" / "api" / "v1" / "orders.py").read_text(encoding="utf-8-sig")
PAYMENT_SERVICE_SOURCE = (
    ROOT / "app" / "services" / "order_payment_service.py"
).read_text(encoding="utf-8-sig")
MENU_SOURCE = (
    ROOT.parent
    / "member-mini-client"
    / "src"
    / "subpkg-order"
    / "pages"
    / "menu.vue"
).read_text(encoding="utf-8-sig")


def function_source(name: str, *, source: str | None = None) -> str:
    text = source if source is not None else ORDERS_SOURCE
    lines = text.splitlines()
    start = next(
        (idx for idx, line in enumerate(lines) if line.startswith(f"async def {name}(")),
        None,
    )
    assert start is not None, f"{name} source not found"
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if line.startswith("@router.") or line.startswith("class ") or line.startswith("async def "):
            end = idx
            break
    return "\n".join(lines[start:end])


class PaymentIdempotencyContractsTest(unittest.TestCase):
    def test_frontend_payment_click_is_guarded_before_request(self):
        self.assertIn("if (paying.value || !pendingOrderId.value) return false", MENU_SOURCE)
        self.assertLess(
            MENU_SOURCE.index("paying.value = true"),
            MENU_SOURCE.index("createWxPayOrder(pendingOrderId.value"),
        )

    def test_wxpay_out_trade_no_uses_stable_order_id(self):
        create_pay_source = function_source("create_wxpay_order", source=PAYMENT_SERVICE_SOURCE)
        self.assertIn("out_trade_no=str(order.id)", create_pay_source)

    def test_direct_success_paths_lock_order_before_payment_success(self):
        mock_source = function_source("mock_pay_order", source=PAYMENT_SERVICE_SOURCE)
        self.assertIn("with_for_update()", mock_source)
        self.assertLess(mock_source.index("with_for_update()"), mock_source.index("_on_payment_success"))

        create_pay_source = function_source("create_wxpay_order", source=PAYMENT_SERVICE_SOURCE)
        self.assertIn("locked_order_result", create_pay_source)
        self.assertLess(create_pay_source.index("locked_order_result"), create_pay_source.index("_on_payment_success"))

        notify_source = function_source("wxpay_notify", source=PAYMENT_SERVICE_SOURCE)
        self.assertIn("with_for_update()", notify_source)
        self.assertLess(notify_source.index("with_for_update()"), notify_source.index("_on_payment_success"))

    def test_printing_is_only_triggered_after_payment_success(self):
        payment_success_source = function_source("_on_payment_success", source=PAYMENT_SERVICE_SOURCE)
        self.assertIn("_print_paid_order_ticket", payment_success_source)
        self.assertIn("reason=\"payment_success\"", payment_success_source)
        self.assertNotIn("print_template_order", function_source("create_wxpay_order", source=PAYMENT_SERVICE_SOURCE))


if __name__ == "__main__":
    unittest.main()

