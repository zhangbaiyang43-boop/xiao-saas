from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.core.logger import logger


CONSUMPTION_CREATED = "consumption.created"

EventHandler = Callable[["DomainEvent"], Awaitable[Any]]


@dataclass(slots=True)
class DomainEvent:
    name: str
    tenant_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    db: Any = None
    source: str = "core"


class EventBus:
    def __init__(self):
        self._handlers: dict[str, list[EventHandler]] = {}

    def register(self, event_name: str, handler: EventHandler):
        self._handlers.setdefault(event_name, [])
        if handler not in self._handlers[event_name]:
            self._handlers[event_name].append(handler)

    def unregister(self, event_name: str, handler: EventHandler):
        handlers = self._handlers.get(event_name, [])
        if handler in handlers:
            handlers.remove(handler)

    def clear(self):
        self._handlers.clear()

    async def dispatch(self, event: DomainEvent) -> list[dict[str, Any]]:
        results = []
        for handler in list(self._handlers.get(event.name, [])):
            handler_name = getattr(handler, "__name__", handler.__class__.__name__)
            try:
                data = await handler(event)
                results.append({"handler": handler_name, "status": "ok", "data": data})
            except Exception as exc:
                logger.exception(f"Event handler failed: {event.name} -> {handler_name}: {exc}")
                results.append({"handler": handler_name, "status": "error", "error": str(exc)})
        return results


event_bus = EventBus()
