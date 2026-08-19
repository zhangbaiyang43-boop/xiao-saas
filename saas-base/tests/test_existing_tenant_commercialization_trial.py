"""F1G-CM-PD0-GF — Existing Tenant Commercialization Grandfather regression
tests.

Scope: the one-time backfill in app/services/tenant_commercialization_grandfather.py
(invoked by migration 20260819_0002) that grants a normal PRO TRIAL to every
tenant with zero historical Subscription rows, so pre-existing production
tenants don't silently lose already-live features (KITCHEN_PRINT, MEMBERSHIP,
COUPONS, DISTRIBUTION_REFERRAL) the instant the commercialization release
deploys.

These tests exercise the ACTUAL backfill function (not a re-implementation),
against a real SQLite schema built from the ORM metadata, then read the
result back through the real, unmodified SubscriptionService ->
EntitlementService chain -- proving this is a one-time data migration, not a
resolver special-case.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.plan_capabilities import (
    CAP_COUPONS,
    CAP_DISTRIBUTION_REFERRAL,
    CAP_KITCHEN_PRINT,
    CAP_MEMBERSHIP,
)
from app.models.base import Base
from app.models.billing import BillingInvoice, BillingPayment
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.services.entitlement_service import EntitlementService
from app.services.subscription_service import (
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_EXPIRED,
    STATUS_TRIAL,
    PLAN_CODE_PRO,
    PLAN_CODE_STANDARD,
    SubscriptionService,
)
from app.services.tenant_commercialization_grandfather import (
    ProPlanMissingError,
    TRIAL_DAYS,
    backfill_zero_history_tenants,
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


FIXED_NOW = datetime(2026, 8, 19, 4, 0, 0)

TENANT_A_ZERO_HISTORY = "tenant-gf-a-zero-history"
TENANT_B_ACTIVE_STANDARD = "tenant-gf-b-active-standard"
TENANT_C_ACTIVE_PRO = "tenant-gf-c-active-pro"
TENANT_D_EXISTING_TRIAL = "tenant-gf-d-existing-trial"
TENANT_E_EXPIRED = "tenant-gf-e-expired"
TENANT_F_CANCELLED = "tenant-gf-f-cancelled"
TENANT_G_POST_MIGRATION_NEW = "tenant-gf-g-post-migration-new"


def _make_tenant(tenant_id: str) -> Tenant:
    return Tenant(tenant_id=tenant_id, name=tenant_id, password_hash="x", status=True)


class ExistingTenantGrandfatherTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.free_plan = Plan(code="FREE", name="免费版", is_active=True)
        self.standard_plan = Plan(code="STANDARD", name="普通版", is_active=True)
        self.pro_plan = Plan(code="PRO", name="专业版", is_active=True)
        self.db.add_all([self.free_plan, self.standard_plan, self.pro_plan])
        await self.db.commit()
        await self.db.refresh(self.free_plan)
        await self.db.refresh(self.standard_plan)
        await self.db.refresh(self.pro_plan)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _run_backfill(self, now: datetime = FIXED_NOW) -> int:
        async with self.engine.begin() as conn:
            return await conn.run_sync(lambda sync_conn: backfill_zero_history_tenants(sync_conn, now=now))

    async def _seed_tenants_a_through_f(self):
        self.db.add_all(
            [
                _make_tenant(TENANT_A_ZERO_HISTORY),
                _make_tenant(TENANT_B_ACTIVE_STANDARD),
                _make_tenant(TENANT_C_ACTIVE_PRO),
                _make_tenant(TENANT_D_EXISTING_TRIAL),
                _make_tenant(TENANT_E_EXPIRED),
                _make_tenant(TENANT_F_CANCELLED),
            ]
        )
        await self.db.commit()

        b_sub = Subscription(
            tenant_id=TENANT_B_ACTIVE_STANDARD,
            plan_id=self.standard_plan.id,
            status=STATUS_ACTIVE,
            started_at=FIXED_NOW - timedelta(days=5),
            ends_at=FIXED_NOW + timedelta(days=25),
        )
        c_sub = Subscription(
            tenant_id=TENANT_C_ACTIVE_PRO,
            plan_id=self.pro_plan.id,
            status=STATUS_ACTIVE,
            started_at=FIXED_NOW - timedelta(days=5),
            ends_at=FIXED_NOW + timedelta(days=25),
        )
        d_sub = Subscription(
            tenant_id=TENANT_D_EXISTING_TRIAL,
            plan_id=self.pro_plan.id,
            status=STATUS_TRIAL,
            trial_started_at=FIXED_NOW - timedelta(days=1),
            trial_ends_at=FIXED_NOW + timedelta(days=29),
        )
        e_sub = Subscription(
            tenant_id=TENANT_E_EXPIRED,
            plan_id=self.pro_plan.id,
            status=STATUS_ACTIVE,
            started_at=FIXED_NOW - timedelta(days=400),
            ends_at=FIXED_NOW - timedelta(days=30),
        )
        f_sub = Subscription(
            tenant_id=TENANT_F_CANCELLED,
            plan_id=self.standard_plan.id,
            status=STATUS_CANCELLED,
            started_at=FIXED_NOW - timedelta(days=100),
            ends_at=FIXED_NOW + timedelta(days=265),
        )
        self.db.add_all([b_sub, c_sub, d_sub, e_sub, f_sub])
        await self.db.commit()
        return {
            "B": b_sub.id,
            "C": c_sub.id,
            "D": d_sub.id,
            "E": e_sub.id,
            "F": f_sub.id,
        }

    # ---- ZERO_HISTORY_BACKFILLED -------------------------------------------

    async def test_zero_history_tenant_backfilled(self):
        self.db.add(_make_tenant(TENANT_A_ZERO_HISTORY))
        await self.db.commit()

        inserted = await self._run_backfill()
        self.assertEqual(inserted, 1)

        service = SubscriptionService(self.db)
        current = await service.get_current_subscription(TENANT_A_ZERO_HISTORY)
        self.assertIsNotNone(current)
        self.assertEqual(current.status, STATUS_TRIAL)
        self.assertEqual(current.plan_id, self.pro_plan.id)
        self.assertEqual(current.trial_started_at, FIXED_NOW)
        self.assertEqual(current.trial_ends_at, FIXED_NOW + timedelta(days=TRIAL_DAYS))
        self.assertIsNone(current.started_at)
        self.assertIsNone(current.ends_at)

    # ---- ACTIVE/TRIAL/EXPIRED/CANCELLED history preserved -------------------

    async def test_existing_subscription_history_untouched(self):
        ids_before = await self._seed_tenants_a_through_f()

        inserted = await self._run_backfill()
        self.assertEqual(inserted, 1, "only tenant A (zero history) should be backfilled")

        service = SubscriptionService(self.db)

        b_after = await service.get_current_subscription(TENANT_B_ACTIVE_STANDARD)
        self.assertEqual(b_after.id, ids_before["B"])
        self.assertEqual(b_after.status, STATUS_ACTIVE)
        self.assertEqual(b_after.plan_id, self.standard_plan.id)

        c_after = await service.get_current_subscription(TENANT_C_ACTIVE_PRO)
        self.assertEqual(c_after.id, ids_before["C"])
        self.assertEqual(c_after.status, STATUS_ACTIVE)
        self.assertEqual(c_after.plan_id, self.pro_plan.id)

        d_after = await service.get_current_subscription(TENANT_D_EXISTING_TRIAL)
        self.assertEqual(d_after.id, ids_before["D"])
        self.assertEqual(d_after.status, STATUS_TRIAL)
        self.assertEqual(d_after.trial_ends_at, FIXED_NOW + timedelta(days=29))

        e_after = await service.get_current_subscription(TENANT_E_EXPIRED)
        self.assertEqual(e_after.id, ids_before["E"])
        self.assertEqual(e_after.status, STATUS_ACTIVE)  # row itself unchanged; already-expired by ends_at

        f_after = await service.get_current_subscription(TENANT_F_CANCELLED)
        self.assertEqual(f_after.id, ids_before["F"])
        self.assertEqual(f_after.status, STATUS_CANCELLED)

        # E and F must NOT have been re-granted a fresh trial -- each still
        # has exactly the one historical row, nothing new inserted for them.
        for tenant_id in (TENANT_E_EXPIRED, TENANT_F_CANCELLED):
            result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))
            self.assertEqual(len(result.scalars().all()), 1)

    # ---- IDEMPOTENT -----------------------------------------------------------

    async def test_backfill_is_idempotent(self):
        self.db.add_all([_make_tenant(TENANT_A_ZERO_HISTORY), _make_tenant(TENANT_G_POST_MIGRATION_NEW)])
        await self.db.commit()

        first_pass = await self._run_backfill()
        self.assertEqual(first_pass, 2)

        second_pass = await self._run_backfill()
        self.assertEqual(second_pass, 0, "re-running the backfill must not grant a second trial to anyone")

        service = SubscriptionService(self.db)
        for tenant_id in (TENANT_A_ZERO_HISTORY, TENANT_G_POST_MIGRATION_NEW):
            result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))
            self.assertEqual(len(result.scalars().all()), 1)

    # ---- PRO_CAPABILITIES_PRESERVED (entitlement continuity) ------------------

    async def test_migrated_tenant_keeps_previously_live_capabilities(self):
        self.db.add(_make_tenant(TENANT_A_ZERO_HISTORY))
        await self.db.commit()

        # Before backfill: zero-history tenant resolves FREE, lacks all four.
        pre_service = EntitlementService(self.db)
        self.assertFalse(await pre_service.has_capability(TENANT_A_ZERO_HISTORY, CAP_KITCHEN_PRINT))
        self.assertFalse(await pre_service.has_capability(TENANT_A_ZERO_HISTORY, CAP_MEMBERSHIP))
        self.assertFalse(await pre_service.has_capability(TENANT_A_ZERO_HISTORY, CAP_COUPONS))
        self.assertFalse(await pre_service.has_capability(TENANT_A_ZERO_HISTORY, CAP_DISTRIBUTION_REFERRAL))

        await self._run_backfill()

        # Fresh EntitlementService instance -- no cross-instance cache to bias the result.
        post_service = EntitlementService(self.db)
        self.assertTrue(await post_service.has_capability(TENANT_A_ZERO_HISTORY, CAP_KITCHEN_PRINT))
        self.assertTrue(await post_service.has_capability(TENANT_A_ZERO_HISTORY, CAP_MEMBERSHIP))
        self.assertTrue(await post_service.has_capability(TENANT_A_ZERO_HISTORY, CAP_COUPONS))
        self.assertTrue(await post_service.has_capability(TENANT_A_ZERO_HISTORY, CAP_DISTRIBUTION_REFERRAL))

        sub_service = SubscriptionService(self.db)
        view = await sub_service.get_effective_subscription_view(TENANT_A_ZERO_HISTORY, now=FIXED_NOW)
        self.assertEqual(view.effective_plan.code, PLAN_CODE_PRO)
        self.assertEqual(view.subscription_status, STATUS_TRIAL)
        self.assertTrue(view.is_trial)

    # ---- FREE_FALLBACK_UNCHANGED ------------------------------------------

    async def test_post_migration_new_tenant_without_onboarding_trial_still_free(self):
        """A tenant created AFTER the migration ran (e.g. registration failed
        to grant its trial, or a fixture created outside normal onboarding)
        must still resolve FREE -- the backfill is a one-time historical data
        migration, not a permanent resolver exception for "any zero-history
        tenant, ever"."""
        await self._run_backfill()  # runs against whatever exists now (nothing yet)

        self.db.add(_make_tenant(TENANT_G_POST_MIGRATION_NEW))
        await self.db.commit()

        service = SubscriptionService(self.db)
        view = await service.get_effective_subscription_view(TENANT_G_POST_MIGRATION_NEW, now=FIXED_NOW)
        self.assertEqual(view.subscription_status, "FREE")
        self.assertEqual(view.effective_plan.code, "FREE")

        entitlement = EntitlementService(self.db)
        self.assertFalse(await entitlement.has_capability(TENANT_G_POST_MIGRATION_NEW, CAP_KITCHEN_PRINT))

    # ---- 30_DAY_EXPIRY_TO_FREE ---------------------------------------------

    async def test_migrated_trial_expires_to_free_after_30_days(self):
        self.db.add(_make_tenant(TENANT_A_ZERO_HISTORY))
        await self.db.commit()
        await self._run_backfill()

        just_after_expiry = FIXED_NOW + timedelta(days=TRIAL_DAYS, seconds=1)
        service = SubscriptionService(self.db)
        view = await service.get_effective_subscription_view(TENANT_A_ZERO_HISTORY, now=just_after_expiry)
        self.assertEqual(view.effective_plan.code, "FREE")
        self.assertEqual(view.subscription_status, STATUS_EXPIRED)

        # Lazy/request-time resolution only -- no row mutation, no deletion.
        result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == TENANT_A_ZERO_HISTORY))
        rows = result.scalars().all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status, STATUS_TRIAL)  # row itself untouched

    # ---- TRIAL_TO_PAID_EXISTING_ALGORITHM ----------------------------------

    async def test_migrated_trial_purchase_uses_existing_trial_preservation_algorithm(self):
        self.db.add(_make_tenant(TENANT_A_ZERO_HISTORY))
        await self.db.commit()
        await self._run_backfill()

        service = SubscriptionService(self.db)
        paid_at = FIXED_NOW + timedelta(days=2)  # purchased partway through the trial
        subscription = await service.apply_paid_purchase(
            TENANT_A_ZERO_HISTORY, PLAN_CODE_STANDARD, "MONTH", paid_at=paid_at
        )

        self.assertEqual(subscription.status, STATUS_ACTIVE)
        self.assertEqual(subscription.plan_id, self.standard_plan.id)
        # Same trial-preservation rule as any other TRIAL->PAID purchase:
        # base_time is the unexpired trial's own end, not paid_at.
        expected_base = FIXED_NOW + timedelta(days=TRIAL_DAYS)
        self.assertEqual(subscription.started_at, paid_at)
        self.assertGreater(subscription.ends_at, expected_base)

    # ---- NO_PAYMENT_FACT_CREATED --------------------------------------------

    async def test_backfill_creates_no_billing_fact(self):
        self.db.add(_make_tenant(TENANT_A_ZERO_HISTORY))
        await self.db.commit()
        await self._run_backfill()

        invoices = (await self.db.execute(select(BillingInvoice))).scalars().all()
        payments = (await self.db.execute(select(BillingPayment))).scalars().all()
        self.assertEqual(invoices, [])
        self.assertEqual(payments, [])

        current = await SubscriptionService(self.db).get_current_subscription(TENANT_A_ZERO_HISTORY)
        self.assertIsNone(current.started_at)
        self.assertIsNone(current.ends_at)

    # ---- Fail-closed on missing PRO plan --------------------------------------

    async def test_backfill_fails_closed_without_pro_plan(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        db = SessionLocal()
        try:
            db.add(_make_tenant(TENANT_A_ZERO_HISTORY))
            await db.commit()

            with self.assertRaises(ProPlanMissingError):
                async with engine.begin() as conn:
                    await conn.run_sync(lambda sync_conn: backfill_zero_history_tenants(sync_conn, now=FIXED_NOW))
        finally:
            await db.close()
            await engine.dispose()
