from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.entitlement_guard import require_capability_response
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
    staff_home_path,
)
from app.core.plan_capabilities import CAP_STAFF_MANAGEMENT
from app.core.rate_limiter import login_limit
from app.core.response import error_response, success_response
from app.schemas.tenant import normalize_phone
from app.services.merchant_account_service import MerchantAccountService
from app.services.staff_session_cookie import deliver_device_credential, read_device_credential
from app.services.staff_session_service import StaffSessionService
from app.services.staff_trusted_device_service import (
    StaffTrustedDeviceService,
    decode_device_credential,
)
from app.services.tenant_service import TenantService
from slowapi.util import get_remote_address

router = APIRouter(prefix="/api/v1", tags=["商家员工"])


class StaffLoginRequest(BaseModel):
    shop_phone: str = Field(..., description="门店老板手机号，用于定位租户")
    username: str
    password: str


class StaffCreateRequest(BaseModel):
    name: str
    role: str  # frontdesk | waiter | kitchen
    username: str | None = None
    password: str | None = None


class StaffUpdateRequest(BaseModel):
    name: str | None = None
    role: str | None = None
    status: str | None = None


class StaffResetPasswordRequest(BaseModel):
    password: str


class StaffBackupLoginRequest(BaseModel):
    username: str
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
            "home_path": "/" if principal.role == ROLE_OWNER else staff_home_path(principal.role),
        }
    )
    if principal.is_owner:
        data["name"] = tenant.name
    return success_response(data=data)


@router.post("/login/staff")
@login_limit()
async def staff_login(
    request: Request,
    response: Response,
    body: StaffLoginRequest,
    db: AsyncSession = Depends(get_db),
):
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
        return error_response(code=400, msg="账号或密码错误")

    await clear_staff_login_failures(tenant.tenant_id, username, client_ip)

    # Plan gate, not a credential gate: password already verified above, so
    # this must never be disguised as "wrong username/password" -- a
    # downgraded tenant's staff account exists and the password is correct,
    # it's the plan that currently disallows STAFF_MANAGEMENT.
    denial = await require_capability_response(db, tenant.tenant_id, CAP_STAFF_MANAGEMENT)
    if denial is not None:
        return denial

    # Store-device trusted login via neutral StaffSessionService (no WeChat dependency).
    # Wrong/disabled password paths never reach here — no device created on failure.
    existing_cred = read_device_credential(request, None)
    existing_id, existing_secret = decode_device_credential(existing_cred)
    issued = await StaffSessionService(db).issue_session_for_account(
        account,
        auth_method="staff_password",
        user_agent=request.headers.get("user-agent"),
        tenant=tenant,
        existing_device_id=existing_id,
        existing_secret=existing_secret,
    )
    if not issued.get("ok"):
        return error_response(code=400, msg=issued.get("msg") or "登录失败", data={"code": issued.get("code")})

    data = deliver_device_credential(response, issued)
    return success_response(data=data, msg="登录成功")


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
    denial = await require_capability_response(db, principal.tenant_id, CAP_STAFF_MANAGEMENT)
    if denial is not None:
        return denial
    return await MerchantAccountService(db).create_account(
        tenant_id=principal.tenant_id,
        name=body.name,
        role=body.role,
        username=body.username,
        password=body.password,
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
    denial = await require_capability_response(db, principal.tenant_id, CAP_STAFF_MANAGEMENT)
    if denial is not None:
        return denial
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
    denial = await require_capability_response(db, principal.tenant_id, CAP_STAFF_MANAGEMENT)
    if denial is not None:
        return denial
    return await MerchantAccountService(db).reset_password(
        tenant_id=principal.tenant_id,
        account_id=int(account_id),
        password=body.password,
    )


@router.post("/merchant-accounts/{account_id}/backup-login")
async def set_backup_login(
    account_id: str,
    body: StaffBackupLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    principal, err = _require_perm(request, PERM_STAFF_MANAGE)
    if err:
        return err
    denial = await require_capability_response(db, principal.tenant_id, CAP_STAFF_MANAGEMENT)
    if denial is not None:
        return denial
    return await MerchantAccountService(db).set_backup_login(
        tenant_id=principal.tenant_id,
        account_id=int(account_id),
        username=body.username,
        password=body.password,
    )


@router.post("/merchant-accounts/{account_id}/devices/revoke-all")
async def revoke_all_devices(
    account_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    principal, err = _require_perm(request, PERM_STAFF_MANAGE)
    if err:
        return err
    denial = await require_capability_response(db, principal.tenant_id, CAP_STAFF_MANAGEMENT)
    if denial is not None:
        return denial
    account = await MerchantAccountService(db).get_by_id(principal.tenant_id, int(account_id))
    if not account:
        return error_response(code=404, msg="员工不存在")
    count = await StaffTrustedDeviceService(db).revoke_all(
        tenant_id=principal.tenant_id, account_id=int(account_id)
    )
    return success_response(data={"revoked": count}, msg="已退出所有设备")
