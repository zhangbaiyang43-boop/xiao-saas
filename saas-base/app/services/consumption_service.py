from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from datetime import datetime
from app.models.consumption import Consumption
from app.services.base_service import BaseService

class ConsumptionService(BaseService):
    def __init__(self, db: AsyncSession):
        super().__init__(db)
    
    async def create_consumption(self, customer_id: int, project: str, amount: float, consume_time, remark: str = None) -> Consumption:
        tenant_id = self.require_tenant_id()
        consumption = Consumption(
            tenant_id=tenant_id,
            customer_id=customer_id,
            project=project,
            amount=amount,
            consume_time=consume_time,
            remark=remark
        )
        self.db.add(consumption)
        await self.db.commit()
        await self.db.refresh(consumption)
        return consumption
    
    async def get_customer_consumptions(self, customer_id: int) -> list:
        self.require_tenant_id()
        query = select(Consumption).filter(Consumption.customer_id == customer_id)
        query = self.filter_by_tenant(query, Consumption)
        query = query.order_by(Consumption.consume_time.desc())
        result = await self.db.execute(query)
        return result.scalars().all()

    async def list_consumptions(
        self,
        customer_id: int | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list:
        self.require_tenant_id()
        query = self.filter_by_tenant(select(Consumption), Consumption)
        if customer_id:
            query = query.filter(Consumption.customer_id == customer_id)
        query = query.order_by(Consumption.consume_time.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def count_consumptions(self, customer_id: int | None = None) -> int:
        self.require_tenant_id()
        query = self.filter_by_tenant(select(func.count()).select_from(Consumption), Consumption)
        if customer_id:
            query = query.filter(Consumption.customer_id == customer_id)
        result = await self.db.execute(query)
        return int(result.scalar() or 0)
