from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.response import RespVo
from app.core.security import verify_token

WHITELIST = {
    "/",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/v1/login",
    "/api/v1/login/code",
    "/api/v1/register",
    "/api/v1/wework/callback",
    "/api/v1/member/login-or-create",
    "/api/v1/entrance-codes/resolve",
    "/api/v1/miniapp/login",
    "/api/v1/miniapp/entry/join",
    "/api/v1/open/pos/verify",
    "/api/v1/orders/wxpay-notify",
    "/api/v1/dining-sessions/resolve",
}

WHITELIST_PREFIXES = [
    "/api/public/",
    "/h5/",
    "/api/super/",   # 超级管理接口由页面自行校验 X-Super-Token
]

# Paths where auth token is parsed if present, but not required (anonymous allowed)
OPTIONAL_AUTH_PATHS = {
    "/api/v1/shop/info",
    "/api/v1/menu/items",
    "/api/v1/orders",
    "/api/v1/orders/my",
    "/api/v1/dining-sessions/current/orders",
    "/api/v1/dining-sessions/checkout-request",
}

# Path prefixes with optional auth (customer or anonymous can access)
OPTIONAL_AUTH_PREFIXES = (
    "/api/v1/orders/",
    "/api/queue/",
)

MEMBER_PATH_PREFIXES = ("/api/v1/member", "/api/v1/miniapp/member", "/api/v1/miniapp/invite")
MERCHANT_PATH_PREFIX = "/api/v1"


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        if request.url.path in WHITELIST or request.url.path.startswith("/static/"):
            return await call_next(request)

        for prefix in WHITELIST_PREFIXES:
            if request.url.path.startswith(prefix):
                return await call_next(request)

        is_optional = (request.url.path in OPTIONAL_AUTH_PATHS or
                       request.url.path.startswith(OPTIONAL_AUTH_PREFIXES))

        token = request.headers.get("Authorization")
        if not token or not token.startswith("Bearer "):
            if is_optional:
                return await call_next(request)
            return JSONResponse(
                status_code=401,
                content=RespVo(code=401, msg="未登录或登录已过期").to_response(),
            )

        payload = verify_token(token[7:])
        if not payload:
            if is_optional:
                return await call_next(request)
            return JSONResponse(
                status_code=401,
                content=RespVo(code=401, msg="未登录或登录已过期").to_response(),
            )

        request.state.tenant_id = payload.get("tenant_id")
        request.state.user_id = payload.get("sub")
        request.state.customer_id = payload.get("customer_id")
        request.state.openid = payload.get("openid")
        request.state.token_type = payload.get("type")

        if is_optional:
            return await call_next(request)

        if request.url.path.startswith(MEMBER_PATH_PREFIXES):
            if payload.get("type") != "member":
                return JSONResponse(
                    status_code=403,
                    content=RespVo(code=403, msg="member auth required").to_response(),
                )
        elif request.url.path.startswith(MERCHANT_PATH_PREFIX):
            if payload.get("type") != "merchant":
                return JSONResponse(
                    status_code=403,
                    content=RespVo(code=403, msg="member auth required").to_response(),
                )

        return await call_next(request)

