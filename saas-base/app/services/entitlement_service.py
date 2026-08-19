"""Backend authority for plan-based capability gating (Phase F1F-A,
docs/saas-subscription-audit.md).

Delegates 100% of effective-plan resolution to
SubscriptionService.get_effective_subscription_view() -- this file must
never re-query Subscription, re-derive expiry, or re-implement a second
FREE fallback. It only asks "does this plan include this capability"
against app/core/plan_capabilities.py's frozen matrix, so
GET /api/v1/subscription/current and entitlement checks always agree,
by construction, on what a tenant's current plan is.

F1F-A wires this into NOTHING: no API route, no middleware, no service
call site consumes it yet (see docs/saas-subscription-audit.md Phase F1F-A
-- this phase's guarantee is zero business behavior change). Wiring is
F1F-B onward.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.plan_capabilities import ALL_CAPABILITIES, PLAN_CAPABILITIES, plans_requiring
from app.services.subscription_service import EffectiveSubscriptionView, SubscriptionService


class UnknownCapabilityError(ValueError):
    """A capability key not present in the frozen matrix was requested --
    a typo/programmer error, never a merchant-facing outcome. Must never be
    swallowed into a bare `False`, since that would silently and invisibly
    turn off a real feature for everyone."""

    pass


class UnknownEffectivePlanCodeError(ValueError):
    """SubscriptionService resolved an effective_plan.code that isn't
    FREE/STANDARD/PRO -- a data/policy integrity problem (e.g. a Plan row
    with a code the commercial contract doesn't recognize). Never silently
    defaulted to FREE: fail-open and fail-closed both hide the underlying
    inconsistency instead of surfacing it."""

    pass


class EntitlementRequiredError(Exception):
    """Raised by require_capability() when the tenant's effective plan
    lacks the requested capability. Carries enough context for a future API
    layer (F1F-B+) to render its own 403/PLAN_CAPABILITY_REQUIRED response
    -- this service layer knows nothing about HTTP status codes, FastAPI,
    or RespVo; that translation is the API boundary's job, not this one's.
    """

    def __init__(self, capability: str, effective_plan_code: str, required_plan_codes: tuple[str, ...]):
        self.capability = capability
        self.effective_plan_code = effective_plan_code
        self.required_plan_codes = required_plan_codes
        super().__init__(
            f"tenant's effective plan {effective_plan_code!r} lacks capability "
            f"{capability!r} (requires one of {required_plan_codes!r})"
        )


class EntitlementService:
    """Tenant-scoped capability authority.

    Every method takes an explicit tenant_id -- this service never reads
    request.state, a JWT, or any global/ambient context itself, so it stays
    a pure Backend domain service. Tenant authority is the caller's
    responsibility (a future API/middleware layer, F1F-B+).

    Memoization is per-instance only (no module cache, no Redis, no TTL
    cache): the authoritative resolver is called at most once across this
    instance's lifetime, keeping the staleness window as small as a single
    request/service-call scope -- the next request constructs a fresh
    EntitlementService and reads current state again. `now` is likewise
    captured once, at first resolution, and reused for that same instance's
    remaining calls so multiple capability checks within one request see a
    consistent time boundary.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._subscription_service = SubscriptionService(db)
        self._now: Optional[datetime] = None
        self._cached_view: Optional[EffectiveSubscriptionView] = None
        self._cached_tenant_id: Optional[str] = None

    async def _resolve_view(self, tenant_id: str) -> EffectiveSubscriptionView:
        if self._cached_view is not None and self._cached_tenant_id == tenant_id:
            return self._cached_view
        if self._now is None:
            self._now = datetime.utcnow()
        view = await self._subscription_service.get_effective_subscription_view(tenant_id, now=self._now)
        self._cached_view = view
        self._cached_tenant_id = tenant_id
        return view

    async def resolve_effective_plan_code(self, tenant_id: str) -> str:
        view = await self._resolve_view(tenant_id)
        plan_code = view.effective_plan.code
        if plan_code not in PLAN_CAPABILITIES:
            raise UnknownEffectivePlanCodeError(
                f"resolved effective_plan.code={plan_code!r} is not a recognized plan "
                f"{tuple(PLAN_CAPABILITIES.keys())!r} -- data/policy integrity error, "
                f"never silently treated as FREE"
            )
        return plan_code

    async def has_capability(self, tenant_id: str, capability: str) -> bool:
        # Validate the capability key first (pure, no DB) before resolving
        # the effective plan (memoized DB call) -- no extra query for a
        # request that was going to fail validation anyway.
        if capability not in ALL_CAPABILITIES:
            raise UnknownCapabilityError(f"unknown capability: {capability!r}")
        plan_code = await self.resolve_effective_plan_code(tenant_id)
        return capability in PLAN_CAPABILITIES[plan_code]

    async def require_capability(self, tenant_id: str, capability: str) -> None:
        if capability not in ALL_CAPABILITIES:
            raise UnknownCapabilityError(f"unknown capability: {capability!r}")
        plan_code = await self.resolve_effective_plan_code(tenant_id)
        if capability in PLAN_CAPABILITIES[plan_code]:
            return
        raise EntitlementRequiredError(capability, plan_code, plans_requiring(capability))
