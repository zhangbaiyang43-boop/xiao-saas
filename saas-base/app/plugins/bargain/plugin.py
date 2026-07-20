from app.plugins.base_plugin import BasePlugin


class BargainPlugin(BasePlugin):
    plugin_code = "bargain"

    @property
    def plugin_name(self) -> str:
        return "砍价营销"

    @property
    def description(self) -> str:
        return "裂砍价活动、参与记录和营销则扩展能力"

    async def install(self, tenant_id: str):
        pass

    async def uninstall(self, tenant_id: str):
        pass
