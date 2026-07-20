from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.response import RespVo
from app.services.customer_service import CustomerService
from app.services.consumption_service import ConsumptionService
from app.services.coupon_service import CouponService
from app.schemas.customer import CreateCustomerRequest, UpdateCustomerRequest

router = APIRouter(prefix="/api/customers", tags=["客户管理"])

@router.get("/", response_model=RespVo)
async def list_customers(request: Request, name: str = None, tags: str = None, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    tenant_id = request.state.tenant_id
    if not tenant_id:
        return RespVo.unauthorized()
    
    service = CustomerService(db)
    service.set_tenant_id(tenant_id)
    tag_list = tags.split(',') if tags else None
    customers = await service.list_customers(name, tag_list, skip, limit)
    return RespVo.success(data=customers, msg="ok")

@router.post("/", response_model=RespVo)
async def create_customer(request: Request, data: CreateCustomerRequest, db: AsyncSession = Depends(get_db)):
    tenant_id = request.state.tenant_id
    if not tenant_id:
        return RespVo.unauthorized()
    
    service = CustomerService(db)
    customer = await service.create_customer(
        tenant_id,
        data.openid,
        external_userid=data.external_userid,
        name=data.name,
        phone=data.phone,
        tags=data.tags
    )
    return RespVo.success(data=customer, msg="ok")

@router.put("/{customer_id}", response_model=RespVo)
async def update_customer(request: Request, customer_id: int, data: UpdateCustomerRequest, db: AsyncSession = Depends(get_db)):
    tenant_id = request.state.tenant_id
    if not tenant_id:
        return RespVo.unauthorized()
    
    service = CustomerService(db)
    service.set_tenant_id(tenant_id)
    customer = await service.update_customer(customer_id, **data.dict(exclude_unset=True))
    
    if not customer:
        return RespVo.not_found(msg="客户不存在")
    
    return RespVo.success(data=customer, msg="ok")

@router.get("/{customer_id}", response_model=RespVo)
async def get_customer(request: Request, customer_id: int, db: AsyncSession = Depends(get_db)):
    tenant_id = request.state.tenant_id
    if not tenant_id:
        return RespVo.unauthorized()
    
    service = CustomerService(db)
    service.set_tenant_id(tenant_id)
    customer = await service.get_customer(customer_id)
    
    if not customer:
        return RespVo.not_found(msg="客户不存在")
    
    return RespVo.success(data=customer, msg="ok")

@router.get("/{customer_id}/timeline", response_model=RespVo)
async def get_customer_timeline(request: Request, customer_id: int, db: AsyncSession = Depends(get_db)):
    tenant_id = request.state.tenant_id
    if not tenant_id:
        return RespVo.unauthorized()
    
    consumption_service = ConsumptionService(db)
    consumption_service.set_tenant_id(tenant_id)
    coupon_service = CouponService(db)
    coupon_service.set_tenant_id(tenant_id)
    
    consumptions = await consumption_service.get_customer_consumptions(customer_id)
    coupons = await coupon_service.get_customer_coupons(customer_id)
    
    timeline = []
    for c in consumptions:
        timeline.append({
            "type": "consumption",
            "time": c.consume_time,
            "project": c.project,
            "amount": float(c.amount)
        })
    
    for c in coupons:
        timeline.append({
            "type": "coupon",
            "time": c.created_at,
            "status": c.status,
            "use_time": c.use_time
        })
    
    timeline.sort(key=lambda x: x["time"], reverse=True)
    
    return RespVo.success(data=timeline, msg="ok")