from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

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

PLAN_CODE_FREE = "FREE"
PLAN_CODE_PRO = "PRO"
DEFAULT_TRIAL_DAYS = 30


class SubscriptionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_current_subscription(self, tenant_id: str) -> Optional[Subscription]:
        result = await self.db.execute(
            select(Subscription)
            .where(Subscription.tenant_id == tenant_id)
            .order_by(Subscription.created_at.desc())
        )
        return result.scalars().first()

    async def get_plan_by_code(self, code: str) -> Optional[Plan]:
        result = await self.db.execute(select(Plan).where(Plan.code == code))
        return result.scalar_one_or_none()

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
