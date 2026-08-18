from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.plan_capabilities import CAP_CHANNEL_ENTRY
from app.core.response import RespVo, error_response, success_response
from app.services.channel_entry_service import ChannelEntryService
from app.services.optional_entitlement import optional_capability_enabled

router = APIRouter(prefix="/api/public/channel-entries", tags=["公开渠道入口"])


@router.get("/{entry_id}", response_model=RespVo)
async def get_h5_config(
    request: Request,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
):
    service = ChannelEntryService(db)
    data = await service.get_entry_with_coupon(entry_id)
    if not data:
        return error_response(code=404, msg="入口不存在或已停用")

    tenant_service = None
    from app.services.tenant_service import TenantService
    tenant_service = TenantService(db)
    tenant = await tenant_service.get_tenant(data["tenant_id"])
    if tenant:
        data["merchant_name"] = tenant.name
        data["merchant_logo"] = tenant.logo_url

    return success_response(data=data, msg="ok")


@router.post("/{entry_id}/visit", response_model=RespVo)
async def record_visit(
    request: Request,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
):
    service = ChannelEntryService(db)

    # Public/unauthenticated resolve is always allowed (Phase F1F-C). Only the
    # visit-tracking side effect is an optional PRO growth-analytics feature:
    # a FREE/STANDARD merchant's already-printed QR code must keep resolving
    # and must never surface a 403/500 to the scanning customer -- it just
    # stops accumulating visit_count/attribution log rows.
    probe = await service.get_public_entry(entry_id)
    if not probe:
        return error_response(code=404, msg="入口不存在或已停用")

    if await optional_capability_enabled(probe.tenant_id, CAP_CHANNEL_ENTRY):
        user_agent = request.headers.get("user-agent")
        referer = request.headers.get("referer")
        client_ip = request.client.host if request.client else None
        entry = await service.record_visit(
            entry_id=entry_id,
            user_agent=user_agent,
            referer=referer,
            ip=client_ip,
            query_params=dict(request.query_params),
        )
        visit_count = entry.visit_count if entry else probe.visit_count
    else:
        visit_count = probe.visit_count

    return success_response(data={"visit_count": visit_count}, msg="ok")