"""Phase 01 — Merchant Provisioning Foundation.

Scope: unify "create a merchant" into one Domain Authority
(MerchantProvisioningService) that both Super Admin (app/api/v1/super_admin.py
::create_merchant) and self-registration (app/api/v1/login.py::register,
covered separately in tests/test_merchant_registration_trial.py) call, instead
of each orchestrating TenantService/SubscriptionService independently. Three
concrete guarantees this file proves against a real database schema (not
mocks): (1) tenant.phone is a DB-enforced unique identity (P0-01) -- a
duplicate insert fails atomically and is translated to a stable business
error, never a raw 500; (2) Tenant+TenantConfig+trial Subscription really is
one all-or-nothing transaction, regardless of which source triggered it; (3)
Super Admin-created tenants now get the same 30-day PRO trial self-registered
tenants always have, closing the divergence the Phase 00 audit found.
"""

from __future__ import annotations

import unittest
from datetime import timedelta

from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1 import super_admin as super_admin_module
from app.models.base import Base
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.services.merchant_provisioning_service import (
    MerchantProvisioningService,
    PhoneAlreadyRegisteredError,
    ProvisioningSource,
    TrialPolicy,
)
from app.services.subscription_service import STATUS_TRIAL, SubscriptionService
from app.utils.id_generator import generate_snowflake_id

@event.listens_for(Plan, "before_insert")
def _assign_plan_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Subscription, "before_insert")
def _assign_subscription_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_super_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/super/merchants",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


class MerchantProvisioningFoundationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.service = MerchantProvisioningService(self.db)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _tenant_count(self, phone: str) -> int:
        result = await self.db.execute(select(Tenant).where(Tenant.phone == phone))
        return len(result.scalars().all())

    async def _config_count(self, tenant_id: str) -> int:
        result = await self.db.execute(select(TenantConfig).where(TenantConfig.tenant_id == tenant_id))
        return len(result.scalars().all())

    async def _subscription_count(self, tenant_id: str) -> int:
        result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))
        return len(result.scalars().all())

    # ---- P0-01 schema proof ----------------------------------------------

    def test_tenant_phone_column_is_declared_unique(self):
        column = Tenant.__table__.c.phone
        self.assertTrue(column.unique, "Tenant.phone must be a unique column (P0-01)")

    # ---- Trial policy parity across sources -------------------------------

    async def test_self_register_source_creates_tenant_config_and_trial(self):
        result = await self.service.provision_merchant(
            name="自助注册店", phone="13700000001", source=ProvisioningSource.SELF_REGISTER
        )
        self.assertEqual(await self._tenant_count("13700000001"), 1)
        self.assertEqual(await self._config_count(result.tenant.tenant_id), 1)
        self.assertEqual(await self._subscription_count(result.tenant.tenant_id), 1)
        self.assertIsNotNone(result.subscription)
        self.assertEqual(result.subscription.status, STATUS_TRIAL)

    # ---- Payment mode policy (Phase 02) ------------------------------------

    async def test_self_register_gets_table_account_payment_mode(self):
        # FIRST_ORDER_SUCCESS must not depend on WeChat Pay credentials only
        # Super Admin can configure -- table_account is the only payment_mode
        # that never touches WxPayService (confirmed in app/api/v1/orders.py
        # and order_payment_service.py's create_wxpay_order guard).
        result = await self.service.provision_merchant(
            name="自助注册店二", phone="13700000011", source=ProvisioningSource.SELF_REGISTER
        )
        self.assertEqual(result.tenant.payment_mode, "table_account")

    async def test_super_admin_source_keeps_unchanged_prepay_default(self):
        # Explicitly frozen per Phase 02 scope: Super-Admin-provisioned
        # tenants keep the pre-existing "prepay" column default untouched --
        # only the self-registration source's payment_mode changes.
        result = await self.service.provision_merchant(
            name="中控台开的店二", phone="13700000012", source=ProvisioningSource.SUPER_ADMIN
        )
        self.assertEqual(result.tenant.payment_mode, "prepay")

    async def test_super_admin_source_now_also_creates_trial(self):
        # This is the Phase 01 behavior change: previously Super Admin-created
        # tenants got zero Subscription rows (see the frozen, unchanged
        # assertion in test_merchant_registration_trial.py that the raw
        # TenantService.create_tenant() primitive still doesn't grant a
        # trial). Going through MerchantProvisioningService instead -- which
        # is what the super_admin router now does -- unifies this.
        result = await self.service.provision_merchant(
            name="中控台开的店", phone="13700000002", source=ProvisioningSource.SUPER_ADMIN
        )
        self.assertEqual(await self._tenant_count("13700000002"), 1)
        self.assertEqual(await self._config_count(result.tenant.tenant_id), 1)
        subscription = await SubscriptionService(self.db).get_current_subscription(result.tenant.tenant_id)
        self.assertIsNotNone(subscription)
        self.assertEqual(subscription.status, STATUS_TRIAL)
        self.assertEqual(subscription.trial_ends_at - subscription.trial_started_at, timedelta(days=30))

    async def test_explicit_no_trial_policy_is_honored(self):
        # trial_policy is an explicit, opt-in decision per call -- not an
        # accident of which source called in. Proves a future legitimate
        # "manual free tenant" caller has a real, honest way to skip the
        # trial without silently reintroducing the old source-based
        # divergence.
        result = await self.service.provision_merchant(
            name="手动免费户",
            phone="13700000003",
            source=ProvisioningSource.SUPER_ADMIN,
            trial_policy=TrialPolicy.NO_TRIAL,
        )
        self.assertIsNone(result.subscription)
        subscription = await SubscriptionService(self.db).get_current_subscription(result.tenant.tenant_id)
        self.assertIsNone(subscription)

    async def test_unknown_source_is_rejected(self):
        with self.assertRaises(ValueError):
            await self.service.provision_merchant(name="x", phone="13700000004", source="NOT_A_REAL_SOURCE")
        self.assertEqual(await self._tenant_count("13700000004"), 0)

    async def test_unknown_trial_policy_is_rejected_and_rolls_back(self):
        with self.assertRaises(ValueError):
            await self.service.provision_merchant(
                name="x",
                phone="13700000005",
                source=ProvisioningSource.SELF_REGISTER,
                trial_policy="NOT_A_REAL_POLICY",
            )
        # Tenant was flushed before the bad trial_policy was evaluated --
        # must not survive the rollback that follows the ValueError.
        self.assertEqual(await self._tenant_count("13700000005"), 0)

    # ---- Duplicate phone: fast pre-check path ------------------------------

    async def test_duplicate_phone_fast_precheck_raises_stable_error(self):
        await self.service.provision_merchant(
            name="第一家", phone="13700000006", source=ProvisioningSource.SELF_REGISTER
        )
        with self.assertRaises(PhoneAlreadyRegisteredError):
            await self.service.provision_merchant(
                name="第二家", phone="13700000006", source=ProvisioningSource.SELF_REGISTER
            )
        self.assertEqual(await self._tenant_count("13700000006"), 1)

    # ---- Duplicate phone: DB constraint is the real authority (P0-01) -----

    async def test_duplicate_phone_db_constraint_backstops_a_race_not_500(self):
        # Simulates two requests that both pass the in-application
        # pre-check before either commits (the exact TOCTOU race P0-01
        # describes): patch get_tenant_by_phone to report "no existing
        # tenant" even though one is already sitting in the DB, so the
        # INSERT is what actually has to stop the duplicate.
        await self.service.provision_merchant(
            name="已存在", phone="13700000007", source=ProvisioningSource.SELF_REGISTER
        )

        from unittest.mock import AsyncMock, patch

        from app.services.tenant_service import TenantService

        with patch.object(TenantService, "get_tenant_by_phone", new=AsyncMock(return_value=None)):
            with self.assertRaises(PhoneAlreadyRegisteredError):
                await self.service.provision_merchant(
                    name="竞态第二家", phone="13700000007", source=ProvisioningSource.SELF_REGISTER
                )

        # Still exactly one tenant -- the DB unique index, not application
        # logic, is what actually stopped the second insert.
        self.assertEqual(await self._tenant_count("13700000007"), 1)

    async def test_non_phone_integrity_error_is_not_swallowed_as_duplicate_phone(self):
        # _is_phone_uniqueness_violation() must not treat every IntegrityError
        # as a phone conflict -- an unrelated constraint violation should
        # propagate as-is, not be misreported as PhoneAlreadyRegisteredError.
        from unittest.mock import patch

        async def _raise_unrelated_integrity_error(*args, **kwargs):
            raise IntegrityError("insert", {}, Exception("CHECK constraint failed: some_other_column"))

        with patch.object(self.db, "commit", side_effect=_raise_unrelated_integrity_error):
            with self.assertRaises(IntegrityError):
                await self.service.provision_merchant(
                    name="x", phone="13700000008", source=ProvisioningSource.SELF_REGISTER
                )
        self.assertEqual(await self._tenant_count("13700000008"), 0)

    # ---- Retry / idempotency ------------------------------------------------

    async def test_retry_after_success_creates_no_second_trial(self):
        first = await self.service.provision_merchant(
            name="重试测试", phone="13700000009", source=ProvisioningSource.SELF_REGISTER
        )
        with self.assertRaises(PhoneAlreadyRegisteredError):
            await self.service.provision_merchant(
                name="重试测试", phone="13700000009", source=ProvisioningSource.SELF_REGISTER
            )
        self.assertEqual(await self._tenant_count("13700000009"), 1)
        self.assertEqual(await self._subscription_count(first.tenant.tenant_id), 1)

    # ---- Atomicity: TenantConfig must not survive a mid-flight failure ----

    async def test_trial_failure_leaves_no_orphan_tenant_config(self):
        from unittest.mock import patch

        with patch.object(
            SubscriptionService, "create_trial_for_tenant", side_effect=RuntimeError("simulated")
        ):
            with self.assertRaises(RuntimeError):
                await self.service.provision_merchant(
                    name="回滚测试", phone="13700000010", source=ProvisioningSource.SELF_REGISTER
                )
        self.assertEqual(await self._tenant_count("13700000010"), 0)
        # TenantConfig is keyed by tenant_id, not by phone -- but since no
        # Tenant survived, no TenantConfig row should exist at all either.
        all_configs = await self.db.execute(select(TenantConfig))
        self.assertEqual(len(all_configs.scalars().all()), 0)


