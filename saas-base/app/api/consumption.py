from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from app.core.database import get_db
from app.core.response import RespVo
from app.services.consumption_service import ConsumptionService
from app.services.customer_service import CustomerService
from app.schemas.consumption import CreateConsumptionRequest

router = APIRouter(prefix="/api/consumptions", tags=["消费记录"])

@router.post("/", response_model=RespVo)
async def create_consumption(request: Request, data: CreateConsumptionRequest, db: AsyncSession = Depends(get_db)):
    tenant_id = request.state.tenant_id
    if not tenant_id:
        return RespVo.unauthorized()
    
    consume_time = datetime.fromisoformat(data.consume_time) if data.consume_time else datetime.utcnow()
    
    consumption_service = ConsumptionService(db)
    customer_service = CustomerService(db)
    
    consumption = await consumption_service.create_consumption(
        tenant_id,
        data.customer_id,
        data.project,
        float(data.amount),
        consume_time,
        data.remark
    )
    
    await customer_service.update_last_consume_time(data.customer_id, consume_time)
    
    return RespVo.success(data=consumption, msg="ok")