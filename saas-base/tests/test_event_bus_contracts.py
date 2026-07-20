import asyncio
import unittest

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.core.events import CONSUMPTION_CREATED, DomainEvent, EventBus
from app.plugins.base_plugin import BasePlugin
from app.plugins.plugin_manager import PluginManager


class DemoPlugin(BasePlugin):
    plugin_code = "demo"

    async def install(self, tenant_id: str):
        pass

    async def uninstall(self, tenant_id: str):
        pass

    async def on_consumption_created(self, event):
        return {"plugin": self.plugin_code, "event": event.name}

    def get_event_handlers(self):
        return {CONSUMPTION_CREATED: self.on_consumption_created}


class EventBusContractsTest(unittest.TestCase):
    def test_event_bus_dispatches_registered_async_handlers(self):
        bus = EventBus()
        calls = []

        async def handler(event):
            calls.append((event.name, event.tenant_id, event.payload["amount"]))
            return "ok"

        bus.register(CONSUMPTION_CREATED, handler)
        result = asyncio.run(bus.dispatch(DomainEvent(
            name=CONSUMPTION_CREATED,
            tenant_id="tenant-001",
            payload={"amount": 99},
        )))

        self.assertEqual(calls, [(CONSUMPTION_CREATED, "tenant-001", 99)])
        self.assertEqual(result[0]["status"], "ok")

    def test_event_bus_isolates_handler_failures(self):
        bus = EventBus()

        async def broken(event):
            raise RuntimeError("boom")

        bus.register(CONSUMPTION_CREATED, broken)
        result = asyncio.run(bus.dispatch(DomainEvent(
            name=CONSUMPTION_CREATED,
            tenant_id="tenant-001",
            payload={},
        )))

        self.assertEqual(result[0]["status"], "error")
        self.assertIn("boom", result[0]["error"])

    def test_plugins_expose_event_handlers(self):
        plugin = DemoPlugin()

        self.assertIn(CONSUMPTION_CREATED, plugin.get_event_handlers())

    def test_plugin_manager_has_event_dispatch_contract(self):
        manager = PluginManager()

        self.assertTrue(hasattr(manager, "dispatch_event"))
        self.assertTrue(asyncio.iscoroutinefunction(manager.dispatch_event))


if __name__ == "__main__":
    unittest.main()
