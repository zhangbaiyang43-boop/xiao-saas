import unittest
from unittest.mock import AsyncMock, patch

from starlette.requests import Request
from starlette.responses import Response

from app.middleware.auth_middleware import AuthMiddleware


def make_request(path: str, token: str | None = "demo-token") -> Request:
    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": headers,
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


async def ok_response(_request: Request) -> Response:
    return Response(status_code=200)


class DemoAuthMiddlewareTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.middleware = AuthMiddleware(app=None)
        self.demo_payload = {
            "sub": "demo-session:123",
            "tenant_id": "demo-tenant",
            "dining_session_id": "123",
            "table_no": "DEMO-01",
            "type": "demo_merchant",
            "scope": "demo_order_fulfillment",
        }

    @patch("app.config.settings.DEMO_TENANT_ID", "demo-tenant")
    @patch("app.middleware.auth_middleware._is_tenant_active", new_callable=AsyncMock)
    @patch("app.middleware.auth_middleware.verify_token")
    async def test_demo_token_reaches_only_demo_api(
        self, mock_verify_token, mock_is_active
    ):
        mock_verify_token.return_value = self.demo_payload
        mock_is_active.return_value = True
        captured = {}

        async def capture(request: Request) -> Response:
            captured["tenant_id"] = request.state.tenant_id
            captured["session_id"] = request.state.demo_session_id
            return Response(status_code=200)

        response = await self.middleware.dispatch(
            make_request("/api/v1/demo/session"), capture
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured, {"tenant_id": "demo-tenant", "session_id": "123"})
        mock_is_active.assert_awaited_once_with("demo-tenant")

    @patch("app.config.settings.DEMO_TENANT_ID", "demo-tenant")
    @patch("app.middleware.auth_middleware._is_tenant_active", new_callable=AsyncMock)
    @patch("app.middleware.auth_middleware.verify_token")
    async def test_demo_token_cannot_reach_formal_orders(
        self, mock_verify_token, mock_is_active
    ):
        mock_verify_token.return_value = self.demo_payload
        mock_is_active.return_value = True

        response = await self.middleware.dispatch(
            make_request("/api/v1/orders"), ok_response
        )

        self.assertEqual(response.status_code, 403)

    @patch("app.config.settings.DEMO_TENANT_ID", "demo-tenant")
    @patch("app.middleware.auth_middleware._is_tenant_active", new_callable=AsyncMock)
    @patch("app.middleware.auth_middleware.verify_token")
    async def test_demo_token_for_wrong_tenant_is_rejected(
        self, mock_verify_token, mock_is_active
    ):
        mock_verify_token.return_value = {**self.demo_payload, "tenant_id": "other"}
        mock_is_active.return_value = True

        response = await self.middleware.dispatch(
            make_request("/api/v1/demo/session"), ok_response
        )

        self.assertEqual(response.status_code, 403)
        mock_is_active.assert_not_awaited()

    async def test_demo_start_route_is_public(self):
        response = await self.middleware.dispatch(
            make_request("/api/v1/demo/sessions/start", token=None), ok_response
        )

        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
