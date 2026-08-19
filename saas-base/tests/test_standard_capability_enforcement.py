"""Phase F1F-B — STANDARD capability enforcement regression tests.

Scope: docs/saas-subscription-audit.md Phase F1F-B. Proves MENU_ADVANCED_TOOLS
and interactive KITCHEN_PRINT are gated at their real API endpoints (never
before the check, always before any side effect), that STAFF_MANAGEMENT is
enforced both at mutation endpoints AND at the login/JWT-issuance step, and
-- the most important gate in this phase -- that AuthMiddleware rejects an
already-issued, unexpired staff JWT the moment the tenant's effective plan
drops STAFF_MANAGEMENT, on every subsequent request, with the owner
structurally exempt from ever reaching that check.

Real business endpoint functions are called directly (this session's
established pattern), and AuthMiddleware.dispatch() is exercised for real
(not mocked) with app.core.database.AsyncSessionLocal patched to the test's
own SQLite engine -- the exact precedent already established in
test_auth_middleware_tenant_status.py.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request
from starlette.responses import Response

from app.api.v1.menu import (
    generate_dish_desc,
    import_dish_library_batch,
    import_menu_batch,
    parse_menu_from_text,
    DishDescRequest,
    DishLibraryImportBatchRequest,
    DishLibraryImportItem,
    MenuTextParseRequest,
)
from app.api.v1.merchant_accounts import (
    StaffCreateRequest,
    StaffLoginRequest,
    StaffResetPasswordRequest,
    create_merchant_account,
    reset_merchant_account_password,
    staff_login,
)
from app.api.v1.orders import OrderReprintBody, reprint_order_ticket
from app.api.v1.queue import print_test_queue_ticket
from app.api.v1.tenant import PrinterConfigRequest, update_printer_config
from app.config import settings
from app.core.security import get_password_hash
from app.core.tenant_context import TenantContext
from app.middleware.auth_middleware import AuthMiddleware
from app.models.base import Base
from app.models.menu_item import MenuItem
from app.models.merchant_account import MerchantAccount
from app.models.order import Order
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.services.subscription_service import STATUS_ACTIVE, SubscriptionService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@event.listens_for(Plan, "before_insert")
def _assign_plan_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Subscription, "before_insert")
def _assign_subscription_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Tenant, "before_insert")
def _assign_tenant_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(MerchantAccount, "before_insert")
def _assign_account_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(MenuItem, "before_insert")
def _assign_menu_item_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Order, "before_insert")
def _assign_order_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_request(*, tenant_id=None, token_type="merchant", method="GET", path="/x", body=None):
    request = Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [(b"authorization", b"Bearer dummy")] if tenant_id else [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    if tenant_id is not None:
        request.state.tenant_id = tenant_id
        request.state.token_type = token_type
    if body is not None:
        async def _body():
            import json
            return json.dumps(body).encode()
        request.body = _body
    return request


def make_raw_request(path="/api/v1/auth/me", method="GET"):
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [(b"authorization", b"Bearer dummy")],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


async def dummy_call_next(request):
    return Response(status_code=200)


TENANT_FREE = "tenant-f1fb-free"
TENANT_STANDARD = "tenant-f1fb-standard"
TENANT_PRO = "tenant-f1fb-pro"


class BaseEntitlementEnforcementTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add_all(
            [
                Tenant(tenant_id=TENANT_FREE, name="Free Tenant", password_hash="x", status=True),
                Tenant(tenant_id=TENANT_STANDARD, name="Standard Tenant", password_hash="x", status=True),
                Tenant(tenant_id=TENANT_PRO, name="Pro Tenant", password_hash="x", status=True),
                Plan(code="FREE", name="免费版", is_active=True, price_month_cents=0, price_year_cents=0, sort_order=0),
                Plan(code="STANDARD", name="普通版", is_active=True, price_month_cents=5900, price_year_cents=60900, sort_order=1),
                Plan(code="PRO", name="专业版", is_active=True, price_month_cents=9900, price_year_cents=102200, sort_order=2),
            ]
        )
        await self.db.commit()
        self.subscription_service = SubscriptionService(self.db)
        await self._activate(TENANT_STANDARD, "STANDARD")
        await self._activate(TENANT_PRO, "PRO")

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _activate(self, tenant_id: str, plan_code: str, *, ends_delta=timedelta(days=30)):
        plan = await self.subscription_service.get_plan_by_code(plan_code)
        now = datetime.utcnow()
        sub = Subscription(
            tenant_id=tenant_id, plan_id=plan.id, status=STATUS_ACTIVE,
            started_at=now, ends_at=now + ends_delta,
        )
        self.db.add(sub)
        await self.db.commit()
        await self.db.refresh(sub)
        return sub

    async def _menu_item_count(self, tenant_id: str) -> int:
        result = await self.db.execute(select(MenuItem).where(MenuItem.tenant_id == tenant_id))
        return len(result.scalars().all())


# ---------------------------------------------------------------------------
# MENU_ADVANCED_TOOLS
# ---------------------------------------------------------------------------

class MenuAdvancedEnforcementTest(BaseEntitlementEnforcementTest):
    async def test_generate_desc_free_denied_ai_not_called(self):
        with patch("app.services.ai_menu_service.generate_dish_description", new=AsyncMock(return_value="x")) as mock_ai:
            resp = await generate_dish_desc(
                DishDescRequest(name="宫保鸡丁"), make_request(tenant_id=TENANT_FREE), db=self.db,
            )
        self.assertEqual(resp.code, 403)
        self.assertEqual(resp.data["error_code"], "PLAN_CAPABILITY_REQUIRED")
        self.assertEqual(resp.data["capability"], "MENU_ADVANCED_TOOLS")
        self.assertEqual(resp.data["effective_plan_code"], "FREE")
        self.assertEqual(resp.data["required_plan_codes"], ["STANDARD", "PRO"])
        mock_ai.assert_not_awaited()

    async def test_generate_desc_standard_allowed(self):
        with patch("app.services.ai_menu_service.generate_dish_description", new=AsyncMock(return_value="好吃")):
            resp = await generate_dish_desc(
                DishDescRequest(name="宫保鸡丁"), make_request(tenant_id=TENANT_STANDARD), db=self.db,
            )
        self.assertEqual(resp.code, 200)

    async def test_generate_desc_pro_allowed(self):
        with patch("app.services.ai_menu_service.generate_dish_description", new=AsyncMock(return_value="好吃")):
            resp = await generate_dish_desc(
                DishDescRequest(name="宫保鸡丁"), make_request(tenant_id=TENANT_PRO), db=self.db,
            )
        self.assertEqual(resp.code, 200)

    async def test_parse_text_free_denied_ai_not_called(self):
        with patch("app.services.ai_menu_service.parse_menu_text", new=AsyncMock(return_value=[])) as mock_ai:
            resp = await parse_menu_from_text(
                MenuTextParseRequest(text="宫保鸡丁 28元"), make_request(tenant_id=TENANT_FREE), db=self.db,
            )
        self.assertEqual(resp.code, 403)
        mock_ai.assert_not_awaited()

    async def test_import_menu_batch_free_denied_no_rows_created(self):
        before = await self._menu_item_count(TENANT_FREE)
        req = make_request(
            tenant_id=TENANT_FREE, method="POST", path="/api/v1/menu/import-batch",
            body={"items": [{"name": "test dish", "price": 10}]},
        )
        resp = await import_menu_batch(req, db=self.db)
        self.assertEqual(resp.code, 403)
        after = await self._menu_item_count(TENANT_FREE)
        self.assertEqual(before, after, "FREE denial must happen before any MenuItem is inserted")

    async def test_import_menu_batch_standard_allowed(self):
        before = await self._menu_item_count(TENANT_STANDARD)
        req = make_request(
            tenant_id=TENANT_STANDARD, method="POST", path="/api/v1/menu/import-batch",
            body={"items": [{"name": "test dish", "price": 10}]},
        )
        resp = await import_menu_batch(req, db=self.db)
        self.assertEqual(resp.code, 200)
        after = await self._menu_item_count(TENANT_STANDARD)
        self.assertEqual(after, before + 1)

    async def test_dish_library_import_batch_free_denied_no_rows_created(self):
        before = await self._menu_item_count(TENANT_FREE)
        resp = await import_dish_library_batch(
            DishLibraryImportBatchRequest(items=[DishLibraryImportItem(id="1")]),
            make_request(tenant_id=TENANT_FREE), db=self.db,
        )
        self.assertEqual(resp.code, 403)
        after = await self._menu_item_count(TENANT_FREE)
        self.assertEqual(before, after)


# ---------------------------------------------------------------------------
# KITCHEN_PRINT (interactive only)
# ---------------------------------------------------------------------------

class KitchenPrintInteractiveEnforcementTest(BaseEntitlementEnforcementTest):
    async def test_printer_config_mutation_free_denied_config_unchanged(self):
        result = await self.db.execute(select(Tenant).where(Tenant.tenant_id == TENANT_FREE))
        tenant = result.scalar_one()
        tenant.feieyun_sn = None
        await self.db.commit()

        # update_printer_config resolves tenant via TenantContext (a
        # contextvar set elsewhere by TenantMiddleware in production), not
        # from a Request param -- set it directly, matching how
        # menu.py's import_menu_batch also calls TenantContext.set_tenant_id().
        TenantContext.set_tenant_id(TENANT_FREE)
        try:
            resp = await update_printer_config(
                PrinterConfigRequest(feieyun_sn="SN123", feieyun_key="KEY123"), db=self.db,
            )
        finally:
            TenantContext.clear()

        self.assertEqual(resp.code, 403)
        self.assertEqual(resp.data["error_code"], "PLAN_CAPABILITY_REQUIRED")
        self.assertEqual(resp.data["capability"], "KITCHEN_PRINT")

        await self.db.refresh(tenant)
        self.assertIsNone(tenant.feieyun_sn, "FREE denial must happen before the printer config is written")

    async def test_printer_config_mutation_standard_allowed(self):
        TenantContext.set_tenant_id(TENANT_STANDARD)
        try:
            resp = await update_printer_config(
                PrinterConfigRequest(feieyun_sn="SN123", feieyun_key="KEY123"), db=self.db,
            )
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 200)

    async def test_test_print_free_denied_provider_not_called(self):
        with patch("app.api.v1.queue.print_queue_test_ticket", new=AsyncMock(return_value={"success": True})) as mock_print:
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as ctx:
                await print_test_queue_ticket(make_request(tenant_id=TENANT_FREE), db=self.db)
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertEqual(ctx.exception.detail["code"], "PLAN_CAPABILITY_REQUIRED")
        mock_print.assert_not_awaited()

    async def test_test_print_standard_allowed(self):
        with patch("app.api.v1.queue.print_queue_test_ticket", new=AsyncMock(return_value={"success": True, "provider": "kuaimai"})):
            resp = await print_test_queue_ticket(make_request(tenant_id=TENANT_STANDARD), db=self.db)
        self.assertTrue(resp["success"])

    def _owner_reprint_request(self, tenant_id: str):
        req = make_request(tenant_id=tenant_id, method="POST", path="/api/v1/orders/1/reprint")
        req.state.role = "owner"
        req.state.account_id = None
        req.state.account_name = None
        req.state.account_username = None
        return req

    async def _make_paid_order(self, tenant_id: str) -> Order:
        order = Order(
            tenant_id=tenant_id, status="done", payment_status="paid", payment_mode="prepay",
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def test_manual_reprint_free_denied_no_print_call(self):
        order = await self._make_paid_order(TENANT_FREE)
        with patch("app.api.v1.orders._print_paid_order_ticket", new=AsyncMock(return_value={"success": True})) as mock_print:
            resp = await reprint_order_ticket(
                str(order.id), self._owner_reprint_request(TENANT_FREE), body=None, db=self.db,
            )
        self.assertEqual(resp.code, 403)
        self.assertEqual(resp.data["error_code"], "PLAN_CAPABILITY_REQUIRED")
        self.assertEqual(resp.data["capability"], "KITCHEN_PRINT")
        mock_print.assert_not_awaited()

    async def test_manual_reprint_standard_allowed(self):
        order = await self._make_paid_order(TENANT_STANDARD)
        with patch("app.api.v1.orders._print_paid_order_ticket", new=AsyncMock(return_value={"success": True})) as mock_print:
            resp = await reprint_order_ticket(
                str(order.id), self._owner_reprint_request(TENANT_STANDARD), body=None, db=self.db,
            )
        self.assertEqual(resp.code, 200)
        mock_print.assert_awaited_once()


# ---------------------------------------------------------------------------
# STAFF_MANAGEMENT -- mutation endpoints
# ---------------------------------------------------------------------------

class StaffMutationEnforcementTest(BaseEntitlementEnforcementTest):
    def _principal_request(self, tenant_id: str):
        req = make_request(tenant_id=tenant_id, method="POST", path="/api/v1/merchant-accounts")
        req.state.role = "owner"
        req.state.account_id = None
        req.state.account_name = None
        req.state.account_username = None
        return req

    async def test_create_staff_free_denied(self):
        req = self._principal_request(TENANT_FREE)
        resp = await create_merchant_account(
            StaffCreateRequest(name="小王", role="frontdesk", username="xw", password="pw123456"),
            req, db=self.db,
        )
        self.assertEqual(resp.code, 403)
        self.assertEqual(resp.data["error_code"], "PLAN_CAPABILITY_REQUIRED")
        self.assertEqual(resp.data["capability"], "STAFF_MANAGEMENT")

    async def test_create_staff_standard_allowed(self):
        req = self._principal_request(TENANT_STANDARD)
        resp = await create_merchant_account(
            StaffCreateRequest(name="小王", role="frontdesk", username="xw2", password="pw123456"),
            req, db=self.db,
        )
        self.assertEqual(resp.code, 200)

    async def test_reset_password_free_denied(self):
        # Existing staff row under a tenant that is currently FREE (e.g. a
        # downgraded former STANDARD/PRO tenant) -- data preserved (Phase 11),
        # but the reset-password MUTATION must still be denied.
        account = MerchantAccount(
            tenant_id=TENANT_FREE, name="小赵", username="xz",
            password_hash=get_password_hash("old-password"), role="waiter", status="active",
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)

        req = self._principal_request(TENANT_FREE)
        resp = await reset_merchant_account_password(
            str(account.id), StaffResetPasswordRequest(password="newpassword123"), req, db=self.db,
        )
        self.assertEqual(resp.code, 403)
        self.assertEqual(resp.data["error_code"], "PLAN_CAPABILITY_REQUIRED")


# ---------------------------------------------------------------------------
# STAFF_MANAGEMENT -- login issuance (independent of AuthMiddleware)
# ---------------------------------------------------------------------------

class StaffLoginGateTest(BaseEntitlementEnforcementTest):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self._original_redis_enabled = settings.REDIS_ENABLED
        settings.REDIS_ENABLED = False
        self._session_patch = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._session_patch.start()

    async def asyncTearDown(self):
        self._session_patch.stop()
        settings.REDIS_ENABLED = self._original_redis_enabled
        await super().asyncTearDown()

    async def _make_staff_account(self, tenant_id: str, username: str, password: str) -> MerchantAccount:
        account = MerchantAccount(
            tenant_id=tenant_id, name="前台小李", username=username,
            password_hash=get_password_hash(password), role="frontdesk", status="active",
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return account

    async def test_free_denies_login_not_disguised_as_wrong_password(self):
        result = await self.db.execute(select(Tenant).where(Tenant.tenant_id == TENANT_FREE))
        tenant = result.scalar_one()
        tenant.phone = "13800000001"
        await self.db.commit()
        await self._make_staff_account(TENANT_FREE, "staff-free", "correct-password-1")

        from starlette.responses import Response as StarletteResponse
        req = Request({"type": "http", "method": "POST", "path": "/api/v1/login/staff", "headers": [], "query_string": b"", "server": ("testserver", 80), "scheme": "http", "client": ("testclient", 50000)})
        resp = await staff_login(
            req, StarletteResponse(),
            StaffLoginRequest(shop_phone="13800000001", username="staff-free", password="correct-password-1"),
            db=self.db,
        )
        self.assertEqual(resp.code, 403)
        self.assertEqual(resp.data["error_code"], "PLAN_CAPABILITY_REQUIRED")
        # Must not be misreported as a credential failure.
        self.assertNotIn("密码", resp.msg)
        self.assertNotIn("账号或密码", resp.msg)

    async def test_missing_plan_catalog_fails_closed_not_login_grant(self):
        """PHASE F1F-BH: a genuine data-integrity error (no FREE plan row --
        the exact gap pre-existing, subscription-unaware test fixtures have)
        must NOT be treated as an implicit capability grant. An otherwise-
        valid staff credential must still be denied a JWT when entitlement
        resolution itself is broken -- PAID_FEATURE_FAILS_CLOSED."""
        result = await self.db.execute(select(Plan).where(Plan.code == "FREE"))
        free_plan = result.scalar_one()
        await self.db.delete(free_plan)
        await self.db.commit()

        result = await self.db.execute(select(Tenant).where(Tenant.tenant_id == TENANT_FREE))
        tenant = result.scalar_one()
        tenant.phone = "13800000003"
        await self.db.commit()
        await self._make_staff_account(TENANT_FREE, "staff-noplan", "correct-password-3")

        from starlette.responses import Response as StarletteResponse
        req = Request({"type": "http", "method": "POST", "path": "/api/v1/login/staff", "headers": [], "query_string": b"", "server": ("testserver", 80), "scheme": "http", "client": ("testclient", 50000)})
        resp = await staff_login(
            req, StarletteResponse(),
            StaffLoginRequest(shop_phone="13800000003", username="staff-noplan", password="correct-password-3"),
            db=self.db,
        )
        self.assertNotEqual(resp.code, 200, "a data-integrity error must never itself issue a staff JWT")
        self.assertEqual(resp.code, 500)
        self.assertEqual(resp.data["error_code"], "INTERNAL_ERROR")
        self.assertIsNone(resp.data.get("token"))

    async def test_standard_allows_login(self):
        result = await self.db.execute(select(Tenant).where(Tenant.tenant_id == TENANT_STANDARD))
        tenant = result.scalar_one()
        tenant.phone = "13800000002"
        await self.db.commit()
        await self._make_staff_account(TENANT_STANDARD, "staff-std", "correct-password-2")

        from starlette.responses import Response as StarletteResponse
        req = Request({"type": "http", "method": "POST", "path": "/api/v1/login/staff", "headers": [], "query_string": b"", "server": ("testserver", 80), "scheme": "http", "client": ("testclient", 50000)})
        resp = await staff_login(
            req, StarletteResponse(),
            StaffLoginRequest(shop_phone="13800000002", username="staff-std", password="correct-password-2"),
            db=self.db,
        )
        self.assertEqual(resp.code, 200)


# ---------------------------------------------------------------------------
# AuthMiddleware -- existing staff token downgrade enforcement (Phase F1F-B's
# most important gate)
# ---------------------------------------------------------------------------

class AuthMiddlewareStaffDowngradeTest(BaseEntitlementEnforcementTest):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self._original_redis_enabled = settings.REDIS_ENABLED
        settings.REDIS_ENABLED = False
        self._session_patch = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._session_patch.start()
        self.middleware = AuthMiddleware(app=None)

    async def asyncTearDown(self):
        self._session_patch.stop()
        settings.REDIS_ENABLED = self._original_redis_enabled
        await super().asyncTearDown()

    async def _make_staff_account(self, tenant_id: str, role="frontdesk") -> MerchantAccount:
        account = MerchantAccount(
            tenant_id=tenant_id, name="前台小李", username=f"staff-{tenant_id}",
            password_hash=get_password_hash("irrelevant"), role=role, status="active",
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return account

    def _staff_payload(self, tenant_id: str, account_id) -> dict:
        return {"tenant_id": tenant_id, "type": "merchant", "account_id": str(account_id), "sub": str(account_id)}

    def _owner_payload(self, tenant_id: str) -> dict:
        return {"tenant_id": tenant_id, "type": "merchant", "sub": tenant_id}

    async def test_staff_token_allowed_while_standard(self):
        account = await self._make_staff_account(TENANT_STANDARD)
        with patch("app.middleware.auth_middleware.verify_token", return_value=self._staff_payload(TENANT_STANDARD, account.id)):
            response = await self.middleware.dispatch(make_raw_request(), dummy_call_next)
        self.assertEqual(response.status_code, 200)

    async def test_staff_downgrade_existing_token_denied_next_request(self):
        """PHASE 17 -- the core contract test: same, still-valid staff token,
        subscription transitions from STANDARD to FREE between two requests,
        and the SAME token must be denied on the second request without any
        new login."""
        account = await self._make_staff_account(TENANT_STANDARD)
        payload = self._staff_payload(TENANT_STANDARD, account.id)

        with patch("app.middleware.auth_middleware.verify_token", return_value=payload):
            first = await self.middleware.dispatch(make_raw_request(), dummy_call_next)
        self.assertEqual(first.status_code, 200, "sanity: token must work while STANDARD")

        # Downgrade: expire the STANDARD subscription (test fixture manipulation
        # of Subscription state, NOT of the entitlement engine itself).
        result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == TENANT_STANDARD))
        sub = result.scalars().first()
        sub.ends_at = datetime.utcnow() - timedelta(seconds=1)
        await self.db.commit()

        with patch("app.middleware.auth_middleware.verify_token", return_value=payload):
            second = await self.middleware.dispatch(make_raw_request(), dummy_call_next)
        self.assertEqual(second.status_code, 403)
        import json
        body = json.loads(second.body)
        self.assertEqual(body["data"]["error_code"], "PLAN_CAPABILITY_REQUIRED")
        self.assertEqual(body["data"]["capability"], "STAFF_MANAGEMENT")
        self.assertEqual(body["data"]["effective_plan_code"], "FREE")

    async def test_staff_reupgrade_same_token_allowed_again(self):
        """PHASE 18 -- STAFF_DATA_PRESERVED: no re-creation of the staff row,
        no re-login; re-extending the SAME tenant's subscription re-enables
        the SAME still-unexpired token immediately."""
        account = await self._make_staff_account(TENANT_STANDARD)
        payload = self._staff_payload(TENANT_STANDARD, account.id)

        result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == TENANT_STANDARD))
        sub = result.scalars().first()
        sub.ends_at = datetime.utcnow() - timedelta(seconds=1)
        await self.db.commit()

        with patch("app.middleware.auth_middleware.verify_token", return_value=payload):
            denied = await self.middleware.dispatch(make_raw_request(), dummy_call_next)
        self.assertEqual(denied.status_code, 403)

        # Re-upgrade: same tenant, same staff row, new unexpired subscription.
        await self._activate(TENANT_STANDARD, "PRO", ends_delta=timedelta(days=30))

        with patch("app.middleware.auth_middleware.verify_token", return_value=payload):
            restored = await self.middleware.dispatch(make_raw_request(), dummy_call_next)
        self.assertEqual(restored.status_code, 200)

        # No new staff row was created for this re-upgrade.
        result = await self.db.execute(select(MerchantAccount).where(MerchantAccount.tenant_id == TENANT_STANDARD))
        accounts = result.scalars().all()
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].id, account.id)

    async def test_owner_structurally_exempt_from_staff_gate(self):
        """PHASE 14/19 -- FREE owner's own JWT must never be touched by the
        STAFF_MANAGEMENT gate, on a real FREE-core order-management route."""
        with patch("app.middleware.auth_middleware.verify_token", return_value=self._owner_payload(TENANT_FREE)):
            response = await self.middleware.dispatch(
                make_raw_request(path="/api/v1/orders/workbench", method="GET"), dummy_call_next,
            )
        self.assertEqual(response.status_code, 200)

    async def test_inactive_plan_existing_standard_rights_retained(self):
        """PHASE 21 (business-level) -- Plan.is_active=False must not strip
        an unexpired existing subscription's staff rights."""
        result = await self.db.execute(select(Plan).where(Plan.code == "STANDARD"))
        plan = result.scalar_one()
        plan.is_active = False
        await self.db.commit()

        account = await self._make_staff_account(TENANT_STANDARD)
        with patch("app.middleware.auth_middleware.verify_token", return_value=self._staff_payload(TENANT_STANDARD, account.id)):
            response = await self.middleware.dispatch(make_raw_request(), dummy_call_next)
        self.assertEqual(response.status_code, 200)

    async def test_entitlement_system_error_fails_closed_not_implicit_grant(self):
        """PHASE F1F-BH: if entitlement resolution itself errors (e.g. a
        missing Plan catalog row -- a system/data problem, not a legitimate
        "lacks capability" outcome), the middleware must fail CLOSED
        (503) rather than letting an unrelated data problem silently grant
        staff access platform-wide. PAID_FEATURE_FAILS_CLOSED: the request
        must not proceed as staff, and must not be misreported as
        PLAN_CAPABILITY_REQUIRED (that would misrepresent a data-integrity
        bug as a legitimate plan-tier denial)."""
        # Delete the FREE plan row to force a genuine data-integrity error
        # inside SubscriptionService, unrelated to this tenant's own state.
        result = await self.db.execute(select(Plan).where(Plan.code == "FREE"))
        free_plan = result.scalar_one()
        await self.db.delete(free_plan)
        await self.db.commit()

        account = await self._make_staff_account(TENANT_FREE)
        with patch("app.middleware.auth_middleware.verify_token", return_value=self._staff_payload(TENANT_FREE, account.id)):
            response = await self.middleware.dispatch(make_raw_request(), dummy_call_next)
        self.assertEqual(response.status_code, 503, "a system error resolving entitlement must fail closed, not proceed as staff")
        import json
        body = json.loads(response.body)
        self.assertEqual(body["data"]["error_code"], "INTERNAL_ERROR")
        self.assertNotEqual(body["data"].get("error_code"), "PLAN_CAPABILITY_REQUIRED")

    async def test_tenant_isolation_free_vs_standard(self):
        free_account = await self._make_staff_account(TENANT_FREE)
        standard_account = await self._make_staff_account(TENANT_STANDARD)

        with patch("app.middleware.auth_middleware.verify_token", return_value=self._staff_payload(TENANT_FREE, free_account.id)):
            free_resp = await self.middleware.dispatch(make_raw_request(), dummy_call_next)
        with patch("app.middleware.auth_middleware.verify_token", return_value=self._staff_payload(TENANT_STANDARD, standard_account.id)):
            standard_resp = await self.middleware.dispatch(make_raw_request(), dummy_call_next)

        self.assertEqual(free_resp.status_code, 403)
        self.assertEqual(standard_resp.status_code, 200)


