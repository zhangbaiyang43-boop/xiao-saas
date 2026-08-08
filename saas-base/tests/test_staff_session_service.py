"""Unit/contract tests for neutral StaffSessionService."""

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
from app.services.staff_session_service import StaffSessionService
from app.services.staff_trusted_device_service import decode_device_credential
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT = "tenant-session-a"
FAKE_HASH = "x"


class StaffSessionServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.waiter_id = generate_snowflake_id()
        self.kitchen_id = generate_snowflake_id()
        async with self.SessionLocal() as db:
            db.add_all(
                [
                    Tenant(
                        tenant_id=TENANT,
                        name="Session店",
                        password_hash="x",
                        phone="13900001111",
                        status=True,
                        is_open=True,
                    ),
                    MerchantAccount(
                        id=self.waiter_id,
                        tenant_id=TENANT,
                        name="服务员",
                        username="waiter_s",
                        password_hash=FAKE_HASH,
                        role="waiter",
                        status="active",
                    ),
                    MerchantAccount(
                        id=self.kitchen_id,
                        tenant_id=TENANT,
                        name="后厨",
                        username="kitchen_s",
                        password_hash=FAKE_HASH,
                        role="kitchen",
                        status="active",
                    ),
                ]
            )
            await db.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _account(self, db, account_id: int) -> MerchantAccount:
        from sqlalchemy import select

        return (
            await db.execute(select(MerchantAccount).where(MerchantAccount.id == account_id))
        ).scalar_one()

    async def test_issue_waiter_and_kitchen(self):
        async with self.SessionLocal() as db:
            svc = StaffSessionService(db)
            waiter = await self._account(db, self.waiter_id)
            kitchen = await self._account(db, self.kitchen_id)
            w = await svc.issue_session_for_account(waiter, auth_method="staff_password")
            k = await svc.issue_session_for_account(kitchen, auth_method="staff_password")
            self.assertTrue(w["ok"])
            self.assertEqual(w["role"], "waiter")
            self.assertEqual(w["home_path"], "/waiter")
            self.assertEqual(set(w["permissions"]), set(permission_list("waiter")))
            self.assertTrue(k["ok"])
            self.assertEqual(k["role"], "kitchen")
            self.assertEqual(k["home_path"], "/kitchen")
            payload = verify_token(w["token"])
            self.assertEqual(int(payload["account_id"]), self.waiter_id)
            self.assertEqual(payload["role"], "waiter")
            self.assertEqual(payload["type"], "merchant")

    async def test_refresh_role_change(self):
        async with self.SessionLocal() as db:
            svc = StaffSessionService(db)
            waiter = await self._account(db, self.waiter_id)
            issued = await svc.issue_session_for_account(waiter, auth_method="staff_password")
            device_id, secret = decode_device_credential(issued["device_credential"])
            waiter.role = "kitchen"
            await db.commit()
            refresh = await svc.refresh_device(device_id=device_id, secret=secret)
            self.assertTrue(refresh["ok"])
            self.assertEqual(refresh["role"], "kitchen")
            self.assertEqual(refresh["home_path"], "/kitchen")
            self.assertEqual(set(refresh["permissions"]), set(permission_list("kitchen")))

    async def test_disabled_refresh_blocked(self):
        async with self.SessionLocal() as db:
            svc = StaffSessionService(db)
            waiter = await self._account(db, self.waiter_id)
            issued = await svc.issue_session_for_account(waiter, auth_method="staff_password")
            device_id, secret = decode_device_credential(issued["device_credential"])
            waiter.status = "disabled"
            await db.commit()
            refresh = await svc.refresh_device(device_id=device_id, secret=secret)
            self.assertFalse(refresh["ok"])

    async def test_device_rotation(self):
        async with self.SessionLocal() as db:
            svc = StaffSessionService(db)
            waiter = await self._account(db, self.waiter_id)
            issued = await svc.issue_session_for_account(waiter, auth_method="staff_password")
            device_id, secret_a = decode_device_credential(issued["device_credential"])
            refresh = await svc.refresh_device(device_id=device_id, secret=secret_a)
            self.assertTrue(refresh["ok"])
            _, secret_b = decode_device_credential(refresh["device_credential"])
            self.assertNotEqual(secret_a, secret_b)
            again = await svc.refresh_device(device_id=device_id, secret=secret_a)
            self.assertFalse(again["ok"])


class StaffSessionRouteUniquenessTest(unittest.TestCase):
    def test_device_and_logout_routes_registered_once(self):
        from app.main import app

        paths = []
        for r in app.routes:
            methods = getattr(r, "methods", None) or set()
            path = getattr(r, "path", None)
            if not path:
                continue
            for m in methods:
                paths.append((m, path))
        device = [p for p in paths if p == ("POST", "/api/v1/login/staff/device")]
        logout = [p for p in paths if p == ("POST", "/api/v1/login/staff/logout-device")]
        login = [p for p in paths if p == ("POST", "/api/v1/login/staff")]
        self.assertEqual(len(device), 1, device)
        self.assertEqual(len(logout), 1, logout)
        self.assertEqual(len(login), 1, login)


class StaffSessionCookieWechatFreeTest(unittest.TestCase):
    def test_cookie_module_has_no_wechat_imports(self):
        import inspect

        import app.services.staff_session_cookie as mod

        src = inspect.getsource(mod)
        self.assertNotIn("StaffWechatAuthService", src)
        self.assertNotIn("staff_wechat", src)
        self.assertNotIn("staff_miniprogram", src)
        self.assertNotIn("from app.services.staff_wechat", src)


if __name__ == "__main__":
    unittest.main()
