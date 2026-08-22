import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MENU_SOURCE = (
    ROOT.parent
    / "member-mini-client"
    / "src"
    / "subpkg-order"
    / "pages"
    / "menu.vue"
).read_text(encoding="utf-8-sig")
CHECKOUT_SOURCE = (
    ROOT.parent
    / "member-mini-client"
    / "src"
    / "subpkg-order"
    / "composables"
    / "useCheckout.js"
).read_text(encoding="utf-8-sig")
ORDERS_SOURCE = (ROOT / "app" / "api" / "v1" / "orders.py").read_text(encoding="utf-8-sig")
PAYMENT_SERVICE_SOURCE = (
    ROOT / "app" / "services" / "order_payment_service.py"
).read_text(encoding="utf-8-sig")
LIFECYCLE_SERVICE_SOURCE = (
    ROOT / "app" / "services" / "order_lifecycle_service.py"
).read_text(encoding="utf-8-sig")


def function_source(source: str, name: str) -> str:
    lines = source.splitlines()
    starts = [
        f"  const {name} = async",
        f"  const {name} = (",
        f"  function {name}",
        f"    const {name} = async",
        f"    const {name} = (",
        f"    function {name}",
        f"    async def {name}(",
        f"async def {name}(",
    ]
    start = next(
        (idx for idx, line in enumerate(lines) if any(line.startswith(prefix) for prefix in starts)),
        None,
    )
    assert start is not None, f"{name} source not found"
    is_two_space_js = lines[start].startswith("  const ") or lines[start].startswith("  function ")
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if (
            (is_two_space_js and (line.startswith("  const ") or line.startswith("  function ")))
            or (not is_two_space_js and line.startswith("    const "))
            or (not is_two_space_js and line.startswith("    function "))
            or line.startswith("    async def ")
            or line.startswith("  async onLoad")
            or line.startswith("  onShow")
            or line.startswith("@router.")
            or line.startswith("async def ")
            or line.startswith("class ")
        ):
            end = idx
            break
    return "\n".join(lines[start:end])


class PaymentResultRecoveryContractsTest(unittest.TestCase):
    def test_backend_order_query_recovers_paid_wxpay_order(self):
        # P1-WXPAY-RECOVERY-GATE: client_order_query now goes through the shared gate
        # (fast_lane=True) on its own isolated recon_db session instead of calling
        # _recover_wxpay_order_if_paid directly -- the gate's own attempt_recovery still
        # calls straight into the same, unmodified core function underneath.
        get_my_order = function_source(LIFECYCLE_SERVICE_SOURCE, "get_my_order")
        recover = function_source(PAYMENT_SERVICE_SOURCE, "_recover_wxpay_order_if_paid")
        self.assertIn("recovery_gate.attempt_recovery(", get_my_order)
        self.assertIn('recon_order, recon_db, source="client_order_query"', get_my_order)
        self.assertIn("query_order_by_out_trade_no", recover)
        self.assertIn("_apply_confirmed_wx_payment", recover)
        self.assertIn("with_for_update()", recover)

    def test_frontend_persists_pending_order_before_payment(self):
        # 实际下单逻辑在 performSubmitOrder 里——submitOrder 现在只是加了重入锁的薄封装，
        # 这样"本桌身份失效，重建后自动重试一次"才能在不撞锁的情况下递归重试。
        self.assertIn("import { useCheckout } from '../composables/useCheckout.js'", MENU_SOURCE)
        self.assertIn("} = useCheckout({", MENU_SOURCE)
        submit_order = function_source(CHECKOUT_SOURCE, "performSubmitOrder")
        self.assertIn("savePendingPaymentOrder()", submit_order)
        self.assertLess(submit_order.index("savePendingPaymentOrder()"), submit_order.index("confirmPay()"))
        self.assertIn("const savePendingPaymentOrder", CHECKOUT_SOURCE)
        self.assertIn("const restorePendingPaymentOrder", CHECKOUT_SOURCE)
        self.assertIn("return await performSubmitOrder()", function_source(CHECKOUT_SOURCE, "submitOrder"))

    def test_frontend_checks_order_status_before_starting_payment_again(self):
        confirm_pay = function_source(CHECKOUT_SOURCE, "confirmPay")
        self.assertIn("recoverPendingPaymentResult({ presentSuccess: true })", confirm_pay)
        self.assertLess(
            confirm_pay.index("recoverPendingPaymentResult({ presentSuccess: true })"),
            confirm_pay.index("await createWxPayOrder("),
        )
        self.assertLess(
            confirm_pay.index("recoverPendingPaymentResult({ presentSuccess: true })"),
            confirm_pay.index("await uni.requestPayment("),
        )

    def test_frontend_recovers_after_request_payment_error_and_page_reentry(self):
        confirm_pay = function_source(CHECKOUT_SOURCE, "confirmPay")
        self.assertIn("let paymentOrderId = ''", confirm_pay)
        self.assertIn("paymentOrderId = pendingOrderId.value", confirm_pay)
        self.assertIn(
            "recoverPaymentResultById(paymentOrderId, { showDetail: true, presentSuccess: true })",
            confirm_pay,
        )
        self.assertNotIn("recoverPendingPaymentResult({ showDetail: true })", confirm_pay)
        self.assertIn("getOrderStatus", CHECKOUT_SOURCE)
        self.assertIn("restorePendingPaymentOrder,", MENU_SOURCE)
        self.assertIn("this.restorePendingPaymentOrder()", MENU_SOURCE)
        self.assertIn("this.recoverPendingPaymentResult", MENU_SOURCE)
        self.assertIn("onShow()", MENU_SOURCE)

    def test_paid_recovery_clears_pending_payment_id_to_prevent_repay(self):
        recover = function_source(CHECKOUT_SOURCE, "recoverPendingPaymentResult")
        by_id = function_source(CHECKOUT_SOURCE, "recoverPaymentResultById")
        self.assertIn(
            "return await recoverPaymentResultById(id, { showDetail, presentSuccess })",
            recover,
        )
        self.assertIn("isPaidOrSubmittedOrder(data)", by_id)
        self.assertIn("if (String(pendingOrderId.value) === String(id))", by_id)
        self.assertIn("clearPendingPaymentOrder()", by_id)
        self.assertLess(
            by_id.index("if (String(pendingOrderId.value) === String(id))"),
            by_id.index("clearPendingPaymentOrder()"),
        )


if __name__ == "__main__":
    unittest.main()
