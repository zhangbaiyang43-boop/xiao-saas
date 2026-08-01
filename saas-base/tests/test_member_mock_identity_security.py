import asyncio
import unittest
from unittest.mock import patch

from app.config import settings
from app.services.wechat_service import WechatService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class MemberMockIdentitySecurityTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._original = {
            "APP_ENV": getattr(settings, "APP_ENV", None),
            "ALLOW_MOCK_WECHAT_SESSION": getattr(settings, "ALLOW_MOCK_WECHAT_SESSION", None),
            "WECHAT_APP_": getattr(settings, "WECHAT_APP_", ""),
            "WECHAT_APP_SECRET": getattr(settings, "WECHAT_APP_SECRET", ""),
        }

    def tearDown(self):
        for key, value in self._original.items():
            if value is None and hasattr(settings, key):
                delattr(settings, key)
            else:
                setattr(settings, key, value)

    async def test_production_missing_appid_rejects_mock_openid(self):
        settings.APP_ENV = "production"
        settings.ALLOW_MOCK_WECHAT_SESSION = False
        settings.WECHAT_APP_ = ""
        settings.WECHAT_APP_SECRET = "secret"

        with self.assertRaises(RuntimeError):
            await WechatService().code2session("prod-code")

    async def test_production_missing_secret_rejects_mock_openid(self):
        settings.APP_ENV = "production"
        settings.ALLOW_MOCK_WECHAT_SESSION = False
        settings.WECHAT_APP_ = "appid"
        settings.WECHAT_APP_SECRET = ""

        with self.assertRaises(RuntimeError):
            await WechatService().code2session("prod-code")

    async def test_production_wechat_request_exception_rejects_mock_openid(self):
        settings.APP_ENV = "production"
        settings.ALLOW_MOCK_WECHAT_SESSION = False
        settings.WECHAT_APP_ = "appid"
        settings.WECHAT_APP_SECRET = "secret"

        with patch("app.services.wechat_service.urllib.request.urlopen", side_effect=OSError("network down")):
            with self.assertRaises(RuntimeError):
                await WechatService().code2session("prod-code")

    async def test_test_environment_can_explicitly_use_mock_openid(self):
        settings.APP_ENV = "test"
        settings.ALLOW_MOCK_WECHAT_SESSION = True
        settings.WECHAT_APP_ = ""
        settings.WECHAT_APP_SECRET = ""

        result = await WechatService().code2session("test-code")

        self.assertTrue(result["openid"].startswith("mock_"))
        self.assertEqual(result["session_key"], "mock_session_key")


if __name__ == "__main__":
    unittest.main()
