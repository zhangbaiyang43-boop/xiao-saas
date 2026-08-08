"""Merchant principal + permission guards.

【前端隐藏不是安全，后端 Permission 才是安全边界。】
【员工默认无权限，只开放岗位履约真正需要的能力。】
"""

from __future__ import annotations

import re
from typing import Callable, Optional

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.cache_helper import get_cache, set_cache
from app.core.permissions import (
    ORDER_STATUS_PERMISSIONS,
    ROLE_OWNER,
    STAFF_ROLES,
    has_any_permission,
    has_permission,
    parse_staff_role,
    permission_list,
)
from app.core.response import RespVo
from app.core.security import get_password_hash, verify_password

ACCOUNT_STATUS_CACHE_TTL = 30
STAFF_LOGIN_FAIL_TTL = 900
STAFF_LOGIN_FAIL_MAX = 10


class MerchantPrincipal:
    def __init__(
        self,
        *,
        tenant_id: str,
        role: str,
        account_id: int | None = None,
        name: str | None = None,
        username: str | None = None,
    ):
        self.tenant_id = tenant_id
        self.role = role
        self.account_id = account_id
        self.name = name
        self.username = username

    @property
    def is_owner(self) -> bool:
        # Owner = Tenant subject (no merchant_accounts row), never a staff account.
        return self.account_id is None and self.role == ROLE_OWNER

    def can(self, permission: str) -> bool:
        return has_permission(self.role, permission)

    def to_session_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "role": self.role,
            "account_id": str(self.account_id) if self.account_id else None,
            "name": self.name,
            "username": self.username,
            "permissions": permission_list(self.role),
        }


def permission_denied_response(msg: str = "当前账号无此权限") -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content=RespVo(code=403, msg=msg).to_response(),
    )


def auth_error_response(status: int, msg: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=RespVo(code=status, msg=msg).to_response(),
    )


async def resolve_merchant_request_auth(payload: dict) -> tuple[dict | None, JSONResponse | None]:
    """Resolve merchant auth from JWT payload.

    Legacy owner (only):
      type=merchant AND account_id is absent → role=owner

    Staff:
      account_id present → load merchant_accounts; role from DB only;
      invalid/missing account/role/status → reject (never owner).
    """
    if payload.get("type") != "merchant":
        return None, None

    tenant_id = payload.get("tenant_id")
    if not tenant_id:
        return None, auth_error_response(401, "未登录或登录已过期")

    account_id = payload.get("account_id")
    if account_id is None:
        return {
            "tenant_id": tenant_id,
            "role": ROLE_OWNER,
            "account_id": None,
            "account_name": None,
            "account_username": None,
        }, None

    try:
        account_id_int = int(account_id)
    except (TypeError, ValueError):
        return None, auth_error_response(401, "未登录或登录已过期")

    auth_state = await load_account_auth_state(account_id_int, tenant_id)
    if not auth_state or auth_state.get("missing"):
        return None, auth_error_response(401, "未登录或登录已过期")
    if auth_state.get("tenant_id") != tenant_id:
        return None, auth_error_response(403, "当前账号无此权限")
    if auth_state.get("status") != "active":
        return None, auth_error_response(403, "账号已停用")

    staff_role = parse_staff_role(auth_state.get("role"))
    if not staff_role:
        # Corrupt / illegal staff role must never elevate to owner.
        return None, auth_error_response(403, "当前账号无此权限")

    return {
        "tenant_id": tenant_id,
        "role": staff_role,
        "account_id": account_id_int,
        "account_name": auth_state.get("name"),
        "account_username": auth_state.get("username"),
    }, None


def get_request_principal(request: Request) -> MerchantPrincipal | None:
    tenant_id = getattr(request.state, "tenant_id", None)
    token_type = getattr(request.state, "token_type", None)
    if not tenant_id or token_type != "merchant":
        return None
    role = getattr(request.state, "role", None)
    account_id = getattr(request.state, "account_id", None)
    if account_id is None:
        if role != ROLE_OWNER:
            return None
    else:
        if role not in STAFF_ROLES:
            return None
    return MerchantPrincipal(
        tenant_id=tenant_id,
        role=role,
        account_id=account_id,
        name=getattr(request.state, "account_name", None),
        username=getattr(request.state, "account_username", None),
    )


def require_permission(permission: str) -> Callable:
    async def _dependency(request: Request) -> MerchantPrincipal:
        principal = get_request_principal(request)
        if not principal:
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail="请先登录")
        if not principal.can(permission):
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="当前账号无此权限")
        return principal

    return Depends(_dependency)


def require_order_status_permission(target_status: str, role: str) -> bool:
    needed = ORDER_STATUS_PERMISSIONS.get((target_status or "").strip().lower())
    if not needed:
        return False
    return has_permission(role, needed)