# ---------------------------------------------------------------------------
# Phase F1F-BH -- entitlement failure semantics: PAID_FEATURE_FAILS_CLOSED.
# A system/data error resolving entitlement must never be treated as an
# implicit capability grant, and must never be misreported as
# PLAN_CAPABILITY_REQUIRED (that would misrepresent a data-integrity bug as
# a legitimate plan-tier denial).
# ---------------------------------------------------------------------------

class MissingFreePlanFailsClosedTest(BaseEntitlementEnforcementTest):
    async def test_missing_free_plan_fails_closed_not_2xx_no_side_effect(self):
        """TENANT_FREE has no Subscription row (BaseEntitlementEnforcementTest
        never activates it) -- resolving its effective plan falls through to
        the FREE-plan-catalog lookup. Deleting that FREE Plan row turns this
        into a genuine data-integrity error, not a legitimate "lacks
        capability" outcome. A STANDARD-only interactive endpoint must
        neither return 2xx nor run its paid side effect, and must not be
        misreported as PLAN_CAPABILITY_REQUIRED."""
        result = await self.db.execute(select(Plan).where(Plan.code == "FREE"))
        free_plan = result.scalar_one()
        await self.db.delete(free_plan)
        await self.db.commit()

        with patch("app.services.ai_menu_service.generate_dish_description", new=AsyncMock(return_value="x")) as mock_ai:
            resp = await generate_dish_desc(
                DishDescRequest(name="宫保鸡丁"), make_request(tenant_id=TENANT_FREE), db=self.db,
            )
        self.assertNotIn(resp.code, (200, 201, 204), "a data-integrity error must never resolve to success")
        self.assertEqual(resp.code, 500)
        self.assertEqual(resp.data["error_code"], "INTERNAL_ERROR")
        self.assertNotEqual(resp.data["error_code"], "PLAN_CAPABILITY_REQUIRED")
        mock_ai.assert_not_awaited()


