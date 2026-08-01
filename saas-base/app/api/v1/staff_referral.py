from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import build_page, normalize_pagination
from app.core.response import RespVo, error_response, success_response
from app.services.commission_service import CommissionService

router = APIRouter(prefix="/api/v1/staff-referral", tags=["员工推荐"])


class StaffReferralSettingsRequest(BaseModel):
    # 跟 distribution 的 settings 接口同一个模式——金额由算法按客单价+强度档位算，
    # 商户能改的只有这一个开关；强度档位走 PUT /v1/tenant/settings 的
    # staff_referral_intensity 字段单独设置。
    enabled: bool = False


class CreateStaffRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)


@router.get("/settings", response_model=RespVo)
async def get_staff_referral_settings(db: AsyncSession = Depends(get_db)):
    rules = await CommissionService(db).get_staff_referral_rules()
    return success_response(data=rules, msg="ok")


@router.put("/settings", response_model=RespVo)
async def update_staff_referral_settings(data: StaffReferralSettingsRequest, db: AsyncSession = Depends(get_db)):
    rules = await CommissionService(db).update_staff_referral_rules(data.model_dump())
    return success_response(data=rules, msg="员工推荐设置已保存")


@router.get("/preview", response_model=RespVo)
async def get_staff_referral_preview(db: AsyncSession = Depends(get_db)):
    data = await CommissionService(db).get_staff_referral_preview()
    return success_response(data=data, msg="ok")


@router.get("/records", response_model=RespVo)
async def list_staff_referral_records(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    skip, limit = normalize_pagination(skip, limit)
    service = CommissionService(db)
    rows, total = await service.list_staff_commission_records(skip=skip, limit=limit)
    return success_response(data=build_page(rows, total, skip, limit), msg="ok")


@router.post("/records/{record_id}/settle", response_model=RespVo)
async def settle_staff_referral_record(record_id: int, db: AsyncSession = Depends(get_db)):
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


@router.post("/staff", response_model=RespVo)
async def create_staff(data: CreateStaffRequest, db: AsyncSession = Depends(get_db)):
    staff = await CommissionService(db).create_staff(data.name)
    return success_response(
        data={
            "id": str(staff.id),
            "name": staff.name,
            "invite_code": staff.invite_code,
            "status": staff.status,
        },
        msg="已创建",
    )


@router.get("/staff", response_model=RespVo)
async def list_staff(db: AsyncSession = Depends(get_db)):
    staff_list = await CommissionService(db).list_staff()
    return success_response(
        data=[
            {
                "id": str(s["id"]),
                "name": s["name"],
                "invite_code": s["invite_code"],
                "status": s["status"],
                "created_at": s["created_at"].isoformat() if s["created_at"] else None,
                "share_code_id": s["share_code_id"],
                "share_image_url": s["share_image_url"],
                "share_generation_status": s["share_generation_status"],
                "share_generation_error": s["share_generation_error"],
            }
            for s in staff_list
        ],
        msg="ok",
    )


class UpdateStaffStatusRequest(BaseModel):
    status: int = Field(..., ge=0, le=1)


@router.put("/staff/{staff_id}/status", response_model=RespVo)
async def update_staff_status(staff_id: int, data: UpdateStaffStatusRequest, db: AsyncSession = Depends(get_db)):
    staff = await CommissionService(db).update_staff_status(staff_id, data.status)
    if not staff:
        return error_response(code=404, msg="员工不存在")
    return success_response(data={"id": str(staff.id), "status": staff.status}, msg="ok")
