import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ORDERS_SOURCE = (ROOT / "app" / "api" / "v1" / "orders.py").read_text(encoding="utf-8-sig")
PAYMENT_SERVICE_SOURCE = (
    ROOT / "app" / "services" / "order_payment_service.py"
).read_text(encoding="utf-8-sig")
TENANT_SOURCE = (ROOT / "app" / "api" / "v1" / "tenant.py").read_text(encoding="utf-8-sig")
MENU_API_SOURCE = (ROOT / "app" / "api" / "v1" / "menu.py").read_text(encoding="utf-8-sig")
MINIAPP_MENU_SOURCE = (
    ROOT.parent / "member-mini-client" / "src" / "subpkg-order" / "pages" / "menu.vue"
).read_text(encoding="utf-8-sig")
# The checkout/payment submission logic that used to live inline in menu.vue was
# already extracted into this composable before this test file was last touched --
# need_payment/pendingOrderId/_handlePaySuccess etc. now live here, not in menu.vue.
USE_CHECKOUT_SOURCE = (
    ROOT.parent / "member-mini-client" / "src" / "subpkg-order" / "composables" / "useCheckout.js"
).read_text(encoding="utf-8-sig")
ADMIN_PAYMENT_SOURCE = (
    ROOT.parent / "admin-h5" / "src" / "views" / "settings" / "PaymentSettings.vue"
).read_text(encoding="utf-8-sig")


def function_source(source: str, name: str) -> str:
    lines = source.splitlines()
    start = next(
        (
            idx
            for idx, line in enumerate(lines)
            if line.startswith(f"async def {name}(")
            or line.startswith(f"def {name}(")
            or line.startswith(f"    async def {name}(")
        ),
        None,
    )
    assert start is not None, f"{name} source not found"
    is_class_method = lines[start].startswith("    async def")
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if is_class_method:
            if line.startswith("    async def ") or line.startswith("    def "):
                end = idx
                break
        elif line.startswith("@router.") or line.startswith("class ") or line.startswith("async def ") or line.startswith("def "):
            end = idx
            break
    return "\n".join(lines[start:end])


class PaymentModeIntegrationContractsTest(unittest.TestCase):
    def test_admin_saved_payment_mode_is_exposed_to_shop_and_order_create(self):
        self.assertIn('payment_mode', ADMIN_PAYMENT_SOURCE)
        self.assertIn('savePaymentMode', ADMIN_PAYMENT_SOURCE)
        self.assertIn('payment_mode', TENANT_SOURCE)
        self.assertIn('"payment_mode"', MENU_API_SOURCE)
        create_source = function_source(ORDERS_SOURCE, "create_order")
        resolve_source = function_source(ORDERS_SOURCE, "_resolve_create_order_payment_mode")
        self.assertIn('tenant.payment_mode', resolve_source)
        self.assertIn('payment_mode = payment_mode if payment_mode in ("prepay", "postpay", "table_account") else "prepay"', resolve_source)

    def test_prepay_mode_returns_payment_action_and_uses_wxpay_only_after_order_exists(self):
        create_source = function_source(ORDERS_SOURCE, "_persist_create_order_and_build_response")
        pay_source = function_source(PAYMENT_SERVICE_SOURCE, "create_wxpay_order")
        self.assertIn('status="pending" if payment_mode in ("postpay", "table_account") else "pending_payment"', create_source)
        self.assertIn('"need_payment": payment_mode == "prepay"', create_source)
        self.assertIn('"next_action": build_order_next_action(payment_mode)', create_source)
        self.assertIn('"order_id": order_data["id"]', create_source)
        self.assertIn('Order.id == int(order_id)', pay_source)
        self.assertIn('Order.tenant_id == str(order.tenant_id)', pay_source)
        self.assertIn('.with_for_update()', pay_source)
        self.assertIn('out_trade_no=str(order.id)', pay_source)
        self.assertIn('data.need_payment !== false', USE_CHECKOUT_SOURCE)
        self.assertLess(
            USE_CHECKOUT_SOURCE.index("pendingOrderId.value = String(data.id || data.order_id || '')"),
            USE_CHECKOUT_SOURCE.index('if (data.need_payment !== false)'),
        )

    def test_postpay_and_table_account_submit_without_wxpay_and_show_success(self):
        create_source = function_source(ORDERS_SOURCE, "_persist_create_order_and_build_response")
        pay_source = function_source(PAYMENT_SERVICE_SOURCE, "create_wxpay_order")
        self.assertIn('"postpay": "order_success"', ORDERS_SOURCE)
        self.assertIn('"table_account": "table_order_success"', ORDERS_SOURCE)
        self.assertIn('payment_mode in ("postpay", "table_account")', create_source)
        self.assertIn('payment_status="unpaid"', create_source)
        self.assertIn('reason="order_created_pay_later"', create_source)
        self.assertIn('getattr(order, "payment_mode", "prepay") != "prepay"', pay_source)
        self.assertIn('"PAYMENT_NOT_REQUIRED"', pay_source)
        self.assertIn('if (data.need_payment !== false)', USE_CHECKOUT_SOURCE)
        completed_id = "const completedOrderId = pendingOrderId.value"
        success_call = (
            "_handlePaySuccess(completedOrderId, "
            "{ ...data, total: payAmount.value, status: data.status || 'pending' })"
        )
        self.assertIn(completed_id, USE_CHECKOUT_SOURCE)
        self.assertIn(success_call, USE_CHECKOUT_SOURCE)
        self.assertLess(
            USE_CHECKOUT_SOURCE.index(completed_id),
            USE_CHECKOUT_SOURCE.index(success_call),
        )


if __name__ == "__main__":
    unittest.main()
