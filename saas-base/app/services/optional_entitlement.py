"""Optional side-effect entitlement checker (Phase F1F-D0,
docs/saas-subscription-audit.md).

Scope boundary -- read this before calling anything in this file:

This module answers exactly one question, safely: "should this OPTIONAL,
non-authoritative side effect run right now?" It exists for money-adjacent
background/optional effects that live inside a larger core transaction --
auto-coupon issuance, membership point accrual, distribution/referral
commission binding, channel visit attribution -- where the core transaction
(payment succeeded, order settled, customer registered) must NEVER be put
at risk by an entitlement lookup that fails for an unrelated reason.

It is NOT an authorization primitive. It must NEVER be used to gate an
interactive paid API. Interactive endpoints have a different, stricter
contract (app/core/entitlement_guard.py, Phase F1F-B/F1F-BH/F1F-C): a
denial is a 403 PLAN_CAPABILITY_REQUIRED, and a system/data error is a
500/503 -- both stop the request. This module does the opposite on error:
it swallows the failure and returns False, because for an optional side
effect, silently skipping the extra feature is always safer than letting
an unrelated entitlement-resolution bug abort or poison the surrounding
business transaction (a paid order, a customer registration).

Authority chain (unchanged, not re-implemented here):
SubscriptionService.get_effective_subscription_view()
  -> EntitlementService.has_capability()
    -> optional_capability_enabled() (this module)

This file never selects Subscription/Plan itself, never re-derives expiry,
and never reads Plan.is_active as an entitlement signal -- it only calls
EntitlementService, exactly like every other entitlement consumer in this
codebase.

F1F-D0 wires nothing: no payment/order/coupon/membership/commission/print
call site imports this module yet. That wiring is F1F-D1's job.
"""

from __future__ import annotations

from app.core.logger import logger
from app.services.entitlement_service import EntitlementService


async def optional_capability_enabled(tenant_id: str, capability: str) -> bool:
    """True only if the tenant's current plan grants `capability` right now.

    False for every other outcome, including ones that are NOT a business
    "plan lacks capability" result:
      - the tenant's plan genuinely lacks the capability (normal, expected;
        not logged as an error)
      - entitlement resolution hits a data-integrity problem (e.g. a
        missing FREE plan row, an unrecognized effective plan code)
      - EntitlementService raises for any other reason (DB error, a
        programmer error like an unknown capability key)

    Never raises. Never grants on error. Runs its own short-lived,
    read-only AsyncSessionLocal() session -- never the caller's business
    session -- so a failure here can never poison a surrounding core
    transaction (payment, order, registration) or force an unwanted
    commit/rollback on it. No caching: every call is a fresh resolution.
    """
    try:
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            return await EntitlementService(db).has_capability(tenant_id, capability)
    except Exception as exc:
        logger.error(
            "[OPTIONAL_ENTITLEMENT_CHECK_FAILED] event=optional_entitlement_check_failed "
            "tenant_id=%s capability=%s error=%s",
            tenant_id, capability, exc,
            exc_info=True,
        )
        return False
