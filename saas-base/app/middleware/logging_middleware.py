import json
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from uuid import uuid4
from app.config import settings
from app.core.logger import logger


SLOW_MENU_API_MS = 500.0
VERY_SLOW_MENU_API_MS = 1000.0


def _log_slow_menu_api(diagnostics: dict) -> None:
    server_total_ms = diagnostics["server_total_ms"]
    if server_total_ms >= VERY_SLOW_MENU_API_MS:
        event = "VERY_SLOW_MENU_API"
    elif server_total_ms >= SLOW_MENU_API_MS:
        event = "SLOW_MENU_API"
    else:
        return
    logger.warning(
        json.dumps(
            {"event": event, **diagnostics},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        extra={"request_id": diagnostics["request_id"]},
    )

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid4())
        request.state.request_id = request_id
        
        start_time = time.time()
        
        try:
            response = await call_next(request)
        except Exception as e:
            logger.error(
                f"Request error: {str(e)}",
                extra={"request_id": request_id}
            )
            raise
        
        cost_ms = round((time.time() - start_time) * 1000, 2)
        log_level = logger.warning if cost_ms > settings.SLOW_REQUEST_MS else logger.info
        response.headers["X-Process-Time-Ms"] = str(cost_ms)

        menu_diagnostics = getattr(request.state, "menu_diagnostics", None)
        if menu_diagnostics is not None:
            menu_diagnostics["server_total_ms"] = cost_ms
            content_length = response.headers.get("content-length")
            menu_diagnostics["payload_bytes"] = int(content_length) if content_length else None
            menu_diagnostics["status_code"] = response.status_code
            _log_slow_menu_api(menu_diagnostics)
        
        log_level(
            "Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "cost_ms": cost_ms
            }
        )
        
        return response
