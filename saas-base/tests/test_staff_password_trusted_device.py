"""Phase 2: password login establishes trusted device; restore/revoke/role/disable.

Avoids real bcrypt (passlib/bcrypt env issues on some local Pythons) by patching
check_staff_password / hash_staff_password — same approach as other staff auth tests
that use FAKE_PW placeholders.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.permissions import permission_list
from app.core.security import verify_token
from app.models.base import Base
from app.models.merchant_account import MerchantAccount
from app.models.merchant_account_trusted_device import MerchantAccountTrustedDevice  # noqa: F401
from app.models.merchant_account_wechat_binding import MerchantAccountWechatBinding  # noqa: F401
from app.models.tenant import Tenant
from app.services.merchant_account_service import MerchantAccountService
from app.services.staff_trusted_device_service import (
    StaffTrustedDeviceService,
    decode_device_credential,
    summarize_user_agent,
)
from app.services.staff_session_service import StaffSessionService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-pwd-td-a"
PLAIN_PW = "StorePass123"
FAKE_HASH = "test-password-hash-not-used-for-verify"


def _fake_check(plain: str, hashed: str | None) -> bool:
    return bool(hashed) and plain == PLAIN_PW


def _fake_hash(password: str) -> str:
    return f"hashed:{password}"


class StaffPasswordTrustedDeviceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
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
                    MerchantAccount(
                        id=self.waiter_id,
                        tenant_id=TENANT_A,
                        name="小王",
                        username="waiter_a",
                        password_hash=FAKE_HASH,
                        role="waiter",
                        status="active",
                    ),
                    MerchantAccount(
                        id=self.kitchen_id,
                        tenant_id=TENANT_A,
                        name="小李",
                        username="kitchen_a",
                        password_hash=FAKE_HASH,
                        role="kitchen",
                        status="active",
                    ),
                    MerchantAccount(
                        id=self.waiter_b_id,
                        tenant_id=TENANT_A,
                        name="小张",
                        username="waiter_b",
                        password_hash=FAKE_HASH,
                        role="waiter",
                        status="active",
                    ),
                ]
            )
            await db.commit()

        self._pw_patch = patch(
            "app.services.merchant_account_service.check_staff_password",
            side_effect=_fake_check,
        )
        self._hash_patch = patch(
            "app.services.merchant_account_service.hash_staff_password",
            side_effect=_fake_hash,
        )
        self._pw_patch.start()
        self._hash_patch.start()

    async def asyncTearDown(self):
        self._pw_patch.stop()
        self._hash_patch.stop()
        await self.engine.dispose()

    async def _password_issue(self, db, *, username: str, existing_device_id=None, existing_secret=None):
        account, err = await MerchantAccountService(db).authenticate(
            tenant_id=TENANT_A, username=username, password=PLAIN_PW
        )
        self.assertIsNone(err)
        self.assertIsNotNone(account)
        tenant = await StaffSessionService(db)._get_tenant(TENANT_A)
        return await StaffSessionService(db).issue_session_for_account(
            account,
            auth_method="staff_password",
            user_agent="Mozilla/5.0 (iPhone)",
            tenant=tenant,
            existing_device_id=existing_device_id,
            existing_secret=existing_secret,
        )

    async def test_password_success_creates_device_credential(self):
        async with self.SessionLocal() as db:
            issued = await self._password_issue(db, username="waiter_a")
            self.assertTrue(issued["ok"])
            self.assertEqual(issued["role"], "waiter")
            self.assertEqual(issued["home_path"], "/waiter")
            self.assertEqual(issued["auth_method"], "staff_password")
            self.assertIn("device_credential", issued)
            self.assertNotIn("openid", issued)
            device_id, secret = decode_device_credential(issued["device_credential"])
            self.assertTrue(device_id and secret)
            payload = verify_token(issued["token"])
            self.assertEqual(int(payload["account_id"]), self.waiter_id)
            count = await StaffTrustedDeviceService(db).count_active(
                tenant_id=TENANT_A, account_id=self.waiter_id
            )
            self.assertEqual(count, 1)

    async def test_wrong_password_does_not_create_device(self):
        async with self.SessionLocal() as db:
            before = await StaffTrustedDeviceService(db).count_active(
                tenant_id=TENANT_A, account_id=self.waiter_id
            )
            account, err = await MerchantAccountService(db).authenticate(
                tenant_id=TENANT_A, username="waiter_a", password="wrong-password"
            )
            self.assertIsNone(account)
            self.assertIsNotNone(err)
            after = await StaffTrustedDeviceService(db).count_active(
                tenant_id=TENANT_A, account_id=self.waiter_id
            )
            self.assertEqual(before, after)

    async def test_device_restore_reads_current_db_role(self):
        async with self.SessionLocal() as db:
            issued = await self._password_issue(db, username="waiter_a")
            device_id, secret = decode_device_credential(issued["device_credential"])
            await MerchantAccountService(db).update_account(
                tenant_id=TENANT_A, account_id=self.waiter_id, role="kitchen"
            )
            refresh = await StaffSessionService(db).refresh_device(
                device_id=device_id, secret=secret
            )
            self.assertTrue(refresh["ok"])
            self.assertEqual(refresh["role"], "kitchen")
            self.assertEqual(refresh["home_path"], "/kitchen")
            self.assertNotIn("pickup.assign", refresh["permissions"])
            self.assertIn("kitchen.print_reprint", refresh["permissions"])

    async def test_disabled_blocks_restore(self):
        async with self.SessionLocal() as db:
            issued = await self._password_issue(db, username="waiter_a")
            device_id, secret = decode_device_credential(issued["device_credential"])
            await MerchantAccountService(db).update_account(
                tenant_id=TENANT_A, account_id=self.waiter_id, status="disabled"
            )
            refresh = await StaffSessionService(db).refresh_device(
                device_id=device_id, secret=secret
            )
            self.assertFalse(refresh["ok"])

    async def test_password_reset_revokes_devices(self):
        async with self.SessionLocal() as db:
            issued = await self._password_issue(db, username="waiter_a")
            device_id, secret = decode_device_credential(issued["device_credential"])
            res = await MerchantAccountService(db).reset_password(
                tenant_id=TENANT_A, account_id=self.waiter_id, password="NewPass1234"
            )
            self.assertEqual(res.code, 200)
            refresh = await StaffSessionService(db).refresh_device(
                device_id=device_id, secret=secret
            )
            self.assertFalse(refresh["ok"])

    async def test_set_login_account_revokes_devices(self):
        async with self.SessionLocal() as db:
            issued = await self._password_issue(db, username="waiter_a")
            device_id, secret = decode_device_credential(issued["device_credential"])
            res = await MerchantAccountService(db).set_backup_login(
                tenant_id=TENANT_A,
                account_id=self.waiter_id,
                username="waiter_a",
                password="AnotherPass9",
            )
            self.assertEqual(res.code, 200)
            refresh = await StaffSessionService(db).refresh_device(
                device_id=device_id, secret=secret
            )
            self.assertFalse(refresh["ok"])

    async def test_account_switch_issues_b_session(self):
        async with self.SessionLocal() as db:
            a = await self._password_issue(db, username="waiter_a")
            a_id, a_secret = decode_device_credential(a["device_credential"])
            b = await self._password_issue(
                db,
                username="waiter_b",
                existing_device_id=a_id,
                existing_secret=a_secret,
            )
            self.assertTrue(b["ok"])
            self.assertEqual(int(b["account_id"]), self.waiter_b_id)
            b_id, b_secret = decode_device_credential(b["device_credential"])
            refresh_b = await StaffSessionService(db).refresh_device(
                device_id=b_id, secret=b_secret
            )
            self.assertTrue(refresh_b["ok"])
            self.assertEqual(int(refresh_b["account_id"]), self.waiter_b_id)

    async def test_revoke_blocks_restore(self):
        async with self.SessionLocal() as db:
            issued = await self._password_issue(db, username="waiter_a")
            device_id, secret = decode_device_credential(issued["device_credential"])
            await StaffTrustedDeviceService(db).revoke_all(
                tenant_id=TENANT_A, account_id=self.waiter_id
            )
            refresh = await StaffSessionService(db).refresh_device(
                device_id=device_id, secret=secret
            )
            self.assertFalse(refresh["ok"])

    async def test_kitchen_permissions_after_password_issue(self):
        async with self.SessionLocal() as db:
            issued = await self._password_issue(db, username="kitchen_a")
            self.assertEqual(issued["role"], "kitchen")
            self.assertEqual(issued["home_path"], "/kitchen")
            self.assertEqual(set(issued["permissions"]), set(permission_list("kitchen")))
            self.assertNotIn("pickup.assign", issued["permissions"])

    def test_ua_display_is_work_device_not_wechat(self):
        name, _ = summarize_user_agent("Mozilla/5.0 (iPhone)")
        self.assertTrue(name.startswith("工作设备"))
        self.assertNotIn("微信", name)


class StaffPasswordLoginCookieModeTest(unittest.TestCase):
    def test_cookie_mode_strips_credential_from_public_payload(self):
        from app.config import settings
        from app.services.staff_session_cookie import public_auth_payload

        with patch.object(settings, "STAFF_DEVICE_COOKIE_ENABLED", True):
            data = public_auth_payload(
                {
                    "ok": True,
                    "token": "t",
                    "role": "waiter",
                    "device_credential": "id.secret",
                }
            )
            self.assertNotIn("device_credential", data)
            self.assertEqual(data["token"], "t")


class StaffPasswordLogoutHttpContractTest(unittest.IsolatedAsyncioTestCase):
    """P0 Final Gate: logout must revoke device; old cookie cannot restore."""

    async def asyncSetUp(self):
        from unittest.mock import AsyncMock

        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.waiter_id = generate_snowflake_id()

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
                    MerchantAccount(
                        id=self.waiter_id,
                        tenant_id=TENANT_A,
                        name="小王",
                        username="waiter_a",
                        password_hash=FAKE_HASH,
                        role="waiter",
                        status="active",
                    ),
                ]
            )
            await db.commit()

        async def override_get_db():
            async with self.SessionLocal() as session:
                yield session

        from app.core.database import get_db
        from app.main import app

        self.app = app
        self.app.dependency_overrides[get_db] = override_get_db
        self._session_patch = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._session_patch.start()
        self._cache_get = patch(
            "app.core.cache_helper.get_cache", new_callable=AsyncMock, return_value=None
        )
        self._cache_set = patch(
            "app.core.cache_helper.set_cache", new_callable=AsyncMock, return_value=None
        )
        self._cache_del = patch(
            "app.core.cache_helper.delete_cache", new_callable=AsyncMock, return_value=None
        )
        self._pw = patch(
            "app.services.merchant_account_service.check_staff_password",
            side_effect=_fake_check,
        )
        self._cookie_on = patch(
            "app.config.settings.STAFF_DEVICE_COOKIE_ENABLED",
            True,
        )
        self._cache_get.start()
        self._cache_set.start()
        self._cache_del.start()
        self._pw.start()
        self._cookie_on.start()

        import httpx

        transport = httpx.ASGITransport(app=self.app)
        # Do not auto-follow cookie jar for restore-after-logout (we send Cookie explicitly).
        self.client = httpx.AsyncClient(transport=transport, base_url="http://test", cookies=httpx.Cookies())

    async def asyncTearDown(self):
        await self.client.aclose()
        self.app.dependency_overrides.clear()
        self._session_patch.stop()
        self._cache_get.stop()
        self._cache_set.stop()
        self._cache_del.stop()
        self._pw.stop()
        self._cookie_on.stop()
        await self.engine.dispose()

    def _cookie_name(self) -> str:
        from app.config import settings

        return settings.STAFF_DEVICE_COOKIE_NAME or "staff_device"

    def _extract_set_cookie_values(self, response) -> list[str]:
        # httpx may expose multiple Set-Cookie; collect raw header strings.
        headers = response.headers
        values = []
        get_list = getattr(headers, "get_list", None)
        if callable(get_list):
            values = get_list("set-cookie") or []
        elif "set-cookie" in headers:
            values = [headers["set-cookie"]]
        return values

    async def test_logout_revokes_device_and_blocks_old_cookie_restore(self):
        cookie_name = self._cookie_name()

        # 1) Password login
        login = await self.client.post(
            "/api/v1/login/staff",
            json={
                "shop_phone": "13800001111",
                "username": "waiter_a",
                "password": PLAIN_PW,
            },
        )
        self.assertEqual(login.status_code, 200, login.text)
        body = login.json()
        self.assertEqual(body.get("code"), 200)
        token = body["data"]["token"]
        self.assertTrue(token)
        self.assertNotIn("device_credential", body["data"])

        staff_cookie = login.cookies.get(cookie_name)
        self.assertTrue(staff_cookie, "password login must Set-Cookie staff_device")
        set_cookies = self._extract_set_cookie_values(login)
        self.assertTrue(any(cookie_name in c for c in set_cookies))

        # 2) First device restore with that cookie
        restore1 = await self.client.post(
            "/api/v1/login/staff/device",
            json={},
            headers={"Cookie": f"{cookie_name}={staff_cookie}"},
        )
        self.assertEqual(restore1.status_code, 200, restore1.text)
        self.assertEqual(restore1.json().get("code"), 200)
        # Rotation may replace cookie
        rotated = restore1.cookies.get(cookie_name) or staff_cookie
        token2 = restore1.json()["data"]["token"]
        self.assertTrue(token2)

        # 3) Logout with JWT + current cookie
        logout = await self.client.post(
            "/api/v1/login/staff/logout-device",
            json={},
            headers={
                "Authorization": f"Bearer {token2}",
                "Cookie": f"{cookie_name}={rotated}",
            },
        )
        self.assertEqual(logout.status_code, 200, logout.text)
        self.assertEqual(logout.json().get("code"), 200)

        clear_headers = self._extract_set_cookie_values(logout)
        self.assertTrue(clear_headers, "logout must Set-Cookie to clear staff_device")
        clear_joined = "\n".join(clear_headers).lower()
        self.assertIn(cookie_name.lower(), clear_joined)
        self.assertTrue(
            ("max-age=0" in clear_joined)
            or ("expires=" in clear_joined)
            or (f"{cookie_name}=" in clear_joined and '""' in clear_joined)
            or (f"{cookie_name}=;" in clear_joined)
            or (f"{cookie_name}= " in clear_joined),
            f"cookie clear marker missing in: {clear_headers}",
        )

        # 4) DB revoked_at written
        from sqlalchemy import select

        async with self.SessionLocal() as db:
            row = (
                await db.execute(
                    select(MerchantAccountTrustedDevice).where(
                        MerchantAccountTrustedDevice.merchant_account_id == self.waiter_id
                    )
                )
            ).scalar_one()
            self.assertIsNotNone(row.revoked_at)

        # 5) Old cookie restore must fail (project contract: HTTP 200 body code 401 OR status 401)
        restore2 = await self.client.post(
            "/api/v1/login/staff/device",
            json={},
            headers={"Cookie": f"{cookie_name}={rotated}"},
        )
        restore_body = restore2.json()
        rejected = (restore2.status_code == 401) or (restore_body.get("code") == 401)
        self.assertTrue(rejected, restore2.text)
        self.assertNotEqual(restore_body.get("code"), 200)


if __name__ == "__main__":
    unittest.main()
