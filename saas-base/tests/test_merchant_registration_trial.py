"""Phase 04 — Merchant Self Registration + Trial Integration.
Phase 01 (Merchant Provisioning Foundation) update: registration now also
requires a REGISTER-purpose SMS OTP (proving phone ownership, the same way
login already does) and delegates the actual Tenant+TenantConfig+trial
creation to MerchantProvisioningService instead of orchestrating
TenantService/SubscriptionService inline in the router.

Phase 02 (Merchant Signup + Activation) update: PLATFORM_REGISTER_KEY is now
a pure server-side availability switch (registration is open whenever an
operator has set ANY non-empty value in the server's own environment) -- the
client no longer supplies or knows a key at all. This closes an architecture
gap the Phase 02 audit flagged: the old exact-match-against-a-client-supplied-
value design would have required a real server secret to live inside the
public admin-h5 bundle (or every request, either way extractable via
DevTools) for self-registration to ever work from a browser.

Scope: docs/saas-subscription-audit.md Phase 04, plus Phase 01's OTP-gate and
provisioning-unification work, plus Phase 02's registration-gate and payment-
mode changes. POST /api/v1/register is still the same URL/method; the request
requires `code` (a REGISTER-purpose OTP obtained from POST /api/v1/register/
code first) and no longer accepts/needs a platform_key field. A successful
registration still creates a 30-day PRO trial Subscription in the SAME
database transaction as the Tenant -- so "registration succeeded" is an
all-or-nothing guarantee covering both rows, proven here by directly querying
the database after simulated failures, not by asserting a mock was called.
"""

from __future__ import annotations

import asyncio
import inspect
import unittest
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1 import login as login_module
from app.config import settings
from app.models.base import Base
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.schemas.tenant import RegisterCodeRequest, RegisterRequest
from app.services import tencent_sms_service as sms_module
from app.services.subscription_service import STATUS_TRIAL, SubscriptionService
from app.services.tencent_sms_service import SmsPurpose, TencentSmsService
from app.services.tenant_service import TenantService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TEST_REGISTER_KEY = "test-registration-key"
VALID_CODE = "654321"


@event.listens_for(Plan, "before_insert")
def _assign_plan_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Subscription, "before_insert")
def _assign_subscription_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/register",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


class MerchantRegistrationTrialTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self._original_key = settings.PLATFORM_REGISTER_KEY
        settings.PLATFORM_REGISTER_KEY = TEST_REGISTER_KEY

    async def asyncTearDown(self):
        settings.PLATFORM_REGISTER_KEY = self._original_key
        sms_module._memory_cache.clear()
        await self.db.close()
        await self.engine.dispose()

    def _register_data(self, phone: str, name: str = "老王川菜馆", code: str = VALID_CODE) -> RegisterRequest:
        return RegisterRequest(name=name, phone=phone, code=code)

    async def _store_valid_register_code(self, phone: str, code: str = VALID_CODE) -> None:
        await TencentSmsService().store_login_code(phone, code, purpose=SmsPurpose.REGISTER)

    async def _tenant_count(self, phone: str) -> int:
        result = await self.db.execute(select(Tenant).where(Tenant.phone == phone))
        return len(result.scalars().all())

    async def _subscription_count_for_phone(self, phone: str) -> int:
        tenant_result = await self.db.execute(select(Tenant).where(Tenant.phone == phone))
        tenant = tenant_result.scalar_one_or_none()
        if tenant is None:
            return 0
        sub_result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == tenant.tenant_id))
        return len(sub_result.scalars().all())

    # ---- Tests 1-5: successful registration creates Tenant + 30-day PRO Trial -

    async def test_valid_registration_creates_tenant(self):
        await self._store_valid_register_code("13800000001")
        res = await login_module.register(make_request(), self._register_data("13800000001"), db=self.db)
        self.assertEqual(res.code, 200, res.msg)
        self.assertEqual(await self._tenant_count("13800000001"), 1)

    async def test_valid_registration_creates_exactly_one_trial_subscription(self):
        await self._store_valid_register_code("13800000002")
        res = await login_module.register(make_request(), self._register_data("13800000002"), db=self.db)
        self.assertEqual(res.code, 200, res.msg)
        self.assertEqual(await self._subscription_count_for_phone("13800000002"), 1)

    async def test_trial_plan_is_pro_and_status_is_trial_and_30_days(self):
        await self._store_valid_register_code("13800000003")
        res = await login_module.register(make_request(), self._register_data("13800000003"), db=self.db)
        self.assertEqual(res.code, 200, res.msg)

        tenant_result = await self.db.execute(select(Tenant).where(Tenant.phone == "13800000003"))
        tenant = tenant_result.scalar_one()
        subscription = await SubscriptionService(self.db).get_current_subscription(tenant.tenant_id)

        self.assertIsNotNone(subscription)
        self.assertEqual(subscription.status, STATUS_TRIAL)
        plan_result = await self.db.execute(select(Plan).where(Plan.id == subscription.plan_id))
        plan = plan_result.scalar_one()
        self.assertEqual(plan.code, "PRO")
        self.assertEqual(subscription.trial_ends_at - subscription.trial_started_at, timedelta(days=30))

    # ---- Test 6 — Trial failure rolls back the whole registration -------------

    async def test_trial_provisioning_failure_leaves_no_tenant_and_no_subscription(self):
        phone = "13800000006"
        await self._store_valid_register_code(phone)
        with patch.object(
            SubscriptionService, "create_trial_for_tenant", side_effect=RuntimeError("simulated trial failure")
        ):
            res = await login_module.register(make_request(), self._register_data(phone), db=self.db)

        self.assertNotEqual(res.code, 200)
        self.assertEqual(await self._tenant_count(phone), 0)
        self.assertEqual(await self._subscription_count_for_phone(phone), 0)

    # ---- Test 7 — Tenant creation failure leaves no Subscription --------------

    async def test_tenant_creation_failure_creates_no_subscription(self):
        phone = "13800000007"
        await self._store_valid_register_code(phone)
        with patch.object(TenantService, "create_tenant", side_effect=RuntimeError("simulated tenant failure")):
            res = await login_module.register(make_request(), self._register_data(phone), db=self.db)

        self.assertNotEqual(res.code, 200)
        self.assertEqual(await self._tenant_count(phone), 0)
        # No Tenant means the subscription lookup can't even resolve one, but
        # assert directly against the whole table too -- nothing should have
        # been inserted anywhere as a side effect of the failed attempt.
        all_subs = await self.db.execute(select(Subscription))
        self.assertEqual(len(all_subs.scalars().all()), 0)

    # ---- Test 8 — Registration gate is a pure server-side switch --------------

    async def test_missing_registration_key_creates_nothing_when_platform_key_unset(self):
        phone = "13800000009"
        settings.PLATFORM_REGISTER_KEY = ""  # simulates the out-of-the-box "not yet opened" state
        res = await login_module.register(make_request(), self._register_data(phone), db=self.db)

        self.assertEqual(res.code, 403)
        self.assertEqual(await self._tenant_count(phone), 0)

    async def test_register_schemas_accept_no_client_supplied_platform_key(self):
        # Phase 02: PLATFORM_REGISTER_KEY is checked purely server-side
        # (settings.PLATFORM_REGISTER_KEY truthy => open); the client never
        # sends a key at all, so neither request schema has the field.
        self.assertNotIn("platform_key", RegisterRequest.model_fields)
        self.assertNotIn("platform_key", RegisterCodeRequest.model_fields)

    # ---- Test 9 — Existing registration response contract is preserved --------

    async def test_registration_response_contract_unchanged(self):
        await self._store_valid_register_code("13800000010")
        res = await login_module.register(make_request(), self._register_data("13800000010"), db=self.db)
        self.assertEqual(res.code, 200)
        self.assertEqual(res.msg, "注册成功")
        data = res.data
        self.assertIn("tenant_id", data)
        self.assertIn("name", data)
        self.assertIn("phone", data)
        self.assertIn("role", data)
        self.assertIn("account_id", data)
        self.assertIn("permissions", data)
        self.assertIn("home_path", data)
        self.assertIn("token", data)
        self.assertIn("token_type", data)
        self.assertEqual(data["phone"], "13800000010")
        self.assertEqual(data["name"], "老王川菜馆")

    async def test_duplicate_phone_registration_still_rejected(self):
        phone = "13800000011"
        await self._store_valid_register_code(phone)
        await login_module.register(make_request(), self._register_data(phone), db=self.db)

        await self._store_valid_register_code(phone)  # a fresh code for the retry attempt
        res = await login_module.register(make_request(), self._register_data(phone), db=self.db)
        self.assertEqual(res.code, 400)
        self.assertEqual(await self._tenant_count(phone), 1)  # still just the first one
        # Test 10 (Phase 01 §21) -- retry after success creates no second trial.
        self.assertEqual(await self._subscription_count_for_phone(phone), 1)

    # ---- Test 10 — Legacy tenant (no registration, no trial) remains valid ----

    async def test_legacy_tenant_without_registration_remains_valid(self):
        legacy = Tenant(tenant_id="legacy-p04", name="老商户", password_hash="x", status=True)
        self.db.add(legacy)
        await self.db.commit()

        current = await SubscriptionService(self.db).get_current_subscription("legacy-p04")
        self.assertIsNone(current)
        tenant_result = await self.db.execute(select(Tenant).where(Tenant.tenant_id == "legacy-p04"))
        self.assertTrue(tenant_result.scalar_one().status)

    # ---- Test 11 — Super Admin tenant creation path is unaffected --------------

    async def test_super_admin_style_tenant_creation_does_not_auto_create_trial(self):
        # This exercises the low-level TenantService.create_tenant() primitive
        # directly (not the super_admin router, which now goes through
        # MerchantProvisioningService and DOES grant a trial -- see
        # tests/test_merchant_provisioning_foundation.py). The primitive
        # itself must remain trial-agnostic: MerchantProvisioningService is
        # the only place a trial decision gets made.
        service = TenantService(self.db)
        tenant = await service.create_tenant(
            tenant_id="super-admin-created",
            name="Admin Created Shop",
            password_hash="",
            phone="13900000000",
            address=None,
            logo_url=None,
        )
        self.assertEqual(tenant.tenant_id, "super-admin-created")

        current = await SubscriptionService(self.db).get_current_subscription("super-admin-created")
        self.assertIsNone(current)

        config_result = await self.db.execute(
            select(TenantConfig).where(TenantConfig.tenant_id == "super-admin-created")
        )
        self.assertIsNotNone(config_result.scalar_one_or_none())

    # ---- Test 12 — Tenant.status is never touched by trial integration --------

    async def test_registration_does_not_modify_tenant_status(self):
        await self._store_valid_register_code("13800000012")
        res = await login_module.register(make_request(), self._register_data("13800000012"), db=self.db)
        self.assertEqual(res.code, 200)
        tenant_result = await self.db.execute(select(Tenant).where(Tenant.phone == "13800000012"))
        tenant = tenant_result.scalar_one()
        self.assertTrue(tenant.status)

    # ---- Test 13 (Phase 01 §21 Test 6) — Invalid register OTP creates nothing -

    async def test_invalid_register_otp_creates_no_tenant(self):
        phone = "13800000013"
        await self._store_valid_register_code(phone, code="111111")
        res = await login_module.register(
            make_request(), self._register_data(phone, code="000000"), db=self.db
        )
        self.assertEqual(res.code, 400)
        self.assertEqual(await self._tenant_count(phone), 0)
        self.assertEqual(await self._subscription_count_for_phone(phone), 0)

    async def test_missing_register_otp_request_creates_no_tenant(self):
        # No /register/code call at all for this phone -- nothing stored to verify against.
        phone = "13800000014"
        res = await login_module.register(make_request(), self._register_data(phone, code="999999"), db=self.db)
        self.assertEqual(res.code, 400)
        self.assertEqual(await self._tenant_count(phone), 0)

    # ---- Test 14 (Phase 01 §21 Test 7) — Expired register OTP creates nothing -

    async def test_expired_register_otp_creates_no_tenant(self):
        phone = "13800000015"
        code = "222222"
        await self._store_valid_register_code(phone, code=code)
        service = TencentSmsService()
        key = service._code_key(phone, SmsPurpose.REGISTER)
        record = await sms_module._cache_get(key)
        record["expires_at"] = int(sms_module._now() - 1)
        await sms_module._cache_set(key, record, 1)

        res = await login_module.register(make_request(), self._register_data(phone, code=code), db=self.db)
        self.assertEqual(res.code, 400)
        self.assertEqual(await self._tenant_count(phone), 0)

    # ---- Test 15 (Phase 01 §21 Test 8) — Login OTP cannot register -------------

    async def test_login_otp_cannot_be_reused_to_register(self):
        phone = "13800000016"
        code = "333333"
        # Stored under the LOGIN purpose (default), never REGISTER.
        await TencentSmsService().store_login_code(phone, code, purpose=SmsPurpose.LOGIN)

        res = await login_module.register(make_request(), self._register_data(phone, code=code), db=self.db)
        self.assertEqual(res.code, 400)
        self.assertEqual(await self._tenant_count(phone), 0)

        # The LOGIN-purpose code is untouched -- a real login attempt with it
        # still works, proving the two purposes are genuinely independent
        # namespaces, not just a registration-side rejection.
        self.assertTrue(await TencentSmsService().verify_login_code(phone, code, purpose=SmsPurpose.LOGIN))

    # ---- Test 16 — POST /register/code contract ---------------------------

    async def test_register_code_endpoint_gated_purely_server_side(self):
        phone = "13800000017"
        settings.PLATFORM_REGISTER_KEY = ""
        closed_res = await login_module.send_register_code(
            make_request(), RegisterCodeRequest(phone=phone), db=self.db
        )
        self.assertEqual(closed_res.code, 403)
        settings.PLATFORM_REGISTER_KEY = TEST_REGISTER_KEY

        with patch.object(TencentSmsService, "is_configured", return_value=True), patch.object(
            TencentSmsService, "send_login_code", return_value=(True, "sent")
        ):
            res = await login_module.send_register_code(
                make_request(), RegisterCodeRequest(phone=phone), db=self.db
            )
        self.assertEqual(res.code, 200, res.msg)

        # The code that was actually stored is REGISTER-purpose, not LOGIN.
        service = TencentSmsService()
        register_key = service._code_key(phone, SmsPurpose.REGISTER)
        login_key = service._code_key(phone, SmsPurpose.LOGIN)
        self.assertIsNotNone(await sms_module._cache_get(register_key))
        self.assertIsNone(await sms_module._cache_get(login_key))

    async def test_register_code_rejects_already_registered_phone(self):
        phone = "13800000018"
        await self._store_valid_register_code(phone)
        await login_module.register(make_request(), self._register_data(phone), db=self.db)

        res = await login_module.send_register_code(
            make_request(), RegisterCodeRequest(phone=phone), db=self.db
        )
        self.assertEqual(res.code, 400)

    # ---- Test 16b (Phase 02) — Self-registration gets an Activation-ready
    # payment_mode, never the WeChat-Pay-dependent default -----------------

    async def test_self_registration_sets_table_account_payment_mode(self):
        phone = "13800000019"
        await self._store_valid_register_code(phone)
        res = await login_module.register(make_request(), self._register_data(phone), db=self.db)
        self.assertEqual(res.code, 200, res.msg)

        tenant_result = await self.db.execute(select(Tenant).where(Tenant.phone == phone))
        tenant = tenant_result.scalar_one()
        self.assertEqual(tenant.payment_mode, "table_account")

    # ---- Test 17 — Provisioning is delegated, router doesn't own the tx ------

    def test_register_delegates_to_merchant_provisioning_service(self):
        source = inspect.getsource(login_module.register)
        self.assertIn("MerchantProvisioningService", source)
        self.assertNotIn("db.commit()", source)

    # ---- Test 18 — No Billing/WxPay/Restaurant imports in the integration -----

    def test_login_module_has_no_forbidden_domain_imports(self):
        forbidden = [
            "BillingService",
            "BillingInvoice",
            "WxPayService",
            "OrderPaymentService",
            "order_print_service",
            "MembershipService",
            "CouponService",
            "PickupNoService",
            "DiningSessionService",
        ]
        module_names = set(vars(login_module).keys())
        for name in forbidden:
            self.assertNotIn(name, module_names, f"login.py must not import {name}")

        import_lines = [
            line for line in inspect.getsource(login_module).splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for line in import_lines:
            for name in forbidden:
                self.assertNotIn(name, line, f"login.py must not import {name}")


if __name__ == "__main__":
    unittest.main()
