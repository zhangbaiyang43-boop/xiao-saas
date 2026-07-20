from contextvars import ContextVar

tenant_ctx = ContextVar('tenant_id', default=None)


class TenantContext:
    @classmethod
    def set_tenant_id(cls, tenant_id):
        tenant_ctx.set(tenant_id)

    @classmethod
    def get_tenant_id(cls):
        return tenant_ctx.get()

    @classmethod
    def get_current_tenant_id(cls):
        return tenant_ctx.get()

    @classmethod
    def clear(cls):
        tenant_ctx.set(None)
