"""Phase F1F-A — Entitlement Engine regression tests.

Scope: docs/saas-subscription-audit.md Phase F1F-A. Proves the frozen
PLAN_CAPABILITIES matrix (app/core/plan_capabilities.py) structurally, and
EntitlementService (app/services/entitlement_service.py) end-to-end against
real Subscription/Plan rows -- delegating 100% of effective-plan resolution
to SubscriptionService.get_effective_subscription_view() (never re-deriving
expiry), memoizing that resolution per-instance, and failing loud (never
silently False/FREE) on an unknown capability key or an unrecognized
effective plan code.

This phase wires EntitlementService into NOTHING business-facing -- these
are the only tests exercising it. See test_zero_wiring.mjs-equivalent proof
in the diff audit for confirmation no production caller exists yet.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.plan_capabilities import (
    ALL_CAPABILITIES,
    CAP_CHANNEL_ENTRY,
    CAP_COUPONS,
    CAP_CUSTOMER_CONSUMPTION,
    CAP_DISTRIBUTION_REFERRAL,
    CAP_KITCHEN_PRINT,
    CAP_MARKETING_AUTOMATION,
    CAP_MEMBER_LEVELS,
    CAP_MEMBERSHIP,
    CAP_MENU_ADVANCED_TOOLS,
    CAP_MENU_BASIC,
    CAP_ORDER_MANAGEMENT,
    CAP_POINTS,
    CAP_SCAN_ORDERING,
    CAP_STAFF_MANAGEMENT,
    CAP_TABLE_MANAGEMENT,
    CAP_WECHAT_PAYMENT,
    FREE_CAPABILITIES,
    PLAN_CAPABILITIES,
    PLAN_CODE_FREE,
    PLAN_CODE_PRO,
    PLAN_CODE_STANDARD,
    PRO_CAPABILITIES,
    STANDARD_CAPABILITIES,
    plans_requiring,
)
from app.models.base import Base
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.services.entitlement_service import (
    EntitlementRequiredError,
    EntitlementService,
    UnknownCapabilityError,
    UnknownEffectivePlanCodeError,
)
from app.services.subscription_service import (
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_TRIAL,
    SubscriptionService,
)
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@event.listens_for(Plan, "before_insert")
def _assign_plan_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Subscription, "before_insert")
def _assign_subscription_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Tenant, "before_insert")
def _assign_tenant_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


# ---------------------------------------------------------------------------
# Pure matrix structure -- no DB involved.
# ---------------------------------------------------------------------------

class PlanCapabilityMatrixTest(unittest.TestCase):
    # ---- FREE_HAS_FREE_CAPABILITIES / FREE_LACKS_STANDARD / FREE_LACKS_PRO
    def test_free_has_free_capabilities(self):
        for cap in (CAP_SCAN_ORDERING, CAP_MENU_BASIC, CAP_ORDER_MANAGEMENT, CAP_WECHAT_PAYMENT, CAP_TABLE_MANAGEMENT):
            self.assertIn(cap, PLAN_CAPABILITIES[PLAN_CODE_FREE])

    def test_free_lacks_standard(self):
        for cap in (CAP_MENU_ADVANCED_TOOLS, CAP_KITCHEN_PRINT, CAP_STAFF_MANAGEMENT):
            self.assertNotIn(cap, PLAN_CAPABILITIES[PLAN_CODE_FREE])

    def test_free_lacks_pro(self):
        for cap in (CAP_MEMBERSHIP, CAP_POINTS, CAP_MEMBER_LEVELS, CAP_COUPONS,
                    CAP_MARKETING_AUTOMATION, CAP_CUSTOMER_CONSUMPTION, CAP_CHANNEL_ENTRY,
                    CAP_DISTRIBUTION_REFERRAL):
            self.assertNotIn(cap, PLAN_CAPABILITIES[PLAN_CODE_FREE])

    # ---- STANDARD_INHERITS_FREE / STANDARD_HAS_STANDARD / STANDARD_LACKS_PRO
    def test_standard_inherits_free(self):
        self.assertTrue(FREE_CAPABILITIES.issubset(PLAN_CAPABILITIES[PLAN_CODE_STANDARD]))

    def test_standard_has_standard(self):
        for cap in (CAP_MENU_ADVANCED_TOOLS, CAP_KITCHEN_PRINT, CAP_STAFF_MANAGEMENT):
            self.assertIn(cap, PLAN_CAPABILITIES[PLAN_CODE_STANDARD])

    def test_standard_lacks_pro(self):
        for cap in (CAP_MEMBERSHIP, CAP_POINTS, CAP_MEMBER_LEVELS, CAP_COUPONS,
                    CAP_MARKETING_AUTOMATION, CAP_CUSTOMER_CONSUMPTION, CAP_CHANNEL_ENTRY,
                    CAP_DISTRIBUTION_REFERRAL):
            self.assertNotIn(cap, PLAN_CAPABILITIES[PLAN_CODE_STANDARD])

    # ---- PRO_HAS_ALL
    def test_pro_has_all(self):
        self.assertEqual(PLAN_CAPABILITIES[PLAN_CODE_PRO], ALL_CAPABILITIES)

    # ---- MATRIX_INHERITANCE: strict subset chain, not just "no missing key"
    def test_matrix_inheritance_strict_subset_chain(self):
        self.assertTrue(FREE_CAPABILITIES < STANDARD_CAPABILITIES < PRO_CAPABILITIES)

    # ---- Phase 8: registry completeness
    def test_all_capabilities_covered_by_pro(self):
        for cap in ALL_CAPABILITIES:
            self.assertIn(cap, PRO_CAPABILITIES, f"{cap} is defined but no plan grants it")

    def test_no_unknown_capability_in_matrix(self):
        for plan_code, caps in PLAN_CAPABILITIES.items():
            for cap in caps:
                self.assertIn(cap, ALL_CAPABILITIES, f"{plan_code} grants unrecognized capability {cap}")

    # ---- REQUIRED_PLAN_LOOKUP
    def test_plans_requiring_menu_basic(self):
        self.assertEqual(plans_requiring(CAP_MENU_BASIC), (PLAN_CODE_FREE, PLAN_CODE_STANDARD, PLAN_CODE_PRO))

    def test_plans_requiring_kitchen_print(self):
        self.assertEqual(plans_requiring(CAP_KITCHEN_PRINT), (PLAN_CODE_STANDARD, PLAN_CODE_PRO))

    def test_plans_requiring_membership(self):
        self.assertEqual(plans_requiring(CAP_MEMBERSHIP), (PLAN_CODE_PRO,))

    def test_plans_requiring_unknown_raises(self):
        with self.assertRaises(ValueError):
            plans_requiring("NOT_A_REAL_CAPABILITY")


# ---------------------------------------------------------------------------
# EntitlementService -- real DB-backed resolution.
# ---------------------------------------------------------------------------

TENANT_A = "tenant-entitlement-a"
TENANT_B = "tenant-entitlement-b"


class EntitlementServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add_all(
            [
                Tenant(tenant_id=TENANT_A, name="Entitlement A", password_hash="x", status=True),
                Tenant(tenant_id=TENANT_B, name="Entitlement B", password_hash="x", status=True),
            ]
        )
        self.db.add_all(
            [
                Plan(code="FREE", name="免费版", is_active=True,
                     price_month_cents=0, price_year_cents=0, sort_order=0),
                Plan(code="STANDARD", name="普通版", is_active=True,
                     price_month_cents=5900, price_year_cents=60900, sort_order=1),
                Plan(code="PRO", name="专业版", is_active=True,
                     price_month_cents=9900, price_year_cents=102200, sort_order=2),
            ]
        )
        await self.db.commit()
        self.subscription_service = SubscriptionService(self.db)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _plan(self, code: str) -> Plan:
        return await self.subscription_service.get_plan_by_code(code)

    async def _make_active(self, tenant_id: str, plan_code: str, *, ends_delta: timedelta) -> Subscription:
        plan = await self._plan(plan_code)
        now = datetime.utcnow()
        sub = Subscription(
            tenant_id=tenant_id, plan_id=plan.id, status=STATUS_ACTIVE,
            started_at=now, ends_at=now + ends_delta,
        )
        self.db.add(sub)
        await self.db.commit()
        await self.db.refresh(sub)
        return sub

    async def _make_trial(self, tenant_id: str, *, ends_delta: timedelta) -> Subscription:
        plan = await self._plan("PRO")
        now = datetime.utcnow()
        return await self.subscription_service.create_trial(
            tenant_id=tenant_id, plan=plan, trial_started_at=now, trial_ends_at=now + ends_delta,
        )

    # ---- NO SUBSCRIPTION -> FREE ------------------------------------------

    async def test_no_subscription_resolves_free(self):
        service = EntitlementService(self.db)
        self.assertEqual(await service.resolve_effective_plan_code(TENANT_A), PLAN_CODE_FREE)
        self.assertTrue(await service.has_capability(TENANT_A, CAP_SCAN_ORDERING))
        self.assertFalse(await service.has_capability(TENANT_A, CAP_STAFF_MANAGEMENT))

    # ---- TRIAL_PRO_HAS_ALL_PRO ---------------------------------------------

    async def test_trial_pro_has_all_pro_capabilities(self):
        await self._make_trial(TENANT_A, ends_delta=timedelta(days=10))
        service = EntitlementService(self.db)
        self.assertEqual(await service.resolve_effective_plan_code(TENANT_A), PLAN_CODE_PRO)
        for cap in PRO_CAPABILITIES:
            self.assertTrue(await EntitlementService(self.db).has_capability(TENANT_A, cap))

    # ---- EXPIRED_PRO_FALLS_TO_FREE / EXPIRED_TRIAL_FALLS_TO_FREE ----------

    async def test_expired_active_pro_falls_to_free(self):
        await self._make_active(TENANT_A, "PRO", ends_delta=timedelta(seconds=-1))
        service = EntitlementService(self.db)
        self.assertEqual(await service.resolve_effective_plan_code(TENANT_A), PLAN_CODE_FREE)
        self.assertFalse(await EntitlementService(self.db).has_capability(TENANT_A, CAP_MEMBERSHIP))

    async def test_expired_trial_falls_to_free(self):
        await self._make_trial(TENANT_A, ends_delta=timedelta(seconds=-1))
        service = EntitlementService(self.db)
        self.assertEqual(await service.resolve_effective_plan_code(TENANT_A), PLAN_CODE_FREE)

    # ---- CANCELLED_PRO_FALLS_TO_FREE ---------------------------------------

    async def test_cancelled_pro_falls_to_free(self):
        sub = await self._make_active(TENANT_A, "PRO", ends_delta=timedelta(days=10))
        await self.subscription_service.cancel(sub)
        service = EntitlementService(self.db)
        self.assertEqual(await service.resolve_effective_plan_code(TENANT_A), PLAN_CODE_FREE)
        self.assertFalse(await EntitlementService(self.db).has_capability(TENANT_A, CAP_MEMBERSHIP))

    # ---- INACTIVE_PLAN_EXISTING_SUBSCRIPTION_RETAINS_RIGHTS ---------------

    async def test_inactive_plan_existing_subscription_retains_rights(self):
        await self._make_active(TENANT_A, "PRO", ends_delta=timedelta(days=10))
        pro_plan = await self._plan("PRO")
        pro_plan.is_active = False
        await self.db.commit()

        service = EntitlementService(self.db)
        self.assertEqual(await service.resolve_effective_plan_code(TENANT_A), PLAN_CODE_PRO)
        self.assertTrue(await EntitlementService(self.db).has_capability(TENANT_A, CAP_MEMBERSHIP))

    # ---- UNKNOWN_CAPABILITY_FAILS_LOUD -------------------------------------

    async def test_unknown_capability_fails_loud(self):
        service = EntitlementService(self.db)
        with self.assertRaises(UnknownCapabilityError):
            await service.has_capability(TENANT_A, "TOTALLY_MADE_UP")
        with self.assertRaises(UnknownCapabilityError):
            await EntitlementService(self.db).require_capability(TENANT_A, "TOTALLY_MADE_UP")

    # ---- UNKNOWN_EFFECTIVE_PLAN_FAILS_LOUD ---------------------------------

    async def test_unknown_effective_plan_code_fails_loud(self):
        rogue_plan = Plan(code="ENTERPRISE", name="未知档位", is_active=True,
                           price_month_cents=0, price_year_cents=0, sort_order=99)
        self.db.add(rogue_plan)
        await self.db.commit()
        await self.db.refresh(rogue_plan)
        now = datetime.utcnow()
        sub = Subscription(
            tenant_id=TENANT_A, plan_id=rogue_plan.id, status=STATUS_ACTIVE,
            started_at=now, ends_at=now + timedelta(days=10),
        )
        self.db.add(sub)
        await self.db.commit()

        service = EntitlementService(self.db)
        with self.assertRaises(UnknownEffectivePlanCodeError):
            await service.resolve_effective_plan_code(TENANT_A)
        # Must not silently degrade to False/FREE -- has_capability must
        # propagate the same integrity error, not swallow it.
        with self.assertRaises(UnknownEffectivePlanCodeError):
            await EntitlementService(self.db).has_capability(TENANT_A, CAP_SCAN_ORDERING)

    # ---- REQUIRE_CAPABILITY_ERROR_CONTEXT ----------------------------------

    async def test_require_capability_error_context_on_free(self):
        service = EntitlementService(self.db)
        with self.assertRaises(EntitlementRequiredError) as ctx:
            await service.require_capability(TENANT_A, CAP_STAFF_MANAGEMENT)
        err = ctx.exception
        self.assertEqual(err.capability, CAP_STAFF_MANAGEMENT)
        self.assertEqual(err.effective_plan_code, PLAN_CODE_FREE)
        self.assertEqual(err.required_plan_codes, (PLAN_CODE_STANDARD, PLAN_CODE_PRO))

    async def test_require_capability_passes_on_pro(self):
        await self._make_active(TENANT_A, "PRO", ends_delta=timedelta(days=10))
        service = EntitlementService(self.db)
        # Must not raise.
        self.assertIsNone(await service.require_capability(TENANT_A, CAP_STAFF_MANAGEMENT))
        self.assertIsNone(await service.require_capability(TENANT_A, CAP_MEMBERSHIP))

    # ---- SERVICE_INSTANCE_MEMOIZES_EFFECTIVE_PLAN --------------------------

    async def test_service_instance_memoizes_effective_plan_resolution(self):
        await self._make_active(TENANT_A, "STANDARD", ends_delta=timedelta(days=10))
        service = EntitlementService(self.db)

        calls = []
        original = SubscriptionService.get_effective_subscription_view

        async def counting(self_svc, tenant_id, **kwargs):
            calls.append(tenant_id)
            return await original(self_svc, tenant_id, **kwargs)

        with patch.object(SubscriptionService, "get_effective_subscription_view", new=counting):
            self.assertTrue(await service.has_capability(TENANT_A, CAP_KITCHEN_PRINT))
            self.assertFalse(await service.has_capability(TENANT_A, CAP_MEMBERSHIP))
            self.assertIsNone(await service.require_capability(TENANT_A, CAP_MENU_BASIC))

        self.assertEqual(len(calls), 1, "one EntitlementService instance must resolve the effective plan at most once")

    # ---- TENANT_ISOLATION ---------------------------------------------------

    async def test_tenant_isolation_across_instances(self):
        await self._make_active(TENANT_B, "PRO", ends_delta=timedelta(days=10))
        # TENANT_A has no subscription at all -> FREE.
        service_a = EntitlementService(self.db)
        service_b = EntitlementService(self.db)

        self.assertEqual(await service_a.resolve_effective_plan_code(TENANT_A), PLAN_CODE_FREE)
        self.assertEqual(await service_b.resolve_effective_plan_code(TENANT_B), PLAN_CODE_PRO)
        self.assertFalse(await service_a.has_capability(TENANT_A, CAP_MEMBERSHIP))
        self.assertTrue(await service_b.has_capability(TENANT_B, CAP_MEMBERSHIP))


if __name__ == "__main__":
    unittest.main()
