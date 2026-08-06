import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MENU_SOURCE = (
    ROOT.parent / "member-mini-client" / "src" / "subpkg-order" / "pages" / "menu.vue"
).read_text(encoding="utf-8-sig")
ORDER_API_SOURCE = (ROOT.parent / "member-mini-client" / "src" / "api" / "order.js").read_text(encoding="utf-8-sig")
ORDERS_SOURCE = (ROOT / "app" / "api" / "v1" / "orders.py").read_text(encoding="utf-8-sig")
PAYMENT_SERVICE_SOURCE = (
    ROOT / "app" / "services" / "order_payment_service.py"
).read_text(encoding="utf-8-sig")
DINING_SOURCE = (ROOT / "app" / "api" / "v1" / "dining_sessions.py").read_text(encoding="utf-8-sig")
CARD_SOURCE = (ROOT.parent / "member-mini-client" / "src" / "subpkg-member" / "pages" / "card.vue").read_text(encoding="utf-8-sig")


def js_function_source(source: str, name: str) -> str:
    lines = source.splitlines()
    start = next((idx for idx, line in enumerate(lines) if line.startswith(f"    const {name} =")), None)
    assert start is not None, f"{name} source not found"
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if line.startswith("    const ") or line.startswith("  async onLoad") or line.startswith("  onShow"):
            end = idx
            break
    return "\n".join(lines[start:end])


def py_function_source(source: str, name: str) -> str:
    lines = source.splitlines()
    start = next((idx for idx, line in enumerate(lines) if line.startswith(f"async def {name}(")), None)
    assert start is not None, f"{name} source not found"
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if line.startswith("@router.") or line.startswith("async def ") or line.startswith("class "):
            end = idx
            break
    return "\n".join(lines[start:end])


class UnauthenticatedBasicOrderContractsTest(unittest.TestCase):
    def test_checkout_does_not_force_phone_auth_before_submit(self):
        go_checkout = js_function_source(MENU_SOURCE, "goCheckout")
        self.assertNotIn("showCheckoutAuth.value = true", go_checkout)
        self.assertNotIn("customer_token", go_checkout)
        self.assertIn("submitOrder()", go_checkout)

    def test_unlogged_payment_uses_wechat_code_not_member_login(self):
        confirm_pay = js_function_source(MENU_SOURCE, "confirmPay")
        self.assertIn("let jsCode = ''", confirm_pay)
        self.assertIn("jsCode = await wxLogin()", confirm_pay)
        self.assertIn("js_code: jsCode", confirm_pay)
        self.assertLess(confirm_pay.index("jsCode = await wxLogin()"), confirm_pay.index("createWxPayOrder"))
        self.assertNotIn("joinByEntranceCode", confirm_pay)
        self.assertIn("js_code: options.js_code || undefined", ORDER_API_SOURCE)

    def test_backend_pay_accepts_js_code_without_customer_id(self):
        create_pay = py_function_source(PAYMENT_SERVICE_SOURCE, "create_wxpay_order")
        self.assertIn("js_code: Optional[str] = None", ORDERS_SOURCE)
        self.assertIn("body.js_code", create_pay)
        self.assertIn("WechatService().code2session", create_pay)
        self.assertIn('openid = wechat_result.get("openid")', create_pay)
        self.assertNotIn('"NEED_LOGIN"', create_pay)
        self.assertIn('"NEED_WECHAT_CODE"', create_pay)

    def test_anonymous_order_create_and_table_order_query_use_participant_token(self):
        create_order = py_function_source(ORDERS_SOURCE, "create_order")
        list_current = py_function_source(DINING_SOURCE, "list_current_dining_orders")
        self.assertIn('customer_id = getattr(request.state, "customer_id", None)', create_order)
        self.assertIn("elif body.client_id", create_order)
        self.assertIn("DiningParticipant.client_id == body.client_id", create_order)
        self.assertIn("participant_token", list_current)
        self.assertIn("if not participant_token and not customer_id", list_current)
        self.assertIn("list_session_orders", list_current)

    def test_member_assets_remain_on_demand_login_only(self):
        load_member = js_function_source(MENU_SOURCE, "loadMemberStatus")
        self.assertIn("if (!token)", load_member)
        self.assertIn("bannerInfo.value = null", load_member)
        # loadMemberStatus 现在把 authRedirect 转发给 getMemberProfile，让调用方（点餐页
        # onLoad/onShow/切到会员 Tab 这些背景查询）能显式传 authRedirect:false，
        # token 过期时安静地掉回未登录态，而不是被全局 401 处理整页踢到"我的"去重新登录。
        self.assertIn("getMemberProfile({ authRedirect: opts.authRedirect !== false })", load_member)
        self.assertIn("getCustomerCoupons('UNUSED', { authRedirect: opts.authRedirect !== false })", load_member)
        self.assertIn("if (!uni.getStorageSync('customer_token'))", CARD_SOURCE)
        self.assertIn("uni.reLaunch({ url: '/pages/mine/mine' })", CARD_SOURCE)


if __name__ == "__main__":
    unittest.main()