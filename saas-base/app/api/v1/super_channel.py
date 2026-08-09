from typing import Any, TypeAlias

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.super_admin import _verify_super_token
from app.core.database import get_db
from app.core.response import RespVo, error_response, success_response
from app.services.channel_commission_service import (
    ChannelCommissionService,
    serialize_ledger,
)
from app.services.channel_partner_service import (
    ChannelPartnerService,
    serialize_binding,
    serialize_lead,
    serialize_partner,
)
from app.services.channel_settlement_service import ChannelSettlementService, serialize_settlement


ApiResponse: TypeAlias = RespVo[Any]

router = APIRouter(
    prefix="/api/super/channel",
    tags=["平台渠道分佣"],
    dependencies=[Depends(_verify_super_token)],
)


class ChannelPartnerCreateRequest(BaseModel):
    partner_code: str | None = Field(None, min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    mobile: str = Field(..., min_length=1, max_length=32)
    partner_type: str = "OTHER"
    status: str = "ACTIVE"


class ChannelLeadCreateRequest(BaseModel):
    partner_id: int
    merchant_name: str = Field(..., min_length=1, max_length=128)
    merchant_mobile: str = Field(..., min_length=1, max_length=32)
    contact_name: str = ""


class ChannelLeadConvertRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=32)


class ChannelSettlementCreateRequest(BaseModel):
    partner_id: int
    ledger_ids: list[int]
    operator: str = ""
    transaction_reference: str | None = None


@router.post("/partners", response_model=RespVo)
async def create_channel_partner(body: ChannelPartnerCreateRequest, db: AsyncSession = Depends(get_db)) -> ApiResponse:
    try:
        partner = await ChannelPartnerService(db).create_partner(
            partner_code=body.partner_code,
            name=body.name,
            mobile=body.mobile,
            partner_type=body.partner_type,
            status=body.status,
        )
    except ValueError as exc:
        return error_response(code=400, msg=str(exc))
    return success_response(data=serialize_partner(partner), msg="渠道伙伴已创建")


@router.get("/partners", response_model=RespVo)
async def list_channel_partners(db: AsyncSession = Depends(get_db)) -> ApiResponse:
    rows = await ChannelPartnerService(db).list_partners()
    return success_response(data=[serialize_partner(row) for row in rows], msg="ok")


@router.post("/leads", response_model=RespVo)
async def create_channel_lead(body: ChannelLeadCreateRequest, db: AsyncSession = Depends(get_db)) -> ApiResponse:
    try:
        lead = await ChannelPartnerService(db).create_lead(
            partner_id=body.partner_id,
            merchant_name=body.merchant_name,
            merchant_mobile=body.merchant_mobile,
            contact_name=body.contact_name,
        )
    except ValueError as exc:
        return error_response(code=400, msg=str(exc))
    return success_response(data=serialize_lead(lead), msg="商机已报备")


@router.get("/leads", response_model=RespVo)
async def list_channel_leads(db: AsyncSession = Depends(get_db)) -> ApiResponse:
    rows = await ChannelPartnerService(db).list_leads()
    return success_response(data=[serialize_lead(row) for row in rows], msg="ok")


@router.post("/leads/{lead_id}/convert", response_model=RespVo)
async def convert_channel_lead(
    lead_id: str,
    body: ChannelLeadConvertRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    try:
        binding = await ChannelPartnerService(db).convert_lead_to_tenant_binding(int(lead_id), body.tenant_id)
    except ValueError as exc:
        return error_response(code=400, msg=str(exc))
    return success_response(data=serialize_binding(binding), msg="渠道归属已绑定")


@router.get("/bindings", response_model=RespVo)
async def list_channel_bindings(db: AsyncSession = Depends(get_db)) -> ApiResponse:
    rows = await ChannelPartnerService(db).list_bindings()
    return success_response(data=[serialize_binding(row) for row in rows], msg="ok")


@router.get("/commission-ledger", response_model=RespVo)
async def list_channel_commission_ledger(
    partner_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    rows = await ChannelCommissionService(db).list_ledgers(partner_id=partner_id)
    await db.commit()
    return success_response(data=[serialize_ledger(row) for row in rows], msg="ok")


@router.get("/partners/{partner_id}/earnings-summary", response_model=RespVo)
async def get_channel_partner_earnings_summary(partner_id: str, db: AsyncSession = Depends(get_db)) -> ApiResponse:
    data = await ChannelCommissionService(db).get_partner_earnings_summary(int(partner_id))
    await db.commit()
    return success_response(data=data, msg="ok")


@router.post("/settlements", response_model=RespVo)
async def create_channel_settlement(body: ChannelSettlementCreateRequest, db: AsyncSession = Depends(get_db)) -> ApiResponse:
    try:
        settlement = await ChannelSettlementService(db).create_manual_settlement(
            partner_id=body.partner_id,
            operator=body.operator,
            ledger_ids=body.ledger_ids,
            transaction_reference=body.transaction_reference,
        )
    except ValueError as exc:
        return error_response(code=400, msg=str(exc))
    return success_response(data=serialize_settlement(settlement), msg="结算已创建")


@router.get("/settlements", response_model=RespVo)
async def list_channel_settlements(partner_id: int | None = None, db: AsyncSession = Depends(get_db)) -> ApiResponse:
    rows = await ChannelSettlementService(db).list_settlements(partner_id=partner_id)
    return success_response(data=[serialize_settlement(row) for row in rows], msg="ok")
