from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.entitlement_guard import require_capability_response
from app.core.pagination import build_page, normalize_pagination
from app.core.plan_capabilities import CAP_DISTRIBUTION_REFERRAL
from app.core.response import RespVo, error_response, success_response
from app.core.tenant_context import TenantContext
from app.services.commission_service import CommissionService

router = APIRouter(prefix="/api/v1/distribution", tags=["邀请奖励"])


class DistributionSettingsRequest(BaseModel):
    # 金额/门槛/有效期不再接受商户直接输入——全部由算法按客单价+强度档位实时计算，
    # 商户能改的只剩这一个开关；强度档位通过 PUT /v1/tenant/settings 的
    # distribution_intensity 字段单独设置。
    invite_reward_enabled: bool = False


@router.get("/settings", response_model=RespVo)
async def get_distribution_settings(db: AsyncSession = Depends(get_db)):
    rules = await CommissionService(db).get_distribution_rules()
    return success_response(data=rules, msg="ok")


@router.put("/settings", response_model=RespVo)
async def update_distribution_settings(data: DistributionSettingsRequest, db: AsyncSession = Depends(get_db)):
    denial = await require_capability_response(db, TenantContext.get_tenant_id(), CAP_DISTRIBUTION_REFERRAL)
    if denial is not None:
        return denial
    service = CommissionService(db)
    rules = await service.update_distribution_rules(data.model_dump())
    return success_response(data=rules, msg="邀请奖励设置已保存")


@router.get("/preview", response_model=RespVo)
async def get_distribution_preview(db: AsyncSession = Depends(get_db)):
    """三档强度各自算出来的真实金额/门槛，供后台"选强度"卡片直接渲染。"""
    denial = await require_capability_response(db, TenantContext.get_tenant_id(), CAP_DISTRIBUTION_REFERRAL)
    if denial is not None:
        return denial
    data = await CommissionService(db).get_distribution_preview()
    return success_response(data=data, msg="ok")


@router.get("/records", response_model=RespVo)
async def list_distribution_records(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    skip, limit = normalize_pagination(skip, limit)
    service = CommissionService(db)
    rows, total = await service.list_records_for_admin(skip=skip, limit=limit)
    return success_response(data=build_page(rows, total, skip, limit), msg="ok")


@router.post("/records/{record_id}/settle", response_model=RespVo)
async def settle_distribution_record(record_id: int, db: AsyncSession = Depends(get_db)):
    record = await CommissionService(db).settle_record(record_id)
    if not record:
        return error_response(code=404, msg="记录不存在")
    return success_response(
        data={
            "id": str(record.id),
            "status": record.status,
            "settled_at": record.settled_at.isoformat() if record.settled_at else None,
        },
        msg="已标记发放",
    )