# Staff default-deny: only these routes may be hit by non-owner merchant tokens.
_STAFF_ROUTE_RULES: list[tuple[str, re.Pattern[str], Optional[str] | tuple[str, ...]]] = [
    ("GET", re.compile(r"^/api/v1/auth/me$"), None),
    ("POST", re.compile(r"^/api/v1/tenant/logout$"), None),
    ("GET", re.compile(r"^/api/v1/orders/workbench$"), "order.view_fulfillment"),
    (
        "PATCH",
        re.compile(r"^/api/v1/orders/\d+/status$"),
        ("order.accept", "order.complete", "finance.settle", "order.reject", "finance.refund"),
    ),
    ("GET", re.compile(r"^/api/v1/pickup-nos/status$"), "pickup.view"),
    ("PATCH", re.compile(r"^/api/v1/orders/\d+/pickup-no$"), ("pickup.assign", "pickup.change")),
    ("POST", re.compile(r"^/api/v1/orders/\d+/reprint$"), "kitchen.print_reprint"),
    ("GET", re.compile(r"^/api/v1/merchant-accounts$"), "staff.view"),
    ("POST", re.compile(r"^/api/v1/merchant-accounts$"), "staff.manage"),
    ("PATCH", re.compile(r"^/api/v1/merchant-accounts/\d+$"), "staff.manage"),
    ("POST", re.compile(r"^/api/v1/merchant-accounts/\d+/reset-password$"), "staff.manage"),
]


def staff_route_allowed(method: str, path: str, role: str) -> bool:
    if role == ROLE_OWNER:
        return True
    if role not in STAFF_ROLES:
        return False
    m = (method or "GET").upper()
    for rule_method, pattern, perm in _STAFF_ROUTE_RULES:
        if rule_method != m:
            continue
        if not pattern.match(path):
            continue
        if perm is None:
            return True
        if isinstance(perm, tuple):
            return has_any_permission(role, perm)
        return has_permission(role, perm)
    return False


async def load_account_auth_state(account_id: int, tenant_id: str) -> dict | None:
    """Return {status, role, name, username, tenant_id} or None. Short-cached."""
    from app.core.database import AsyncSessionLocal
    from app.models.merchant_account import MerchantAccount

    cache_key = f"merchant_account_auth:{account_id}"
    cached = await get_cache(cache_key)
    if cached is not None:
        if cached.get("missing"):
            return None
        if cached.get("tenant_id") != tenant_id:
            return None
        return cached

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(MerchantAccount).where(MerchantAccount.id == int(account_id))
        )
        account = result.scalar_one_or_none()
        if not account:
            await set_cache(cache_key, {"missing": True}, ttl=ACCOUNT_STATUS_CACHE_TTL)
            return None
        data = {
            "tenant_id": account.tenant_id,
            "status": account.status,
            "role": account.role,
            "name": account.name,
            "username": account.username,
        }
    await set_cache(cache_key, data, ttl=ACCOUNT_STATUS_CACHE_TTL)
    if data["tenant_id"] != tenant_id:
        return None
    return data


async def invalidate_account_auth_cache(account_id: int) -> None:
    from app.core.cache_helper import delete_cache

    await delete_cache(f"merchant_account_auth:{account_id}")


def hash_staff_password(password: str) -> str:
    return get_password_hash(password)


def check_staff_password(plain: str, hashed: str) -> bool:
    return verify_password(plain, hashed)


def validate_staff_password(password: str | None) -> str | None:
    """Return error message or None if ok. Min length 8; reject whitespace-only."""
    raw = "" if password is None else str(password)
    if not raw or not raw.strip() or raw.isspace():
        return "密码不能为空或纯空格"
    if len(raw) < 8 or len(raw) > 64:
        return "密码长度需为8-64位"
    return None


def _staff_fail_key(tenant_id: str, username: str, ip: str) -> str:
    return f"staff_login_fail:{tenant_id}:{username.strip().lower()}:{ip or 'unknown'}"


async def staff_login_allowed(tenant_id: str, username: str, ip: str) -> tuple[bool, str | None]:
    fails = await get_cache(_staff_fail_key(tenant_id, username, ip))
    try:
        count = int(fails or 0)
    except (TypeError, ValueError):
        count = 0
    if count >= STAFF_LOGIN_FAIL_MAX:
        return False, "尝试次数过多，请稍后再试"
    return True, None


async def record_staff_login_failure(tenant_id: str, username: str, ip: str) -> None:
    key = _staff_fail_key(tenant_id, username, ip)
    fails = await get_cache(key)
    try:
        count = int(fails or 0) + 1
    except (TypeError, ValueError):
        count = 1
    await set_cache(key, count, ttl=STAFF_LOGIN_FAIL_TTL)


async def clear_staff_login_failures(tenant_id: str, username: str, ip: str) -> None:
    from app.core.cache_helper import delete_cache

    await delete_cache(_staff_fail_key(tenant_id, username, ip))
