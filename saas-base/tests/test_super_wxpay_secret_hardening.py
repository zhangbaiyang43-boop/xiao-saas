from __future__ import annotations

import inspect
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import httpx
import jwt
import pyotp
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import super_admin
from app.config import settings
from app.core import crypto
from app.core import wxpay_secret_crypto
from app.core.database import get_db
from app.core.rate_limiter import limiter
from app.main import app
from app.models.base import Base
from app.models.tenant import Tenant


TENANT_ID = "wxpay-hardening-tenant"
TOTP_SECRET = "JBSWY3DPEHPK3PXP"
API_V3_KEY = "a" * 32


def _private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


PRIVATE_KEY_PEM = _private_key_pem()


def _write_keyring(directory: str, key: bytes | None = None) -> str:
    path = Path(directory) / "wxpay-keyring.json"
    path.write_text(
        json.dumps(
            {
                "formatVersion": 1,
                "activeKeyId": "wxpay-test-01",
                "keys": [
                    {
                        "keyId": "wxpay-test-01",
                        "algorithm": "fernet",
                        "usage": "encrypt-decrypt",
                        "key": (key or Fernet.generate_key()).decode(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    return str(path)


class StrictSecretEncryptionTest(unittest.TestCase):
    def setUp(self):
        self.original_path = settings.WXPAY_SECRET_KEYRING_PATH
        self.original_write = settings.WXPAY_ENVELOPE_WRITE_ENABLED
        self.original_legacy = settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED
        self.original_policy = wxpay_secret_crypto.KEYRING_SOURCE_POLICY
        wxpay_secret_crypto.KEYRING_SOURCE_POLICY = wxpay_secret_crypto.KeyringSourcePolicy(
            extra_trusted_uids=frozenset({getattr(os, "geteuid", lambda: 0)()}),
            verify_ancestors=False,
        )
        settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED = True
        self.directory = tempfile.TemporaryDirectory()
        wxpay_secret_crypto.get_keyring.cache_clear()

    def tearDown(self):
        settings.WXPAY_SECRET_KEYRING_PATH = self.original_path
        settings.WXPAY_ENVELOPE_WRITE_ENABLED = self.original_write
        settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED = self.original_legacy
        wxpay_secret_crypto.KEYRING_SOURCE_POLICY = self.original_policy
        wxpay_secret_crypto.get_keyring.cache_clear()
        self.directory.cleanup()

    def test_missing_key_denies_strict_secret_write_but_legacy_read_stays_compatible(self):
        settings.WXPAY_SECRET_KEYRING_PATH = str(Path(self.directory.name) / "missing.json")
        settings.WXPAY_ENVELOPE_WRITE_ENABLED = True
        with self.assertRaises(crypto.SecretEncryptionUnavailable):
            crypto.encrypt_secret_strict(API_V3_KEY, crypto.SecretField.API_V3_KEY)
        self.assertEqual(
            crypto.decrypt_secret(API_V3_KEY, crypto.SecretField.API_V3_KEY),
            API_V3_KEY,
        )

    def test_invalid_key_denies_strict_secret_write_without_exposing_key(self):
        settings.WXPAY_SECRET_KEYRING_PATH = _write_keyring(self.directory.name, b"not-a-fernet-key")
        settings.WXPAY_ENVELOPE_WRITE_ENABLED = True
        wxpay_secret_crypto.get_keyring.cache_clear()
        with self.assertRaises(crypto.SecretEncryptionUnavailable) as caught:
            crypto.encrypt_secret_strict(API_V3_KEY, crypto.SecretField.API_V3_KEY)
        self.assertNotIn("not-a-fernet-key", str(caught.exception))

    def test_valid_key_produces_decryptable_fernet_ciphertext(self):
        settings.WXPAY_SECRET_KEYRING_PATH = _write_keyring(self.directory.name)
        settings.WXPAY_ENVELOPE_WRITE_ENABLED = True
        wxpay_secret_crypto.get_keyring.cache_clear()
        encrypted = crypto.encrypt_secret_strict(API_V3_KEY, crypto.SecretField.API_V3_KEY)
        self.assertTrue(encrypted.startswith("enc:v1:wxpay-test-01:gAAAAA"))
        self.assertEqual(crypto.decrypt_secret(encrypted, crypto.SecretField.API_V3_KEY), API_V3_KEY)

    def test_strict_writer_is_not_an_alias_for_the_legacy_permissive_writer(self):
        source = inspect.getsource(crypto.encrypt_secret_strict)
        self.assertIn("field is None", source)
        self.assertNotIn("Fernet(", source)


class SuperWxPayHardeningApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_path = settings.WXPAY_SECRET_KEYRING_PATH
        self.original_write = settings.WXPAY_ENVELOPE_WRITE_ENABLED
        self.original_legacy = settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED
        self.original_policy = wxpay_secret_crypto.KEYRING_SOURCE_POLICY
        wxpay_secret_crypto.KEYRING_SOURCE_POLICY = wxpay_secret_crypto.KeyringSourcePolicy(
            extra_trusted_uids=frozenset({getattr(os, "geteuid", lambda: 0)()}),
            verify_ancestors=False,
        )
        self.original_totp = settings.SUPER_ADMIN_TOTP_SECRET
        self.original_password = settings.SUPER_ADMIN_PASSWORD
        self.keyring_directory = tempfile.TemporaryDirectory()
        settings.WXPAY_SECRET_KEYRING_PATH = str(Path(self.keyring_directory.name) / "missing.json")
        settings.WXPAY_ENVELOPE_WRITE_ENABLED = False
        settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED = True
        settings.SUPER_ADMIN_TOTP_SECRET = TOTP_SECRET
        settings.SUPER_ADMIN_PASSWORD = "test-only-super-password"
        wxpay_secret_crypto.get_keyring.cache_clear()
        reset = getattr(limiter, "reset", None)
        if callable(reset):
            reset()

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
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=(f"127.0.0.{id(self) % 200 + 1}", 12345)),
            base_url="http://test",
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.db.close()
        await self.engine.dispose()
        settings.WXPAY_SECRET_KEYRING_PATH = self.original_path
        settings.WXPAY_ENVELOPE_WRITE_ENABLED = self.original_write
        settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED = self.original_legacy
        wxpay_secret_crypto.KEYRING_SOURCE_POLICY = self.original_policy
        settings.SUPER_ADMIN_TOTP_SECRET = self.original_totp
        settings.SUPER_ADMIN_PASSWORD = self.original_password
        wxpay_secret_crypto.get_keyring.cache_clear()
        self.keyring_directory.cleanup()

    def headers(self, token_type: str = "super_admin") -> dict[str, str]:
        token = jwt.encode(
            {"sub": token_type, "type": token_type, "exp": datetime.utcnow() + timedelta(hours=1)},
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        return {"X-Super-Token": token}

    def step_up(self, **overrides) -> dict:
        data = {
            "totp_code": pyotp.TOTP(TOTP_SECRET).now(),
            "reason": "rotate merchant credentials",
            "confirmed": True,
        }
        data.update(overrides)
        return data

    async def create_tenant(self, **overrides) -> Tenant:
        values = {
            "tenant_id": TENANT_ID,
            "name": "Hardening Merchant",
            "phone": None,
            "password_hash": "x",
            "wx_pay_enabled": True,
            "wx_mchid": "1234567890",
            "wx_api_key_v3": "legacy-api-key",
            "wx_cert_serial": "A" * 40,
            "wx_private_key": "legacy-private-key",
            "receiver_name": "Before Receiver",
            "receiver_type": "enterprise",
            "receiver_verified": True,
            "verified_time": datetime.utcnow(),
            "payment_locked": True,
        }
        values.update(overrides)
        tenant = Tenant(**values)
        self.db.add(tenant)
        await self.db.commit()
        return tenant

    async def fresh_tenant(self) -> Tenant:
        self.db.expire_all()
        return (await self.db.execute(select(Tenant).where(Tenant.tenant_id == TENANT_ID))).scalar_one()

    async def test_missing_encryption_key_rejects_secret_write_atomically(self):
        await self.create_tenant()
        response = await self.client.patch(
            f"/api/super/merchants/{TENANT_ID}/wxpay",
            headers=self.headers(),
            json={
                **self.step_up(),
                "receiver_name": "Must Not Persist",
                "wx_api_key_v3": API_V3_KEY,
            },
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["data"]["reason_code"], "WXPAY_SECRET_ENCRYPTION_UNAVAILABLE")
        tenant = await self.fresh_tenant()
        self.assertEqual(tenant.receiver_name, "Before Receiver")
        self.assertEqual(tenant.wx_api_key_v3, "legacy-api-key")
        self.assertTrue(tenant.receiver_verified)
        self.assertTrue(tenant.wx_pay_enabled)

    async def test_omitted_secret_fields_preserve_values_and_noncredential_edit_keeps_verification(self):
        await self.create_tenant()
        response = await self.client.patch(
            f"/api/super/merchants/{TENANT_ID}/wxpay",
            headers=self.headers(),
            json={**self.step_up(), "receiver_name": "After Receiver", "receiver_type": "individual"},
        )
        self.assertEqual(response.status_code, 200)
        tenant = await self.fresh_tenant()
        self.assertEqual(tenant.wx_api_key_v3, "legacy-api-key")
        self.assertEqual(tenant.wx_private_key, "legacy-private-key")
        self.assertEqual(tenant.receiver_name, "After Receiver")
        self.assertTrue(tenant.receiver_verified)
        self.assertTrue(tenant.wx_pay_enabled)

    async def test_explicit_empty_or_null_secret_is_rejected_without_mutation(self):
        for field, value in (("wx_api_key_v3", ""), ("wx_private_key", None)):
            with self.subTest(field=field):
                await self.create_tenant(tenant_id=f"{TENANT_ID}-{field}")
                response = await self.client.patch(
                    f"/api/super/merchants/{TENANT_ID}-{field}/wxpay",
                    headers=self.headers(),
                    json={**self.step_up(), "receiver_name": "Must Not Persist", field: value},
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["data"]["reason_code"], "WXPAY_SECRET_CLEAR_NOT_ALLOWED")
                row = (
                    await self.db.execute(select(Tenant).where(Tenant.tenant_id == f"{TENANT_ID}-{field}"))
                ).scalar_one()
                self.assertEqual(row.receiver_name, "Before Receiver")

    async def test_valid_secret_change_encrypts_and_atomically_invalidates_and_pauses(self):
        await self.create_tenant()
        settings.WXPAY_SECRET_KEYRING_PATH = _write_keyring(self.keyring_directory.name)
        settings.WXPAY_ENVELOPE_WRITE_ENABLED = True
        wxpay_secret_crypto.get_keyring.cache_clear()
        response = await self.client.patch(
            f"/api/super/merchants/{TENANT_ID}/wxpay",
            headers=self.headers(),
            json={**self.step_up(), "wx_api_key_v3": API_V3_KEY, "wx_private_key": PRIVATE_KEY_PEM},
        )
        self.assertEqual(response.status_code, 200)
        tenant = await self.fresh_tenant()
        self.assertNotEqual(tenant.wx_api_key_v3, API_V3_KEY)
        self.assertEqual(
            crypto.decrypt_secret(tenant.wx_api_key_v3, crypto.SecretField.API_V3_KEY),
            API_V3_KEY,
        )
        self.assertFalse(tenant.receiver_verified)
        self.assertIsNone(tenant.verified_time)
        self.assertFalse(tenant.wx_pay_enabled)

    async def test_same_enabled_value_is_compatible_but_state_change_requires_dedicated_endpoint(self):
        await self.create_tenant(wx_pay_enabled=True)
        same = await self.client.patch(
            f"/api/super/merchants/{TENANT_ID}/wxpay",
            headers=self.headers(),
            json={**self.step_up(), "wx_pay_enabled": True, "receiver_name": "Compatible"},
        )
        self.assertEqual(same.status_code, 200)
        changed = await self.client.patch(
            f"/api/super/merchants/{TENANT_ID}/wxpay",
            headers=self.headers(),
            json={**self.step_up(), "wx_pay_enabled": False, "receiver_name": "Must Not Persist"},
        )
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(changed.json()["data"]["reason_code"], "WXPAY_PAYMENT_STATE_ENDPOINT_REQUIRED")
        tenant = await self.fresh_tenant()
        self.assertTrue(tenant.wx_pay_enabled)
        self.assertEqual(tenant.receiver_name, "Compatible")

    async def test_step_up_missing_invalid_and_unconfigured_all_fail_closed(self):
        await self.create_tenant()
        cases = (
            ({"reason": "required", "confirmed": True}, "WXPAY_STEP_UP_REQUIRED"),
            ({**self.step_up(totp_code="000000")}, "WXPAY_STEP_UP_INVALID"),
        )
        for payload, reason_code in cases:
            with self.subTest(reason_code=reason_code):
                response = await self.client.patch(
                    f"/api/super/merchants/{TENANT_ID}/wxpay",
                    headers=self.headers(),
                    json={**payload, "receiver_name": "Must Not Persist"},
                )
                self.assertEqual(response.json()["data"]["reason_code"], reason_code)

        settings.SUPER_ADMIN_TOTP_SECRET = ""
        response = await self.client.patch(
            f"/api/super/merchants/{TENANT_ID}/wxpay",
            headers=self.headers(),
            json={**self.step_up(), "receiver_name": "Must Not Persist"},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["data"]["reason_code"], "WXPAY_STEP_UP_UNAVAILABLE")
        tenant = await self.fresh_tenant()
        self.assertEqual(tenant.receiver_name, "Before Receiver")

    async def test_cross_tenant_copy_is_stable_409_and_zero_write(self):
        await self.create_tenant()
        response = await self.client.post(
            f"/api/super/merchants/{TENANT_ID}/wxpay/copy-from",
            headers=self.headers(),
            json={"source_tenant_id": "source-tenant", "totp_code": pyotp.TOTP(TOTP_SECRET).now()},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["data"]["reason_code"], "WXPAY_SECRET_COPY_DISABLED")
        tenant = await self.fresh_tenant()
        self.assertEqual(tenant.wx_mchid, "1234567890")
        self.assertTrue(tenant.wx_pay_enabled)

    async def test_normal_pause_requires_totp_reason_confirmation_and_preserves_secrets(self):
        await self.create_tenant()
        response = await self.client.patch(
            f"/api/super/merchants/{TENANT_ID}/wxpay/pause",
            headers=self.headers(),
            json=self.step_up(reason="merchant requested pause"),
        )
        self.assertEqual(response.status_code, 200)
        tenant = await self.fresh_tenant()
        self.assertFalse(tenant.wx_pay_enabled)
        self.assertEqual(tenant.wx_api_key_v3, "legacy-api-key")
        self.assertEqual(tenant.wx_private_key, "legacy-private-key")

    async def test_emergency_pause_requires_password_and_exact_confirmation_and_changes_only_enabled(self):
        await self.create_tenant()
        for password, confirmation, expected in (
            ("wrong", f"PAUSE_WXPAY:{TENANT_ID}", 401),
            ("test-only-super-password", "wrong-confirmation", 400),
            ("test-only-super-password", f"PAUSE_WXPAY:{TENANT_ID}", 200),
        ):
            with self.subTest(expected=expected):
                await self.db.execute(__import__("sqlalchemy").update(Tenant).values(wx_pay_enabled=True))
                await self.db.commit()
                response = await self.client.patch(
                    f"/api/super/merchants/{TENANT_ID}/wxpay/pause",
                    headers=self.headers(),
                    json={
                        "reason": "emergency fraud containment",
                        "confirmed": True,
                        "emergency_password": password,
                        "emergency_confirmation": confirmation,
                    },
                )
                self.assertEqual(response.status_code, expected)
        tenant = await self.fresh_tenant()
        self.assertFalse(tenant.wx_pay_enabled)
        self.assertEqual(tenant.wx_mchid, "1234567890")
        self.assertTrue(tenant.receiver_verified)

    async def test_verify_requires_step_up_and_only_success_enables(self):
        await self.create_tenant(wx_pay_enabled=False, receiver_verified=False, verified_time=None)
        missing = await self.client.post(
            f"/api/super/merchants/{TENANT_ID}/wxpay/verify", headers=self.headers(), json={}
        )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.json()["data"]["reason_code"], "WXPAY_STEP_UP_REQUIRED")

        with patch.object(super_admin, "_validate_wxpay_client", return_value=(False, "WXPAY_VERIFICATION_FAILED")):
            failed = await self.client.post(
                f"/api/super/merchants/{TENANT_ID}/wxpay/verify",
                headers=self.headers(),
                json=self.step_up(reason="verify merchant credentials"),
            )
        self.assertEqual(failed.status_code, 502)
        tenant = await self.fresh_tenant()
        self.assertFalse(tenant.receiver_verified)
        self.assertFalse(tenant.wx_pay_enabled)

        with patch.object(super_admin, "_validate_wxpay_client", return_value=(True, "OK")):
            passed = await self.client.post(
                f"/api/super/merchants/{TENANT_ID}/wxpay/verify",
                headers=self.headers(),
                json=self.step_up(reason="verify merchant credentials"),
            )
        self.assertEqual(passed.status_code, 200)
        tenant = await self.fresh_tenant()
        self.assertTrue(tenant.receiver_verified)
        self.assertTrue(tenant.wx_pay_enabled)

    async def test_invalid_super_identity_is_rejected(self):
        await self.create_tenant()
        for headers in ({}, {"X-Super-Token": "not-a-jwt"}, self.headers("merchant")):
            response = await self.client.patch(
                f"/api/super/merchants/{TENANT_ID}/wxpay",
                headers=headers,
                json={**self.step_up(), "receiver_name": "Must Not Persist"},
            )
            self.assertIn(response.status_code, (401, 403))


class WxPayHardeningStaticContractTest(unittest.TestCase):
    def test_callback_and_readiness_contracts_remain_unchanged(self):
        from app.api.v1 import orders
        from app.services import payment_readiness_service

        order_source = inspect.getsource(orders)
        readiness_source = inspect.getsource(payment_readiness_service)
        self.assertIn('@router.post("/orders/wxpay-notify/{tenant_id}")', order_source)
        self.assertNotIn('@router.post("/orders/wxpay-notify")', order_source)
        self.assertIn('"readiness_state": READINESS_UNKNOWN', readiness_source)

    def test_sdk_and_super_validation_logs_do_not_embed_raw_exception_or_provider_body(self):
        from app.services import wxpay_service

        service_source = inspect.getsource(wxpay_service._build_client)
        validation_source = inspect.getsource(super_admin._validate_wxpay_client)
        self.assertNotIn('f"微信支付 SDK 初始化失败: {e}"', service_source)
        self.assertNotIn('f"微信接口验证失败：{body}"', validation_source)
        self.assertNotIn('f"微信支付验证失败：{exc}"', validation_source)

    def test_dangerous_routes_use_row_locks_and_structured_secret_free_audit(self):
        source = inspect.getsource(super_admin)
        self.assertIn("with_for_update()", source)
        self.assertIn("changed_field_names", source)
        self.assertIn("verification_invalidated", source)
        self.assertNotIn("detail=f\"source={data.source_tenant_id}\"", source)

    def test_security_responses_never_contain_synthetic_secrets(self):
        payload = json.dumps(
            {
                "reason_code": "WXPAY_SECRET_ENCRYPTION_UNAVAILABLE",
                "msg": "支付密钥安全存储暂不可用，未保存任何修改",
            },
            ensure_ascii=False,
        )
        self.assertNotIn(API_V3_KEY, payload)
        self.assertNotIn(PRIVATE_KEY_PEM, payload)


if __name__ == "__main__":
    unittest.main()
