from app.core.events import CONSUMPTION_CREATED
from app.plugins.base_plugin import BasePlugin


class PointsPlugin(BasePlugin):
    plugin_code = "points"

    @property
    def plugin_name(self) -> str:
        return "积分体系"

    @property
    def description(self) -> str:
        return "会员积分、积分流水和积分兑换扩展能力"

    async def install(self, tenant_id: str):
        pass

    async def uninstall(self, tenant_id: str):
        pass

    async def on_consumption_created(self, event):
        return {
            "handled": True,
            "event": event.name,
            "customer_id": event.payload.get("customer_id"),
            "amount": event.payload.get("amount"),
        }

    def get_event_handlers(self):
        return {
            CONSUMPTION_CREATED: self.on_consumption_created,
        }
