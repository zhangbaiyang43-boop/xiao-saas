import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
LOGIN_SOURCE = (ROOT / "app" / "api" / "v1" / "login.py").read_text(encoding="utf-8-sig")
CONFIG_SOURCE = (ROOT / "app" / "config.py").read_text(encoding="utf-8-sig")
SMS_SERVICE = ROOT / "app" / "services" / "tencent_sms_service.py"
ADMIN_API_SOURCE = (
    ROOT.parent / "admin-h5" / "src" / "api" / "index.js"
).read_text(encoding="utf-8-sig")
LOGIN_VIEW_SOURCE = (
    ROOT.parent / "admin-h5" / "src" / "views" / "Login.vue"
).read_text(encoding="utf-8-sig")


class MerchantSmsLoginContractsTest(unittest.TestCase):
    def test_backend_has_sms_send_and_login_verification_contract(self):
        self.assertIn('@router.post("/login/code"', LOGIN_SOURCE)
        self.assertIn("LoginCodeRequest", LOGIN_SOURCE)
        self.assertIn("账号不存在，请联系服务商：15936889988", LOGIN_SOURCE)
        self.assertIn("TencentSmsService", LOGIN_SOURCE)
        self.assertIn("verify_login_code", LOGIN_SOURCE)
        self.assertNotIn('MVP_LOGIN_CODE = "123456"', LOGIN_SOURCE)
        self.assertNotIn('data.code != MVP_LOGIN_CODE', LOGIN_SOURCE)

    def test_sms_service_uses_tencent_sms_without_new_database_table(self):
        self.assertTrue(SMS_SERVICE.exists())
        source = SMS_SERVICE.read_text(encoding="utf-8-sig")
        self.assertIn("TC3-HMAC-SHA256", source)
        self.assertIn("sms.tencentcloudapi.com", source)
        self.assertIn("TENCENT_SMS_LOGIN_TEMPLATE_ID", source)
        self.assertIn('"TemplateParamSet": [code]', source)
        self.assertNotIn('"TemplateParamSet": [settings.TENCENT_SMS_LOGIN_TEMPLATE_PARAM_1, code]', source)
        self.assertIn("hash_login_code", source)
        self.assertIn("get_cache", source)
        self.assertIn("set_cache", source)
        self.assertIn("_memory_cache", source)
        self.assertNotIn("Column(", source)

    def test_config_declares_required_sms_environment(self):
        for name in [
            "TENCENTCLOUD_SECRET_ID",
            "TENCENTCLOUD_SECRET_KEY",
            "TENCENT_SMS_APP_ID",
            "TENCENT_SMS_SIGN_NAME",
            "TENCENT_SMS_LOGIN_TEMPLATE_ID",
            "TENCENT_SMS_LOGIN_TEMPLATE_PARAM_1",
            "SMS_CODE_TTL_SECONDS",
            "SMS_CODE_SEND_INTERVAL_SECONDS",
            "SMS_CODE_DAILY_LIMIT",
        ]:
            self.assertIn(name, CONFIG_SOURCE)

    def test_admin_login_page_sends_real_sms_code(self):
        self.assertIn("sendLoginCode", ADMIN_API_SOURCE)
        self.assertIn("request.post('/v1/login/code'", ADMIN_API_SOURCE)
        self.assertIn("sendLoginCode", LOGIN_VIEW_SOURCE)
        self.assertIn("handleSendCode", LOGIN_VIEW_SOURCE)
        self.assertIn("codeCountdown", LOGIN_VIEW_SOURCE)
        self.assertIn("账号不存在，请联系服务商：15936889988", LOGIN_VIEW_SOURCE)
        self.assertNotIn("fillTestCode", LOGIN_VIEW_SOURCE)
        self.assertNotIn("测试验证码：123456", LOGIN_VIEW_SOURCE)


if __name__ == "__main__":
    unittest.main()