class SuperAdminProvisioningIntegrationTest(unittest.IsolatedAsyncioTestCase):
    """Router-level proof that POST /api/super/merchants itself (not just
    the service in isolation) now grants a trial and handles duplicate
    phones cleanly -- calling the route function directly the same way
    tests/test_merchant_registration_trial.py exercises login_module.register,
    bypassing FastAPI's dependency injection (Depends(_verify_super_token) is
    route metadata, not a decorator, so it is not enforced on a direct call)."""

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _request_data(self, phone: str, name: str = "中控台商户"):
        return super_admin_module.CreateMerchantRequest(name=name, phone=phone)

    async def test_create_merchant_endpoint_grants_trial_and_keeps_response_contract(self):
        res = await super_admin_module.create_merchant(
            make_super_request(), self._request_data("13700000101"), db=self.db
        )
        self.assertEqual(res.code, 200, res.msg)
        # Legacy response contract fields preserved (admin-h5 depends on these).
        self.assertIn("tenant_id", res.data)
        self.assertIn("name", res.data)
        self.assertIn("phone", res.data)
        self.assertIn("login_code", res.data)
        self.assertEqual(res.data["login_code"], "123456")

        tenant_result = await self.db.execute(select(Tenant).where(Tenant.phone == "13700000101"))
        tenant = tenant_result.scalar_one()
        subscription = await SubscriptionService(self.db).get_current_subscription(tenant.tenant_id)
        self.assertIsNotNone(subscription)
        self.assertEqual(subscription.status, STATUS_TRIAL)

    async def test_create_merchant_endpoint_rejects_duplicate_phone_cleanly(self):
        await super_admin_module.create_merchant(make_super_request(), self._request_data("13700000102"), db=self.db)
        res = await super_admin_module.create_merchant(
            make_super_request(), self._request_data("13700000102", name="重复"), db=self.db
        )
        self.assertEqual(res.code, 400)
        self.assertEqual(res.msg, "该手机号已注册")

        tenant_result = await self.db.execute(select(Tenant).where(Tenant.phone == "13700000102"))
        self.assertEqual(len(tenant_result.scalars().all()), 1)

    async def test_create_merchant_uses_provisioning_service_not_tenant_service_directly(self):
        import inspect

        source = inspect.getsource(super_admin_module.create_merchant)
        self.assertIn("MerchantProvisioningService", source)
        self.assertNotIn("TenantService", source)


if __name__ == "__main__":
    unittest.main()
