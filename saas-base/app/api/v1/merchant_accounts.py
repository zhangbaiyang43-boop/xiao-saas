from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
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
from app.services import staff_bind_token_service as bind_tokens
from app.services import staff_mp_bind_session_service as mp_bind
from app.services.merchant_account_service import MerchantAccountService
from app.services.staff_bind_token_service import StaffAuthStoreUnavailable
from app.services.staff_miniprogram_provider import (
    build_staff_mp_test_scan_payload,
    staff_miniprogram_auth_enabled,
    staff_miniprogram_test_scan_enabled,
)
from app.services.staff_trusted_device_service import StaffTrustedDeviceService
from app.services.staff_wechat_auth_service import StaffWechatAuthService
from app.services.tenant_service import TenantService
from slowapi.util import get_remote_address

router = APIRouter(prefix="/api/v1", tags=["商家员工"])


class StaffLoginRequest(BaseModel):
    shop_phone: str = Field(..., description="门店老板手机号，用于定位租户")
    username: str
    password: str


class StaffCreateRequest(BaseModel):
    name: str
    role: str  # waiter | kitchen
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


def _staff_access_token(tenant_id: str, role: str, account_id: int) -> str:
    minutes = max(15, int(settings.STAFF_ACCESS_TOKEN_MINUTES or 120))
    return create_access_token(
        tenant_id,
        expires_delta=timedelta(minutes=minutes),
        role=role,
        account_id=int(account_id),
    )


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
        return error_response(code=400, msg="账号或密码错误")

    await clear_staff_login_failures(tenant.tenant_id, username, client_ip)
    token = _staff_access_token(tenant.tenant_id, account.role, int(account.id))
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
            "auth_method": "staff_password",
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
    return await MerchantAccountService(db).set_backup_login(
        tenant_id=principal.tenant_id,
        account_id=int(account_id),
        username=body.username,
        password=body.password,
    )


