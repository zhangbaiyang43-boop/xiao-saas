import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.v1.demo import DemoSessionService
from app.config import settings
from app.core.database import get_db
from app.core.security import create_demo_session_token
from app.main import app
from app.services.demo_session_service import DemoOrderNotFoundError, DemoPoolFullError


class DemoApiTest(unittest.TestCase):
    def setUp(self):
        async def override_get_db():
            yield object()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.settings_patch = patch.object(
            settings, "DEMO_TENANT_ID", "demo-tenant"
        )
        self.settings_patch.start()
        self.active_patch = patch(
            "app.middleware.auth_middleware._is_tenant_active",
            new=AsyncMock(return_value=True),
        )
        self.active_patch.start()
        self.demo_token = create_demo_session_token(
            tenant_id="demo-tenant",
            dining_session_id="123",
            table_no="DEMO-01",
        )

    def tearDown(self):
        self.active_patch.stop()
        self.settings_patch.stop()
        app.dependency_overrides.clear()

    @staticmethod
    def start_payload():
        return {
            "demoToken": "demo-token",
            "expiresAt": "2099-01-01T00:00:00",
            "diningSessionId": "123",
            "tableNo": "DEMO-01",
            "customerCodeImageUrl": "/static/demo-01.png",
            "shopName": "开心点单体验店",
        }

    def auth_headers(self):
        return {"Authorization": f"Bearer {self.demo_token}"}

    @patch.object(DemoSessionService, "start_session", new_callable=AsyncMock)
    def test_start_returns_respvo_and_camel_case_data(self, mock_start):
        mock_start.return_value = self.start_payload()

        response = self.client.post(
            "/api/v1/demo/sessions/start", json={"launchCode": "launch-code"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 200)
        self.assertEqual(
            set(response.json()["data"]),
            {
                "demoToken",
                "expiresAt",
                "diningSessionId",
                "tableNo",
                "customerCodeImageUrl",
                "shopName",
            },
        )

    @patch.object(DemoSessionService, "start_session", new_callable=AsyncMock)
    def test_pool_full_returns_http_429_and_respvo(self, mock_start):
        mock_start.side_effect = DemoPoolFullError("full")

        response = self.client.post(
            "/api/v1/demo/sessions/start", json={"launchCode": "launch-code"}
        )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["code"], 429)
        self.assertEqual(response.json()["data"], None)

    def test_demo_snapshot_requires_demo_token(self):
        response = self.client.get("/api/v1/demo/session")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], 401)

    @patch.object(DemoSessionService, "update_order_status", new_callable=AsyncMock)
    def test_cross_session_action_returns_404(self, mock_update):
        mock_update.side_effect = DemoOrderNotFoundError("missing")

        response = self.client.patch(
            "/api/v1/demo/orders/999/status",
            headers=self.auth_headers(),
            json={"status": "preparing"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], 404)


if __name__ == "__main__":
    unittest.main()
