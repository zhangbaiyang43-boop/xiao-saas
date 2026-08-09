from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.security import verify_token
from app.core.tenant_context import TenantContext

WHITELIST = {
    "/",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/v1/login",
    "/api/v1/login/code",
    "/api/v1/channel/auth/request-code",
    "/api/v1/channel/auth/login",
    "/api/v1/register",
    "/api/v1/wework/callback",
    "/api/v1/member/login-or-create",
    "/api/v1/entrance-codes/resolve",
    "/api/v1/dining-sessions/resolve",
    "/api/v1/dining-sessions/current/orders",
    "/api/v1/open/pos/verify",
}


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        TenantContext.clear()

        if request.method == "OPTIONS":
            return await call_next(request)

        if request.url.path in WHITELIST or request.url.path.startswith("/static/"):
            return await call_next(request)

        token = request.headers.get("Authorization")
        if token and token.startswith("Bearer "):
            payload = verify_token(token[7:])
            if payload:
                if payload.get("type") == "channel_partner":
                    request.state.token_type = "channel_partner"
                    request.state.partner_id = payload.get("partner_id")
                    return await call_next(request)
                tenant_id = payload.get("tenant_id")
                TenantContext.set_tenant_id(tenant_id)
                request.state.tenant_id = tenant_id
                request.state.token_type = payload.get("type")
                request.state.customer_id = payload.get("customer_id")

        return await call_next(request)

