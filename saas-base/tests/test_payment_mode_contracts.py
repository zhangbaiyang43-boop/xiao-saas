import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ORDERS_SOURCE = (ROOT / "app" / "api" / "v1" / "orders.py").read_text(encoding="utf-8-sig")
PAYMENT_SERVICE_SOURCE = (
    ROOT / "app" / "services" / "order_payment_service.py"
).read_text(encoding="utf-8-sig")
LIFECYCLE_SERVICE_SOURCE = (
    ROOT / "app" / "services" / "order_lifecycle_service.py"
).read_text(encoding="utf-8-sig")
TENANT_MODEL_SOURCE = (ROOT / "app" / "models" / "tenant.py").read_text(encoding="utf-8-sig")
ORDER_MODEL_SOURCE = (ROOT / "app" / "models" / "order.py").read_text(encoding="utf-8-sig")
TENANT_API_SOURCE = (ROOT / "app" / "api" / "v1" / "tenant.py").read_text(encoding="utf-8-sig")
MENU_API_SOURCE = (ROOT / "app" / "api" / "v1" / "menu.py").read_text(encoding="utf-8-sig")
MINIAPP_MENU_SOURCE = (
    ROOT.parent / "member-mini-client" / "src" / "subpkg-order" / "pages" / "menu.vue"
).read_text(encoding="utf-8-sig")
# The checkout/payment submission logic that used to live inline in menu.vue was
# already extracted into this composable before this test file was last touched --
# need_payment/savePendingPaymentOrder/clearStalePrepayOrderForPayLater etc. now
# live here, not in menu.vue itself.
USE_CHECKOUT_SOURCE = (
    ROOT.parent / "member-mini-client" / "src" / "subpkg-order" / "composables" / "useCheckout.js"
).read_text(encoding="utf-8-sig")
ADMIN_PAYMENT_SOURCE = (
    ROOT.parent / "admin-h5" / "src" / "views" / "settings" / "PaymentSettings.vue"
).read_text(encoding="utf-8-sig")
ADMIN_ORDER_MANAGE_SOURCE = (
    ROOT.parent / "admin-h5" / "src" / "views" / "OrderManage.vue"
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


class PaymentModeContractsTest(unittest.TestCase):
    def test_models_persist_tenant_and_order_payment_mode(self):
        self.assertIn("payment_mode", TENANT_MODEL_SOURCE)
        self.assertIn('"prepay"', TENANT_MODEL_SOURCE)
        self.assertIn("payment_mode", ORDER_MODEL_SOURCE)

    def test_create_order_branches_by_tenant_payment_mode(self):
        resolve_source = function_source(ORDERS_SOURCE, "_resolve_create_order_payment_mode")
        persist_source = function_source(ORDERS_SOURCE, "_persist_create_order_and_build_response")
        self.assertIn("tenant.payment_mode", resolve_source)
        self.assertIn('is_postpay = payment_mode == "postpay"', resolve_source)
        self.assertIn('is_table_account = payment_mode == "table_account"', resolve_source)
        self.assertIn('payment_mode = "prepay"', resolve_source)
        self.assertIn('"need_payment": payment_mode == "prepay"', persist_source)

    def test_unpaid_pay_later_orders_can_enter_kitchen_and_print(self):
        source = function_source(ORDERS_SOURCE, "_persist_create_order_and_build_response")
        self.assertIn('status="pending" if payment_mode in ("postpay", "table_account") else "pending_payment"', source)
        self.assertIn('payment_status="unpaid"', source)
        self.assertIn('reason="order_created_pay_later"', source)

    def test_tenant_profile_exposes_payment_mode(self):
        self.assertIn('"payment_mode"', TENANT_API_SOURCE)
        profile_source = function_source(TENANT_API_SOURCE, "get_profile")
        self.assertIn('**data["profile"]', profile_source)

    def test_shop_info_exposes_payment_mode_for_checkout_copy(self):
        source = function_source(MENU_API_SOURCE, "get_shop_info")
        self.assertIn('"payment_mode"', source)
        self.assertIn('getattr(tenant, "payment_mode", "prepay")', source)

    def test_frontend_only_pays_when_backend_requires_payment(self):
        self.assertIn("data.need_payment !== false", USE_CHECKOUT_SOURCE)
        self.assertIn("paymentMode.value", MINIAPP_MENU_SOURCE)
        self.assertIn("savePendingPaymentOrder()", USE_CHECKOUT_SOURCE)
        self.assertLess(
            USE_CHECKOUT_SOURCE.index("if (data.need_payment !== false)"),
            USE_CHECKOUT_SOURCE.index("savePendingPaymentOrder()"),
        )
        self.assertIn('v-model:value="paymentMode"', ADMIN_PAYMENT_SOURCE)
        self.assertIn("res.data.payment_mode", ADMIN_PAYMENT_SOURCE)

    def test_miniapp_confirmation_copy_follows_payment_mode(self):
        self.assertIn("normalizePaymentMode(d.payment_mode)", MINIAPP_MENU_SOURCE)
        self.assertIn("confirmPaymentLabel", MINIAPP_MENU_SOURCE)
        self.assertIn("submitTableAccount", MINIAPP_MENU_SOURCE)
        self.assertIn("authSheetText.confirmSubmit", MINIAPP_MENU_SOURCE)
        # 性能优化第1批：openCart 不再等 loadShopSettings 才显示购物车——那份数据
        # onLoad 时已经拉过一次了，这里只是顺手刷新，不该卡住购物车面板的展示。
        self.assertNotIn("await loadShopSettings()", MINIAPP_MENU_SOURCE)
        self.assertIn("loadShopSettings().catch(() => {})", MINIAPP_MENU_SOURCE)

    def test_pay_later_clears_stale_prepay_before_checkout(self):
        self.assertIn("clearStalePrepayOrderForPayLater", USE_CHECKOUT_SOURCE)
        self.assertIn("if (isPrepayMode.value || !pendingOrderId.value) return", USE_CHECKOUT_SOURCE)
        self.assertLess(USE_CHECKOUT_SOURCE.index("clearStalePrepayOrderForPayLater()"), USE_CHECKOUT_SOURCE.index("if (pendingOrderId.value) return confirmPay()"))
        self.assertIn("paymentMode.value = normalizePaymentMode(data.payment_mode)", USE_CHECKOUT_SOURCE)


    def test_admin_order_manage_can_see_pay_later_orders(self):
        self.assertIn("o.status === 'pending'", ADMIN_ORDER_MANAGE_SOURCE)
        self.assertIn("statusLabel(order.status", ADMIN_ORDER_MANAGE_SOURCE)
        self.assertIn("pendingPaymentOrders", ADMIN_ORDER_MANAGE_SOURCE)

    def test_pay_later_add_on_uses_any_active_session_order_as_parent(self):
        source = function_source(ORDERS_SOURCE, "_resolve_create_order_dining_context")
        self.assertIn('payment_status_filter = [Order.payment_status == "paid"] if payment_mode == "prepay" else []', source)
        self.assertIn("*payment_status_filter", source)

    def test_pay_later_coupon_lifecycle_is_closed(self):
        create_source = function_source(ORDERS_SOURCE, "_apply_create_order_coupon")
        status_source = lifecycle_method_source("update_order_status")
        settle_source = lifecycle_method_source("settle_table")
        self.assertIn("_mark_order_coupon_used_if_locked", ORDERS_SOURCE)
        self.assertIn("_unlock_order_coupon_if_locked", ORDERS_SOURCE)
        self.assertIn("await _mark_order_coupon_used_if_locked(order, self.db)", status_source)
        self.assertIn("await _unlock_order_coupon_if_locked(order, self.db)", status_source)
        self.assertIn("await _mark_order_coupon_used_if_locked(o, self.db)", settle_source)
        self.assertIn('coupon.status = "LOCKED"', create_source)

    def test_wxpay_endpoint_rejects_non_prepay_orders(self):
        source = function_source(PAYMENT_SERVICE_SOURCE, "create_wxpay_order")
        self.assertIn("PAYMENT_NOT_REQUIRED", source)
        self.assertIn('getattr(order, "payment_mode", "prepay") != "prepay"', source)


if __name__ == "__main__":
    unittest.main()