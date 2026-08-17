"""Phase F1B — Subscription Renewal Core regression tests.

Scope: docs/saas-subscription-audit.md Phase F1B. Proves the calendar-month
date algorithm and SubscriptionService.apply_paid_purchase() against the
frozen commercial contract: FREE->PAID, TRIAL->PAID (preserving unexpired
trial time), same-plan renewal (early and post-expiry), active-paid
cross-plan blocking, expired/cancelled restart, deterministic
get_current_subscription() ordering, and commit=False composability.

No Billing bridge, no API router, no payment provider exist yet in this
phase -- apply_paid_purchase() is exercised directly as a trusted
"purchase already verified" entry point. Real MySQL row-lock concurrency
is out of scope here (SQLite has no true FOR UPDATE semantics); see
test_tenant_lock_query_path / test_sequential_renewals_accumulate_periods
docstrings for exactly what is and isn't proven by this file.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.services.subscription_service import (
    BILLING_PERIOD_MONTH,
    BILLING_PERIOD_YEAR,
    STATUS_ACTIVE,
    STATUS_TRIAL,
    CrossPlanChangeNotAllowedError,
    InvalidBillingPeriodError,
    PlanInactiveError,
    PlanNotFoundError,
    SubscriptionPurchaseNotAllowedError,
    SubscriptionService,
    TenantNotFoundError,
    _add_calendar_months_clamped,
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
# Pure calendar-month algorithm -- no DB involved.
# ---------------------------------------------------------------------------

class CalendarMonthAlgorithmTest(unittest.TestCase):
    def test_jan31_non_leap(self):
        # CALENDAR_MONTH_JAN31_NON_LEAP_TEST
        self.assertEqual(
            _add_calendar_months_clamped(datetime(2027, 1, 31), 1),
            datetime(2027, 2, 28),
        )

    def test_jan31_leap(self):
        # CALENDAR_MONTH_JAN31_LEAP_TEST
        self.assertEqual(
            _add_calendar_months_clamped(datetime(2028, 1, 31), 1),
            datetime(2028, 2, 29),
        )

    def test_year_leap_day(self):
        # CALENDAR_YEAR_LEAP_DAY_TEST
        self.assertEqual(
            _add_calendar_months_clamped(datetime(2028, 2, 29), 12),
            datetime(2029, 2, 28),
        )

    def test_april_clamp(self):
        # CALENDAR_APRIL_CLAMP_TEST
        self.assertEqual(
            _add_calendar_months_clamped(datetime(2027, 3, 31), 1),
            datetime(2027, 4, 30),
        )

    def test_year_boundary(self):
        # CALENDAR_YEAR_BOUNDARY_TEST
        self.assertEqual(
            _add_calendar_months_clamped(datetime(2027, 12, 31), 1),
            datetime(2028, 1, 31),
        )

    def test_time_of_day_preserved_through_clamp(self):
        self.assertEqual(
            _add_calendar_months_clamped(datetime(2027, 1, 31, 9, 30, 15, 500), 1),
            datetime(2027, 2, 28, 9, 30, 15, 500),
        )


# ---------------------------------------------------------------------------
# apply_paid_purchase() -- DB-backed service tests.
# ---------------------------------------------------------------------------

class ApplyPaidPurchaseTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add_all(
            [
                Plan(code="FREE", name="免费版", is_active=True,
                     price_month_cents=0, price_year_cents=0, sort_order=0),
                Plan(code="STANDARD", name="普通版", is_active=True,
                     price_month_cents=5900, price_year_cents=60900, sort_order=1),
                Plan(code="PRO", name="专业版", is_active=True,
                     price_month_cents=9900, price_year_cents=102200, sort_order=2),
                Plan(code="RETIRED", name="停用版", is_active=False,
                     price_month_cents=1234, price_year_cents=5678, sort_order=99),
            ]
        )
        await self.db.commit()
        self.service = SubscriptionService(self.db)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_tenant(self, tenant_id: str) -> Tenant:
        tenant = Tenant(tenant_id=tenant_id, name=tenant_id, password_hash="x", status=True)
        self.db.add(tenant)
        await self.db.commit()
        return tenant

    async def _make_trial(self, tenant_id: str, trial_ends_at: datetime) -> Subscription:
        plan = await self.service.get_plan_by_code("PRO")
        return await self.service.create_trial(
            tenant_id=tenant_id,
            plan=plan,
            trial_started_at=datetime(2026, 8, 1),
            trial_ends_at=trial_ends_at,
        )

    async def _subscription_count(self, tenant_id: str) -> int:
        result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))
        return len(result.scalars().all())

    # ---- FREE -> PAID -------------------------------------------------

    async def test_free_to_standard_month(self):
        await self._make_tenant("t-free-standard-month")
        paid_at = datetime(2026, 8, 17, 10, 0, 0)
        sub = await self.service.apply_paid_purchase(
            "t-free-standard-month", "STANDARD", BILLING_PERIOD_MONTH, paid_at
        )
        self.assertEqual(sub.status, STATUS_ACTIVE)
        self.assertEqual(sub.started_at, paid_at)
        self.assertEqual(sub.ends_at, datetime(2026, 9, 17, 10, 0, 0))
        self.assertIsNone(sub.trial_started_at)
        self.assertIsNone(sub.trial_ends_at)

    async def test_free_to_standard_year(self):
        await self._make_tenant("t-free-standard-year")
        paid_at = datetime(2026, 8, 17, 10, 0, 0)
        sub = await self.service.apply_paid_purchase(
            "t-free-standard-year", "STANDARD", BILLING_PERIOD_YEAR, paid_at
        )
        self.assertEqual(sub.ends_at, datetime(2027, 8, 17, 10, 0, 0))

    async def test_free_to_pro_month(self):
        await self._make_tenant("t-free-pro-month")
        paid_at = datetime(2026, 8, 17, 10, 0, 0)
        sub = await self.service.apply_paid_purchase(
            "t-free-pro-month", "PRO", BILLING_PERIOD_MONTH, paid_at
        )
        self.assertEqual(sub.ends_at, datetime(2026, 9, 17, 10, 0, 0))

    # ---- TRIAL -> PAID (unexpired trial time must be preserved) ---------

    async def test_trial_to_standard_month(self):
        tenant_id = "t-trial-standard-month"
        await self._make_tenant(tenant_id)
        trial = await self._make_trial(tenant_id, datetime(2026, 8, 31))
        paid_at = datetime(2026, 8, 10)
        sub = await self.service.apply_paid_purchase(tenant_id, "STANDARD", BILLING_PERIOD_MONTH, paid_at)
        self.assertEqual(sub.status, STATUS_ACTIVE)
        self.assertEqual(sub.started_at, paid_at)
        self.assertEqual(sub.ends_at, datetime(2026, 9, 30))
        # old trial row is history -- must not be mutated.
        reloaded_trial = await self.db.get(Subscription, trial.id)
        self.assertEqual(reloaded_trial.status, STATUS_TRIAL)
        self.assertEqual(reloaded_trial.trial_ends_at, datetime(2026, 8, 31))

    async def test_trial_to_standard_year(self):
        # Frozen-contract example: trial 2026-08-01..2026-08-31, buy 2026-08-10 -> 2027-08-31.
        tenant_id = "t-trial-standard-year"
        await self._make_tenant(tenant_id)
        await self._make_trial(tenant_id, datetime(2026, 8, 31))
        paid_at = datetime(2026, 8, 10)
        sub = await self.service.apply_paid_purchase(tenant_id, "STANDARD", BILLING_PERIOD_YEAR, paid_at)
        self.assertEqual(sub.started_at, paid_at)
        self.assertEqual(sub.ends_at, datetime(2027, 8, 31))

    async def test_trial_to_pro(self):
        tenant_id = "t-trial-pro"
        await self._make_tenant(tenant_id)
        await self._make_trial(tenant_id, datetime(2026, 8, 31))
        paid_at = datetime(2026, 8, 10)
        sub = await self.service.apply_paid_purchase(tenant_id, "PRO", BILLING_PERIOD_MONTH, paid_at)
        self.assertEqual(sub.ends_at, datetime(2026, 9, 30))

    # ---- SAME PLAN renewal ------------------------------------------------

    async def test_same_plan_early_renewal(self):
        # ends 2027-08-17, renew 2027-07-01 YEAR -> 2028-08-17 (extends from
        # the still-unexpired old end, not from paid_at).
        tenant_id = "t-same-plan-early"
        await self._make_tenant(tenant_id)
        first = await self.service.apply_paid_purchase(
            tenant_id, "STANDARD", BILLING_PERIOD_YEAR, datetime(2026, 8, 17)
        )
        self.assertEqual(first.ends_at, datetime(2027, 8, 17))
        second = await self.service.apply_paid_purchase(
            tenant_id, "STANDARD", BILLING_PERIOD_YEAR, datetime(2027, 7, 1)
        )
        self.assertEqual(second.started_at, datetime(2027, 7, 1))
        self.assertEqual(second.ends_at, datetime(2028, 8, 17))

    async def test_same_plan_expired_renewal(self):
        tenant_id = "t-same-plan-expired"
        await self._make_tenant(tenant_id)
        first = await self.service.apply_paid_purchase(
            tenant_id, "STANDARD", BILLING_PERIOD_MONTH, datetime(2026, 1, 1)
        )
        self.assertEqual(first.ends_at, datetime(2026, 2, 1))
        paid_at = datetime(2026, 6, 15)  # well after 2026-02-01 expiry
        second = await self.service.apply_paid_purchase(tenant_id, "STANDARD", BILLING_PERIOD_MONTH, paid_at)
        self.assertEqual(second.started_at, paid_at)
        self.assertEqual(second.ends_at, datetime(2026, 7, 15))

    # ---- EXPIRED no longer blocks a different plan -----------------------

    async def test_expired_standard_can_buy_pro(self):
        tenant_id = "t-expired-to-pro"
        await self._make_tenant(tenant_id)
        await self.service.apply_paid_purchase(tenant_id, "STANDARD", BILLING_PERIOD_MONTH, datetime(2026, 1, 1))
        paid_at = datetime(2026, 6, 15)
        sub = await self.service.apply_paid_purchase(tenant_id, "PRO", BILLING_PERIOD_MONTH, paid_at)
        self.assertEqual(sub.started_at, paid_at)
        self.assertEqual(sub.ends_at, datetime(2026, 7, 15))
        pro_plan = await self.service.get_plan_by_code("PRO")
        self.assertEqual(sub.plan_id, pro_plan.id)

    # ---- ACTIVE PAID cross-plan defense -----------------------------------

    async def test_active_standard_to_pro_blocked(self):
        tenant_id = "t-active-standard-blocked"
        await self._make_tenant(tenant_id)
        await self.service.apply_paid_purchase(tenant_id, "STANDARD", BILLING_PERIOD_YEAR, datetime(2026, 8, 17))
        with self.assertRaises(CrossPlanChangeNotAllowedError):
            await self.service.apply_paid_purchase(tenant_id, "PRO", BILLING_PERIOD_MONTH, datetime(2026, 9, 1))
        self.assertEqual(await self._subscription_count(tenant_id), 1)

    async def test_active_pro_to_standard_blocked(self):
        tenant_id = "t-active-pro-blocked"
        await self._make_tenant(tenant_id)
        await self.service.apply_paid_purchase(tenant_id, "PRO", BILLING_PERIOD_YEAR, datetime(2026, 8, 17))
        with self.assertRaises(CrossPlanChangeNotAllowedError):
            await self.service.apply_paid_purchase(tenant_id, "STANDARD", BILLING_PERIOD_MONTH, datetime(2026, 9, 1))
        self.assertEqual(await self._subscription_count(tenant_id), 1)

    # ---- CANCELLED restart --------------------------------------------

    async def test_cancelled_can_buy_new_plan(self):
        tenant_id = "t-cancelled-restart"
        await self._make_tenant(tenant_id)
        sub = await self.service.apply_paid_purchase(tenant_id, "STANDARD", BILLING_PERIOD_YEAR, datetime(2026, 8, 17))
        await self.service.cancel(sub)
        paid_at = datetime(2026, 9, 1)
        new_sub = await self.service.apply_paid_purchase(tenant_id, "PRO", BILLING_PERIOD_MONTH, paid_at)
        self.assertEqual(new_sub.status, STATUS_ACTIVE)
        self.assertEqual(new_sub.started_at, paid_at)
        self.assertEqual(new_sub.ends_at, datetime(2026, 10, 1))

    # ---- Input validation --------------------------------------------

    async def test_unknown_plan(self):
        await self._make_tenant("t-unknown-plan")
        with self.assertRaises(PlanNotFoundError):
            await self.service.apply_paid_purchase(
                "t-unknown-plan", "ENTERPRISE", BILLING_PERIOD_MONTH, datetime(2026, 8, 17)
            )

    async def test_inactive_plan(self):
        await self._make_tenant("t-inactive-plan")
        with self.assertRaises(PlanInactiveError):
            await self.service.apply_paid_purchase(
                "t-inactive-plan", "RETIRED", BILLING_PERIOD_MONTH, datetime(2026, 8, 17)
            )

    async def test_free_plan_not_payable(self):
        await self._make_tenant("t-free-not-payable")
        with self.assertRaises(SubscriptionPurchaseNotAllowedError):
            await self.service.apply_paid_purchase(
                "t-free-not-payable", "FREE", BILLING_PERIOD_MONTH, datetime(2026, 8, 17)
            )

    async def test_invalid_period(self):
        await self._make_tenant("t-invalid-period")
        with self.assertRaises(InvalidBillingPeriodError):
            await self.service.apply_paid_purchase(
                "t-invalid-period", "STANDARD", "WEEK", datetime(2026, 8, 17)
            )

    async def test_tenant_not_found(self):
        with self.assertRaises(TenantNotFoundError):
            await self.service.apply_paid_purchase(
                "no-such-tenant", "STANDARD", BILLING_PERIOD_MONTH, datetime(2026, 8, 17)
            )

    # ---- get_current_subscription deterministic ordering -----------------

    async def test_current_subscription_deterministic_tiebreak(self):
        """Two rows with an identical created_at must still resolve
        deterministically: id DESC breaks the tie (Phase F1B)."""
        tenant_id = "t-order-tiebreak"
        await self._make_tenant(tenant_id)
        same_ts = datetime(2026, 8, 17, 12, 0, 0)
        plan = await self.service.get_plan_by_code("STANDARD")

        older = Subscription(
            tenant_id=tenant_id, plan_id=plan.id, status=STATUS_ACTIVE,
            started_at=same_ts, ends_at=same_ts, created_at=same_ts,
        )
        self.db.add(older)
        await self.db.commit()
        await self.db.refresh(older)

        newer = Subscription(
            tenant_id=tenant_id, plan_id=plan.id, status=STATUS_ACTIVE,
            started_at=same_ts, ends_at=same_ts, created_at=same_ts,
        )
        self.db.add(newer)
        await self.db.commit()
        await self.db.refresh(newer)

        self.assertEqual(older.created_at, newer.created_at)
        self.assertGreater(newer.id, older.id)
        current = await self.service.get_current_subscription(tenant_id)
        self.assertEqual(current.id, newer.id)

    # ---- commit=False composability (F1C billing-transaction gate) -------

    async def test_commit_false_does_not_commit(self):
        """commit=False must not call self.db.commit(): proven by wrapping
        the actual bound AsyncSession.commit and asserting it is never
        invoked (not source-text inspection), plus behavioral confirmation
        that the row only exists via flush() -- a rollback on this same
        session discards it entirely, proving nothing was durably committed.

        (A second independent SessionLocal() against this in-memory SQLite
        engine is deliberately NOT used to prove non-visibility here: this
        engine's pool hands out the same underlying connection to every
        session, so an uncommitted flush on one session is visible to another
        session sharing that connection -- that would test SQLite's pooling,
        not apply_paid_purchase's commit contract.)"""
        tenant_id = "t-commit-false"
        await self._make_tenant(tenant_id)
        paid_at = datetime(2026, 8, 17)

        commit_calls = []
        original_commit = self.db.commit

        async def _tracking_commit():
            commit_calls.append(True)
            return await original_commit()

        self.db.commit = _tracking_commit
        try:
            sub = await self.service.apply_paid_purchase(
                tenant_id, "STANDARD", BILLING_PERIOD_MONTH, paid_at, commit=False
            )
        finally:
            self.db.commit = original_commit

        self.assertEqual(commit_calls, [], "apply_paid_purchase(commit=False) must not call self.db.commit()")
        self.assertIsNotNone(sub.id)

        # flush() made it visible within THIS session/transaction...
        result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))
        self.assertEqual(len(result.scalars().all()), 1)

        # ...but it was never committed, so a rollback discards it entirely.
        await self.db.rollback()
        result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))
        self.assertEqual(len(result.scalars().all()), 0)

    async def test_commit_true_is_visible_to_other_sessions(self):
        tenant_id = "t-commit-true"
        await self._make_tenant(tenant_id)
        paid_at = datetime(2026, 8, 17)
        await self.service.apply_paid_purchase(
            tenant_id, "STANDARD", BILLING_PERIOD_MONTH, paid_at, commit=True
        )
        other_session = self.SessionLocal()
        try:
            result = await other_session.execute(
                select(Subscription).where(Subscription.tenant_id == tenant_id)
            )
            self.assertEqual(len(result.scalars().all()), 1)
        finally:
            await other_session.close()

    # ---- Tenant row lock contract -----------------------------------------

    async def test_tenant_lock_query_path(self):
        """apply_paid_purchase must select the Tenant row with
        .with_for_update(), same pattern as create_trial_for_tenant().
        Checked via Select._for_update_arg rather than string-matching
        rendered SQL, because SQLite's dialect silently drops the FOR UPDATE
        clause at compile time (no real row locking) -- this proves the
        query/path was taken, not MySQL locking semantics.
        MYSQL_ROW_LOCK_CONCURRENCY_TEST is deliberately deferred to a real
        MySQL gate."""
        tenant_id = "t-lock-path"
        await self._make_tenant(tenant_id)
        seen_for_update_on_tenants = []

        def _capture(conn, clauseelement, multiparams, params, execution_options):
            if getattr(clauseelement, "_for_update_arg", None) is not None:
                if "tenant" in str(clauseelement):
                    seen_for_update_on_tenants.append(True)

        event.listen(self.engine.sync_engine, "before_execute", _capture)
        try:
            await self.service.apply_paid_purchase(
                tenant_id, "STANDARD", BILLING_PERIOD_MONTH, datetime(2026, 8, 17)
            )
        finally:
            event.remove(self.engine.sync_engine, "before_execute", _capture)

        self.assertTrue(
            seen_for_update_on_tenants,
            "apply_paid_purchase must SELECT the Tenant row FOR UPDATE",
        )

    async def test_sequential_renewals_accumulate_periods(self):
        """Two sequential same-plan renewals for the same tenant must each
        see the other's new ends_at and accumulate both paid periods. This
        is the sequential half of the tenant-lock contract; concurrent
        MySQL transaction locking is DEFERRED (see class docstring)."""
        tenant_id = "t-sequential-accumulate"
        await self._make_tenant(tenant_id)
        first = await self.service.apply_paid_purchase(
            tenant_id, "STANDARD", BILLING_PERIOD_MONTH, datetime(2026, 1, 1)
        )
        second = await self.service.apply_paid_purchase(
            tenant_id, "STANDARD", BILLING_PERIOD_MONTH, datetime(2026, 1, 15)
        )
        self.assertEqual(first.ends_at, datetime(2026, 2, 1))
        # second renewal must extend from first's new ends_at (2026-02-01 >
        # paid_at 2026-01-15), not from paid_at -- proves the re-read after
        # the lock actually picks up the first purchase's effect.
        self.assertEqual(second.ends_at, datetime(2026, 3, 1))
        self.assertEqual(await self._subscription_count(tenant_id), 2)


if __name__ == "__main__":
    unittest.main()
