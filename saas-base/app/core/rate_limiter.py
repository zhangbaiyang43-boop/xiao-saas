from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from app.core.tenant_context import TenantContext
from app.config import settings

limiter = Limiter(key_func=get_remote_address)

def get_tenant_key(request: Request):
    tenant_id = TenantContext.get_current_tenant_id()
    return tenant_id or get_remote_address(request)

tenant_limiter = Limiter(key_func=get_tenant_key)

LOGIN_LIMIT = settings.RATE_LIMIT_LOGIN
PUBLIC_LIMIT = settings.RATE_LIMIT_PUBLIC
TENANT_LIMIT = settings.RATE_LIMIT_TENANT
JOIN_LIMIT = settings.RATE_LIMIT_JOIN

def login_limit():
    return limiter.limit(LOGIN_LIMIT)

def public_limit():
    return limiter.limit(PUBLIC_LIMIT)

def tenant_limit():
    return tenant_limiter.limit(TENANT_LIMIT)

def join_limit():
    """入会注册接口专用限流（按 IP）：防止批量刷券攻击。"""
    return limiter.limit(JOIN_LIMIT)