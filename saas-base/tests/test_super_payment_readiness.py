import json
import inspect
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import jwt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1 import super_admin
from app.config import settings
from app.core.database import get_db
from app.main import app
from app.models.base import Base
from app.models.tenant import Tenant


TENANT_ID = "payment-readiness-tenant"


def _private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def _public_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def _valid_fixture(*, public_key_mode: bool = False):
    encryption_key = Fernet.generate_key().decode()
    fernet = Fernet(encryption_key.encode())
    tenant = SimpleNamespace(
        tenant_id=TENANT_ID,
        payment_mode="prepay",
        wx_pay_enabled=True,
        wx_mchid="1234567890",
        wx_api_key_v3=fernet.encrypt(b"a" * 32).decode(),
        wx_cert_serial="A" * 40,
        wx_private_key=fernet.encrypt(_private_key_pem().encode()).decode(),
        wx_public_key_id="PUB_KEY_ID_" + "B" * 40 if public_key_mode else None,
        wx_public_key=_public_key_pem() if public_key_mode else None,
        wx_verify_mode="public_key",
        receiver_verified=True,
        verified_time=datetime.utcnow(),
    )
    global_config = SimpleNamespace(
        WECHAT_APP_ID="wx1234567890abcdef",
        WECHAT_APP_SECRET="app-secret-present",
        H5_ORDER_BASE_URL="https://saas.example.com",
        SECRET_ENCRYPTION_KEY=encryption_key,
    )
    return tenant, global_config


