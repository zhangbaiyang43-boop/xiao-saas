from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import build_page, normalize_pagination
from app.core.response import RespVo, error_response, success_response
from app.services.commission_service import CommissionService

router = APIRouter(prefix="/api/v1/distribution", tags=["邀请奖励"])


class DistributionSettingsRequest(BaseModel):
    invite_reward_enabled: bool = False
    inviter_reward_amount: float = Field(5.0, ge=0)
    invitee_reward_amount: float = Field(5.0, ge=0)
    invite_reward_min_spend: float = Field(0.0, ge=0)
    invite_reward_valid_days: int = Field(30, ge=1)


@router.get("/settings", response_model=RespVo)
async def get_distribution_settings(db: AsyncSession = Depends(get_db)):
    rules = await CommissionService(db).get_distribution_rules()
    return success_response(data=rules, msg="ok")


@router.put("/settings", response_model=RespVo)
async def update_distribution_settings(data: DistributionSettingsRequest, db: AsyncSession = Depends(get_db)):
    service = CommissionService(db)
    rules = await service.update_distribution_rules(data.model_dump())
    return success_response(data=rules, msg="邀请奖励设置已保存")


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
