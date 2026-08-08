"""Staff mini-program Authentication (wx.login + handoff). Authorization unchanged."""

# NOTE: Do NOT use `from __future__ import annotations` here.
# FastAPI + Pydantic must resolve request models at route-registration time.

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.core.rate_limiter import login_limit
from app.core.response import error_response, success_response
from app.services import staff_handoff_service as handoff_svc
from app.services import staff_mp_bind_session_service as mp_bind
from app.services.staff_bind_token_service import StaffAuthStoreUnavailable
from app.services.staff_miniprogram_provider import (
    get_staff_miniprogram_provider,
    staff_miniprogram_auth_enabled,
    staff_official_account_oauth_enabled,
)
from app.services.staff_session_cookie import cookie_name, deliver_device_credential
from app.services.staff_session_service import StaffSessionService
from app.services.staff_trusted_device_service import decode_device_credential
from app.services.staff_wechat_auth_service import StaffWechatAuthService

router = APIRouter(prefix="/api/v1", tags=["员工小程序登录"])


@router.get("/staff/miniprogram/status")
async def mp_auth_status():
    """Public feature flag for H5 / miniapp entry gating (no secrets)."""
    return success_response(
        data={
            "enabled": staff_miniprogram_auth_enabled(),
            "official_account_oauth_enabled": staff_official_account_oauth_enabled(),
        }
    )


class MpBindPreviewRequest(BaseModel):
    scene: str


class MpBindConfirmRequest(BaseModel):
    scene: str
    code: str


class MpLoginRequest(BaseModel):
    code: str


class MpLoginSelectRequest(BaseModel):
    code: str
    account_id: str


class StaffHandoffRequest(BaseModel):
    handoff_token: str


