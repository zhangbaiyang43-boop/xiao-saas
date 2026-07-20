from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from uuid import uuid4
from app.config import settings
from app.core.logger import logger
import time

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
