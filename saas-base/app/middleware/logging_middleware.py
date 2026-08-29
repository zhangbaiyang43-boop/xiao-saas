import json
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import settings
from app.core.logger import logger
from app.core.request_context import RequestContext


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
        extra={"request_id": diagnostics["request_id"], "event": event},
    )


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid4())
        request.state.request_id = request_id
        context_token = RequestContext.set_request_id(request_id)
        start_time = time.time()

        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                logger.exception(
                    "HTTP_REQUEST_FAILED",
                    extra={
                        "event": "HTTP_REQUEST_FAILED",
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "error_type": type(exc).__name__,
                    },
                )
                raise

            cost_ms = round((time.time() - start_time) * 1000, 2)
            log_level = logger.warning if cost_ms > settings.SLOW_REQUEST_MS else logger.info
            response.headers["X-Process-Time-Ms"] = str(cost_ms)
            # P0-16 Phase B1: the request_id already minted above never left the
            # server before this -- a customer's error screenshot had nothing to
            # correlate against backend logs. Covers success, business-error (200
            # with an error code in the body), and any exception response that
            # FastAPI's own registered handlers turned into a Response before
            # reaching this point (the only path that can't get the header is a
            # raw exception escaping call_next entirely, handled in the except
            # block above -- there is no Response object to attach it to there).
            response.headers["X-Request-ID"] = request_id

            menu_diagnostics = getattr(request.state, "menu_diagnostics", None)
            if menu_diagnostics is not None:
                menu_diagnostics["server_total_ms"] = cost_ms
                content_length = response.headers.get("content-length")
                menu_diagnostics["payload_bytes"] = int(content_length) if content_length else None
                menu_diagnostics["status_code"] = response.status_code
                _log_slow_menu_api(menu_diagnostics)

            log_level(
                "HTTP_REQUEST_COMPLETED",
                extra={
                    "event": "HTTP_REQUEST_COMPLETED",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "cost_ms": cost_ms,
                },
            )
            return response
        finally:
            RequestContext.reset(context_token)