def _ua(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _h5_base() -> str:
    return (settings.PUBLIC_BASE_URL or settings.H5_ORDER_BASE_URL or "").rstrip("/")


def _feature_disabled():
    return error_response(code=403, msg="员工小程序登录未启用")


async def _exchange_code(code: str):
    provider = get_staff_miniprogram_provider()
    if not provider.is_configured() and not staff_miniprogram_mock_allowed():
        raise ValueError("miniprogram_not_configured")
    return await provider.exchange_code(code)


async def _make_handoff_response(svc: StaffWechatAuthService, account, identity) -> dict:
    token_data = await handoff_svc.create_handoff(
        tenant_id=account.tenant_id,
        account_id=int(account.id),
        wechat_app_id=identity.app_id,
        openid=identity.openid,
    )
    role = account.role
    return {
        "ok": True,
        "handoff_token": token_data["handoff_token"],
        "expires_at": token_data["expires_at"],
        "expires_in": token_data["expires_in"],
        "h5_url": f"{_h5_base()}/staff-handoff#t={token_data['handoff_token']}",
        "role": role,
        "role_label": "服务员" if role == "waiter" else "后厨",
        "staff_name": account.name,
    }


@router.post("/staff/miniprogram/bind/preview")
@login_limit()
async def mp_bind_preview(
    body: MpBindPreviewRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if not staff_miniprogram_auth_enabled():
        return _feature_disabled()
    peek = await mp_bind.peek_mp_bind_scene(body.scene)
    if not peek:
        return error_response(code=400, msg="绑定码已失效，请让老板重新生成", data={"code": "bind_expired"})

    svc = StaffWechatAuthService(db)
    account = await svc._get_account(peek["tenant_id"], int(peek["account_id"]))
    if not account or account.status != "active":
        return error_response(code=400, msg="员工账号不可用", data={"code": "account_invalid"})
    if await svc.is_wechat_bound(tenant_id=account.tenant_id, account_id=int(account.id)):
        return error_response(
            code=400,
            msg="该员工已绑定微信，请老板先解除绑定",
            data={"code": "already_bound"},
        )
    tenant = await svc._get_tenant(account.tenant_id)
    return success_response(
        data={
            "shop_name": tenant.name if tenant else "门店",
            "staff_name": account.name,
            "role": account.role,
            "role_label": "服务员" if account.role == "waiter" else "后厨",
            "expires_at": peek.get("expires_at"),
        }
    )


@router.post("/staff/miniprogram/bind/confirm")
@login_limit()
async def mp_bind_confirm(
    body: MpBindConfirmRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if not staff_miniprogram_auth_enabled():
        return _feature_disabled()

    scene = (body.scene or "").strip()
    code = (body.code or "").strip()
    if not scene or not code:
        return error_response(code=400, msg="缺少绑定参数")

    peek = await mp_bind.peek_mp_bind_scene(scene)
    if not peek:
        return error_response(code=400, msg="绑定码已失效，请让老板重新生成", data={"code": "bind_expired"})

    try:
        identity = await _exchange_code(code)
    except ValueError as exc:
        msg = "微信登录失败，请重试"
        if str(exc) == "miniprogram_not_configured":
            msg = "员工小程序登录尚未配置"
        return error_response(code=400, msg=msg, data={"code": "code2session_failed"})

    svc = StaffWechatAuthService(db)
    bound = await svc.bind_wechat_identity(
        tenant_id=peek["tenant_id"],
        account_id=int(peek["account_id"]),
        identity=identity,
    )
    if not bound.get("ok"):
        return error_response(code=400, msg=bound.get("msg") or "绑定失败", data={"code": bound.get("code")})

    consumed = await mp_bind.consume_mp_bind_scene(scene)
    if not consumed:
        return error_response(code=400, msg="绑定码已失效，请让老板重新生成", data={"code": "bind_expired"})

    try:
        handoff = await _make_handoff_response(svc, bound["account"], identity)
    except StaffAuthStoreUnavailable as exc:
        return error_response(code=503, msg=exc.msg)
    return success_response(data=handoff, msg="绑定成功")


@router.post("/staff/miniprogram/login")
@login_limit()
async def mp_login(
    body: MpLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if not staff_miniprogram_auth_enabled():
        return _feature_disabled()
    code = (body.code or "").strip()
    if not code:
        return error_response(code=400, msg="缺少微信登录凭证")

    try:
        identity = await _exchange_code(code)
    except ValueError as exc:
        msg = "微信登录失败，请重试"
        if str(exc) == "miniprogram_not_configured":
            msg = "员工小程序登录尚未配置"
        return error_response(code=400, msg=msg, data={"code": "code2session_failed"})

    svc = StaffWechatAuthService(db)
    matches = await svc.list_active_accounts_for_openid(app_id=identity.app_id, openid=identity.openid)
    if not matches:
        # Distinguish unbound vs bound-but-disabled (do not leak openid).
        from sqlalchemy import select
        from app.models.merchant_account_wechat_binding import MerchantAccountWechatBinding

        bind_rows = (
            await db.execute(
                select(MerchantAccountWechatBinding).where(
                    MerchantAccountWechatBinding.wechat_app_id == identity.app_id,
                    MerchantAccountWechatBinding.openid == identity.openid,
                    MerchantAccountWechatBinding.revoked_at.is_(None),
                )
            )
        ).scalars().all()
        for b in bind_rows:
            acc = await svc._get_account(b.tenant_id, int(b.merchant_account_id))
            if acc and acc.status != "active":
                return error_response(code=400, msg="账号已停用", data={"code": "account_disabled"})
        return error_response(
            code=400,
            msg="当前微信尚未绑定员工身份，请让门店老板在员工管理中生成微信绑定码",
            data={"code": "not_bound"},
        )
    if len(matches) > 1:
        return success_response(
            data={
                "multiple_accounts": True,
                "accounts": [
                    {
                        "account_id": str(a.id),
                        "shop_name": t.name,
                        "staff_name": a.name,
                        "role": a.role,
                        "role_label": "服务员" if a.role == "waiter" else "后厨",
                    }
                    for a, t in matches
                ],
            },
            msg="请选择工作门店",
        )

    account, _tenant = matches[0]
    try:
        handoff = await _make_handoff_response(svc, account, identity)
    except StaffAuthStoreUnavailable as exc:
        return error_response(code=503, msg=exc.msg)
    return success_response(data=handoff, msg="登录成功")


@router.post("/staff/miniprogram/login/select")
@login_limit()
async def mp_login_select(
    body: MpLoginSelectRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if not staff_miniprogram_auth_enabled():
        return _feature_disabled()
    code = (body.code or "").strip()
    if not code or not body.account_id:
        return error_response(code=400, msg="缺少登录参数")

    try:
        identity = await _exchange_code(code)
    except ValueError:
        return error_response(code=400, msg="微信登录失败，请重试", data={"code": "code2session_failed"})

    try:
        account_id = int(body.account_id)
    except (TypeError, ValueError):
        return error_response(code=400, msg="无效的员工身份")

    svc = StaffWechatAuthService(db)
    matches = await svc.list_active_accounts_for_openid(app_id=identity.app_id, openid=identity.openid)
    chosen = [(a, t) for a, t in matches if int(a.id) == account_id]
    if not chosen:
        return error_response(code=400, msg="未找到可登录的员工身份", data={"code": "account_not_found"})

    account, _tenant = chosen[0]
    try:
        handoff = await _make_handoff_response(svc, account, identity)
    except StaffAuthStoreUnavailable as exc:
        return error_response(code=503, msg=exc.msg)
    return success_response(data=handoff, msg="登录成功")


@router.post("/login/staff/handoff")
@login_limit()
async def staff_handoff_login(
    body: StaffHandoffRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    if not staff_miniprogram_auth_enabled():
        return _feature_disabled()

    try:
        payload = await handoff_svc.consume_handoff(body.handoff_token or "")
    except StaffAuthStoreUnavailable as exc:
        return error_response(code=503, msg=exc.msg)
    if not payload:
        return error_response(code=401, msg="登录已失效，请返回微信重新进入", data={"code": "handoff_invalid"})

    wechat = StaffWechatAuthService(db)
    account = await wechat._get_account(payload["tenant_id"], int(payload["account_id"]))
    if not account or account.status != "active":
        return error_response(code=401, msg="账号已停用", data={"code": "account_disabled"})
    if account.tenant_id != payload["tenant_id"]:
        return error_response(code=401, msg="登录已失效，请返回微信重新进入")

    existing_id = existing_secret = None
    if settings.STAFF_DEVICE_COOKIE_ENABLED:
        cookie = request.cookies.get(cookie_name())
        if cookie:
            existing_id, existing_secret = decode_device_credential(cookie.strip())

    result = await StaffSessionService(db).issue_session_for_account(
        account,
        auth_method="staff_mp_handoff",
        user_agent=_ua(request),
        existing_device_id=existing_id,
        existing_secret=existing_secret,
    )
    if not result.get("ok"):
        return error_response(code=401, msg=result.get("msg") or "登录失败", data={"code": result.get("code")})

    return success_response(data=deliver_device_credential(response, result), msg="登录成功")