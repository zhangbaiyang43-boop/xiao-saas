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
    has_any_permission,
    has_permission,
    normalize_role,
    permission_list,
)
from app.core.response import RespVo
from app.core.security import get_password_hash, verify_password

ACCOUNT_STATUS_CACHE_TTL = 30


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
        self.role = normalize_role(role)
        self.account_id = account_id
        self.name = name
        self.username = username

    @property
    def is_owner(self) -> bool:
        return self.role == ROLE_OWNER

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


def get_request_principal(request: Request) -> MerchantPrincipal | None:
    tenant_id = getattr(request.state, "tenant_id", None)
    token_type = getattr(request.state, "token_type", None)
    if not tenant_id or token_type != "merchant":
        return None
    return MerchantPrincipal(
        tenant_id=tenant_id,
        role=getattr(request.state, "role", ROLE_OWNER) or ROLE_OWNER,
        account_id=getattr(request.state, "account_id", None),
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
# Permission is checked here (and again in handlers for body-dependent actions).
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
    role = normalize_role(role)
    if role == ROLE_OWNER:
        return True
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
