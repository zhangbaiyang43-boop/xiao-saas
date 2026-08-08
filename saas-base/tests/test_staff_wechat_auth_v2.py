"""Staff WeChat bind + trusted device Authentication V2 tests."""

from __future__ import annotations

import asyncio
import unittest

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.permissions import permission_list
from app.core.security import verify_token
from app.models.base import Base
from app.models.merchant_account import MerchantAccount
from app.models.merchant_account_trusted_device import MerchantAccountTrustedDevice  # noqa: F401
from app.models.merchant_account_wechat_binding import MerchantAccountWechatBinding  # noqa: F401
from app.models.tenant import Tenant
from app.services import staff_bind_token_service as bind_tokens
from app.services.merchant_account_service import MerchantAccountService
from app.services.staff_trusted_device_service import (
    StaffTrustedDeviceService,
    decode_device_credential,
)
from app.services.staff_wechat_auth_service import StaffWechatAuthService
from app.services.staff_wechat_provider import MockWechatIdentityProvider, WechatIdentity
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-wx-a"
TENANT_B = "tenant-wx-b"
# Avoid passlib/bcrypt local env issues (same pattern as security_gate tests).
FAKE_PW = "test-password-hash-not-used-for-verify"


class StaffWechatAuthV2Test(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        bind_tokens._MEMORY.clear()
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

        self.waiter_id = generate_snowflake_id()
        self.kitchen_id = generate_snowflake_id()
        self.waiter_b_id = generate_snowflake_id()

        async with self.SessionLocal() as db:
            db.add_all(
                [
                    Tenant(
                        tenant_id=TENANT_A,
                        name="老王川菜馆",
                        password_hash="x",
                        phone="13800001111",
                        status=True,
                        is_open=True,
                    ),
                    Tenant(
                        tenant_id=TENANT_B,
                        name="老李烧烤",
                        password_hash="x",
                        phone="13800002222",
                        status=True,
                        is_open=True,
                    ),
                    MerchantAccount(
                        id=self.waiter_id,
                        tenant_id=TENANT_A,
                        name="张白杨",
                        username=None,
                        password_hash=None,
                        role="waiter",
                        status="active",
                    ),
                    MerchantAccount(
                        id=self.kitchen_id,
                        tenant_id=TENANT_A,
                        name="小李",
                        username="kitchen1",
                        password_hash=FAKE_PW,
                        role="kitchen",
                        status="active",
                    ),
                    MerchantAccount(
                        id=self.waiter_b_id,
                        tenant_id=TENANT_B,
                        name="张白杨",
                        username=None,
                        password_hash=None,
                        role="kitchen",
                        status="active",
                    ),
                ]
            )
            await db.commit()

    async def test_bind_token_single_use_and_regenerate(self):
        t1 = await bind_tokens.create_bind_token(
            tenant_id=TENANT_A, account_id=self.waiter_id, created_by_owner=TENANT_A
        )
        raw1 = t1["binding_url"].split("t=")[1]
        self.assertIsNotNone(await bind_tokens.peek_bind_token(raw1))

        t2 = await bind_tokens.create_bind_token(
            tenant_id=TENANT_A, account_id=self.waiter_id, created_by_owner=TENANT_A
        )
        raw2 = t2["binding_url"].split("t=")[1]
        self.assertIsNone(await bind_tokens.peek_bind_token(raw1))
        self.assertIsNotNone(await bind_tokens.peek_bind_token(raw2))

        consumed = await bind_tokens.consume_bind_token(raw2)
        self.assertEqual(int(consumed["account_id"]), self.waiter_id)
        self.assertIsNone(await bind_tokens.consume_bind_token(raw2))
        self.assertEqual(await bind_tokens.get_bind_status_for_account(self.waiter_id), "bound")

    async def test_oauth_state_single_use(self):
        state = await bind_tokens.create_oauth_state({"purpose": "bind", "bind_token": "x"})
        data = await bind_tokens.consume_oauth_state(state)
        self.assertEqual(data["purpose"], "bind")
        self.assertIsNone(await bind_tokens.consume_oauth_state(state))

    async def test_wechat_bind_and_device_refresh_rotation(self):
        async with self.SessionLocal() as db:
            svc = StaffWechatAuthService(db)
            token_data = await bind_tokens.create_bind_token(
                tenant_id=TENANT_A, account_id=self.waiter_id, created_by_owner=TENANT_A
            )
            raw = token_data["binding_url"].split("t=")[1]
            identity = WechatIdentity(app_id="mock_staff_app", openid="openid_waiter_a")
            result = await svc.confirm_bind(bind_token=raw, identity=identity, user_agent="MicroMessenger iPhone")
            self.assertTrue(result["ok"])
            self.assertEqual(result["role"], "waiter")
            self.assertIn("account_id", result)
            self.assertNotIn("openid", result)
            payload = verify_token(result["token"])
            self.assertEqual(payload["account_id"], self.waiter_id)
            self.assertEqual(payload["role"], "waiter")
            self.assertNotEqual(payload.get("role"), "owner")

            cred = result["device_credential"]
            device_id, secret_a = decode_device_credential(cred)
            refresh = await svc.refresh_device(device_id=device_id, secret=secret_a)
            self.assertTrue(refresh["ok"])
            _, secret_b = decode_device_credential(refresh["device_credential"])
            self.assertNotEqual(secret_a, secret_b)

            # Old secret must fail after rotation.
            again = await svc.refresh_device(device_id=device_id, secret=secret_a)
            self.assertFalse(again["ok"])

            ok = await svc.refresh_device(device_id=device_id, secret=secret_b)
            self.assertTrue(ok["ok"])

    async def test_already_bound_blocks_other_wechat(self):
        async with self.SessionLocal() as db:
            svc = StaffWechatAuthService(db)
            t1 = await bind_tokens.create_bind_token(
                tenant_id=TENANT_A, account_id=self.waiter_id, created_by_owner=TENANT_A
            )
            await svc.confirm_bind(
                bind_token=t1["binding_url"].split("t=")[1],
                identity=WechatIdentity(app_id="mock_staff_app", openid="wx_a"),
            )
            t2 = await bind_tokens.create_bind_token(
                tenant_id=TENANT_A, account_id=self.waiter_id, created_by_owner=TENANT_A
            )
            # Bound account should refuse new token generation path at preview/confirm.
            preview = await svc.preview_bind(bind_token=t2["binding_url"].split("t=")[1])
            self.assertFalse(preview["ok"])
            self.assertEqual(preview["code"], "already_bound")

    async def test_idempotent_same_openid_rebind(self):
        async with self.SessionLocal() as db:
            svc = StaffWechatAuthService(db)
            identity = WechatIdentity(app_id="mock_staff_app", openid="same_openid")
            t1 = await bind_tokens.create_bind_token(
                tenant_id=TENANT_A, account_id=self.waiter_id, created_by_owner=TENANT_A
            )
            r1 = await svc.confirm_bind(bind_token=t1["binding_url"].split("t=")[1], identity=identity)
            self.assertTrue(r1["ok"])
            # Unbind then rebind same openid.
            await svc.unbind_wechat(tenant_id=TENANT_A, account_id=self.waiter_id)
            t2 = await bind_tokens.create_bind_token(
                tenant_id=TENANT_A, account_id=self.waiter_id, created_by_owner=TENANT_A
            )
            r2 = await svc.confirm_bind(bind_token=t2["binding_url"].split("t=")[1], identity=identity)
            self.assertTrue(r2["ok"])

    async def test_disabled_blocks_device_and_wechat_login(self):
        async with self.SessionLocal() as db:
            svc = StaffWechatAuthService(db)
            t = await bind_tokens.create_bind_token(
                tenant_id=TENANT_A, account_id=self.waiter_id, created_by_owner=TENANT_A
            )
            bound = await svc.confirm_bind(
                bind_token=t["binding_url"].split("t=")[1],
                identity=WechatIdentity(app_id="mock_staff_app", openid="openid_dis"),
            )
            device_id, secret = decode_device_credential(bound["device_credential"])

            await MerchantAccountService(db).update_account(
                tenant_id=TENANT_A, account_id=self.waiter_id, status="disabled"
            )
            refresh = await svc.refresh_device(device_id=device_id, secret=secret)
            self.assertFalse(refresh["ok"])

            login = await svc.login_with_identity(
                identity=WechatIdentity(app_id="mock_staff_app", openid="openid_dis")
            )
            self.assertFalse(login["ok"])

    async def test_role_change_reflected_on_refresh(self):
        async with self.SessionLocal() as db:
            svc = StaffWechatAuthService(db)
            t = await bind_tokens.create_bind_token(
                tenant_id=TENANT_A, account_id=self.waiter_id, created_by_owner=TENANT_A
            )
            bound = await svc.confirm_bind(
                bind_token=t["binding_url"].split("t=")[1],
                identity=WechatIdentity(app_id="mock_staff_app", openid="openid_role"),
            )
            device_id, secret = decode_device_credential(bound["device_credential"])
            await MerchantAccountService(db).update_account(
                tenant_id=TENANT_A, account_id=self.waiter_id, role="kitchen"
            )
            # After disable-path revoke on status? role-only update keeps devices.
            # But update with role only — devices remain.
            # Rotation may have happened — use latest secret from first refresh after role change.
            # First refresh after role change:
            # Device was created; secret still valid unless revoke_all on disable only.
            refresh = await svc.refresh_device(device_id=device_id, secret=secret)
            self.assertTrue(refresh["ok"])
            self.assertEqual(refresh["role"], "kitchen")
            self.assertNotIn("pickup.assign", refresh["permissions"])
            token = verify_token(refresh["token"])
            self.assertEqual(token["role"], "kitchen")

    async def test_unbind_revokes_devices(self):
        async with self.SessionLocal() as db:
            svc = StaffWechatAuthService(db)
            t = await bind_tokens.create_bind_token(
                tenant_id=TENANT_A, account_id=self.waiter_id, created_by_owner=TENANT_A
            )
            bound = await svc.confirm_bind(
                bind_token=t["binding_url"].split("t=")[1],
                identity=WechatIdentity(app_id="mock_staff_app", openid="openid_unbind"),
            )
            device_id, secret = decode_device_credential(bound["device_credential"])
            await svc.unbind_wechat(tenant_id=TENANT_A, account_id=self.waiter_id)
            refresh = await svc.refresh_device(device_id=device_id, secret=secret)
            self.assertFalse(refresh["ok"])

    async def test_revoke_all_keeps_wechat_binding(self):
        async with self.SessionLocal() as db:
            svc = StaffWechatAuthService(db)
            devices = StaffTrustedDeviceService(db)
            t = await bind_tokens.create_bind_token(
                tenant_id=TENANT_A, account_id=self.waiter_id, created_by_owner=TENANT_A
            )
            bound = await svc.confirm_bind(
                bind_token=t["binding_url"].split("t=")[1],
                identity=WechatIdentity(app_id="mock_staff_app", openid="openid_rev"),
            )
            device_id, secret = decode_device_credential(bound["device_credential"])
            await devices.revoke_all(tenant_id=TENANT_A, account_id=self.waiter_id)
            self.assertTrue(await svc.is_wechat_bound(tenant_id=TENANT_A, account_id=self.waiter_id))
            refresh = await svc.refresh_device(device_id=device_id, secret=secret)
            self.assertFalse(refresh["ok"])
            login = await svc.login_with_identity(
                identity=WechatIdentity(app_id="mock_staff_app", openid="openid_rev")
            )
            self.assertTrue(login["ok"])

    async def test_multiple_accounts_not_auto_picked(self):
        async with self.SessionLocal() as db:
            svc = StaffWechatAuthService(db)
            identity = WechatIdentity(app_id="mock_staff_app", openid="shared_openid")
            for aid in (self.waiter_id, self.waiter_b_id):
                tenant = TENANT_A if aid == self.waiter_id else TENANT_B
                t = await bind_tokens.create_bind_token(
                    tenant_id=tenant, account_id=aid, created_by_owner=tenant
                )
                r = await svc.confirm_bind(bind_token=t["binding_url"].split("t=")[1], identity=identity)
                self.assertTrue(r["ok"])

            login = await svc.login_with_identity(identity=identity)
            self.assertFalse(login["ok"])
            self.assertEqual(login["code"], "multiple_accounts")
            self.assertEqual(len(login["accounts"]), 2)

            chosen = await svc.login_with_identity(identity=identity, account_id=self.waiter_b_id)
            self.assertTrue(chosen["ok"])
            self.assertEqual(chosen["tenant_id"], TENANT_B)

    async def test_password_login_null_hash_fails_softly(self):
        async with self.SessionLocal() as db:
            missing, err_missing = await MerchantAccountService(db).authenticate(
                tenant_id=TENANT_A, username="zhang", password="password12"
            )
            self.assertIsNone(missing)
            self.assertEqual(err_missing, "账号或密码错误")

            kitchen = await db.get(MerchantAccount, self.kitchen_id)
            kitchen.password_hash = None
            await db.commit()
            no_pw, err_pw = await MerchantAccountService(db).authenticate(
                tenant_id=TENANT_A, username="kitchen1", password="password12"
            )
            self.assertIsNone(no_pw)
            self.assertEqual(err_pw, "账号或密码错误")

    async def test_create_staff_without_password(self):
        async with self.SessionLocal() as db:
            res = await MerchantAccountService(db).create_account(
                tenant_id=TENANT_A, name="新员工", role="waiter"
            )
            self.assertEqual(res.code, 200)
            self.assertIsNone(res.data["username"])
            self.assertFalse(res.data["has_password"])
            self.assertFalse(res.data["wechat_bound"])

    async def test_cross_tenant_bind_token_cannot_hijack(self):
        async with self.SessionLocal() as db:
            svc = StaffWechatAuthService(db)
            # Token for A waiter
            t = await bind_tokens.create_bind_token(
                tenant_id=TENANT_A, account_id=self.waiter_id, created_by_owner=TENANT_A
            )
            raw = t["binding_url"].split("t=")[1]
            peek = await bind_tokens.peek_bind_token(raw)
            self.assertEqual(peek["tenant_id"], TENANT_A)
            # Confirm still binds only that account (tenant from token payload).
            result = await svc.confirm_bind(
                bind_token=raw,
                identity=WechatIdentity(app_id="mock_staff_app", openid="x"),
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["tenant_id"], TENANT_A)

    async def test_mock_provider_exchange(self):
        provider = MockWechatIdentityProvider(app_id="mock_staff_app")
        ident = await provider.exchange_code("mock:abc:union1")
        self.assertEqual(ident.openid, "abc")
        self.assertEqual(ident.unionid, "union1")

    async def test_secret_not_stored_plaintext(self):
        async with self.SessionLocal() as db:
            devices = StaffTrustedDeviceService(db)
            row, secret = await devices.create_device(
                tenant_id=TENANT_A, account_id=self.waiter_id, user_agent="Android"
            )
            self.assertNotEqual(row.device_secret_hash, secret)
            self.assertNotIn(secret, row.device_secret_hash)

    async def test_wechat_cannot_set_owner_role(self):
        async with self.SessionLocal() as db:
            svc = StaffWechatAuthService(db)
            t = await bind_tokens.create_bind_token(
                tenant_id=TENANT_A, account_id=self.waiter_id, created_by_owner=TENANT_A
            )
            result = await svc.confirm_bind(
                bind_token=t["binding_url"].split("t=")[1],
                identity=WechatIdentity(app_id="mock_staff_app", openid="no_owner"),
            )
            self.assertEqual(result["role"], "waiter")
            self.assertNotEqual(result["role"], "owner")
            # Permissions come from waiter map, not owner *.
            self.assertNotIn("*", result["permissions"])
            self.assertEqual(result["permissions"], permission_list("waiter"))


class StaffDeviceTransportAndRedisGateTest(unittest.IsolatedAsyncioTestCase):
    """Cookie vs JSON credential mutual exclusion + production Redis fail-closed."""

    async def asyncSetUp(self):
        bind_tokens._MEMORY.clear()

    async def test_production_redis_down_fails_closed_no_memory_token(self):
        from unittest.mock import patch

        from app.services.staff_bind_token_service import StaffAuthStoreUnavailable

        bind_tokens._MEMORY.clear()
        with patch.object(bind_tokens.settings, "APP_ENV", "production"), patch.object(
            bind_tokens.settings, "STAFF_WECHAT_ALLOW_MEMORY_STORE", False
        ), patch.object(bind_tokens.settings, "REDIS_ENABLED", False):
            with self.assertRaises(StaffAuthStoreUnavailable):
                await bind_tokens.create_bind_token(
                    tenant_id="t", account_id=1, created_by_owner="t"
                )
            with self.assertRaises(StaffAuthStoreUnavailable):
                await bind_tokens.create_oauth_state({"purpose": "login"})
            self.assertEqual(len(bind_tokens._MEMORY), 0)

    async def test_development_allows_memory_when_redis_down(self):
        from unittest.mock import patch

        bind_tokens._MEMORY.clear()
        with patch.object(bind_tokens.settings, "APP_ENV", "development"), patch.object(
            bind_tokens.settings, "STAFF_WECHAT_ALLOW_MEMORY_STORE", False
        ), patch.object(bind_tokens.settings, "REDIS_ENABLED", False):
            data = await bind_tokens.create_bind_token(
                tenant_id="t", account_id=99, created_by_owner="t"
            )
            raw = data["binding_url"].split("t=")[1]
            self.assertIsNotNone(await bind_tokens.peek_bind_token(raw))

    async def test_cookie_mode_strips_device_credential_from_json(self):
        from unittest.mock import MagicMock, patch

        from app.api.v1 import staff_wechat_auth as api

        result = {
            "ok": True,
            "token": "jwt",
            "role": "waiter",
            "device_credential": "dev.secret",
            "device_id": "dev",
        }
        response = MagicMock()
        with patch.object(api.settings, "STAFF_DEVICE_COOKIE_ENABLED", True), patch.object(
            api.settings, "APP_ENV", "production"
        ):
            public = api._deliver_device_credential(response, result)
            self.assertNotIn("device_credential", public)
            self.assertEqual(public.get("token"), "jwt")
            response.set_cookie.assert_called()
            kwargs = response.set_cookie.call_args.kwargs
            self.assertTrue(kwargs.get("httponly"))
            self.assertTrue(kwargs.get("secure"))
            self.assertEqual(kwargs.get("samesite"), "lax")

    async def test_js_mode_keeps_device_credential_in_json(self):
        from unittest.mock import MagicMock, patch

        from app.api.v1 import staff_wechat_auth as api

        result = {
            "ok": True,
            "token": "jwt",
            "device_credential": "dev.secret",
        }
        response = MagicMock()
        with patch.object(api.settings, "STAFF_DEVICE_COOKIE_ENABLED", False):
            public = api._deliver_device_credential(response, result)
            self.assertEqual(public.get("device_credential"), "dev.secret")
            response.set_cookie.assert_not_called()

    async def test_cookie_mode_ignores_body_credential(self):
        from unittest.mock import MagicMock, patch

        from app.api.v1 import staff_wechat_auth as api

        request = MagicMock()
        request.cookies = {}
        with patch.object(api.settings, "STAFF_DEVICE_COOKIE_ENABLED", True):
            self.assertIsNone(api._read_device_credential(request, "leaked.secret"))

    async def test_cookie_mode_refresh_rotation_strips_json(self):
        from unittest.mock import MagicMock, patch

        from app.api.v1 import staff_wechat_auth as api

        result = {
            "ok": True,
            "token": "newjwt",
            "role": "waiter",
            "device_credential": "id.newsecret",
        }
        response = MagicMock()
        with patch.object(api.settings, "STAFF_DEVICE_COOKIE_ENABLED", True):
            public = api._deliver_device_credential(response, result)
            self.assertNotIn("device_credential", public)
            response.set_cookie.assert_called_once()


if __name__ == "__main__":
    unittest.main()

