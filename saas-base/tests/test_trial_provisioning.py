"""Phase 03 — Trial Provisioning regression tests.

Scope: docs/saas-subscription-audit.md Phase 03. SubscriptionService.create_trial_for_tenant()
and ensure_plan() are a shadow domain capability — no production entry point (registration,
tenant provisioning, admin UI) calls them yet. These tests only prove the capability itself
is safe: idempotent plan bootstrap, idempotent + non-destructive trial creation, tenant
existence enforced, Tenant.status never touched, legacy tenants unaffected.

Concurrency note (read before trusting the "idempotent" tests too literally): SQLite has no
real row-level locking, so the SELECT ... FOR UPDATE inside create_trial_for_tenant() is a
silent no-op under the sqlite+aiosqlite dialect used here — these tests exercise a single
connection making sequential calls, which proves APPLICATION-level idempotency (the
check-then-insert logic is correct) but does NOT prove true concurrent-transaction safety.
The DATABASE-level guarantee (two real concurrent MySQL transactions serializing on the
locked Tenant row) is a production-only property that this test suite cannot exercise and
does not claim to.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.services import subscription_service as subscription_service_module
from app.services.subscription_service import (
    DEFAULT_TRIAL_DAYS,
    PLAN_CODE_PRO,
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_EXPIRED,
    STATUS_TRIAL,
    SubscriptionService,
)
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-trial-a"
TENANT_LEGACY = "tenant-trial-legacy"


@event.listens_for(Plan, "before_insert")
def _assign_plan_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Subscription, "before_insert")
def _assign_subscription_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


class TrialProvisioningTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.service = SubscriptionService(self.db)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _add_tenant(self, tenant_id: str, *, status: bool = True) -> Tenant:
        tenant = Tenant(tenant_id=tenant_id, name="T", password_hash="x", status=status)
        self.db.add(tenant)
        await self.db.commit()
        await self.db.refresh(tenant)
        return tenant

    async def _plan_count(self, code: str) -> int:
        result = await self.db.execute(select(Plan).where(Plan.code == code))
        return len(result.scalars().all())

    async def _subscription_count(self, tenant_id: str) -> int:
        result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))
        return len(result.scalars().all())

    # ---- Test 1 — Ensure PRO Plan ---------------------------------------------

    async def test_ensure_pro_plan_succeeds(self):
        plan = await self.service.ensure_plan(PLAN_CODE_PRO, "专业版")
        self.assertEqual(plan.code, "PRO")
        self.assertEqual(plan.name, "专业版")
        self.assertTrue(plan.is_active)

    # ---- Test 2 — Plan Bootstrap Idempotent ------------------------------------

    async def test_ensure_pro_plan_is_idempotent(self):
        first = await self.service.ensure_plan(PLAN_CODE_PRO, "专业版")
        second = await self.service.ensure_plan(PLAN_CODE_PRO, "专业版")
        self.assertEqual(first.id, second.id)
        self.assertEqual(await self._plan_count("PRO"), 1)

    # ---- Test 3 — Tenant Trial Creation ----------------------------------------

    async def test_create_trial_for_tenant_sets_status_and_plan(self):
        await self._add_tenant(TENANT_A)
        subscription = await self.service.create_trial_for_tenant(TENANT_A)
        self.assertEqual(subscription.tenant_id, TENANT_A)
        self.assertEqual(subscription.status, STATUS_TRIAL)
        plan_result = await self.db.execute(select(Plan).where(Plan.id == subscription.plan_id))
        plan = plan_result.scalar_one()
        self.assertEqual(plan.code, "PRO")

    # ---- Test 4 — 30 Day Trial --------------------------------------------------

    async def test_trial_duration_is_30_days(self):
        await self._add_tenant(TENANT_A)
        subscription = await self.service.create_trial_for_tenant(TENANT_A)
        self.assertEqual(DEFAULT_TRIAL_DAYS, 30)
        delta = subscription.trial_ends_at - subscription.trial_started_at
        self.assertEqual(delta, timedelta(days=30))

    async def test_trial_days_override_is_respected(self):
        await self._add_tenant(TENANT_A)
        subscription = await self.service.create_trial_for_tenant(TENANT_A, trial_days=7)
        delta = subscription.trial_ends_at - subscription.trial_started_at
        self.assertEqual(delta, timedelta(days=7))

    # ---- Test 5 — Idempotent Trial Creation ------------------------------------

    async def test_repeated_create_trial_does_not_duplicate_or_extend(self):
        await self._add_tenant(TENANT_A)
        first = await self.service.create_trial_for_tenant(TENANT_A)
        second = await self.service.create_trial_for_tenant(TENANT_A)

        self.assertEqual(first.id, second.id)
        self.assertEqual(first.trial_ends_at, second.trial_ends_at)
        self.assertEqual(await self._subscription_count(TENANT_A), 1)

    # ---- Test 6 — Existing ACTIVE Subscription is never overwritten -----------

    async def test_active_subscription_is_not_overwritten_by_trial_call(self):
        await self._add_tenant(TENANT_A)
        plan = await self.service.ensure_plan(PLAN_CODE_PRO, "专业版")
        now = datetime(2026, 1, 1)
        active = await self.service.create_trial(TENANT_A, plan, now, now + timedelta(days=30))
        active = await self.service.activate(active, started_at=now, ends_at=now + timedelta(days=365))

        result = await self.service.create_trial_for_tenant(TENANT_A)

        self.assertEqual(result.id, active.id)
        self.assertEqual(result.status, STATUS_ACTIVE)
        self.assertEqual(result.ends_at, now + timedelta(days=365))
        self.assertEqual(await self._subscription_count(TENANT_A), 1)

    # ---- Test 7 — Existing EXPIRED Subscription is never re-trialed -----------

    async def test_expired_subscription_is_not_re_trialed(self):
        await self._add_tenant(TENANT_A)
        plan = await self.service.ensure_plan(PLAN_CODE_PRO, "专业版")
        now = datetime(2026, 1, 1)
        sub = await self.service.create_trial(TENANT_A, plan, now, now + timedelta(days=30))
        sub.status = STATUS_EXPIRED
        await self.db.commit()

        result = await self.service.create_trial_for_tenant(TENANT_A)

        self.assertEqual(result.id, sub.id)
        self.assertEqual(result.status, STATUS_EXPIRED)
        self.assertEqual(await self._subscription_count(TENANT_A), 1)

    # ---- Test 8 — Existing CANCELLED Subscription is never re-trialed ---------

    async def test_cancelled_subscription_is_not_re_trialed(self):
        await self._add_tenant(TENANT_A)
        plan = await self.service.ensure_plan(PLAN_CODE_PRO, "专业版")
        now = datetime(2026, 1, 1)
        sub = await self.service.create_trial(TENANT_A, plan, now, now + timedelta(days=30))
        sub = await self.service.cancel(sub)

        result = await self.service.create_trial_for_tenant(TENANT_A)

        self.assertEqual(result.id, sub.id)
        self.assertEqual(result.status, STATUS_CANCELLED)
        self.assertEqual(await self._subscription_count(TENANT_A), 1)

    # ---- Test 9 — Unknown Tenant fails safely, creates nothing -----------------

    async def test_unknown_tenant_fails_and_creates_nothing(self):
        with self.assertRaises(ValueError):
            await self.service.create_trial_for_tenant("does-not-exist")

        tenant_result = await self.db.execute(select(Tenant).where(Tenant.tenant_id == "does-not-exist"))
        self.assertIsNone(tenant_result.scalar_one_or_none())
        self.assertEqual(await self._subscription_count("does-not-exist"), 0)

    # ---- Test 10 — Tenant.status is never touched ------------------------------

    async def test_tenant_status_unchanged_by_trial_creation(self):
        await self._add_tenant(TENANT_A, status=True)
        await self.service.create_trial_for_tenant(TENANT_A)

        tenant_result = await self.db.execute(select(Tenant).where(Tenant.tenant_id == TENANT_A))
        tenant = tenant_result.scalar_one()
        self.assertTrue(tenant.status)

    async def test_disabled_tenant_status_also_unchanged_by_trial_creation(self):
        # A disabled (banned) tenant can still legally have create_trial_for_tenant
        # called on it (e.g. by an internal script) -- this service has no opinion
        # on Tenant.status, it neither reads it as a gate nor writes it.
        await self._add_tenant(TENANT_A, status=False)
        await self.service.create_trial_for_tenant(TENANT_A)

        tenant_result = await self.db.execute(select(Tenant).where(Tenant.tenant_id == TENANT_A))
        tenant = tenant_result.scalar_one()
        self.assertFalse(tenant.status)

    # ---- Test 11 — Legacy Tenant (no Subscription, trial never called) --------

    async def test_legacy_tenant_without_any_trial_call_remains_legal(self):
        await self._add_tenant(TENANT_LEGACY)

        current = await self.service.get_current_subscription(TENANT_LEGACY)
        self.assertIsNone(current)

        tenant_result = await self.db.execute(select(Tenant).where(Tenant.tenant_id == TENANT_LEGACY))
        tenant = tenant_result.scalar_one()
        self.assertTrue(tenant.status)
        self.assertEqual(await self._subscription_count(TENANT_LEGACY), 0)

    # ---- Test 12 — Zero cross-domain calls -------------------------------------

    async def test_ensure_plan_reraises_integrity_error_that_is_not_a_code_race(self):
        # ensure_plan()'s except-IntegrityError branch must not swallow an
        # IntegrityError that turns out NOT to be a same-code race (i.e. the
        # post-rollback re-query by code still finds nothing). We force exactly
        # that by making the recovery query always return None, then trigger a
        # real IntegrityError via a duplicate primary key -- proving the
        # exception propagates instead of being silently absorbed.
        from unittest.mock import AsyncMock, patch

        from sqlalchemy.exc import IntegrityError

        async def _raise_integrity_error(*args, **kwargs):
            try:
                raise IntegrityError("insert", {}, Exception("forced"))
            finally:
                await self.db.rollback()

        with patch.object(self.db, "commit", side_effect=_raise_integrity_error), \
             patch.object(SubscriptionService, "get_plan_by_code", new=AsyncMock(return_value=None)):
            with self.assertRaises(IntegrityError):
                await self.service.ensure_plan(PLAN_CODE_PRO, "专业版")

    def test_subscription_service_has_no_cross_domain_imports(self):
        forbidden = [
            "TenantService",
            "OrderService",
            "OrderPaymentService",
            "WxPayService",
            "order_print_service",
            "MembershipService",
            "CouponService",
            "BillingService",
            "TencentSmsService",
        ]
        module_names = set(vars(subscription_service_module).keys())
        for name in forbidden:
            self.assertNotIn(name, module_names, f"SubscriptionService must not import {name}")


if __name__ == "__main__":
    unittest.main()
