from __future__ import annotations

import calendar
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant

# Phase 02/03/04 — Subscription Data Skeleton + Trial Provisioning + Registration
# Integration (docs/saas-subscription-audit.md).
#
# This service is intentionally an isolated domain. Its only production caller
# (Phase 04) is POST /api/v1/register in app/api/v1/login.py, which calls
# create_trial_for_tenant() after creating a Tenant — nothing else calls in.
# It must never call TenantService / OrderService / OrderPaymentService / WxPayService /
# order_print_service / MembershipService / CouponService / BillingService / SMS,
# and it must never write to Tenant.status — Tenant.status is a manual ban switch,
# unrelated to subscription state (audit §10/§15). It only reaches judgments
# (is_trial/is_active); it never disables a tenant, changes a plan, hides a
# feature, or blocks an API. The one Tenant touch that IS allowed is reading the
# Tenant row directly (model import, not a TenantService call) to confirm the
# tenant exists and to serialize concurrent trial creation for the same tenant
# — see create_trial_for_tenant().

STATUS_TRIAL = "TRIAL"
STATUS_ACTIVE = "ACTIVE"
STATUS_EXPIRED = "EXPIRED"
STATUS_CANCELLED = "CANCELLED"

# API-facing subscription_status value for "no Subscription row at all"
# (Phase F1D, GET /api/v1/subscription/current). Deliberately a separate
# constant from PLAN_CODE_FREE below even though the string value matches --
# one names a Plan.code, the other a subscription_status a merchant sees.
SUBSCRIPTION_STATUS_FREE = "FREE"

PLAN_CODE_FREE = "FREE"
PLAN_CODE_STANDARD = "STANDARD"
PLAN_CODE_PRO = "PRO"
DEFAULT_TRIAL_DAYS = 30

BILLING_PERIOD_MONTH = "MONTH"
BILLING_PERIOD_YEAR = "YEAR"
_VALID_BILLING_PERIODS = (BILLING_PERIOD_MONTH, BILLING_PERIOD_YEAR)
_CALENDAR_MONTHS_PER_PERIOD = {
    BILLING_PERIOD_MONTH: 1,
    BILLING_PERIOD_YEAR: 12,
}


def _add_calendar_months_clamped(dt: datetime, months: int) -> datetime:
    """Add `months` calendar months to `dt`, clamping the day-of-month to the
    target month's last valid day (Jan 31 + 1 month = Feb 28/29, never
    rolling over into March). hour/minute/second/microsecond pass through
    unchanged via datetime.replace(); naive-UTC convention is untouched.

    Deliberately stdlib-only (calendar.monthrange), not
    timedelta(days=30)/timedelta(days=365), which drift against real
    calendar-month/year billing periods (Phase F1B,
    docs/saas-subscription-audit.md)."""
    total_months = dt.month - 1 + months
    year = dt.year + total_months // 12
    month = total_months % 12 + 1
    last_day_of_month = calendar.monthrange(year, month)[1]
    day = min(dt.day, last_day_of_month)
    return dt.replace(year=year, month=month, day=day)


def resolve_days_remaining(effective_end: Optional[datetime], *, now: Optional[datetime] = None) -> int:
    """Frozen ceil-days display algorithm (Phase F1D): 0 if there's no
    effective_end or it's already passed; otherwise ceil(remaining_seconds /
    86400) -- 3h remaining is "1 day", exactly 24h remaining is "1 day",
    24h+1s remaining is "2 days". Public (no leading underscore): the F1D API
    layer calls this directly to render GET /current's days_remaining."""
    if effective_end is None:
        return 0
    now = now or datetime.utcnow()
    remaining_seconds = (effective_end - now).total_seconds()
    if remaining_seconds <= 0:
        return 0
    return math.ceil(remaining_seconds / 86400)

