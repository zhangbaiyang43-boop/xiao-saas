from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.database import get_db
from app.core.response import RespVo
from app.services.coupon_service import CouponService
from app.models.coupon import Coupon
from app.schemas.coupon import SendCouponsRequest

router = APIRouter(prefix="/api/coupons", tags=["优惠券"])

@router.post("/send", response_model=RespVo)
async def send_coupons(request: Request, data: SendCouponsRequest, db: AsyncSession = Depends(get_db)):
    tenant_id = request.state.tenant_id
    if not tenant_id:
        return RespVo.unauthorized()
    
    service = CouponService(db)
    service.set_tenant_id(tenant_id)
    coupons = await service.send_coupons(data.template_id, data.customer_ids)
    return RespVo.success(data={"count": len(coupons)}, msg="ok")

@router.get("/", response_model=RespVo)
async def list_coupons(request: Request, status: str = None, customer_id: int = None, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    tenant_id = request.state.tenant_id
    if not tenant_id:
        return RespVo.unauthorized()
    
    service = CouponService(db)
    service.set_tenant_id(tenant_id)
    
    if customer_id:
        coupons = await service.get_customer_coupons(customer_id, status)
    else:
        query = select(Coupon).filter(Coupon.tenant_id == tenant_id)
        if status:
            query = query.filter(Coupon.status == status)
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        coupons = result.scalars().all()
    
    return RespVo.success(data=coupons, msg="ok")

@router.get("/{coupon_id}", response_model=RespVo)
async def get_coupon(request: Request, coupon_id: int, db: AsyncSession = Depends(get_db)):
    tenant_id = request.state.tenant_id
    if not tenant_id:
        return RespVo.unauthorized()
    
    service = CouponService(db)
    service.set_tenant_id(tenant_id)
    coupon = await service.get_coupon(coupon_id)
    
    if not coupon:
        return RespVo.not_found(msg="优惠券不存在")
    
    return RespVo.success(data=coupon, msg="ok")