class UnknownEffectivePlanFailsClosedTest(BaseEntitlementEnforcementTest):
    async def test_unknown_plan_code_fails_closed_not_defaulted(self):
        """An effective_plan.code outside FREE/STANDARD/PRO is a data/policy
        integrity error (app/services/entitlement_service.py's
        UnknownEffectivePlanCodeError) -- must never be silently treated as
        FREE (denied) or as an unrecognized-but-granted tier (allowed).
        Either would hide the underlying inconsistency; the only correct
        outcome is a fail-closed system error with no paid side effect."""
        tenant_id = "tenant-f1fb-unknown-plan"
        self.db.add(Tenant(tenant_id=tenant_id, name="Unknown Plan Tenant", password_hash="x", status=True))
        self.db.add(Plan(code="ENTERPRISE", name="未知档位", is_active=True, price_month_cents=0, price_year_cents=0, sort_order=9))
        await self.db.commit()
        plan = await self.subscription_service.get_plan_by_code("ENTERPRISE")
        now = datetime.utcnow()
        self.db.add(Subscription(
            tenant_id=tenant_id, plan_id=plan.id, status=STATUS_ACTIVE,
            started_at=now, ends_at=now + timedelta(days=30),
        ))
        await self.db.commit()

        with patch("app.services.ai_menu_service.generate_dish_description", new=AsyncMock(return_value="x")) as mock_ai:
            resp = await generate_dish_desc(
                DishDescRequest(name="宫保鸡丁"), make_request(tenant_id=tenant_id), db=self.db,
            )
        self.assertNotIn(resp.code, (200, 201, 204))
        self.assertEqual(resp.code, 500)
        self.assertEqual(resp.data["error_code"], "INTERNAL_ERROR")
        mock_ai.assert_not_awaited()