@router.post("/merchant-accounts/{account_id}/miniprogram-bind-session")
async def create_miniprogram_bind_session(
    account_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Owner: generate WeChat mini-program code for staff bind (primary)."""
    if not staff_miniprogram_auth_enabled():
        return error_response(code=403, msg="员工小程序绑定未启用")
    principal, err = _require_perm(request, PERM_STAFF_MANAGE)
    if err:
        return err
    svc = MerchantAccountService(db)
    account = await svc.get_by_id(principal.tenant_id, int(account_id))
    if not account:
        return error_response(code=404, msg="员工不存在")
    if account.status != "active":
        return error_response(code=400, msg="请先启用员工再生成绑定码")
    if account.role not in ("waiter", "kitchen"):
        return error_response(code=400, msg="该账号不支持微信绑定")

    bound = await StaffWechatAuthService(db).is_wechat_bound(
        tenant_id=principal.tenant_id, account_id=int(account.id)
    )
    if bound:
        return error_response(code=400, msg="该员工已绑定微信，请先解除绑定")

    try:
        session = await mp_bind.create_mp_bind_session(
            tenant_id=principal.tenant_id,
            account_id=int(account.id),
            created_by_owner=principal.tenant_id,
        )
    except StaffAuthStoreUnavailable as exc:
        return error_response(code=503, msg=exc.msg)

    from app.services.staff_wxacode_service import generate_staff_bind_wxacode

    try:
        image_bytes = await generate_staff_bind_wxacode(session["scene"])
    except Exception as exc:
        from app.core.logger import logger

        logger.warning(
            "staff_mp_bind_wxacode_failed account_id=%s tenant_id=%s err=%s",
            account.id,
            principal.tenant_id,
            type(exc).__name__,
        )
        return error_response(code=502, msg="员工绑定码生成失败，请稍后重试")

    import base64

    qrcode_data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
    data = {
        "session_id": session["session_id"],
        "expires_at": session["expires_at"],
        "expires_in": session["expires_in"],
        "qrcode_data_url": qrcode_data_url,
        "staff_name": account.name,
        "role": account.role,
        "role_label": "服务员" if account.role == "waiter" else "后厨",
    }
    # TEMP_STAFF_BIND_TEST_SCAN — same scene as wxacode; omit when flag off.
    # Remove after MiniProgram production release verification.
    if staff_miniprogram_test_scan_enabled():
        data["test_scan_payload"] = build_staff_mp_test_scan_payload(session["scene"])
    return success_response(data=data)


@router.get("/merchant-accounts/{account_id}/miniprogram-bind-status")
async def miniprogram_bind_status(
    account_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if not staff_miniprogram_auth_enabled():
        return error_response(code=403, msg="员工小程序绑定未启用")
    principal, err = _require_perm(request, PERM_STAFF_MANAGE)
    if err:
        return err
    account = await MerchantAccountService(db).get_by_id(principal.tenant_id, int(account_id))
    if not account:
        return error_response(code=404, msg="员工不存在")
    status = await mp_bind.get_mp_bind_status_for_account(int(account_id))
    if status != "bound":
        if await StaffWechatAuthService(db).is_wechat_bound(
            tenant_id=principal.tenant_id, account_id=int(account_id)
        ):
            status = "bound"
    return success_response(data={"status": status})


@router.post("/merchant-accounts/{account_id}/wechat-bind-token")
async def create_wechat_bind_token(
    account_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Legacy H5 URL bind token — disabled when OA OAuth is off (default)."""
    from app.services.staff_miniprogram_provider import staff_official_account_oauth_enabled

    if not staff_official_account_oauth_enabled():
        return error_response(code=403, msg="公众号员工绑定已停用，请使用小程序绑定码")
    principal, err = _require_perm(request, PERM_STAFF_MANAGE)
    if err:
        return err
    svc = MerchantAccountService(db)
    account = await svc.get_by_id(principal.tenant_id, int(account_id))
    if not account:
        return error_response(code=404, msg="员工不存在")
    if account.status != "active":
        return error_response(code=400, msg="请先启用员工再生成绑定码")
    if account.role not in ("waiter", "kitchen"):
        return error_response(code=400, msg="该账号不支持微信绑定")

    bound = await StaffWechatAuthService(db).is_wechat_bound(
        tenant_id=principal.tenant_id, account_id=int(account.id)
    )
    if bound:
        return error_response(code=400, msg="该员工已绑定微信，请先解除绑定")

    try:
        data = await bind_tokens.create_bind_token(
            tenant_id=principal.tenant_id,
            account_id=int(account.id),
            created_by_owner=principal.tenant_id,
        )
    except StaffAuthStoreUnavailable as exc:
        return error_response(code=503, msg=exc.msg)
    return success_response(
        data={
            **data,
            "staff_name": account.name,
            "role": account.role,
            "role_label": "服务员" if account.role == "waiter" else "后厨",
        }
    )


@router.get("/merchant-accounts/{account_id}/wechat-bind-status")
async def wechat_bind_status(
    account_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    principal, err = _require_perm(request, PERM_STAFF_MANAGE)
    if err:
        return err
    account = await MerchantAccountService(db).get_by_id(principal.tenant_id, int(account_id))
    if not account:
        return error_response(code=404, msg="员工不存在")
    # Prefer mini-program bind status; fall back to legacy redis marker.
    status = await mp_bind.get_mp_bind_status_for_account(int(account_id))
    if status == "expired":
        status = await bind_tokens.get_bind_status_for_account(int(account_id))
    if status != "bound":
        if await StaffWechatAuthService(db).is_wechat_bound(
            tenant_id=principal.tenant_id, account_id=int(account_id)
        ):
            status = "bound"
    return success_response(data={"status": status})


@router.post("/merchant-accounts/{account_id}/wechat-unbind")
async def wechat_unbind(
    account_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    principal, err = _require_perm(request, PERM_STAFF_MANAGE)
    if err:
        return err
    account = await MerchantAccountService(db).get_by_id(principal.tenant_id, int(account_id))
    if not account:
        return error_response(code=404, msg="员工不存在")
    data = await StaffWechatAuthService(db).unbind_wechat(
        tenant_id=principal.tenant_id, account_id=int(account_id)
    )
    return success_response(data=data, msg="已解除微信绑定")


@router.post("/merchant-accounts/{account_id}/devices/revoke-all")
async def revoke_all_devices(
    account_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    principal, err = _require_perm(request, PERM_STAFF_MANAGE)
    if err:
        return err
    account = await MerchantAccountService(db).get_by_id(principal.tenant_id, int(account_id))
    if not account:
        return error_response(code=404, msg="员工不存在")
    count = await StaffTrustedDeviceService(db).revoke_all(
        tenant_id=principal.tenant_id, account_id=int(account_id)
    )
    return success_response(data={"revoked": count}, msg="已退出所有设备")
