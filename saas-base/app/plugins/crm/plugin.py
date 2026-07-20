from app.plugins.base_plugin import BasePlugin


class CrmPlugin(BasePlugin):
    plugin_code = "crm"

    @property
    def plugin_name(self) -> str:
        return "客户 CRM"

    @property
    def description(self) -> str:
        return "客户分层、客户标签、客户跟进记录等 CRM 扩展能力"

    async def install(self, tenant_id: str):
        pass

    async def uninstall(self, tenant_id: str):
        pass
