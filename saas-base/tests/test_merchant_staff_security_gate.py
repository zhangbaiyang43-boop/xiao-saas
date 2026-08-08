"""P0 security gate: owner fallback, cross-tenant HTTP, DTO, password, throttle."""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.merchant_auth import (
    resolve_merchant_request_auth,
    staff_login_allowed,
    staff_route_allowed,
    validate_staff_password,
)
from app.core.permissions import (
    ROLE_KITCHEN,
    ROLE_OWNER,
    ROLE_PERMISSIONS,
    ROLE_WAITER,
    STAFF_ROLES,
    has_permission,
    parse_staff_role,
    permission_list,
)
from app.core.security import create_access_token, verify_token

# Avoid passlib/bcrypt backend issues in local Py3.14 test env; auth path under test
# does not verify password hashes for resolve_merchant_request_auth / HTTP role gates.
FAKE_PW_HASH = "test-password-hash-not-used-for-verify"
from app.models.base import Base
from app.models.merchant_account import MerchantAccount
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.api.v1.orders import serialize_fulfillment_order
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-staff-a"
TENANT_B = "tenant-staff-b"


class OwnerFallbackAndStaffAuthTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

        self.waiter_id = generate_snowflake_id()
        self.kitchen_id = generate_snowflake_id()
        self.disabled_id = generate_snowflake_id()
        self.bad_role_id = generate_snowflake_id()

        async with self.SessionLocal() as db:
            db.add_all(
                [
                    Tenant(
                        tenant_id=TENANT_A,
                        name="Shop A",
                        password_hash="x",
                        phone="13800000001",
                        status=True,
                        is_open=True,
                    ),
                    Tenant(
                        tenant_id=TENANT_B,
                        name="Shop B",
                        password_hash="x",
                        phone="13800000002",
                        status=True,
                        is_open=True,
                    ),
                    MerchantAccount(
                        id=self.waiter_id,
                        tenant_id=TENANT_A,
                        name="Waiter A",
                        username="waiter_a",
                        password_hash=FAKE_PW_HASH,
                        role="waiter",
                        status="active",
                    ),
                    MerchantAccount(
                        id=self.kitchen_id,
                        tenant_id=TENANT_A,
                        name="Kitchen A",
                        username="kitchen_a",
                        password_hash=FAKE_PW_HASH,
                        role="kitchen",
                        status="active",
                    ),
                    MerchantAccount(
                        id=self.disabled_id,
                        tenant_id=TENANT_A,
                        name="Disabled",
                        username="disabled_a",
                        password_hash=FAKE_PW_HASH,
                        role="waiter",
                        status="disabled",
                    ),
                    MerchantAccount(
                        id=self.bad_role_id,
                        tenant_id=TENANT_A,
                        name="BadRole",
                        username="badrole_a",
                        password_hash=FAKE_PW_HASH,
                        role="owner",  # illegal for staff row
                        status="active",
                    ),
                ]
            )
            await db.commit()

        self._db_patch = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._auth_db_patch = patch(
            "app.core.merchant_auth.AsyncSessionLocal", self.SessionLocal, create=True
        )
        # load_account_auth_state imports AsyncSessionLocal from app.core.database inside function
        self._db_patch.start()

    async def asyncTearDown(self):
        self._db_patch.stop()
        await self.engine.dispose()

    async def test_01_legacy_tenant_token_without_role_is_owner(self):
        token = create_access_token(TENANT_A)  # no account_id
        payload = verify_token(token)
        # strip role to simulate pre-staff JWT
        payload.pop("role", None)
        state, err = await resolve_merchant_request_auth(payload)
        self.assertIsNone(err)
        self.assertEqual(state["role"], ROLE_OWNER)
        self.assertIsNone(state["account_id"])
        self.assertTrue(has_permission(state["role"], "finance.settle"))

    async def test_02_staff_token_missing_jwt_role_never_becomes_owner(self):
        token = create_access_token(TENANT_A, role="waiter", account_id=self.waiter_id)
        payload = verify_token(token)
        payload.pop("role", None)
        state, err = await resolve_merchant_request_auth(payload)
        self.assertIsNone(err)
        self.assertEqual(state["role"], ROLE_WAITER)
        self.assertEqual(state["account_id"], self.waiter_id)
        self.assertFalse(has_permission(state["role"], "finance.settle"))
        self.assertNotEqual(state["role"], ROLE_OWNER)

    async def test_02b_staff_jwt_role_owner_claim_ignored_uses_db(self):
        token = create_access_token(TENANT_A, role="owner", account_id=self.waiter_id)
        payload = verify_token(token)
        state, err = await resolve_merchant_request_auth(payload)
        self.assertIsNone(err)
        self.assertEqual(state["role"], ROLE_WAITER)

    async def test_02c_staff_row_with_owner_role_rejected(self):
        token = create_access_token(TENANT_A, role="waiter", account_id=self.bad_role_id)
        payload = verify_token(token)
        state, err = await resolve_merchant_request_auth(payload)
        self.assertIsNone(state)
        self.assertIsNotNone(err)
        self.assertEqual(err.status_code, 403)

    async def test_03_missing_staff_account_rejected(self):
        token = create_access_token(TENANT_A, role="waiter", account_id=999999999)
        payload = verify_token(token)
        state, err = await resolve_merchant_request_auth(payload)
        self.assertIsNone(state)
        self.assertEqual(err.status_code, 401)

    async def test_04_disabled_staff_rejected(self):
        token = create_access_token(TENANT_A, role="waiter", account_id=self.disabled_id)
        payload = verify_token(token)
        state, err = await resolve_merchant_request_auth(payload)
        self.assertIsNone(state)
        self.assertEqual(err.status_code, 403)

    async def test_role_change_waiter_to_kitchen_effective_next_request(self):
        async with self.SessionLocal() as db:
            from sqlalchemy import select

            row = (
                await db.execute(select(MerchantAccount).where(MerchantAccount.id == self.waiter_id))
            ).scalar_one()
            row.role = "kitchen"
            await db.commit()
        from app.core.merchant_auth import invalidate_account_auth_cache

        await invalidate_account_auth_cache(self.waiter_id)
        token = create_access_token(TENANT_A, role="waiter", account_id=self.waiter_id)
        payload = verify_token(token)
        state, err = await resolve_merchant_request_auth(payload)
        self.assertIsNone(err)
        self.assertEqual(state["role"], ROLE_KITCHEN)
        self.assertTrue(has_permission(state["role"], "order.complete"))
        self.assertFalse(has_permission(state["role"], "pickup.assign"))