# Plan price resolution errors (Phase F1A). Plain ValueError subclasses,
# following the existing repo convention (see PaymentFactError in
# app/services/order_payment_service.py) rather than a bespoke exception
# framework for just four cases.


class PlanResolutionError(ValueError):
    pass


class PlanNotFoundError(PlanResolutionError):
    pass


class PlanInactiveError(PlanResolutionError):
    pass


class InvalidBillingPeriodError(PlanResolutionError):
    pass


class SubscriptionPurchaseNotAllowedError(PlanResolutionError):
    pass


class CrossPlanChangeNotAllowedError(PlanResolutionError):
    """Raised when a tenant with an active, unexpired paid subscription tries
    to purchase a *different* plan. V1 has no proration/credit/pending-switch
    -- the tenant must let the current plan run out (or cancel) first."""

    pass


class TenantNotFoundError(ValueError):
    pass


class PlanDataIntegrityError(RuntimeError):
    """Raised when the plan catalog is missing data the frozen commercial
    contract guarantees should exist -- e.g. no FREE row, or a Subscription
    referencing a plan_id that no longer exists in `plans`. This is a
    server-side data problem, not a client input error (hence RuntimeError,
    not a PlanResolutionError/ValueError): never silently fabricate a
    placeholder Plan to paper over it (Phase F1D)."""

    pass


@dataclass(frozen=True)
class EffectiveSubscriptionView:
    """Merchant-facing read model for GET /api/v1/subscription/current
    (Phase F1D). Deliberately not an entitlement object -- nothing outside
    this file reads Subscription state to authorize behavior (see the module
    docstring above); this only answers what the merchant should see."""

    effective_plan: Plan
    subscription_status: str
    is_trial: bool
    trial_ends_at: Optional[datetime]
    paid_started_at: Optional[datetime]
    paid_ends_at: Optional[datetime]
    days_remaining: int
    can_renew: bool


class SubscriptionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_current_subscription(self, tenant_id: str) -> Optional[Subscription]:
        result = await self.db.execute(
            select(Subscription)
            .where(Subscription.tenant_id == tenant_id)
            .order_by(Subscription.created_at.desc(), Subscription.id.desc())
        )
        return result.scalars().first()

    async def get_plan_by_code(self, code: str) -> Optional[Plan]:
        result = await self.db.execute(select(Plan).where(Plan.code == code))
        return result.scalar_one_or_none()

    async def get_active_plans(self) -> List[Plan]:
        """Plan catalog, is_active=true only, sort_order ASC then id ASC as a
        stable secondary order (two plans never share a sort_order in the
        frozen commercial contract, but this keeps the ordering deterministic
        even if that ever changes)."""
        result = await self.db.execute(
            select(Plan)
            .where(Plan.is_active.is_(True))
            .order_by(Plan.sort_order.asc(), Plan.id.asc())
        )
        return list(result.scalars().all())

    async def _require_plan_by_id(self, plan_id: int) -> Plan:
        result = await self.db.execute(select(Plan).where(Plan.id == plan_id))
        plan = result.scalar_one_or_none()
        if plan is None:
            raise PlanDataIntegrityError(f"subscription references missing plan_id={plan_id}")
        return plan

    async def _require_free_plan(self) -> Plan:
        plan = await self.get_plan_by_code(PLAN_CODE_FREE)
        if plan is None:
            raise PlanDataIntegrityError("FREE plan is missing from the plan catalog")
        return plan

    async def get_effective_subscription_view(
        self, tenant_id: str, *, now: Optional[datetime] = None
    ) -> EffectiveSubscriptionView:
        """Read-only resolution for GET /api/v1/subscription/current (Phase
        F1D). Reuses is_active()/is_trial() (Phase 02) rather than
        re-deriving expiry logic, so this always agrees with the judgments
        those two already make elsewhere.

        can_renew is unconditionally True here: AuthMiddleware already blocks
        banned/inactive tenants before a request reaches this far (see
        _is_tenant_active in app/middleware/auth_middleware.py), and every
        remaining status (FREE/TRIAL/ACTIVE/EXPIRED/CANCELLED) permits at
        least a STANDARD/PRO purchase per the frozen commercial contract --
        so there is no second tenant-eligibility judgment to make here.
        """
        now = now or datetime.utcnow()
        current = await self.get_current_subscription(tenant_id)
        unexpired = self.is_active(current, now=now)

        if current is not None and unexpired and current.status == STATUS_ACTIVE:
            plan = await self._require_plan_by_id(current.plan_id)
            return EffectiveSubscriptionView(
                effective_plan=plan,
                subscription_status=STATUS_ACTIVE,
                is_trial=False,
                trial_ends_at=None,
                paid_started_at=current.started_at,
                paid_ends_at=current.ends_at,
                days_remaining=resolve_days_remaining(current.ends_at, now=now),
                can_renew=True,
            )

        if current is not None and unexpired and self.is_trial(current):
            plan = await self._require_plan_by_id(current.plan_id)
            return EffectiveSubscriptionView(
                effective_plan=plan,
                subscription_status=STATUS_TRIAL,
                is_trial=True,
                trial_ends_at=current.trial_ends_at,
                paid_started_at=None,
                paid_ends_at=None,
                days_remaining=resolve_days_remaining(current.trial_ends_at, now=now),
                can_renew=True,
            )

        free_plan = await self._require_free_plan()
        if current is None:
            status = SUBSCRIPTION_STATUS_FREE
        elif current.status == STATUS_CANCELLED:
            status = STATUS_CANCELLED
        else:
            # ACTIVE or TRIAL, but expired (unexpired was False above) -- or
            # any other/future stored status: no current entitlement.
            status = STATUS_EXPIRED
        return EffectiveSubscriptionView(
            effective_plan=free_plan,
            subscription_status=status,
            is_trial=False,
            trial_ends_at=None,
            paid_started_at=None,
            paid_ends_at=None,
            days_remaining=0,
            can_renew=True,
        )

    async def validate_renewal_purchase(
        self, tenant_id: str, plan_code: str, billing_period: str, *, now: Optional[datetime] = None
    ) -> tuple[Plan, int]:
        """Pre-payment validation for POST /api/v1/subscription/renewal-orders
        (Phase F1D). Reuses resolve_plan_price() for the plan/period/price
        checks (plan exists, is_active, not FREE, billing_period valid) and
        adds the cross-plan-purchase gate on top, evaluated at invoice-
        creation time (`now`).

        This is a fail-fast convenience check, NOT the authoritative one:
        apply_paid_purchase() (Phase F1C/F1B) re-checks for real at actual
        payment time, since state can change between order creation and
        payment (e.g. the blocking subscription expires, or another renewal
        completes first) -- SubscriptionService remains the last-resort
        domain invariant regardless of what this endpoint already rejected.

        Deliberately duplicates apply_paid_purchase()'s small cross-plan
        predicate rather than refactoring that already-tested method to share
        it -- the two are evaluated at different reference times (`now` here
        vs. actual `paid_at` there) and this phase's instructions are to
        touch existing, frozen F1B/F1C logic only if truly necessary.
        """
        now = now or datetime.utcnow()
        amount_cents = await self.resolve_plan_price(plan_code, billing_period)
        plan = await self.get_plan_by_code(plan_code)

        current = await self.get_current_subscription(tenant_id)
        if (
            current is not None
            and current.status == STATUS_ACTIVE
            and current.ends_at is not None
            and current.ends_at > now
            and current.plan_id != plan.id
        ):
            raise CrossPlanChangeNotAllowedError(
                f"tenant {tenant_id!r} has an active paid subscription for a "
                f"different plan; cannot switch to {plan_code!r} while active"
            )
        return plan, amount_cents

    async def resolve_plan_price(self, plan_code: str, billing_period: str) -> int:
        """Fixed final price in integer cents, read directly from the Plan row
        this DB is the sole price authority. Never ×12×0.86, never float,
        never a client-supplied amount (docs/saas-subscription-audit.md Phase
        F1A). FREE is never payable."""
        if billing_period not in _VALID_BILLING_PERIODS:
            raise InvalidBillingPeriodError(f"invalid billing_period: {billing_period!r}")

        plan = await self.get_plan_by_code(plan_code)
        if plan is None:
            raise PlanNotFoundError(f"plan not found: {plan_code!r}")
        if not plan.is_active:
            raise PlanInactiveError(f"plan inactive: {plan_code!r}")
        if plan.code == PLAN_CODE_FREE:
            raise SubscriptionPurchaseNotAllowedError("FREE plan is not payable")

        if billing_period == BILLING_PERIOD_MONTH:
            return plan.price_month_cents
        return plan.price_year_cents

    async def ensure_plan(self, code: str, name: str, *, commit: bool = True) -> Plan:
        """get-or-create, idempotent under concurrent callers.

        Plan.code carries a DB-level UniqueConstraint (ux_plan_code, Phase 02).
        Two concurrent ensure_plan("PRO", ...) calls can both pass the
        get_plan_by_code() check before either commits; the loser's INSERT then
        hits that unique constraint. We catch exactly that, roll back, and
        re-read the row the winner created — never swallowing any other
        IntegrityError (re-raised as-is if the row still isn't there after
        rollback, since that means something else caused the failure).

        commit=False (used by create_trial_for_tenant() when it's itself being
        called with commit=False, i.e. as part of a larger caller-owned
        transaction such as registration) deliberately skips that local
        catch-and-rollback: rolling back here would also discard whatever else
        the caller already flushed earlier in the SAME transaction (e.g. a
        just-created, not-yet-committed Tenant), which is not this method's
        business to decide. A flush()-time IntegrityError is left to propagate
        to the caller, whose own rollback handles it correctly, and whose retry
        (or the end client's retry) then finds the Plan the concurrent winner
        already committed. In practice this only matters for the very first
        ever ensure_plan("PRO") in the system's history — after that the row
        exists permanently and every call takes the fast read-only path above.
        """
        existing = await self.get_plan_by_code(code)
        if existing is not None:
            return existing
        plan = Plan(code=code, name=name, is_active=True)
        self.db.add(plan)
        if not commit:
            await self.db.flush()
            await self.db.refresh(plan)
            return plan
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            existing = await self.get_plan_by_code(code)
            if existing is None:
                raise
            return existing
        await self.db.refresh(plan)
        return plan

    async def create_trial_for_tenant(
        self,
        tenant_id: str,
        trial_days: int = DEFAULT_TRIAL_DAYS,
        *,
        commit: bool = True,
    ) -> Subscription:
        """Create a PRO trial for an explicit, already-existing tenant.

        Idempotency rule (deliberately uniform across every status): if the
        tenant already has ANY subscription row — TRIAL, ACTIVE, EXPIRED, or
        CANCELLED — this returns it unchanged. It never resets a trial's
        countdown, never overwrites an ACTIVE paid subscription, and never
        auto-re-trials an EXPIRED/CANCELLED tenant (that's a future business
        decision, not this phase's).

        Concurrency: two overlapping calls for the SAME tenant_id must not both
        insert a Subscription row. There is no DB-level uniqueness on
        subscriptions.tenant_id (Phase 02 deliberately allows multiple historical
        rows per tenant), so this locks the Tenant row itself
        (SELECT ... FOR UPDATE) as the per-tenant serialization point: the second
        caller blocks until the first's transaction commits, then its own
        get_current_subscription() re-check sees the row the first caller just
        created and returns that instead of inserting a duplicate. (SQLite, used
        in tests, has no real row locking and silently no-ops the FOR UPDATE
        clause — this only becomes a true lock under MySQL/production. See the
        test file's own docstring for what is and isn't actually proven by the
        test suite.)

        commit=False lets a caller (the self-registration endpoint) fold the
        Subscription insert -- and, on the rare first-ever call, the Plan insert
        too, see ensure_plan()'s own docstring -- into the SAME transaction as
        the Tenant it was just created in, so a failure here rolls back the
        tenant too instead of leaving an orphaned, trial-less tenant.
        """
        plan = await self.ensure_plan(PLAN_CODE_PRO, "专业版", commit=commit)

        tenant_result = await self.db.execute(
            select(Tenant).where(Tenant.tenant_id == tenant_id).with_for_update()
        )
        tenant = tenant_result.scalar_one_or_none()
        if tenant is None:
            raise ValueError(f"tenant not found: {tenant_id}")

        existing = await self.get_current_subscription(tenant_id)
        if existing is not None:
            return existing

        now = datetime.utcnow()
        return await self.create_trial(
            tenant_id=tenant_id,
            plan=plan,
            trial_started_at=now,
            trial_ends_at=now + timedelta(days=trial_days),
            commit=commit,
        )

    async def create_trial(
        self,
        tenant_id: str,
        plan: Plan,
        trial_started_at: datetime,
        trial_ends_at: datetime,
        *,
        commit: bool = True,
    ) -> Subscription:
        subscription = Subscription(
            tenant_id=tenant_id,
            plan_id=plan.id,
            status=STATUS_TRIAL,
            trial_started_at=trial_started_at,
            trial_ends_at=trial_ends_at,
        )
        self.db.add(subscription)
        if commit:
            await self.db.commit()
        else:
            await self.db.flush()
        await self.db.refresh(subscription)
        return subscription

    async def apply_paid_purchase(
        self,
        tenant_id: str,
        plan_code: str,
        billing_period: str,
        paid_at: datetime,
        *,
        commit: bool = True,
    ) -> Subscription:
        """Apply a verified paid purchase (Phase F1B, docs/saas-subscription-audit.md).

        The caller (future F1C BillingService) is solely responsible for
        confirming the purchase actually succeeded and for exactly-once
        delivery via BillingInvoice.success_processed_at -- this method does
        zero idempotency bookkeeping of its own (no billing_invoice FK, no
        processed-purchase table: a second "was this already applied"
        authority would fight the one F1C already owns). Every call here is
        trusted to represent a genuinely new, not-yet-applied paid event.

        Always INSERTs a new Subscription row -- never mutates the tenant's
        existing TRIAL/ACTIVE row, which is kept as unmodified history.

        FREE->PAID, TRIAL->PAID, and same-plan renewal all extend from
        whichever is later of (a) the tenant's current unexpired entitlement
        end and (b) paid_at, so early renewal never shortens what was already
        paid for and a lapsed/cancelled entitlement never grants free
        backdated time. A still-active, unexpired paid plan blocks switching
        to any *other* plan (no proration/credit/pending-switch in V1) --
        this is the last-resort domain invariant; the future F1D API/Invoice
        layer is expected to reject the same case earlier, but this must not
        rely on that alone.

        commit=False lets a future caller (F1C's BillingService, inside its
        own open transaction) fold this insert into that same transaction
        instead of committing here -- see ensure_plan()/create_trial()'s own
        commit=False handling for the same pattern in this file.
        """
        if billing_period not in _VALID_BILLING_PERIODS:
            raise InvalidBillingPeriodError(f"invalid billing_period: {billing_period!r}")
        if paid_at is None:
            raise ValueError("paid_at is required")

        plan = await self.get_plan_by_code(plan_code)
        if plan is None:
            raise PlanNotFoundError(f"plan not found: {plan_code!r}")
        if not plan.is_active:
            raise PlanInactiveError(f"plan inactive: {plan_code!r}")
        if plan.code == PLAN_CODE_FREE:
            raise SubscriptionPurchaseNotAllowedError("FREE plan is not payable")

        # Serialize concurrent purchases for the SAME tenant on the tenant row
        # itself -- same per-tenant lock pattern as create_trial_for_tenant().
        # The second of two near-simultaneous paid purchases must block until
        # the first commits, then its own get_current_subscription() re-read
        # (below) sees the first purchase's new ends_at as the base to extend
        # from. Without this, both transactions could read the same stale
        # current subscription and one paid period would be silently lost.
        tenant_result = await self.db.execute(
            select(Tenant).where(Tenant.tenant_id == tenant_id).with_for_update()
        )
        tenant = tenant_result.scalar_one_or_none()
        if tenant is None:
            raise TenantNotFoundError(f"tenant not found: {tenant_id}")

        current = await self.get_current_subscription(tenant_id)
        base_time = paid_at
        if current is not None:
            if current.status == STATUS_TRIAL:
                if current.trial_ends_at is not None and current.trial_ends_at > paid_at:
                    base_time = current.trial_ends_at
                # else: trial already lapsed -- nothing left to preserve,
                # base_time stays paid_at.
            elif current.status == STATUS_ACTIVE:
                if current.ends_at is not None and current.ends_at > paid_at:
                    # Still-active paid entitlement: only a same-plan renewal
                    # is allowed. Compared by plan_id rather than re-fetching
                    # current's Plan row -- equivalent given Plan.code's
                    # DB-level uniqueness (ux_plan_code, Phase 02).
                    if current.plan_id != plan.id:
                        raise CrossPlanChangeNotAllowedError(
                            f"tenant {tenant_id!r} has an active paid subscription for a "
                            f"different plan; cannot switch to {plan_code!r} while active"
                        )
                    base_time = current.ends_at
                # else: ACTIVE but ends_at already passed -- treated as
                # expired, base_time stays paid_at, no cross-plan block.
            # STATUS_CANCELLED, STATUS_EXPIRED, or any other stored status:
            # no current entitlement to extend or protect -- base_time stays
            # paid_at, any paid plan may be purchased.

        months = _CALENDAR_MONTHS_PER_PERIOD[billing_period]
        new_ends_at = _add_calendar_months_clamped(base_time, months)

        subscription = Subscription(
            tenant_id=tenant_id,
            plan_id=plan.id,
            status=STATUS_ACTIVE,
            started_at=paid_at,
            ends_at=new_ends_at,
            trial_started_at=None,
            trial_ends_at=None,
        )
        self.db.add(subscription)
        if commit:
            await self.db.commit()
        else:
            await self.db.flush()
        await self.db.refresh(subscription)
        return subscription

    async def activate(
        self,
        subscription: Subscription,
        started_at: datetime,
        ends_at: Optional[datetime] = None,
    ) -> Subscription:
        subscription.status = STATUS_ACTIVE
        subscription.started_at = started_at
        subscription.ends_at = ends_at
        await self.db.commit()
        await self.db.refresh(subscription)
        return subscription

    async def cancel(self, subscription: Subscription) -> Subscription:
        subscription.status = STATUS_CANCELLED
        await self.db.commit()
        await self.db.refresh(subscription)
        return subscription

    def is_trial(self, subscription: Optional[Subscription]) -> bool:
        return bool(subscription and subscription.status == STATUS_TRIAL)

    def is_active(self, subscription: Optional[Subscription], *, now: Optional[datetime] = None) -> bool:
        """纯领域判断，不执行任何动作——不禁用租户、不改套餐、不隐藏功能、不拦 API。"""
        if not subscription:
            return False
        now = now or datetime.utcnow()
        if subscription.status == STATUS_ACTIVE:
            return subscription.ends_at is None or now < subscription.ends_at
        if subscription.status == STATUS_TRIAL:
            return subscription.trial_ends_at is None or now < subscription.trial_ends_at
        return False
