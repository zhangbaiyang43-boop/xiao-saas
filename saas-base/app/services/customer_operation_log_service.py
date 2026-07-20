from sqlalchemy import desc
from sqlalchemy.future import select

from app.models.customer_operation_log import CustomerOperationLog
from app.services.base_service import BaseService


class CustomerOperationLogService(BaseService):
    async def record(
        self,
        *,
        customer_id=None,
        action: str,
        source: str = "system",
        actor_type: str = "system",
        actor_id=None,
        actor_name=None,
        phone=None,
        openid=None,
        detail=None,
        ip=None,
        user_agent=None,
        commit: bool = True,
    ):
        tenant_id = self.require_tenant_id()
        item = CustomerOperationLog(
            tenant_id=tenant_id,
            customer_id=customer_id,
            action=action,
            source=source,
            actor_type=actor_type,
            actor_id=str(actor_id) if actor_id is not None else None,
            actor_name=actor_name,
            phone=phone,
            openid=openid,
            detail=detail or {},
            ip=ip,
            user_agent=(user_agent or "")[:255] or None,
        )
        self.db.add(item)
        if commit:
            await self.db.commit()
            await self.db.refresh(item)
        return item

    async def list_by_customer(self, customer_id: int, skip: int = 0, limit: int = 50):
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(CustomerOperationLog)
            .filter(
                CustomerOperationLog.tenant_id == tenant_id,
                CustomerOperationLog.customer_id == customer_id,
            )
            .order_by(desc(CustomerOperationLog.created_at))
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()
