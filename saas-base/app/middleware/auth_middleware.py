from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings
from app.core.logger import logger
from app.core.merchant_auth import resolve_merchant_request_auth, staff_route_allowed
from app.core.permissions import ROLE_OWNER
from app.core.plan_capabilities import CAP_STAFF_MANAGEMENT
from app.core.response import RespVo
from app.core.security import verify_token

# 封禁商家后已签发的 token 有效期长达 7-30 天，之前只在 /login 那一刻查 tenant.status，
# 已登录的会话不受影响——被封的商家/顾客还能再用好几天。这里加一层实时状态检查，但不能
# 对每个已登录请求都直接查库（量大了是个隐患），所以结果按 tenant_id 缓存一小段时间：
# 封禁生效的延迟从"最长 7 天"缩短到"最多这个 TTL"，而绝大多数请求命中缓存、不产生额外查询。
TENANT_STATUS_CACHE_TTL_SECONDS = 45


async def _is_tenant_active(tenant_id: str) -> bool:
    from app.core.cache_helper import get_cache, set_cache

    cache_key = f"tenant_active:{tenant_id}"
    cached = await get_cache(cache_key)
    if cached is not None:
        return bool(cached)

    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.tenant import Tenant

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Tenant.status).where(Tenant.tenant_id == tenant_id))
        status = result.scalar_one_or_none()

    active = bool(status)
    await set_cache(cache_key, active, ttl=TENANT_STATUS_CACHE_TTL_SECONDS)
    return active


# Phase F1F-B (docs/saas-subscription-audit.md): a staff JWT can live for
# days, and a tenant's plan can lapse/downgrade at any moment -- so this
# check runs fresh on every non-owner request, with NO cross-request cache
# (unlike _is_tenant_active's TTL cache above). The frozen contract requires
# a downgrade to take effect on the very next request, not after up to
# TENANT_STATUS_CACHE_TTL_SECONDS of staleness; EntitlementService's own
# per-instance memoization (a fresh instance every call here) is the only
# memoization in play. Read-only: this session never commits, and its
# lifetime is scoped to entitlement resolution alone -- never the request's
# own business transaction.
#
# Phase F1F-BH: only EntitlementRequiredError (a clean "this plan lacks the
# capability" outcome) is caught here. Any other exception -- a genuine
# system/data error resolving entitlement -- is deliberately left to
# propagate to the caller (dispatch()), which fails the request CLOSED
# (503) rather than letting an unrelated data/infra problem silently grant
# staff access platform-wide. PAID_FEATURE_FAILS_CLOSED.
async def _staff_capability_denial(tenant_id: str):
    from app.core.database import AsyncSessionLocal
    from app.services.entitlement_service import EntitlementRequiredError, EntitlementService

    async with AsyncSessionLocal() as session:
        try:
            await EntitlementService(session).require_capability(tenant_id, CAP_STAFF_MANAGEMENT)
        except EntitlementRequiredError as exc:
            return exc
    return None