class PermissionMatrixFromCodeTest(unittest.TestCase):
    def test_matrix_generated_from_role_permissions(self):
        staff_keys = sorted(
            {
                p
                for role, perms in ROLE_PERMISSIONS.items()
                if role in STAFF_ROLES
                for p in perms
            }
        )
        for p in ("order.accept", "order.complete", "pickup.assign", "kitchen.print_reprint"):
            self.assertIn(p, staff_keys)
        # Owner-only perms are covered by wildcard, not listed on staff sets.
        self.assertNotIn("finance.settle", staff_keys)
        self.assertNotIn("staff.manage", staff_keys)

        self.assertEqual(ROLE_PERMISSIONS[ROLE_OWNER], frozenset({"*"}))
        self.assertTrue(has_permission(ROLE_OWNER, "finance.settle"))
        self.assertTrue(has_permission(ROLE_OWNER, "staff.manage"))
        self.assertTrue(has_permission(ROLE_WAITER, "order.accept"))
        self.assertFalse(has_permission(ROLE_WAITER, "order.complete"))
        self.assertFalse(has_permission(ROLE_WAITER, "finance.settle"))
        self.assertTrue(has_permission(ROLE_KITCHEN, "order.complete"))
        self.assertFalse(has_permission(ROLE_KITCHEN, "pickup.assign"))
        self.assertTrue(has_permission(ROLE_KITCHEN, "kitchen.print_reprint"))
        self.assertIsNone(parse_staff_role("owner"))
        self.assertEqual(parse_staff_role("waiter"), "waiter")


class PasswordAndThrottleTest(unittest.IsolatedAsyncioTestCase):
    def test_password_policy(self):
        self.assertIsNotNone(validate_staff_password("1234567"))
        self.assertIsNotNone(validate_staff_password("        "))
        self.assertIsNotNone(validate_staff_password(""))
        self.assertIsNone(validate_staff_password("password123"))

    async def test_staff_login_throttle(self):
        with patch("app.core.merchant_auth.get_cache", new_callable=AsyncMock) as gc:
            gc.return_value = 10
            ok, msg = await staff_login_allowed(TENANT_A, "waiter_a", "1.2.3.4")
            self.assertFalse(ok)
            self.assertIn("过多", msg or "")


class FulfillmentDtoContractTest(unittest.TestCase):
    def test_forbidden_fields_absent(self):
        class O:
            id = 111
            status = "pending"
            table_no = "A1"
            pickup_no = "8"
            created_at = datetime(2026, 8, 8, 12, 0, 0)
            remark = "少辣"
            staff_note = ""
            dining_session_id = 9
            order_type = "dine_in"
            phone = "13800000000"
            total = 88
            customer_id = 7

        class I:
            name = "汤"
            qty = 1
            price = 12

        payload = serialize_fulfillment_order(O(), [I()])
        forbidden = {
            "total",
            "price",
            "payment_status",
            "payment_method",
            "phone",
            "openid",
            "customer_id",
            "discount_amount",
            "coupon_id",
            "wx_mchid",
            "api_key",
        }
        self.assertTrue(forbidden.isdisjoint(payload.keys()))
        self.assertTrue(forbidden.isdisjoint(payload["items"][0].keys()))
        for k in ("id", "status", "table_no", "pickup_no", "created_at", "items"):
            self.assertIn(k, payload)


