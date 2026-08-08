"""Phase R1: frontdesk role + Waiter/Kitchen duty realignment contracts.

Avoids real bcrypt (passlib/bcrypt env issues) — same FAKE_HASH approach as other staff tests.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.merchant_auth import staff_route_allowed
from app.core.permissions import (
    ROLE_FRONTDESK,
    ROLE_KITCHEN,
    ROLE_OWNER,
    ROLE_WAITER,
    STAFF_ROLES,
    has_permission,
    parse_staff_role,
    permission_list,
    staff_home_path,
)
from app.core.security import create_access_token
from app.models.base import Base
from app.models.merchant_account import MerchantAccount
from app.models.merchant_account_trusted_device import MerchantAccountTrustedDevice  # noqa: F401
from app.models.merchant_account_wechat_binding import MerchantAccountWechatBinding  # noqa: F401
from app.models.order import Order, OrderItem  # noqa: F401
from app.models.tenant import Tenant
from app.services.merchant_account_service import MerchantAccountService
from app.services.staff_session_service import StaffSessionService
from app.services.staff_trusted_device_service import decode_device_credential
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT = "tenant-r1-a"
PLAIN = "Password1234"
FAKE_HASH = "test-password-hash-not-used-for-verify"


def _fake_hash(password: str) -> str:
    return f"hashed:{password}"


class PhaseR1FrontdeskRolesTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.waiter_id = generate_snowflake_id()
        self.frontdesk_id = generate_snowflake_id()
        self.kitchen_id = generate_snowflake_id()
        async with self.SessionLocal() as db:
            db.add_all(
                [
                    Tenant(
                        tenant_id=TENANT,
                        name="R1店",
                        password_hash="x",
                        phone="13900002222",
                        status=True,
                        is_open=True,
                    ),
                    MerchantAccount(
                        id=self.waiter_id,
                        tenant_id=TENANT,
                        name="历史服务员",
                        username="waiter_r1",
                        password_hash=FAKE_HASH,
                        role="waiter",
                        status="active",
                    ),
                    MerchantAccount(
                        id=self.frontdesk_id,
                        tenant_id=TENANT,
                        name="前台",
                        username="front_r1",
                        password_hash=FAKE_HASH,
                        role="frontdesk",
                        status="active",
                    ),
                    MerchantAccount(
                        id=self.kitchen_id,
                        tenant_id=TENANT,
                        name="后厨",
                        username="kitchen_r1",
                        password_hash=FAKE_HASH,
                        role="kitchen",
                        status="active",
                    ),
                ]
            )
            await db.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    def test_r1_01_staff_roles_include_frontdesk(self):
        self.assertIn(ROLE_FRONTDESK, STAFF_ROLES)
        self.assertEqual(parse_staff_role("frontdesk"), "frontdesk")
        self.assertIsNone(parse_staff_role("cashier"))
        self.assertIsNone(parse_staff_role("owner"))

    async def test_r1_02_create_frontdesk_ok_cashier_owner_rejected(self):
        async with self.SessionLocal() as db:
            svc = MerchantAccountService(db)
            with patch(
                "app.services.merchant_account_service.hash_staff_password",
                side_effect=_fake_hash,
            ):
                ok = await svc.create_account(
                    tenant_id=TENANT,
                    name="新前台",
                    role="frontdesk",
                    username="front_new",
                    password=PLAIN,
                )
            self.assertEqual(ok.code, 200)
            self.assertEqual(ok.data["role"], "frontdesk")

            bad_cashier = await svc.create_account(
                tenant_id=TENANT,
                name="收银",
                role="cashier",
                username="cashier_x",
                password=PLAIN,
            )
            self.assertEqual(bad_cashier.code, 400)

            bad_owner = await svc.create_account(
                tenant_id=TENANT,
                name="伪老板",
                role="owner",
                username="owner_x",
                password=PLAIN,
            )
            self.assertEqual(bad_owner.code, 400)

    async def test_r1_04_frontdesk_password_login_home(self):
        async with self.SessionLocal() as db:
            from sqlalchemy import select

            account = (
                await db.execute(
                    select(MerchantAccount).where(MerchantAccount.id == self.frontdesk_id)
                )
            ).scalar_one()
            issued = await StaffSessionService(db).issue_session_for_account(
                account, auth_method="staff_password"
            )
            self.assertTrue(issued["ok"])
            self.assertEqual(issued["role"], "frontdesk")
            self.assertEqual(issued["home_path"], "/frontdesk")
            self.assertEqual(staff_home_path(issued["role"]), "/frontdesk")
            self.assertIn("pickup.assign", issued["permissions"])
            self.assertNotIn("order.accept", issued["permissions"])

    async def test_r1_05_06_trusted_device_role_change_to_frontdesk(self):
        async with self.SessionLocal() as db:
            from sqlalchemy import select

            waiter = (
                await db.execute(select(MerchantAccount).where(MerchantAccount.id == self.waiter_id))
            ).scalar_one()
            issued = await StaffSessionService(db).issue_session_for_account(
                waiter, auth_method="staff_password"
            )
            device_id, secret = decode_device_credential(issued["device_credential"])
            upd = await MerchantAccountService(db).update_account(
                tenant_id=TENANT, account_id=self.waiter_id, role="frontdesk"
            )
            self.assertEqual(upd.code, 200)
            refresh = await StaffSessionService(db).refresh_device(
                device_id=device_id, secret=secret
            )
            self.assertTrue(refresh["ok"])
            self.assertEqual(refresh["role"], "frontdesk")
            self.assertEqual(refresh["home_path"], "/frontdesk")
            self.assertIn("pickup.assign", refresh["permissions"])
            self.assertNotIn("order.accept", refresh["permissions"])

    def test_r1_07_19_permission_matrix_api_routes(self):
        self.assertFalse(has_permission(ROLE_WAITER, "order.accept"))
        self.assertFalse(staff_route_allowed("PATCH", "/api/v1/orders/1/status", ROLE_WAITER))
        self.assertFalse(staff_route_allowed("PATCH", "/api/v1/orders/1/pickup-no", ROLE_WAITER))

        self.assertTrue(staff_route_allowed("PATCH", "/api/v1/orders/1/pickup-no", ROLE_FRONTDESK))
        self.assertFalse(staff_route_allowed("PATCH", "/api/v1/orders/1/status", ROLE_FRONTDESK))
        self.assertFalse(staff_route_allowed("POST", "/api/v1/orders/1/reprint", ROLE_FRONTDESK))
        self.assertFalse(staff_route_allowed("GET", "/api/v1/merchant-accounts", ROLE_FRONTDESK))
        self.assertFalse(staff_route_allowed("GET", "/api/v1/customers/", ROLE_FRONTDESK))
        self.assertFalse(staff_route_allowed("GET", "/api/v1/tenant/settings", ROLE_FRONTDESK))
        self.assertFalse(has_permission(ROLE_FRONTDESK, "order.accept"))
        self.assertFalse(has_permission(ROLE_FRONTDESK, "order.complete"))
        self.assertFalse(has_permission(ROLE_FRONTDESK, "kitchen.print_reprint"))

        self.assertTrue(staff_route_allowed("PATCH", "/api/v1/orders/1/status", ROLE_KITCHEN))
        self.assertTrue(staff_route_allowed("POST", "/api/v1/orders/1/reprint", ROLE_KITCHEN))
        self.assertFalse(staff_route_allowed("PATCH", "/api/v1/orders/1/pickup-no", ROLE_KITCHEN))
        self.assertTrue(has_permission(ROLE_KITCHEN, "order.accept"))
        self.assertTrue(has_permission(ROLE_KITCHEN, "order.complete"))

        self.assertTrue(has_permission(ROLE_OWNER, "order.accept"))
        self.assertTrue(has_permission(ROLE_OWNER, "pickup.assign"))
        self.assertTrue(has_permission(ROLE_OWNER, "kitchen.print_reprint"))
        self.assertEqual(permission_list(ROLE_OWNER), ["*"])

    def test_r1_no_auto_migrate_historical_waiter(self):
        self.assertEqual(parse_staff_role("waiter"), "waiter")
        self.assertNotEqual(staff_home_path("waiter"), "/frontdesk")

    def test_r1_35_deferred_print_hook_still_wired(self):
        import inspect

        from app.services import order_lifecycle_service as ols

        src = inspect.getsource(ols.OrderLifecycleService.update_order_pickup_no)
        self.assertIn("pickup_no_assigned", src)
        self.assertTrue(
            staff_route_allowed("PATCH", "/api/v1/orders/1/pickup-no", ROLE_FRONTDESK)
        )


class PhaseR1HttpGateTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.waiter_id = generate_snowflake_id()
        self.frontdesk_id = generate_snowflake_id()
        self.kitchen_id = generate_snowflake_id()
        self.order_id = generate_snowflake_id()
        async with self.SessionLocal() as db:
            db.add_all(
                [
                    Tenant(
                        tenant_id=TENANT,
                        name="R1 HTTP",
                        password_hash="x",
                        phone="13900003333",
                        status=True,
                        is_open=True,
                    ),
                    MerchantAccount(
                        id=self.waiter_id,
                        tenant_id=TENANT,
                        name="W",
                        username="w_http",
                        password_hash=FAKE_HASH,
                        role="waiter",
                        status="active",
                    ),
                    MerchantAccount(
                        id=self.frontdesk_id,
                        tenant_id=TENANT,
                        name="F",
                        username="f_http",
                        password_hash=FAKE_HASH,
                        role="frontdesk",
                        status="active",
                    ),
                    MerchantAccount(
                        id=self.kitchen_id,
                        tenant_id=TENANT,
                        name="K",
                        username="k_http",
                        password_hash=FAKE_HASH,
                        role="kitchen",
                        status="active",
                    ),
                    Order(
                        id=self.order_id,
                        tenant_id=TENANT,
                        table_no="T1",
                        total=12,
                        status="pending",
                        payment_status="paid",
                        payment_mode="postpay",
                    ),
                ]
            )
            await db.commit()

        from app.main import app

        self.app = app
        self._session_patch = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._session_patch.start()
        self._cache_get = patch(
            "app.core.cache_helper.get_cache", new_callable=AsyncMock, return_value=None
        )
        self._cache_set = patch(
            "app.core.cache_helper.set_cache", new_callable=AsyncMock, return_value=None
        )
        self._cache_get.start()
        self._cache_set.start()
        import httpx

        transport = httpx.ASGITransport(app=self.app)
        self.client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        self._session_patch.stop()
        self._cache_get.stop()
        self._cache_set.stop()
        await self.engine.dispose()

    def _auth(self, role: str, account_id: int) -> dict:
        token = create_access_token(TENANT, role=role, account_id=account_id)
        return {"Authorization": f"Bearer {token}"}

    async def test_r1_waiter_accept_and_pickup_403(self):
        h = self._auth("waiter", self.waiter_id)
        r = await self.client.patch(
            f"/api/v1/orders/{self.order_id}/status",
            headers=h,
            json={"status": "preparing"},
        )
        self.assertEqual(r.status_code, 403)
        r = await self.client.patch(
            f"/api/v1/orders/{self.order_id}/pickup-no",
            headers=h,
            json={"pickup_no": "3"},
        )
        self.assertEqual(r.status_code, 403)

    async def test_r1_frontdesk_accept_complete_reprint_403(self):
        h = self._auth("frontdesk", self.frontdesk_id)
        r = await self.client.patch(
            f"/api/v1/orders/{self.order_id}/status",
            headers=h,
            json={"status": "preparing"},
        )
        self.assertEqual(r.status_code, 403)
        r = await self.client.patch(
            f"/api/v1/orders/{self.order_id}/status",
            headers=h,
            json={"status": "done"},
        )
        self.assertEqual(r.status_code, 403)
        r = await self.client.post(
            f"/api/v1/orders/{self.order_id}/reprint",
            headers=h,
            json={"print_type": "kitchen"},
        )
        self.assertEqual(r.status_code, 403)

    async def test_r1_kitchen_pickup_403_accept_allowed_route(self):
        h = self._auth("kitchen", self.kitchen_id)
        r = await self.client.patch(
            f"/api/v1/orders/{self.order_id}/pickup-no",
            headers=h,
            json={"pickup_no": "3"},
        )
        self.assertEqual(r.status_code, 403)
        with patch(
            "app.services.order_lifecycle_service.OrderLifecycleService.update_order_status",
            new_callable=AsyncMock,
        ) as upd:
            from app.core.response import success_response

            upd.return_value = success_response(msg="ok")
            r = await self.client.patch(
                f"/api/v1/orders/{self.order_id}/status",
                headers=h,
                json={"status": "preparing"},
            )
            self.assertNotEqual(r.status_code, 403)

    async def test_r1_frontdesk_workbench_readable(self):
        h = self._auth("frontdesk", self.frontdesk_id)
        r = await self.client.get("/api/v1/orders/workbench", headers=h)
        self.assertEqual(r.status_code, 200)
        r = await self.client.get("/api/v1/orders/workbench/changes", headers=h)
        self.assertIn(r.status_code, (200, 400))

    async def test_r1_frontdesk_cannot_cross_tenant_settings(self):
        h = self._auth("frontdesk", self.frontdesk_id)
        for path in (
            "/api/v1/merchant-accounts",
            "/api/v1/customers/",
            "/api/v1/tenant/settings",
            "/api/v1/orders",
        ):
            r = await self.client.get(path, headers=h)
            self.assertEqual(r.status_code, 403, msg=path)


if __name__ == "__main__":
    unittest.main()