WHITELIST = {
    "/",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/v1/login",
    "/api/v1/login/code",
    "/api/v1/login/staff",
    "/api/v1/login/staff/device",
    "/api/v1/channel/auth/request-code",
    "/api/v1/channel/auth/login",
    "/api/v1/register",
    "/api/v1/register/code",
    "/api/v1/wework/callback",
    "/api/v1/member/login-or-create",
    "/api/v1/entrance-codes/resolve",
    "/api/v1/miniapp/entry/join",
    "/api/v1/open/pos/verify",
    "/api/v1/orders/wxpay-notify",
    "/api/v1/billing/wxpay-notify",
    "/api/v1/dining-sessions/resolve",
    "/api/v1/demo/sessions/start",
    "/api/v1/perf/report",
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
CHANNEL_PATH_PREFIX = "/api/v1/channel"
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
        request.state.partner_id = payload.get("partner_id")
        request.state.role = None
        request.state.account_id = None
        request.state.account_name = None
        request.state.account_username = None

        if payload.get("type") == "demo_merchant":
            expected_tenant = (settings.DEMO_TENANT_ID or "").strip()
            allowed = bool(
                expected_tenant
                and request.url.path.startswith("/api/v1/demo/")
                and payload.get("tenant_id") == expected_tenant
                and payload.get("scope") == "demo_order_fulfillment"
                and payload.get("dining_session_id")
            )
            if not allowed:
                return JSONResponse(
                    status_code=403,
                    content=RespVo(code=403, msg="体验凭证无权访问此功能").to_response(),
                )
            request.state.demo_session_id = str(payload["dining_session_id"])
            request.state.demo_table_no = str(payload.get("table_no") or "")
            if not await _is_tenant_active(expected_tenant):
                return JSONResponse(
                    status_code=403,
                    content=RespVo(code=403, msg="体验门店不可用").to_response(),
                )
            return await call_next(request)

        if payload.get("type") == "merchant":
            auth_state, err = await resolve_merchant_request_auth(payload)
            if err is not None:
                return err
            if auth_state is None:
                return JSONResponse(
                    status_code=401,
                    content=RespVo(code=401, msg="未登录或登录已过期").to_response(),
                )
            request.state.tenant_id = auth_state["tenant_id"]
            request.state.role = auth_state["role"]
            request.state.account_id = auth_state["account_id"]
            request.state.account_name = auth_state["account_name"]
            request.state.account_username = auth_state["account_username"]

            # Staff default-deny (owner keeps full access). Applies on optional paths too.
            if request.state.role != ROLE_OWNER:
                if not staff_route_allowed(request.method, request.url.path, request.state.role):
                    return JSONResponse(
                        status_code=403,
                        content=RespVo(code=403, msg="当前账号无此权限").to_response(),
                    )
                # Plan-downgrade enforcement (Phase F1F-B): an existing, unexpired staff
                # JWT must not keep working once the tenant's effective plan lacks
                # STAFF_MANAGEMENT. Owner is structurally exempt -- this whole block only
                # runs for role != ROLE_OWNER, so an owner request can never reach here
                # regardless of the tenant's plan.
                try:
                    staff_denial = await _staff_capability_denial(request.state.tenant_id)
                except Exception as exc:
                    # Phase F1F-BH: a system/data error resolving entitlement must
                    # NOT be treated as "capability granted." Fail closed -- this
                    # request does not proceed as staff.
                    logger.exception(
                        "[STAFF_ENTITLEMENT_CHECK_FAILED] tenant_id=%s error=%s",
                        request.state.tenant_id, exc,
                    )
                    return JSONResponse(
                        status_code=503,
                        content=RespVo(
                            code=503,
                            msg="系统繁忙，请稍后重试",
                            data={"error_code": "INTERNAL_ERROR"},
                        ).to_response(),
                    )
                if staff_denial is not None:
                    return JSONResponse(
                        status_code=403,
                        content=RespVo(
                            code=403,
                            msg="该功能需要更高套餐",
                            data={
                                "error_code": "PLAN_CAPABILITY_REQUIRED",
                                "capability": staff_denial.capability,
                                "effective_plan_code": staff_denial.effective_plan_code,
                                "required_plan_codes": list(staff_denial.required_plan_codes),
                            },
                        ).to_response(),
                    )

        if is_optional:
            return await call_next(request)

        if request.url.path.startswith(CHANNEL_PATH_PREFIX):
            if payload.get("type") != "channel_partner" or not payload.get("partner_id"):
                return JSONResponse(
                    status_code=403,
                    content=RespVo(code=403, msg="channel auth required").to_response(),
                )
            return await call_next(request)

        if request.state.tenant_id and not await _is_tenant_active(request.state.tenant_id):
            return JSONResponse(
                status_code=403,
                content=RespVo(code=403, msg="商家已停用").to_response(),
            )

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
