from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.merchant_auth import (
    clear_staff_login_failures,
    get_request_principal,
    record_staff_login_failure,
    staff_login_allowed,
)
from app.core.permissions import (
    PERM_STAFF_MANAGE,
    PERM_STAFF_VIEW,
    ROLE_OWNER,
    permission_list,
)
from app.core.rate_limiter import login_limit
from app.core.response import error_response, success_response
from app.core.security import create_access_token
from app.schemas.tenant import normalize_phone
from app.services.merchant_account_service import MerchantAccountService
from app.services.tenant_service import TenantService
from slowapi.util import get_remote_address

router = APIRouter(prefix="/api/v1", tags=["商家员工"])


class StaffLoginRequest(BaseModel):
    shop_phone: str = Field(..., description="门店老板手机号，用于定位租户")
    username: str
    password: str


class StaffCreateRequest(BaseModel):
    name: str
    username: str
    password: str
    role: str  # waiter | kitchen


class StaffUpdateRequest(BaseModel):
    name: str | None = None
    role: str | None = None
    status: str | None = None


class StaffResetPasswordRequest(BaseModel):
    password: str


def _require_perm(request: Request, permission: str):
    principal = get_request_principal(request)
    if not principal:
        return None, error_response(code=401, msg="请先登录")
    if not principal.can(permission):
        return None, error_response(code=403, msg="当前账号无此权限")
    return principal, None


@router.get("/auth/me")
async def auth_me(request: Request, db: AsyncSession = Depends(get_db)):
    principal = get_request_principal(request)
    if not principal:
        return error_response(code=401, msg="请先登录")

    tenant = await TenantService(db).get_tenant(principal.tenant_id)
    if not tenant or not tenant.status:
        return error_response(code=403, msg="商家已停用")

    data = principal.to_session_dict()
    data.update(
        {
            "tenant_name": tenant.name,
            "phone": tenant.phone if principal.is_owner else None,
            "home_path": {
                ROLE_OWNER: "/",
                "waiter": "/waiter",
                "kitchen": "/kitchen",
            }.get(principal.role, "/"),
        }
    )
    if principal.is_owner:
        data["name"] = tenant.name
    return success_response(data=data)


@router.post("/login/staff")
@login_limit()
async def staff_login(request: Request, body: StaffLoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        phone = normalize_phone(body.shop_phone)
    except ValueError:
        return error_response(code=400, msg="请输入正确的门店手机号")

    tenant = await TenantService(db).get_tenant_by_phone(phone)
    if not tenant:
        return error_response(code=404, msg="门店不存在")
    if not tenant.status:
        return error_response(code=403, msg="商家账号已停用")

    client_ip = get_remote_address(request) or "unknown"
    username = (body.username or "").strip().lower()
    allowed, throttle_msg = await staff_login_allowed(tenant.tenant_id, username, client_ip)
    if not allowed:
        return error_response(code=429, msg=throttle_msg or "尝试次数过多，请稍后再试")

    account, err = await MerchantAccountService(db).authenticate(
        tenant_id=tenant.tenant_id,
        username=username,
        password=body.password,
    )
    if err:
        await record_staff_login_failure(tenant.tenant_id, username, client_ip)
        # Unified message — never reveal whether username exists.
        return error_response(code=400, msg="账号或密码错误")

    await clear_staff_login_failures(tenant.tenant_id, username, client_ip)
    token = create_access_token(
        tenant.tenant_id,
        role=account.role,
        account_id=int(account.id),
    )
    return success_response(
        data={
            "tenant_id": tenant.tenant_id,
            "name": account.name,
            "phone": None,
            "token": token,
            "token_type": "bearer",
            "role": account.role,
            "account_id": str(account.id),
            "username": account.username,
            "permissions": permission_list(account.role),
            "home_path": "/waiter" if account.role == "waiter" else "/kitchen",
        },
        msg="登录成功",
    )


@router.get("/merchant-accounts")
async def list_merchant_accounts(request: Request, db: AsyncSession = Depends(get_db)):
    principal, err = _require_perm(request, PERM_STAFF_VIEW)
    if err:
        return err
    return await MerchantAccountService(db).list_accounts(principal.tenant_id)


@router.post("/merchant-accounts")
async def create_merchant_account(
    body: StaffCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    principal, err = _require_perm(request, PERM_STAFF_MANAGE)
    if err:
        return err
    return await MerchantAccountService(db).create_account(
        tenant_id=principal.tenant_id,
        name=body.name,
        username=body.username,
        password=body.password,
        role=body.role,
    )


@router.patch("/merchant-accounts/{account_id}")
async def update_merchant_account(
    account_id: str,
    body: StaffUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    principal, err = _require_perm(request, PERM_STAFF_MANAGE)
    if err:
        return err
    return await MerchantAccountService(db).update_account(
        tenant_id=principal.tenant_id,
        account_id=int(account_id),
        name=body.name,
        role=body.role,
        status=body.status,
    )


@router.post("/merchant-accounts/{account_id}/reset-password")
async def reset_merchant_account_password(
    account_id: str,
    body: StaffResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    principal, err = _require_perm(request, PERM_STAFF_MANAGE)
    if err:
        return err
    return await MerchantAccountService(db).reset_password(
        tenant_id=principal.tenant_id,
        account_id=int(account_id),
        password=body.password,
    )
