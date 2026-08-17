from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.entitlement_guard import require_capability_response
from app.core.plan_capabilities import CAP_MEMBERSHIP
from app.core.response import RespVo, error_response, success_response
from app.core.tenant_context import TenantContext
from app.services.customer_service import CustomerService
from app.services.membership_service import MembershipService

router = APIRouter(prefix="/api/v1/membership", tags=["全域会员"])


def serialize_account(account):
    if not account:
        return {
            "level_code": "LV1",
            "level_name": "普通会员",
            "points_balance": 0,
            "total_consumption": 0.0,
            "consume_count": 0,
            "last_consume_time": None,
        }
    return {
        "id": str(account.id),
        "customer_id": str(account.customer_id),
        "member_id": account.member_id,
        "level_code": account.level_code or "LV1",
        "level_name": account.level_name or "普通会员",
        "total_consumption": float(account.total_consumption or 0),
        "yearly_consumption": float(account.yearly_consumption or 0),
        "points_balance": account.points_balance or 0,
        "consume_count": getattr(account, 'consume_count', 0),
        "last_consume_time": account.last_consume_time,
    }


def serialize_ledger(item):
    return {
        "id": str(item.id),
        "customer_id": str(item.customer_id),
        "member_id": item.member_id,
        "event_type": item.event_type,
        "points": item.points,
        "balance_after": item.balance_after,
        "source_channel": item.source_channel,
        "expire_at": item.expire_at,
        "remark": item.remark,
        "created_at": item.created_at,
    }


def serialize_benefit(item):
    return {
        "id": str(item.id),
        "name": item.name,
        "level_code": item.level_code,
        "type": item.type,
        "value": float(item.value or 0),
        "condition": item.condition,
        "channel": item.channel,
        "expire_at": item.expire_at,
        "cycle": item.cycle,
        "config": item.config or {},
    }


@router.get("/config", response_model=RespVo)
async def get_membership_config(db: AsyncSession = Depends(get_db)):
    tenant_id = TenantContext.get_tenant_id()
    denial = await require_capability_response(db, tenant_id, CAP_MEMBERSHIP)
    if denial is not None:
        return denial
    service = MembershipService(db)
    benefits = await service.list_benefits()
    data = service.get_config()
    data["benefits"] = [serialize_benefit(item) for item in benefits]
    return success_response(data=data, msg="ok")


@router.get("/customers/{customer_id}", response_model=RespVo)
async def get_customer_membership(request: Request, customer_id: int, db: AsyncSession = Depends(get_db)):
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        return error_response(code=401, msg="未授权")

    denial = await require_capability_response(db, tenant_id, CAP_MEMBERSHIP)
    if denial is not None:
        return denial

    TenantContext.set_tenant_id(tenant_id)

    customer_service = CustomerService(db)
    customer_service.set_tenant_id(tenant_id)
    customer = await customer_service.get_customer(customer_id)
    if not customer:
        return error_response(code=404, msg="客户不存在")

    service = MembershipService(db)
    service.set_tenant_id(tenant_id)
    account = await service.ensure_account(customer)
    ledger = await service.list_point_ledger(customer_id)
    benefits = await service.list_benefits()
    return success_response(data={
        "account": serialize_account(account),
        "points_ledger": [serialize_ledger(item) for item in ledger],
        "benefits": [serialize_benefit(item) for item in benefits if item.level_code in ["LV1", account.level_code]] if account else [],
    }, msg="ok")
