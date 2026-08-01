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
            raise ValueError("tenant_id is required for tenant-scoped operations")
        self.tenant_id = tenant_id
        return tenant_id
    
    def filter_by_tenant(self, query, model):
        if not self.tenant_id:
            raise ValueError("tenant_id is required for tenant-scoped queries")
        return query.filter(model.tenant_id == self.tenant_id)
