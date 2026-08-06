from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from datetime import datetime

from app.core.logger import logger
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


async def _record_order_consumption(order, db: AsyncSession) -> None:
    """订单结账后转成一条消费记录，供顾客端"消费记录"页展示。
    没有 customer_id（匿名/未登录下单）就跳过；记录失败不影响结账本身。"""
    if not order.customer_id:
        return
    try:
        from app.models.order import OrderItem

        items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
        items = items_result.scalars().all()
        if items:
            names = "、".join(i.name for i in items[:3])
            if len(items) > 3:
                names += f"等{len(items)}件"
            project = names
        else:
            project = "堂食点餐"

        consumption_service = ConsumptionService(db)
        consumption_service.set_tenant_id(order.tenant_id)
        await consumption_service.create_consumption(
            customer_id=order.customer_id,
            project=project,
            amount=float(order.total or 0),
            consume_time=order.completed_at or datetime.utcnow(),
            remark=f"订单 #{order.id}" + (f" · {order.table_no}桌" if order.table_no else ""),
        )
    except Exception as e:
        logger.error(f"结账后生成消费记录失败 - order_id: {order.id}, error: {e}")