class CrossTenantHttpIntegrationTest(unittest.IsolatedAsyncioTestCase):
    """Full ASGI path: HTTP → AuthMiddleware → router → service tenant filter."""

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

        self.waiter_id = generate_snowflake_id()
        self.kitchen_id = generate_snowflake_id()
        self.order_b_id = generate_snowflake_id()

        async with self.SessionLocal() as db:
            db.add_all(
                [
                    Tenant(
                        tenant_id=TENANT_A,
                        name="Shop A",
                        password_hash="x",
                        phone="13900000001",
                        status=True,
                        is_open=True,
                    ),
                    Tenant(
                        tenant_id=TENANT_B,
                        name="Shop B",
                        password_hash="x",
                        phone="13900000002",
                        status=True,
                        is_open=True,
                    ),
                    MerchantAccount(
                        id=self.waiter_id,
                        tenant_id=TENANT_A,
                        name="WA",
                        username="wa",
                        password_hash=FAKE_PW_HASH,
                        role="waiter",
                        status="active",
                    ),
                    MerchantAccount(
                        id=self.kitchen_id,
                        tenant_id=TENANT_A,
                        name="KA",
                        username="ka",
                        password_hash=FAKE_PW_HASH,
                        role="kitchen",
                        status="active",
                    ),
                    Order(
                        id=self.order_b_id,
                        tenant_id=TENANT_B,
                        table_no="B01",
                        total=25,
                        status="pending",
                        payment_status="paid",
                        payment_mode="postpay",
                        pickup_no="3",
                    ),
                ]
            )
            await db.flush()
            db.add(
                OrderItem(
                    id=generate_snowflake_id(),
                    order_id=self.order_b_id,
                    name="beef soup",
                    price=25,
                    qty=1,
                )
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
        # middleware tenant active cache
        self._cache_get = patch(
            "app.middleware.auth_middleware.get_cache",
            new_callable=AsyncMock,
            return_value=None,
        )
        # get_cache imported inside functions — patch cache_helper
        self._cache_helper_get = patch(
            "app.core.cache_helper.get_cache", new_callable=AsyncMock, return_value=None
        )
        self._cache_helper_set = patch(
            "app.core.cache_helper.set_cache", new_callable=AsyncMock, return_value=None
        )
        self._cache_helper_get.start()
        self._cache_helper_set.start()

        import httpx

        transport = httpx.ASGITransport(app=self.app)
        self.client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        self.app.dependency_overrides.clear()
        self._session_patch.stop()
        self._cache_helper_get.stop()
        self._cache_helper_set.stop()
        await self.engine.dispose()

    def _auth(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    async def test_waiter_cannot_touch_tenant_b_order_or_pickup(self):
        token = create_access_token(TENANT_A, role="waiter", account_id=self.waiter_id)
        oid = self.order_b_id

        r = await self.client.get(f"/api/v1/orders/{oid}", headers=self._auth(token))
        # staff cannot use full order GET (not in whitelist) → 403
        self.assertIn(r.status_code, (403, 404, 405))

        r = await self.client.patch(
            f"/api/v1/orders/{oid}/status",
            headers=self._auth(token),
            json={"status": "preparing"},
        )
        # Allowed permission but tenant filter → 404 body (or HTTP 200 with code 404)
        self.assertNotEqual(r.status_code, 500)
        if r.status_code == 200:
            body = r.json()
            self.assertEqual(body.get("code"), 404)
        else:
            self.assertIn(r.status_code, (403, 404))

        r = await self.client.patch(
            f"/api/v1/orders/{oid}/pickup-no",
            headers=self._auth(token),
            json={"pickup_no": "9"},
        )
        if r.status_code == 200:
            self.assertIn(r.json().get("code"), (404, 403, 400, 409))
        else:
            self.assertIn(r.status_code, (403, 404))

        # Confirm B order unchanged
        async with self.SessionLocal() as db:
            from sqlalchemy import select

            order = (
                await db.execute(select(Order).where(Order.id == self.order_b_id))
            ).scalar_one()
            self.assertEqual(order.status, "pending")
            self.assertEqual(order.pickup_no, "3")

    async def test_kitchen_cannot_complete_or_reprint_tenant_b(self):
        token = create_access_token(TENANT_A, role="kitchen", account_id=self.kitchen_id)
        oid = self.order_b_id

        r = await self.client.patch(
            f"/api/v1/orders/{oid}/status",
            headers=self._auth(token),
            json={"status": "done"},
        )
        if r.status_code == 200:
            self.assertEqual(r.json().get("code"), 404)
        else:
            self.assertIn(r.status_code, (403, 404))

        r = await self.client.post(
            f"/api/v1/orders/{oid}/reprint",
            headers=self._auth(token),
            json={"print_type": "kitchen"},
        )
        if r.status_code == 200:
            self.assertEqual(r.json().get("code"), 404)
        else:
            self.assertIn(r.status_code, (403, 404))

    async def test_sensitive_apis_forbidden_for_staff(self):
        for role, aid in (("waiter", self.waiter_id), ("kitchen", self.kitchen_id)):
            token = create_access_token(TENANT_A, role=role, account_id=aid)
            headers = self._auth(token)
            cases = [
                ("POST", "/api/v1/orders/settle-table", {"table_no": "A1"}),
                ("GET", "/api/v1/customers/", None),
                ("GET", "/api/v1/coupons/", None),
                ("GET", "/api/v1/tenant/settings", None),
                ("GET", "/api/v1/merchant-accounts", None),
                ("GET", "/api/v1/orders", None),
            ]
            for method, path, body in cases:
                if method == "POST":
                    r = await self.client.post(path, headers=headers, json=body or {})
                else:
                    r = await self.client.get(path, headers=headers)
                self.assertEqual(
                    r.status_code,
                    403,
                    msg=f"{role} {method} {path} => {r.status_code} {r.text}",
                )

        # kitchen cannot assign pickup
        token = create_access_token(TENANT_A, role="kitchen", account_id=self.kitchen_id)
        r = await self.client.patch(
            f"/api/v1/orders/{self.order_b_id}/pickup-no",
            headers=self._auth(token),
            json={"pickup_no": "1"},
        )
        self.assertEqual(r.status_code, 403)

    async def test_kitchen_cannot_reprint_non_kitchen_ticket_type(self):
        # Even for same-tenant order, non-kitchen print_type must 403 for staff
        same_order = generate_snowflake_id()
        async with self.SessionLocal() as db:
            db.add(
                Order(
                    id=same_order,
                    tenant_id=TENANT_A,
                    table_no="A9",
                    total=10,
                    status="preparing",
                    payment_status="paid",
                    payment_mode="postpay",
                )
            )
            await db.commit()
        token = create_access_token(TENANT_A, role="kitchen", account_id=self.kitchen_id)
        r = await self.client.post(
            f"/api/v1/orders/{same_order}/reprint",
            headers=self._auth(token),
            json={"print_type": "receipt"},
        )
        self.assertEqual(r.status_code, 403)

    async def test_workbench_dto_minimal(self):
        same_order = generate_snowflake_id()
        async with self.SessionLocal() as db:
            db.add(
                Order(
                    id=same_order,
                    tenant_id=TENANT_A,
                    table_no="A2",
                    total=99.5,
                    status="pending",
                    payment_status="paid",
                    payment_mode="postpay",
                    phone="13800001111",
                    pickup_no="7",
                )
            )
            await db.flush()
            db.add(
                OrderItem(
                    id=generate_snowflake_id(),
                    order_id=same_order,
                    name="noodles",
                    price=19,
                    qty=2,
                )
            )
            await db.commit()

        token = create_access_token(TENANT_A, role="waiter", account_id=self.waiter_id)
        r = await self.client.get("/api/v1/orders/workbench", headers=self._auth(token))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body.get("code"), 200)
        rows = body.get("data") or []
        self.assertTrue(any(str(x.get("id")) == str(same_order) for x in rows))
        row = next(x for x in rows if str(x.get("id")) == str(same_order))
        for bad in ("total", "phone", "payment_status", "payment_method", "customer_id"):
            self.assertNotIn(bad, row)
        self.assertNotIn("price", (row.get("items") or [{}])[0])


class StaffRouteDefaultDenyTest(unittest.TestCase):
    def test_unknown_api_denied(self):
        self.assertFalse(staff_route_allowed("GET", "/api/v1/stats/dashboard", ROLE_WAITER))
        self.assertFalse(staff_route_allowed("POST", "/api/v1/orders/settle-table", ROLE_KITCHEN))
        self.assertTrue(staff_route_allowed("GET", "/api/v1/orders/workbench", ROLE_WAITER))
        self.assertTrue(staff_route_allowed("GET", "/api/v1/orders", ROLE_OWNER))


if __name__ == "__main__":
    unittest.main()
