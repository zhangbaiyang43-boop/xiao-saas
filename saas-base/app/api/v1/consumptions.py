from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.events import CONSUMPTION_CREATED, DomainEvent, event_bus
from app.core.pagination import build_page, normalize_pagination
from app.core.response import RespVo, success_response
from app.core.tenant_context import TenantContext
from app.schemas.consumption import CreateConsumptionRequest
from app.services.consumption_service import ConsumptionService
from app.services.coupon_service import CouponService

router = APIRouter(prefix="/api/v1/consumptions", tags=["消费记录"])


def serialize_consumption(consumption):
    return {
        "id": str(consumption.id),
        "tenant_id": consumption.tenant_id,
        "customer_id": str(consumption.customer_id),
        "project": consumption.project,
        "amount": float(consumption.amount or 0),
        "consume_time": consumption.consume_time,
        "remark": consumption.remark,
        "created_at": consumption.created_at,
        "updated_at": consumption.updated_at,
    }


@router.get("/", response_model=RespVo)
async def list_consumptions(
    customer_id: int = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    skip, limit = normalize_pagination(skip, limit)
    service = ConsumptionService(db)
    consumptions = await service.list_consumptions(customer_id=customer_id, skip=skip, limit=limit)
    total = await service.count_consumptions(customer_id=customer_id)
    return success_response(data=build_page([serialize_consumption(item) for item in consumptions], total, skip, limit), msg="ok")


@router.post("/", response_model=RespVo)
async def create_consumption(data: CreateConsumptionRequest, db: AsyncSession = Depends(get_db)):
    consume_time = datetime.fromisoformat(data.consume_time) if data.consume_time else datetime.utcnow()

    consumption_service = ConsumptionService(db)
    consumption = await consumption_service.create_consumption(
        customer_id=data.customer_id,
        project=data.project,
        amount=float(data.amount),
        consume_time=consume_time,
        remark=data.remark,
    )

    TenantContext.set_tenant_id(consumption.tenant_id)

    coupon_service = CouponService(db)
    coupon_result = await coupon_service.issue_auto_coupon(
        data.customer_id,
        "consumption_coupon",
        consumption_amount=float(data.amount)
    )

    event_results = await event_bus.dispatch(DomainEvent(
        name=CONSUMPTION_CREATED,
        tenant_id=consumption.tenant_id,
        db=db,
        source="consumption_api",
        payload={
            "consumption_id": str(consumption.id),
            "customer_id": data.customer_id,
            "project": data.project,
            "amount": float(data.amount),
            "consume_time": consume_time,
            "remark": data.remark,
        },
    ))

    return success_response(
        data={
            "consumption": serialize_consumption(consumption),
            "coupon_result": coupon_result,
            "events": event_results
        },
        msg="建成功",
    )
