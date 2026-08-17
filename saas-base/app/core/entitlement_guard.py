"""Thin HTTP adaptation for EntitlementService (Phase F1F-B,
docs/saas-subscription-audit.md).

Does exactly one thing: turn an EntitlementRequiredError into the existing
RespVo/error_response 403 shape every interactive route in this repo
already uses for auth failures. Defines no capability, judges no plan
hierarchy, queries no Subscription -- all of that stays solely in
app/core/plan_capabilities.py and app/services/entitlement_service.py.
Not every route in this codebase uses the RespVo convention (one print
endpoint returns raw dicts + HTTPException) -- those call sites build their
own response from EntitlementService directly rather than using this
helper, since forcing a foreign response shape onto them would be its own
kind of duplication.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.core.response import RespVo, error_response
from app.services.entitlement_service import EntitlementRequiredError, EntitlementService


async def require_capability_response(db: AsyncSession, tenant_id: str, capability: str) -> Optional[RespVo]:
    """None if the tenant has `capability`; otherwise the RespVo the caller
    should `return` immediately. Never leaks the Python exception
    class/message to the client -- only frozen contract fields.

    A genuine system/data error resolving entitlement (e.g. a missing Plan
    catalog row) is not the same outcome as "this tenant's plan lacks the
    capability" -- but it must not be treated as an implicit grant either.
    PAID_FEATURE_FAILS_CLOSED: an unexpected exception here denies the
    request with a system-error response, same as a real data-integrity
    problem should never silently become "request allowed." Logged loudly
    so it gets fixed.
    """
    try:
        await EntitlementService(db).require_capability(tenant_id, capability)
    except EntitlementRequiredError as exc:
        return error_response(
            code=403,
            msg="该功能需要更高套餐",
            data={
                "error_code": "PLAN_CAPABILITY_REQUIRED",
                "capability": exc.capability,
                "effective_plan_code": exc.effective_plan_code,
                "required_plan_codes": list(exc.required_plan_codes),
            },
        )
    except Exception as exc:
        logger.exception("[ENTITLEMENT_CHECK_FAILED] tenant_id=%s capability=%s error=%s", tenant_id, capability, exc)
        return error_response(
            code=500,
            msg="系统繁忙，请稍后重试",
            data={"error_code": "INTERNAL_ERROR"},
        )
    return None
