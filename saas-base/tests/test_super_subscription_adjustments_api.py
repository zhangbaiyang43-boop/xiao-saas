"""Phase 05A HTTP contracts. Authored for CI; not executed in the implementation session."""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta
from uuid import uuid4

import httpx
import jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.core.database import get_db
from app.main import app
from app.models.base import Base
from app.models.billing import BillingPayment
from app.models.subscription import Plan, Subscription
from app.models.subscription_adjustment import SubscriptionAdjustment
from app.models.tenant import Tenant


if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class SuperSubscriptionAdjustmentsApiTest(unittest.IsolatedAsyncioTestCase):
    NOW = datetime.utcnow().replace(microsecond=0)

    async def asyncSetUp(self):
        self.engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        async def override_get_db():
            yield self.db

        app.dependency_overrides[get_db] = override_get_db
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        self.tenant = Tenant(tenant_id="tenant-http-adjust", name="HTTP Merchant", password_hash="x", status=True)
        self.plan = Plan(code="PRO_HTTP", name="HTTP 专业版", is_active=True)
        self.db.add_all([self.tenant, self.plan])
        await self.db.commit()

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.db.close()
        await self.engine.dispose()

    def _headers(self):
        token = jwt.encode(
            {"sub": "phase05a-operator", "type": "super_admin", "exp": datetime.utcnow() + timedelta(hours=1)},
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        return {"X-Super-Token": token}

    async def _subscription(self, *, status="ACTIVE", expiry=None):
        expiry = expiry if expiry is not None else self.NOW + timedelta(days=10)
        row = Subscription(
            tenant_id=self.tenant.tenant_id,
            plan_id=self.plan.id,
            status=status,
            started_at=self.NOW - timedelta(days=2) if status == "ACTIVE" else None,
            ends_at=expiry if status == "ACTIVE" else None,
            trial_started_at=self.NOW - timedelta(days=2) if status == "TRIAL" else None,
            trial_ends_at=expiry if status == "TRIAL" else None,
        )
        self.db.add(row)
        await self.db.commit()
        return row

    def _preview_payload(self, **overrides):
        payload = {
            "operation_type": "ADD_DAYS",
            "days": 7,
            "expires_at": None,
            "adjustment_type": "GIFT",
            "reason": "customer care",
            "note": None,
        }
        payload.update(overrides)
        return payload

    def _path(self, suffix=""):
        return f"/api/super/merchants/{self.tenant.tenant_id}/subscription-adjustments{suffix}"

    async def _preview(self, **overrides):
        return await self.client.post(self._path("/preview"), headers=self._headers(), json=self._preview_payload(**overrides))

    async def test_all_endpoints_require_super_token(self):
        preview = await self.client.post(self._path("/preview"), json=self._preview_payload())
        commit = await self.client.post(self._path(), json={})
        history = await self.client.get(self._path())
        self.assertEqual(preview.status_code, 401)
        self.assertEqual(preview.json()["code"], 401)
        self.assertEqual(preview.json()["data"]["error_code"], "UNAUTHORIZED")
        self.assertNotEqual(commit.status_code, 200)
        self.assertNotEqual(history.status_code, 200)

    async def test_valid_non_super_token_returns_structured_forbidden(self):
        token = jwt.encode(
            {"sub": "tenant-user", "type": "tenant", "exp": datetime.utcnow() + timedelta(hours=1)},
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        response = await self.client.post(
            self._path("/preview"),
            headers={"X-Super-Token": token},
            json=self._preview_payload(),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], 403)
        self.assertEqual(response.json()["data"]["error_code"], "FORBIDDEN")

    async def test_preview_is_read_only_and_serializes_bigint_id_as_string(self):
        row = await self._subscription()
        response = await self._preview()
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["code"], 200)
        self.assertEqual(body["data"]["subscription_id"], str(row.id))
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(SubscriptionAdjustment)), 0)

    async def test_commit_is_atomic_and_does_not_create_payment(self):
        row = await self._subscription()
        preview = (await self._preview()).json()["data"]
        payload = {
            **self._preview_payload(),
            "expected_subscription_id": preview["subscription_id"],
            "expected_before_expiry": preview["before_expiry"],
            "idempotency_key": str(uuid4()),
        }
        response = await self.client.post(self._path(), headers=self._headers(), json=payload)
        await self.db.refresh(row)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json()["data"]["adjustment_id"], str)
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(SubscriptionAdjustment)), 1)
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(BillingPayment)), 0)

    async def test_stale_guard_returns_http_409_with_machine_code(self):
        await self._subscription()
        preview = (await self._preview()).json()["data"]
        payload = {
            **self._preview_payload(),
            "expected_subscription_id": "1",
            "expected_before_expiry": preview["before_expiry"],
            "idempotency_key": str(uuid4()),
        }
        response = await self.client.post(self._path(), headers=self._headers(), json=payload)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["data"]["error_code"], "STALE_SUBSCRIPTION")

    async def test_same_idempotency_key_replays_and_conflicting_payload_is_409(self):
        await self._subscription()
        preview = (await self._preview()).json()["data"]
        key = str(uuid4())
        payload = {
            **self._preview_payload(),
            "expected_subscription_id": preview["subscription_id"],
            "expected_before_expiry": preview["before_expiry"],
            "idempotency_key": key,
        }
        first = await self.client.post(self._path(), headers=self._headers(), json=payload)
        replay = await self.client.post(self._path(), headers=self._headers(), json=payload)
        conflict = await self.client.post(self._path(), headers=self._headers(), json={**payload, "days": 8})
        self.assertEqual(replay.json()["data"]["adjustment_id"], first.json()["data"]["adjustment_id"])
        self.assertTrue(replay.json()["data"]["idempotent_replay"])
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["data"]["error_code"], "DUPLICATE_REQUEST")

    async def test_client_cannot_submit_after_expiry(self):
        await self._subscription()
        response = await self._preview(after_expiry="2099-01-01T00:00:00Z")
        self.assertEqual(response.status_code, 422)

    async def test_history_is_capped_and_contains_audit_evidence(self):
        await self._subscription()
        preview = (await self._preview()).json()["data"]
        payload = {
            **self._preview_payload(),
            "expected_subscription_id": preview["subscription_id"],
            "expected_before_expiry": preview["before_expiry"],
            "idempotency_key": str(uuid4()),
        }
        await self.client.post(self._path(), headers={**self._headers(), "X-Forwarded-For": "203.0.113.8"}, json=payload)
        response = await self.client.get(self._path(), headers=self._headers(), params={"limit": 20})
        invalid = await self.client.get(self._path(), headers=self._headers(), params={"limit": 21})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"][0]["operator_ip"], "203.0.113.8")
        self.assertEqual(response.json()["data"][0]["plan"]["plan_name"], "HTTP 专业版")
        self.assertEqual(invalid.status_code, 422)

    async def test_merchant_detail_exposes_natural_recovery_context(self):
        row = await self._subscription(expiry=self.NOW - timedelta(days=1))
        response = await self.client.get(
            f"/api/super/merchants/{self.tenant.tenant_id}",
            headers=self._headers(),
        )
        context = response.json()["data"]["subscription_adjustment"]
        self.assertTrue(context["adjustable"])
        self.assertTrue(context["natural_expiry_recovery"])
        self.assertEqual(context["subscription_id"], str(row.id))
        self.assertEqual(context["subscription_status"], "EXPIRED")


if __name__ == "__main__":
    unittest.main()
