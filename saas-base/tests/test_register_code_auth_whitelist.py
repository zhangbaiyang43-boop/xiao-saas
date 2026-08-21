"""P0 hotfix -- POST /api/v1/register/code was missing from AuthMiddleware's
WHITELIST, so every anonymous merchant self-registration attempt got a hard
401 "未登录或登录已过期" before ever reaching send_register_code(). The
frontend's global 401 handler (admin-h5/src/api/request.js) then force-
reloaded the page to /login, which resets Login.vue's `mode` back to its
default 'owner' -- observed by the user as "注册页 -> 点击获取验证码 ->
瞬间跳回老板登录页", registration completely blocked before a code could
ever be entered.

Proves the fix at two levels:
  1. AuthMiddleware.dispatch() in isolation (same convention as
     test_auth_middleware_tenant_status.py) -- fastest, isolates exactly the
     whitelist classification this hotfix touches.
  2. The real app + the real middleware stack + the real route handler via
     httpx.ASGITransport -- proves an anonymous request doesn't just avoid a
     401, it reaches send_register_code()'s/register()'s own business logic
     (new-phone success, existing-phone 400, registration-closed 403, bad-code
     400), and that this fix did NOT widen auth anywhere else.

TencentSmsService is mocked throughout -- this test never sends a real SMS.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings
from app.core.database import get_db
from app.main import app
from app.middleware.auth_middleware import AuthMiddleware
from app.models.base import Base
from app.models.tenant import Tenant

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def make_anonymous_request(path: str, method: str = "POST") -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


async def dummy_call_next(request):
    return Response(status_code=200)


class AuthMiddlewareRegisterWhitelistTest(unittest.IsolatedAsyncioTestCase):
    """Direct AuthMiddleware.dispatch() proof."""

    async def asyncSetUp(self):
        self.middleware = AuthMiddleware(app=None)

    async def test_anonymous_register_code_passes_middleware(self):
        response = await self.middleware.dispatch(
            make_anonymous_request("/api/v1/register/code"), dummy_call_next
        )
        self.assertEqual(response.status_code, 200)

    async def test_anonymous_register_passes_middleware(self):
        response = await self.middleware.dispatch(
            make_anonymous_request("/api/v1/register"), dummy_call_next
        )
        self.assertEqual(response.status_code, 200)

    async def test_anonymous_protected_route_still_401(self):
        # Regression guard: this fix must not widen auth beyond exactly
        # /api/v1/register/code -- a real protected merchant endpoint with
        # no token must still be rejected.
        response = await self.middleware.dispatch(
            make_anonymous_request("/api/v1/customers", method="GET"), dummy_call_next
        )
        self.assertEqual(response.status_code, 401)


class RegisterCodeEndToEndTest(unittest.IsolatedAsyncioTestCase):
    """Full app + real AuthMiddleware + real route handler."""

    async def asyncSetUp(self):
        self._original_register_key = settings.PLATFORM_REGISTER_KEY
        settings.PLATFORM_REGISTER_KEY = "test-registration-key"

        self.engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        async def override_get_db():
            yield self.db

        app.dependency_overrides[get_db] = override_get_db
        transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async def asyncTearDown(self):
        settings.PLATFORM_REGISTER_KEY = self._original_register_key
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.db.close()
        await self.engine.dispose()

    @patch("app.api.v1.login.TencentSmsService.request_login_code")
    async def test_anonymous_new_phone_reaches_registration_handler(self, mock_send):
        # Case A: anonymous POST /api/v1/register/code -> reaches the
        # handler and returns its real success response, NOT a 401.
        mock_send.return_value = (True, "验证码已发送", {"retry_after": 60})

        res = await self.client.post("/api/v1/register/code", json={"phone": "13800001111"})

        self.assertNotEqual(res.status_code, 401)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body.get("code"), 200)
        mock_send.assert_awaited_once()

    async def test_anonymous_existing_phone_gets_business_error_not_401(self):
        # Existing-phone contract (section 7): business 400 "已注册", never
        # an auth 401 -- and Login.vue only offers a manual "去登录" link
        # for this exact message, it must never auto-switch mode itself.
        self.db.add(
            Tenant(
                tenant_id="tenant-existing",
                name="Existing Shop",
                phone="13900002222",
                password_hash="x",
                status=True,
            )
        )
        await self.db.commit()

        res = await self.client.post("/api/v1/register/code", json={"phone": "13900002222"})

        self.assertNotEqual(res.status_code, 401)
        body = res.json()
        self.assertEqual(body.get("code"), 400)
        self.assertIn("已注册", body.get("msg", ""))

    async def test_registration_closed_returns_403_not_401(self):
        # Section 6 contract: PLATFORM_REGISTER_KEY empty -> business 403
        # "registration closed", strictly distinct from a 401 auth failure.
        settings.PLATFORM_REGISTER_KEY = ""

        res = await self.client.post("/api/v1/register/code", json={"phone": "13800003333"})

        self.assertNotEqual(res.status_code, 401)
        body = res.json()
        self.assertEqual(body.get("code"), 403)
        self.assertIn("暂未开放", body.get("msg", ""))

    async def test_full_register_endpoint_still_public(self):
        # Case B: anonymous POST /api/v1/register is still public. A wrong
        # OTP proves the request reached the handler's own verification
        # logic (business 400), not an auth-layer 401.
        res = await self.client.post(
            "/api/v1/register",
            json={"name": "测试小店", "phone": "13800004444", "code": "000000"},
        )

        self.assertNotEqual(res.status_code, 401)
        body = res.json()
        self.assertEqual(body.get("code"), 400)
        self.assertIn("验证码", body.get("msg", ""))

    async def test_protected_merchant_endpoint_still_401(self):
        # Case C: a real protected merchant endpoint without a token must
        # still be rejected -- proves this fix did not widen AuthMiddleware.
        res = await self.client.get("/api/v1/customers/")

        self.assertEqual(res.status_code, 401)


if __name__ == "__main__":
    unittest.main()
