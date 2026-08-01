import asyncio
import unittest
from unittest.mock import patch

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings
from app.models.base import Base
from app.models.tenant import Tenant
from app.middleware.auth_middleware import AuthMiddleware, _is_tenant_active

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


def make_request(path="/api/v1/customers", token="valid-token"):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [(b"authorization", f"Bearer {token}".encode())],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


async def dummy_call_next(request):
    return Response(status_code=200)


class IsTenantActiveTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._original_redis_enabled = settings.REDIS_ENABLED
        settings.REDIS_ENABLED = False  # exercise the DB path directly, no cache involved

        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        async with SessionLocal() as db:
            db.add(Tenant(tenant_id=TENANT_A, name="Test Restaurant", password_hash="x", status=True, is_open=True))
            db.add(Tenant(tenant_id="tenant-banned", name="Banned Restaurant", password_hash="x", status=False, is_open=True))
            await db.commit()

        self._session_patch = patch("app.core.database.AsyncSessionLocal", SessionLocal)
        self._session_patch.start()

    async def asyncTearDown(self):
        self._session_patch.stop()
        settings.REDIS_ENABLED = self._original_redis_enabled
        await self.engine.dispose()

    async def test_active_tenant_is_active(self):
        self.assertTrue(await _is_tenant_active(TENANT_A))

    async def test_disabled_tenant_is_inactive(self):
        self.assertFalse(await _is_tenant_active("tenant-banned"))

    async def test_unknown_tenant_is_inactive(self):
        self.assertFalse(await _is_tenant_active("no-such-tenant"))


class AuthMiddlewareTenantStatusTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.middleware = AuthMiddleware(app=None)

    @patch("app.middleware.auth_middleware._is_tenant_active")
    @patch("app.middleware.auth_middleware.verify_token")
    async def test_disabled_tenant_token_is_rejected_on_a_protected_route(self, mock_verify_token, mock_is_active):
        mock_verify_token.return_value = {"tenant_id": TENANT_A, "type": "merchant", "sub": "1"}
        mock_is_active.return_value = False

        response = await self.middleware.dispatch(make_request(), dummy_call_next)

        self.assertEqual(response.status_code, 403)
        mock_is_active.assert_awaited_once_with(TENANT_A)

    @patch("app.middleware.auth_middleware._is_tenant_active")
    @patch("app.middleware.auth_middleware.verify_token")
    async def test_active_tenant_token_passes_through(self, mock_verify_token, mock_is_active):
        mock_verify_token.return_value = {"tenant_id": TENANT_A, "type": "merchant", "sub": "1"}
        mock_is_active.return_value = True

        response = await self.middleware.dispatch(make_request(), dummy_call_next)

        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
