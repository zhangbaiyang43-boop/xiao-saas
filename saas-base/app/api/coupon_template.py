from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime
from app.core.database import get_db
from app.core.response import RespVo
from app.models.coupon_template import CouponTemplate
from app.schemas.coupon import CreateCouponTemplateRequest

router = APIRouter(prefix="/api/coupon-templates", tags=["优惠券模"])

@router.get("/", response_model=RespVo)
async def list_coupon_templates(request: Request, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    tenant_id = request.state.tenant_id
    if not tenant_id:
        return RespVo.unauthorized()
    
    query = select(CouponTemplate).filter(CouponTemplate.tenant_id == tenant_id).offset(skip).limit(limit)
    result = await db.execute(query)
    templates = result.scalars().all()
    return RespVo.success(data=templates, msg="ok")

@router.get("/{template_id}", response_model=RespVo)
async def get_coupon_template(request: Request, template_id: int, db: AsyncSession = Depends(get_db)):
    tenant_id = request.state.tenant_id
    if not tenant_id:
        return RespVo.unauthorized()
    
    query = select(CouponTemplate).filter(
        CouponTemplate.id == template_id,
        CouponTemplate.tenant_id == tenant_id
    )
    result = await db.execute(query)
    template = result.scalar_one_or_none()
    
    if not template:
        return RespVo.not_found(msg="模不存在")
    
    return RespVo.success(data=template, msg="ok")

@router.post("/", response_model=RespVo)
async def create_coupon_template(request: Request, data: CreateCouponTemplateRequest, db: AsyncSession = Depends(get_db)):
    tenant_id = request.state.tenant_id
    if not tenant_id:
        return RespVo.unauthorized()
    
    template = CouponTemplate(
        tenant_id=tenant_id,
        name=data.name,
        type=data.type,
        value=data.value,
        min_amount=data.min_amount,
        total_stock=data.total_stock,
        start_time=datetime.fromisoformat(data.start_time),
        end_time=datetime.fromisoformat(data.end_time)
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return RespVo.success(data=template, msg="ok")

@router.put("/{template_id}", response_model=RespVo)
async def update_coupon_template(request: Request, template_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    tenant_id = request.state.tenant_id
    if not tenant_id:
        return RespVo.unauthorized()
    
    query = select(CouponTemplate).filter(
        CouponTemplate.id == template_id,
        CouponTemplate.tenant_id == tenant_id
    )
    result = await db.execute(query)
    template = result.scalar_one_or_none()
    
    if not template:
        return RespVo.not_found(msg="模不存在")
    
    for key, value in data.items():
        if key in ['start_time', 'end_time'] and value:
            setattr(template, key, datetime.fromisoformat(value))
        elif value is not None:
            setattr(template, key, value)
    
    await db.commit()
    await db.refresh(template)
    return RespVo.success(data=template, msg="ok")

@router.delete("/{template_id}", response_model=RespVo)
async def delete_coupon_template(request: Request, template_id: int, db: AsyncSession = Depends(get_db)):
    tenant_id = request.state.tenant_id
    if not tenant_id:
        return RespVo.unauthorized()
    
    query = select(CouponTemplate).filter(
        CouponTemplate.id == template_id,
        CouponTemplate.tenant_id == tenant_id
    )
    result = await db.execute(query)
    template = result.scalar_one_or_none()
    
    if not template:
        return RespVo.not_found(msg="模不存在")
    
    await db.delete(template)
    await db.commit()
    return RespVo.success(msg="ok")