class StaffExistingTokenDataErrorFailsClosedTest(BaseEntitlementEnforcementTest):
    """AuthMiddleware, real dispatch -- an existing, otherwise-valid staff
    JWT must be denied (not proceed to the business route) when entitlement
    resolution raises for a reason other than a clean plan-tier denial."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self._original_redis_enabled = settings.REDIS_ENABLED
        settings.REDIS_ENABLED = False
        self._session_patch = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._session_patch.start()
        self.middleware = AuthMiddleware(app=None)

    async def asyncTearDown(self):
        self._session_patch.stop()
        settings.REDIS_ENABLED = self._original_redis_enabled
        await super().asyncTearDown()

    async def test_staff_token_denied_when_entitlement_resolution_raises(self):
        account = MerchantAccount(
            tenant_id=TENANT_STANDARD, name="前台", username="staff-dataerr",
            password_hash=get_password_hash("irrelevant"), role="frontdesk", status="active",
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        payload = {"tenant_id": TENANT_STANDARD, "type": "merchant", "account_id": str(account.id), "sub": str(account.id)}

        route_called = {"value": False}

        async def call_next(request):
            route_called["value"] = True
            return Response(status_code=200)

        from app.services.entitlement_service import EntitlementService

        with patch("app.middleware.auth_middleware.verify_token", return_value=payload), \
             patch.object(EntitlementService, "require_capability", new=AsyncMock(side_effect=RuntimeError("entitlement resolution exploded"))):
            response = await self.middleware.dispatch(make_raw_request(), call_next)

        self.assertEqual(response.status_code, 503, "entitlement resolution errors must deny, not proceed as staff")
        self.assertFalse(route_called["value"], "business route must never execute when entitlement resolution fails")
        import json
        body = json.loads(response.body)
        self.assertEqual(body["data"]["error_code"], "INTERNAL_ERROR")


class OwnerStructuralExemptionUnderEntitlementFailureTest(BaseEntitlementEnforcementTest):
    """Even if EntitlementService itself is broken for STAFF_MANAGEMENT,
    a FREE owner's own request must never reach that resolution at all --
    the owner branch is structurally exempt (role != ROLE_OWNER gates the
    entire staff entitlement block), not merely a check that happens to
    pass. The entitlement engine must not become a new dependency for
    owner-core requests."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self._original_redis_enabled = settings.REDIS_ENABLED
        settings.REDIS_ENABLED = False
        self._session_patch = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._session_patch.start()
        self.middleware = AuthMiddleware(app=None)

    async def asyncTearDown(self):
        self._session_patch.stop()
        settings.REDIS_ENABLED = self._original_redis_enabled
        await super().asyncTearDown()

    async def test_owner_request_never_calls_broken_entitlement_engine(self):
        payload = {"tenant_id": TENANT_FREE, "type": "merchant", "sub": TENANT_FREE}

        from app.services.entitlement_service import EntitlementService

        with patch("app.middleware.auth_middleware.verify_token", return_value=payload), \
             patch.object(EntitlementService, "require_capability", new=AsyncMock(side_effect=RuntimeError("entitlement resolution exploded"))) as mock_require:
            response = await self.middleware.dispatch(
                make_raw_request(path="/api/v1/orders/workbench", method="GET"), dummy_call_next,
            )

        self.assertEqual(response.status_code, 200, "owner must remain structurally exempt from the staff entitlement gate")
        mock_require.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
