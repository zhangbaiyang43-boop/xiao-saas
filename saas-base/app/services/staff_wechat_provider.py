"""WeChat identity provider for staff Authentication (openid only).

Authorization is NEVER derived here — only app_id + openid (+ optional unionid).
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Optional, Protocol

import httpx

from app.config import settings
from app.core.logger import logger


@dataclass(frozen=True)
class WechatIdentity:
    app_id: str
    openid: str
    unionid: Optional[str] = None


class WechatIdentityProvider(Protocol):
    def is_configured(self) -> bool: ...

    def build_oauth_url(self, *, redirect_uri: str, state: str, scope: str = "snsapi_base") -> str: ...

    async def exchange_code(self, code: str) -> WechatIdentity: ...


class OfficialAccountWechatProvider:
    """公众号网页授权 (snsapi_base → openid)."""

    AUTHORIZE_URL = "https://open.weixin.qq.com/connect/oauth2/authorize"
    TOKEN_URL = "https://api.weixin.qq.com/sns/oauth2/access_token"

    def __init__(
        self,
        *,
        app_id: str | None = None,
        app_secret: str | None = None,
    ):
        self.app_id = (app_id if app_id is not None else settings.STAFF_WECHAT_APP_ID) or ""
        self.app_secret = (app_secret if app_secret is not None else settings.STAFF_WECHAT_APP_SECRET) or ""

    def is_configured(self) -> bool:
        return bool(
            settings.STAFF_WECHAT_LOGIN_ENABLED
            and self.app_id
            and self.app_secret
            and settings.STAFF_WECHAT_OAUTH_REDIRECT_URI
        )

    def build_oauth_url(self, *, redirect_uri: str, state: str, scope: str = "snsapi_base") -> str:
        params = {
            "appid": self.app_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope or "snsapi_base",
            "state": state,
        }
        return f"{self.AUTHORIZE_URL}?{urllib.parse.urlencode(params)}#wechat_redirect"

    async def exchange_code(self, code: str) -> WechatIdentity:
        code = (code or "").strip()
        if not code:
            raise ValueError("missing_oauth_code")
        params = {
            "appid": self.app_id,
            "secret": self.app_secret,
            "code": code,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(self.TOKEN_URL, params=params)
            data = resp.json()
        openid = (data or {}).get("openid")
        if not openid:
            # Never log code / secret / full error payload with secrets.
            logger.warning(
                "staff_wechat_oauth_exchange_failed errcode=%s",
                (data or {}).get("errcode"),
            )
            raise ValueError("oauth_exchange_failed")
        return WechatIdentity(
            app_id=self.app_id,
            openid=str(openid),
            unionid=(data or {}).get("unionid") or None,
        )


class MockWechatIdentityProvider:
    """Test / non-prod provider. code format: mock:<openid>[:unionid]."""

    def __init__(self, app_id: str = "mock_staff_app"):
        self.app_id = app_id

    def is_configured(self) -> bool:
        return True

    def build_oauth_url(self, *, redirect_uri: str, state: str, scope: str = "snsapi_base") -> str:
        # Local mock: bounce back to callback with synthetic code.
        sep = "&" if "?" in redirect_uri else "?"
        return f"{redirect_uri}{sep}code=mock:test_openid&state={urllib.parse.quote(state)}"

    async def exchange_code(self, code: str) -> WechatIdentity:
        raw = (code or "").strip()
        if raw.startswith("mock:"):
            body = raw[5:]
            parts = body.split(":", 1)
            openid = parts[0] or "mock_openid"
            unionid = parts[1] if len(parts) > 1 else None
            return WechatIdentity(app_id=self.app_id, openid=openid, unionid=unionid)
        return WechatIdentity(app_id=self.app_id, openid=raw or "mock_openid")


def staff_wechat_mock_allowed() -> bool:
    if settings.APP_ENV == "production" or (not settings.DEBUG and settings.APP_ENV == "prod"):
        return False
    return bool(settings.STAFF_WECHAT_ALLOW_MOCK or settings.ALLOW_MOCK_WECHAT_SESSION)


def get_staff_wechat_provider() -> WechatIdentityProvider:
    real = OfficialAccountWechatProvider()
    if real.is_configured():
        return real
    if staff_wechat_mock_allowed():
        app_id = settings.STAFF_WECHAT_APP_ID or "mock_staff_app"
        return MockWechatIdentityProvider(app_id=app_id)
    return real


def staff_wechat_config_status() -> dict:
    real = OfficialAccountWechatProvider()
    missing = []
    if not settings.STAFF_WECHAT_LOGIN_ENABLED:
        missing.append("STAFF_WECHAT_LOGIN_ENABLED")
    if not settings.STAFF_WECHAT_APP_ID:
        missing.append("STAFF_WECHAT_APP_ID")
    if not settings.STAFF_WECHAT_APP_SECRET:
        missing.append("STAFF_WECHAT_APP_SECRET")
    if not settings.STAFF_WECHAT_OAUTH_REDIRECT_URI:
        missing.append("STAFF_WECHAT_OAUTH_REDIRECT_URI")
    from app.services.staff_bind_token_service import memory_store_allowed

    return {
        "enabled": bool(settings.STAFF_WECHAT_LOGIN_ENABLED),
        "configured": real.is_configured(),
        "mock_allowed": staff_wechat_mock_allowed(),
        "missing": missing,
        "scope": "snsapi_base",
        "app_id_configured": bool(settings.STAFF_WECHAT_APP_ID),
        "device_cookie_enabled": bool(settings.STAFF_DEVICE_COOKIE_ENABLED),
        "memory_store_allowed": memory_store_allowed(),
    }