class PaymentReadinessEvaluatorTest(unittest.TestCase):
    def evaluate(self, tenant=None, global_config=None):
        from app.services.payment_readiness_service import evaluate_payment_readiness

        if tenant is None or global_config is None:
            tenant, global_config = _valid_fixture()
        return evaluate_payment_readiness(tenant, global_config)

    def item(self, result, code):
        return next(item for item in result["online_payment"]["checklist"] if item["code"] == code)

    def test_disabled_is_not_reported_as_broken_online_payment(self):
        tenant, config = _valid_fixture()
        tenant.wx_pay_enabled = False
        result = self.evaluate(tenant, config)
        self.assertEqual(result["online_payment"]["readiness_state"], "DISABLED")
        self.assertEqual(self.item(result, "WX_MCHID")["status"], "NOT_APPLICABLE")

    def test_missing_blocking_fields_return_incomplete(self):
        cases = (
            ("wx_mchid", "WX_MCHID"),
            ("wx_api_key_v3", "WX_API_KEY_V3"),
            ("wx_private_key", "WX_PRIVATE_KEY"),
        )
        for attribute, code in cases:
            with self.subTest(attribute=attribute):
                tenant, config = _valid_fixture()
                setattr(tenant, attribute, None)
                result = self.evaluate(tenant, config)
                self.assertEqual(result["online_payment"]["readiness_state"], "INCOMPLETE")
                self.assertEqual(self.item(result, code)["status"], "MISSING")

    def test_valid_platform_certificate_configuration_is_static_unknown(self):
        result = self.evaluate()
        online = result["online_payment"]
        self.assertEqual(online["effective_verify_mode"], "platform_certificate")
        self.assertEqual(online["validation_level"], "STATIC_VALID")
        self.assertEqual(online["readiness_state"], "UNKNOWN")
        self.assertIsNone(online["validation_evidence_time"])

    def test_valid_public_key_configuration_is_static_unknown(self):
        tenant, config = _valid_fixture(public_key_mode=True)
        result = self.evaluate(tenant, config)
        self.assertEqual(result["online_payment"]["effective_verify_mode"], "public_key")
        self.assertEqual(result["online_payment"]["readiness_state"], "UNKNOWN")

    def test_partial_public_key_pair_is_invalid(self):
        tenant, config = _valid_fixture(public_key_mode=True)
        tenant.wx_public_key = None
        result = self.evaluate(tenant, config)
        self.assertEqual(result["online_payment"]["effective_verify_mode"], "invalid")
        self.assertEqual(result["online_payment"]["readiness_state"], "INVALID")
        self.assertEqual(self.item(result, "WX_PUBLIC_KEY")["status"], "INVALID")

    def test_missing_and_invalid_precedence_is_incomplete_with_both_reasons(self):
        tenant, config = _valid_fixture()
        tenant.wx_mchid = None
        config.H5_ORDER_BASE_URL = "http://unsafe.example.com"
        result = self.evaluate(tenant, config)
        online = result["online_payment"]
        self.assertEqual(online["readiness_state"], "INCOMPLETE")
        self.assertIn("WX_MCHID_MISSING", online["missing_reasons"])
        self.assertIn("CALLBACK_URL_INVALID", online["invalid_reasons"])

    def test_global_dependencies_are_blocking(self):
        cases = (
            ("WECHAT_APP_ID", "GLOBAL_APP_ID"),
            ("WECHAT_APP_SECRET", "GLOBAL_APP_SECRET"),
            ("H5_ORDER_BASE_URL", "GLOBAL_CALLBACK_URL"),
            ("SECRET_ENCRYPTION_KEY", "GLOBAL_SECRET_ENCRYPTION"),
        )
        for attribute, code in cases:
            with self.subTest(attribute=attribute):
                tenant, config = _valid_fixture()
                setattr(config, attribute, "")
                result = self.evaluate(tenant, config)
                self.assertEqual(result["online_payment"]["readiness_state"], "INCOMPLETE")
                self.assertEqual(self.item(result, code)["status"], "MISSING")

    def test_invalid_https_url_is_rejected_locally(self):
        for invalid_url in (
            "http://saas.example.com",
            "https://saas.example.com/base?token=unsafe",
            "https://saas.example.com/base#fragment",
        ):
            with self.subTest(invalid_url=invalid_url):
                tenant, config = _valid_fixture()
                config.H5_ORDER_BASE_URL = invalid_url
                result = self.evaluate(tenant, config)
                self.assertEqual(result["online_payment"]["readiness_state"], "INVALID")
                self.assertEqual(self.item(result, "GLOBAL_CALLBACK_URL")["status"], "INVALID")

    def test_legacy_app_id_fallback_matches_customer_payment_runtime(self):
        tenant, config = _valid_fixture()
        config.WECHAT_APP_ID = ""
        config.WECHAT_APP_ = "wx1234567890abcdef"
        result = self.evaluate(tenant, config)
        self.assertEqual(self.item(result, "GLOBAL_APP_ID")["status"], "CONFIGURED")
        self.assertEqual(result["online_payment"]["readiness_state"], "UNKNOWN")

    def test_plaintext_compatibility_fallback_is_not_accepted(self):
        tenant, config = _valid_fixture()
        tenant.wx_api_key_v3 = "p" * 32
        tenant.wx_private_key = _private_key_pem()
        result = self.evaluate(tenant, config)
        self.assertEqual(result["online_payment"]["readiness_state"], "INVALID")
        self.assertEqual(self.item(result, "WX_API_KEY_V3")["reason_code"], "SECRET_DECRYPT_FAILED")
        self.assertEqual(self.item(result, "WX_PRIVATE_KEY")["reason_code"], "SECRET_DECRYPT_FAILED")

    def test_receiver_verified_never_creates_ready_evidence(self):
        tenant, config = _valid_fixture()
        tenant.receiver_verified = True
        tenant.verified_time = datetime.utcnow()
        result = self.evaluate(tenant, config)
        self.assertEqual(result["online_payment"]["readiness_state"], "UNKNOWN")
        self.assertIsNone(result["online_payment"]["validation_evidence_time"])

    def test_payment_timing_labels_offline_availability_and_mask(self):
        expected = {
            "prepay": ("先付款后出单", False),
            "postpay": ("餐后线下付款", True),
            "table_account": ("桌台累计统一结账", True),
        }
        for mode, (label, offline) in expected.items():
            with self.subTest(mode=mode):
                tenant, config = _valid_fixture()
                tenant.payment_mode = mode
                result = self.evaluate(tenant, config)
                self.assertEqual(result["payment_timing"]["label"], label)
                self.assertEqual(result["payment_timing"]["offline_collection_available"], offline)
                self.assertEqual(result["online_payment"]["masked_identifiers"]["wx_mchid"], "123****890")

    def test_verify_mode_drift_is_non_blocking(self):
        tenant, config = _valid_fixture()
        tenant.wx_verify_mode = "public_key"
        result = self.evaluate(tenant, config)
        mode_item = self.item(result, "WX_VERIFY_MODE")
        self.assertFalse(mode_item["blocking"])
        self.assertEqual(mode_item["status"], "UNKNOWN")
        self.assertEqual(result["online_payment"]["readiness_state"], "UNKNOWN")

    def test_secret_values_never_appear_in_response_or_logs(self):
        tenant, config = _valid_fixture(public_key_mode=True)
        result = self.evaluate(tenant, config)
        payload = json.dumps(result, ensure_ascii=False)
        for secret in (
            tenant.wx_api_key_v3,
            tenant.wx_private_key,
            tenant.wx_public_key,
            config.WECHAT_APP_SECRET,
            config.SECRET_ENCRYPTION_KEY,
        ):
            self.assertNotIn(secret, payload)

    def test_unexpected_checker_error_fails_closed_unknown(self):
        tenant, config = _valid_fixture()
        with patch(
            "app.services.payment_readiness_service._evaluate_payment_readiness",
            side_effect=RuntimeError("secret-bearing unexpected error"),
        ):
            result = self.evaluate(tenant, config)
        self.assertEqual(result["online_payment"]["readiness_state"], "UNKNOWN")
        self.assertNotIn("secret-bearing", json.dumps(result))

    def test_evaluator_has_no_remote_wxpay_or_secret_logging_path(self):
        from app.services import payment_readiness_service

        source = inspect.getsource(payment_readiness_service)
        self.assertNotIn("from app.services.wxpay_service", source)
        self.assertNotIn("import requests", source)
        self.assertNotIn("import httpx", source)
        self.assertNotIn("logger.", source)
        self.assertNotIn("logging.", source)


class SuperPaymentReadinessApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        async def override_get_db():
            yield self.db

        app.dependency_overrides[get_db] = override_get_db
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.db.close()
        await self.engine.dispose()

    @staticmethod
    def token(token_type: str) -> str:
        return jwt.encode(
            {"sub": token_type, "type": token_type, "exp": datetime.utcnow() + timedelta(hours=1)},
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

    async def create_tenant(self, tenant_id: str) -> Tenant:
        tenant = Tenant(
            tenant_id=tenant_id,
            name=f"Merchant {tenant_id}",
            phone=None,
            password_hash="x",
            payment_mode="postpay",
            wx_pay_enabled=False,
        )
        self.db.add(tenant)
        await self.db.commit()
        return tenant

    async def test_auth_contract_is_401_for_missing_invalid_and_403_for_wrong_type(self):
        path = f"/api/super/merchants/{TENANT_ID}/payment-readiness"
        for headers in ({}, {"X-Super-Token": "not-a-jwt"}):
            response = await self.client.get(path, headers=headers)
            self.assertEqual(response.status_code, 401)
        response = await self.client.get(path, headers={"X-Super-Token": self.token("merchant")})
        self.assertEqual(response.status_code, 403)

    async def test_tenant_scope_unknown_tenant_and_read_only_behavior(self):
        await self.create_tenant("tenant-a")
        await self.create_tenant("tenant-b")
        headers = {"X-Super-Token": self.token("super_admin")}
        response = await self.client.get("/api/super/merchants/tenant-b/payment-readiness", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["tenant_id"], "tenant-b")
        self.assertEqual(response.json()["data"]["online_payment"]["readiness_state"], "DISABLED")

        missing = await self.client.get("/api/super/merchants/not-found/payment-readiness", headers=headers)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["code"], 404)

        rows = list((await self.db.execute(__import__("sqlalchemy").select(Tenant))).scalars().all())
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(not row.receiver_verified for row in rows))
        self.assertTrue(all(row.verified_time is None for row in rows))

    async def test_database_failure_is_not_disguised_as_unknown(self):
        class BrokenDb:
            async def execute(self, _statement):
                raise RuntimeError("database unavailable")

        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            await super_admin.get_merchant_payment_readiness(TENANT_ID, db=BrokenDb())

    def test_route_is_single_tenant_select_without_write_operations(self):
        source = inspect.getsource(super_admin.get_merchant_payment_readiness)
        self.assertEqual(source.count("select(Tenant)"), 1)
        for write_call in ("db.add(", "db.delete(", "db.flush(", "db.commit("):
            self.assertNotIn(write_call, source)


if __name__ == "__main__":
    unittest.main()
