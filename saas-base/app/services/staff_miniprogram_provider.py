"""Mini-program identity for staff Authentication (wx.login → code2session).

Authorization is NEVER derived here — only app_id + openid (+ optional unionid).
"""

from __future__ import annotations

from typing import Optional, Protocol

from app.config import settings
from app.core.logger import logger
from app.services.staff_wechat_provider import WechatIdentity
from app.services.wechat_service import WechatService


class MiniProgramIdentityProvider(Protocol):
    def is_configured(self) -> bool: ...

    async def exchange_code(self, code: str) -> WechatIdentity: ...


class WechatMiniProgramIdentityProvider:
    """Wraps existing WechatService.code2session (platform 开心点单 miniapp)."""

    def __init__(self, wechat: WechatService | None = None):
        self._wechat = wechat or WechatService()

    def is_configured(self) -> bool:
        return bool(settings.STAFF_MINIPROGRAM_AUTH_ENABLED and self._wechat.app_id and self._wechat.app_secret)

    async def exchange_code(self, code: str) -> WechatIdentity:
        code = (code or "").strip()
        if not code:
            raise ValueError("missing_wx_code")
        try:
            data = await self._wechat.code2session(code)
        except Exception:
            logger.warning("staff_mp_code2session_failed")
            raise ValueError("code2session_failed")
        openid = (data or {}).get("openid")
        if not openid:
            logger.warning("staff_mp_code2session_missing_openid")
            raise ValueError("code2session_failed")
        app_id = self._wechat.app_id or settings.WECHAT_APP_ID or settings.WECHAT_APP_ or ""
        # Never log session_key / openid / code.
        return WechatIdentity(
            app_id=app_id,
            openid=str(openid),
            unionid=(data or {}).get("unionid") or None,
        )


class MockMiniProgramIdentityProvider:
    """Test / non-prod: code format mock:<openid>[:unionid]."""

    def __init__(self, app_id: str | None = None):
        self.app_id = app_id or settings.WECHAT_APP_ID or settings.WECHAT_APP_ or "mock_miniapp"

    def is_configured(self) -> bool:
        return True

    async def exchange_code(self, code: str) -> WechatIdentity:
        raw = (code or "").strip()
        if raw.startswith("mock:"):
            body = raw[5:]
            parts = body.split(":", 1)
            openid = parts[0] or "mock_openid"
            unionid = parts[1] if len(parts) > 1 else None
            return WechatIdentity(app_id=self.app_id, openid=openid, unionid=unionid)
        return WechatIdentity(app_id=self.app_id, openid=raw or "mock_openid")


def staff_miniprogram_mock_allowed() -> bool:
    if (settings.APP_ENV or "").lower() in ("production", "prod"):
        return False
    return bool(settings.STAFF_WECHAT_ALLOW_MOCK or settings.ALLOW_MOCK_WECHAT_SESSION)


def get_staff_miniprogram_provider() -> MiniProgramIdentityProvider:
    real = WechatMiniProgramIdentityProvider()
    if real.is_configured():
        return real
    if staff_miniprogram_mock_allowed():
        return MockMiniProgramIdentityProvider()
    return real


def staff_official_account_oauth_enabled() -> bool:
    return bool(settings.STAFF_OFFICIAL_ACCOUNT_OAUTH_ENABLED or settings.STAFF_WECHAT_LOGIN_ENABLED)


def staff_miniprogram_auth_enabled() -> bool:
    return bool(settings.STAFF_MINIPROGRAM_AUTH_ENABLED)


# TEMP_STAFF_BIND_TEST_SCAN — Remove after MiniProgram production release verification.
STAFF_MP_TEST_SCAN_PREFIX = "KXD_STAFF_BIND_V1:"


def staff_miniprogram_test_scan_enabled() -> bool:
    """Plain QR test transport only. Does not enable/disable formal MiniProgram Auth."""
    return bool(getattr(settings, "STAFF_MINIPROGRAM_TEST_SCAN_ENABLED", False))


def build_staff_mp_test_scan_payload(scene: str) -> str:
    return f"{STAFF_MP_TEST_SCAN_PREFIX}{(scene or '').strip()}"
