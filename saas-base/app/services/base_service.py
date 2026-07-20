from sqlalchemy.ext.asyncio import AsyncSession
from app.core.tenant_context import TenantContext

class BaseService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.tenant_id = None
    
    def set_tenant_id(self, tenant_id: str):
        self.tenant_id = tenant_id

    def require_tenant_id(self) -> str:
        tenant_id = self.tenant_id or TenantContext.get_current_tenant_id()
        if not tenant_id:
            raise ValueError("缺少租户上下文")
        self.tenant_id = tenant_id
        return tenant_id
    
    def filter_by_tenant(self, query, model):
        if self.tenant_id:
            return query.filter(model.tenant_id == self.tenant_id)
        return query
