from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Plan, Subscription

# Phase 02 — Subscription Data Skeleton (docs/saas-subscription-audit.md).
#
# This service is intentionally an isolated domain with no production caller yet.
# It must never call TenantService / OrderService / OrderPaymentService / WxPayService /
# order_print_service / MembershipService / CouponService / SMS, and it must never
# write to Tenant.status — Tenant.status is a manual ban switch, unrelated to
# subscription state (audit §10/§15). It only reaches judgments (is_trial/is_active);
# it never disables a tenant, changes a plan, hides a feature, or blocks an API.

STATUS_TRIAL = "TRIAL"
STATUS_ACTIVE = "ACTIVE"
STATUS_EXPIRED = "EXPIRED"
STATUS_CANCELLED = "CANCELLED"


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

    async def create_trial(
        self,
        tenant_id: str,
        plan: Plan,
        trial_started_at: datetime,
        trial_ends_at: datetime,
    ) -> Subscription:
        subscription = Subscription(
            tenant_id=tenant_id,
            plan_id=plan.id,
            status=STATUS_TRIAL,
            trial_started_at=trial_started_at,
            trial_ends_at=trial_ends_at,
        )
        self.db.add(subscription)
        await self.db.commit()
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
