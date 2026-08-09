from typing import Any, TypeAlias

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.channel_auth import ChannelPrincipal, get_current_channel_partner
from app.core.database import get_db
from app.core.response import RespVo, error_response, success_response
from app.core.security import create_channel_partner_access_token
from app.models.tenant import Tenant
from app.services.channel_auth_code_service import ChannelAuthCodeService
from app.services.channel_commission_service import ChannelCommissionService, serialize_ledger
from app.services.channel_dashboard_service import ChannelDashboardService
from app.services.channel_partner_service import (
    PARTNER_STATUS_ACTIVE,
    PARTNER_STATUS_DISABLED,
    ChannelPartnerService,
    normalize_mobile,
    serialize_binding,
    serialize_lead,
    serialize_partner,
)
from app.services.channel_settlement_service import ChannelSettlementService, serialize_settlement

ApiResponse: TypeAlias = RespVo[Any]

router = APIRouter(prefix="/api/v1/channel", tags=["渠道伙伴门户"])

MAX_PAGE_SIZE = 100


class ChannelCodeRequest(BaseModel):
    mobile: str = Field(..., min_length=1, max_length=32)


class ChannelLoginRequest(BaseModel):
    mobile: str = Field(..., min_length=1, max_length=32)
    code: str = Field(..., min_length=1, max_length=12)


class ChannelLeadCreateRequest(BaseModel):
    merchant_name: str = Field(..., min_length=1, max_length=128)
    merchant_mobile: str = Field(..., min_length=1, max_length=32)
    contact_name: str = Field("", max_length=64)
    remark: str = Field("", max_length=255)


def _page(page: int, page_size: int) -> tuple[int, int, int]:
    page = max(int(page or 1), 1)
    page_size = min(max(int(page_size or 20), 1), MAX_PAGE_SIZE)
    return page, page_size, (page - 1) * page_size


def _page_payload(items: list[dict], total: int, page: int, page_size: int) -> dict:
    return {
        "items": items,
        "total": int(total),
        "page": int(page),
        "page_size": int(page_size),
    }


async def _tenant_name_map(db: AsyncSession, tenant_ids: list[str]) -> dict[str, str]:
    ids = sorted({item for item in tenant_ids if item})
    if not ids:
        return {}
    result = await db.execute(select(Tenant.tenant_id, Tenant.name).where(Tenant.tenant_id.in_(ids)))
    return {tenant_id: name for tenant_id, name in result.all()}


def _serialize_binding_safe(binding, tenant_names: dict[str, str] | None = None) -> dict:
    data = serialize_binding(binding)
    data["merchant_display_name"] = (tenant_names or {}).get(binding.tenant_id, "")
    return data


def _serialize_binding_with_earnings(
    binding,
    tenant_names: dict[str, str] | None = None,
    earnings_by_binding_id: dict[int, int] | None = None,
) -> dict:
    data = _serialize_binding_safe(binding, tenant_names)
    data["net_earned_cents"] = int((earnings_by_binding_id or {}).get(int(binding.id), 0))
    return data


@router.post("/auth/request-code", response_model=RespVo)
async def request_channel_login_code(body: ChannelCodeRequest, db: AsyncSession = Depends(get_db)) -> ApiResponse:
    mobile_key = normalize_mobile(body.mobile)
    partner = await ChannelPartnerService(db).get_partner_by_mobile_normalized(mobile_key)
    if not partner:
        return error_response(code=404, msg="渠道账号不存在")
    if partner.status == PARTNER_STATUS_DISABLED:
        return error_response(code=403, msg="渠道账号已停用")
    ok, msg, payload = await ChannelAuthCodeService().request_login_code(mobile_key)
    if not ok:
        return error_response(code=400, msg=msg, data=payload or None)
    return success_response(data=payload, msg=msg)


@router.post("/auth/login", response_model=RespVo)
async def channel_login(body: ChannelLoginRequest, db: AsyncSession = Depends(get_db)) -> ApiResponse:
    mobile_key = normalize_mobile(body.mobile)
    partner = await ChannelPartnerService(db).get_partner_by_mobile_normalized(mobile_key)
    if not partner:
        return error_response(code=404, msg="渠道账号不存在")
    if partner.status == PARTNER_STATUS_DISABLED:
        return error_response(code=403, msg="渠道账号已停用")
    if not await ChannelAuthCodeService().verify_login_code(mobile_key, body.code):
        return error_response(code=400, msg="验证码错误或已过期")
    token = create_channel_partner_access_token(int(partner.id))
    return success_response(
        data={
            "token": token,
            "token_type": "bearer",
            "partner": serialize_partner(partner),
        },
        msg="登录成功",
    )


@router.post("/auth/logout", response_model=RespVo)
async def channel_logout(_: ChannelPrincipal = Depends(get_current_channel_partner)) -> ApiResponse:
    return success_response(msg="已退出")


@router.get("/me", response_model=RespVo)
async def channel_me(principal: ChannelPrincipal = Depends(get_current_channel_partner)) -> ApiResponse:
    return success_response(data=serialize_partner(principal.partner), msg="ok")


