from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache_helper import cache_result, clear_cache_pattern
from app.core.database import get_db
from app.core.pagination import build_page, normalize_pagination
from app.core.rate_limiter import tenant_limit
from app.core.response import RespVo, error_response, success_response
from app.schemas.coupon import CreateCouponTemplateRequest, UpdateCouponTemplateRequest
from app.services.coupon_service import CouponService

router = APIRouter(prefix="/api/v1/coupon-templates", tags=["优惠券"])


def serialize_template(template):
    return {
        "id": str(template.id),
        "tenant_id": template.tenant_id,
        "name": template.name,
        "type": template.type,
        "value": float(template.value or 0),
        "min_amount": float(template.min_amount or 0),
        "total_stock": int(template.total_stock or 0),
        "used_stock": int(template.used_stock or 0),
        "start_time": template.start_time,
        "end_time": template.end_time,
        "status": int(template.status or 0),
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }


@router.get("/", response_model=RespVo)
@tenant_limit()
@cache_result("coupon_templates")
async def list_templates(request: Request, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    skip, limit = normalize_pagination(skip, limit)
    service = CouponService(db)
    templates = await service.list_templates(skip, limit)
    total = await service.count_templates()
    return success_response(data=build_page([serialize_template(item) for item in templates], total, skip, limit), msg="ok")


@router.get("/{template_id}", response_model=RespVo)
@tenant_limit()
async def get_template(request: Request, template_id: int, db: AsyncSession = Depends(get_db)):
    service = CouponService(db)
    template = await service.get_template(template_id)
    if not template:
        return error_response(code=404, msg="优惠券不存在")
    return success_response(data=serialize_template(template), msg="ok")


@router.post("/", response_model=RespVo)
@tenant_limit()
async def create_template(request: Request, data: CreateCouponTemplateRequest, db: AsyncSession = Depends(get_db)):
    service = CouponService(db)
    template = await service.create_template(
        name=data.name,
        type=data.type,
        value=float(data.value),
        min_amount=float(data.min_amount),
        total_stock=data.total_stock,
        start_time=datetime.fromisoformat(data.start_time),
        end_time=datetime.fromisoformat(data.end_time),
        status=data.status,
    )

    await clear_cache_pattern("coupon_templates:*")
    return success_response(data=serialize_template(template), msg="建成功")


@router.put("/{template_id}", response_model=RespVo)
@tenant_limit()
async def update_template(
    request: Request,
    template_id: int,
    data: UpdateCouponTemplateRequest,
    db: AsyncSession = Depends(get_db),
):
    service = CouponService(db)
    payload = data.model_dump(exclude_unset=True)
    if "start_time" in payload and payload["start_time"]:
        payload["start_time"] = datetime.fromisoformat(payload["start_time"])
    if "end_time" in payload and payload["end_time"]:
        payload["end_time"] = datetime.fromisoformat(payload["end_time"])
    template = await service.update_template(template_id, **payload)
    if not template:
        return error_response(code=404, msg="优惠券不存在")

    await clear_cache_pattern("coupon_templates:*")
    return success_response(data=serialize_template(template), msg="更新成功")


@router.delete("/{template_id}", response_model=RespVo)
@tenant_limit()
async def delete_template(request: Request, template_id: int, db: AsyncSession = Depends(get_db)):
    service = CouponService(db)
    success = await service.delete_template(template_id)
    if not success:
        return error_response(code=404, msg="优惠券不存在")

    await clear_cache_pattern("coupon_templates:*")
    return success_response(msg="删除成功")