@router.get("/dashboard", response_model=RespVo)
async def channel_dashboard(
    principal: ChannelPrincipal = Depends(get_current_channel_partner),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    data = await ChannelDashboardService(db).get_dashboard(principal.partner_id)
    await db.commit()
    return success_response(data=data, msg="ok")


@router.post("/leads", response_model=RespVo)
async def create_channel_lead(
    body: ChannelLeadCreateRequest,
    principal: ChannelPrincipal = Depends(get_current_channel_partner),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    if principal.partner.status != PARTNER_STATUS_ACTIVE:
        return error_response(code=403, msg="渠道账号当前不可新增报备")
    try:
        lead = await ChannelPartnerService(db).create_lead(
            partner_id=principal.partner_id,
            merchant_name=body.merchant_name,
            merchant_mobile=body.merchant_mobile,
            contact_name=body.contact_name,
        )
    except ValueError as exc:
        return error_response(code=400, msg=str(exc))
    return success_response(data=serialize_lead(lead), msg="商机已报备")


@router.get("/leads", response_model=RespVo)
async def list_channel_leads(
    page: int = 1,
    page_size: int = 20,
    principal: ChannelPrincipal = Depends(get_current_channel_partner),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    page, page_size, skip = _page(page, page_size)
    rows, total = await ChannelPartnerService(db).list_leads_for_partner(principal.partner_id, skip, page_size)
    return success_response(data=_page_payload([serialize_lead(row) for row in rows], total, page, page_size), msg="ok")


@router.get("/leads/{lead_id}", response_model=RespVo)
async def get_channel_lead(
    lead_id: str,
    principal: ChannelPrincipal = Depends(get_current_channel_partner),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    lead = await ChannelPartnerService(db).get_lead_for_partner(principal.partner_id, int(lead_id))
    if not lead:
        return error_response(code=404, msg="记录不存在")
    return success_response(data=serialize_lead(lead), msg="ok")


@router.get("/merchants", response_model=RespVo)
async def list_channel_merchants(
    page: int = 1,
    page_size: int = 20,
    principal: ChannelPrincipal = Depends(get_current_channel_partner),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    page, page_size, skip = _page(page, page_size)
    rows, total = await ChannelPartnerService(db).list_bindings_for_partner(principal.partner_id, skip, page_size)
    tenant_names = await _tenant_name_map(db, [row.tenant_id for row in rows])
    earnings = await ChannelCommissionService(db).get_net_earned_cents_by_binding_ids(
        partner_id=principal.partner_id,
        binding_ids=[int(row.id) for row in rows],
    )
    return success_response(
        data=_page_payload(
            [_serialize_binding_with_earnings(row, tenant_names, earnings) for row in rows],
            total,
            page,
            page_size,
        ),
        msg="ok",
    )


@router.get("/merchants/{binding_id}", response_model=RespVo)
async def get_channel_merchant(
    binding_id: str,
    principal: ChannelPrincipal = Depends(get_current_channel_partner),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    binding = await ChannelPartnerService(db).get_binding_for_partner(principal.partner_id, int(binding_id))
    if not binding:
        return error_response(code=404, msg="记录不存在")
    tenant_names = await _tenant_name_map(db, [binding.tenant_id])
    earnings = await ChannelCommissionService(db).get_net_earned_cents_by_binding_ids(
        partner_id=principal.partner_id,
        binding_ids=[int(binding.id)],
    )
    return success_response(data=_serialize_binding_with_earnings(binding, tenant_names, earnings), msg="ok")


@router.get("/commissions", response_model=RespVo)
async def list_channel_commissions(
    page: int = 1,
    page_size: int = 20,
    principal: ChannelPrincipal = Depends(get_current_channel_partner),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    page, page_size, skip = _page(page, page_size)
    rows, total = await ChannelCommissionService(db).list_ledgers_for_partner(principal.partner_id, skip, page_size)
    await db.commit()
    return success_response(data=_page_payload([serialize_ledger(row) for row in rows], total, page, page_size), msg="ok")


@router.get("/commissions/{ledger_id}", response_model=RespVo)
async def get_channel_commission(
    ledger_id: str,
    principal: ChannelPrincipal = Depends(get_current_channel_partner),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    ledger = await ChannelCommissionService(db).get_ledger_for_partner(principal.partner_id, int(ledger_id))
    await db.commit()
    if not ledger:
        return error_response(code=404, msg="记录不存在")
    return success_response(data=serialize_ledger(ledger), msg="ok")


@router.get("/earnings-summary", response_model=RespVo)
async def get_channel_earnings_summary(
    principal: ChannelPrincipal = Depends(get_current_channel_partner),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    data = await ChannelCommissionService(db).get_partner_earnings_summary(principal.partner_id)
    await db.commit()
    return success_response(data=data, msg="ok")


@router.get("/settlements", response_model=RespVo)
async def list_channel_settlements(
    page: int = 1,
    page_size: int = 20,
    principal: ChannelPrincipal = Depends(get_current_channel_partner),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    page, page_size, skip = _page(page, page_size)
    rows, total = await ChannelSettlementService(db).list_settlements_for_partner(principal.partner_id, skip, page_size)
    return success_response(data=_page_payload([serialize_settlement(row) for row in rows], total, page, page_size), msg="ok")


@router.get("/settlements/{settlement_id}", response_model=RespVo)
async def get_channel_settlement(
    settlement_id: str,
    principal: ChannelPrincipal = Depends(get_current_channel_partner),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    settlement = await ChannelSettlementService(db).get_settlement_for_partner(principal.partner_id, int(settlement_id))
    if not settlement:
        return error_response(code=404, msg="记录不存在")
    return success_response(data=serialize_settlement(settlement), msg="ok")
