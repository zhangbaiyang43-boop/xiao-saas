"""Staff WeChat OAuth + bind + trusted device login APIs."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.core.merchant_auth import get_request_principal
from app.core.rate_limiter import login_limit
from app.core.response import error_response, success_response
from app.services import staff_bind_token_service as bind_tokens
from app.services.staff_bind_token_service import StaffAuthStoreUnavailable
from app.services.staff_trusted_device_service import (
    StaffTrustedDeviceService,
    decode_device_credential,
)
from app.services.staff_wechat_auth_service import StaffWechatAuthService
from app.services.staff_wechat_provider import (
    WechatIdentity,
    get_staff_wechat_provider,
    staff_wechat_config_status,
    staff_wechat_mock_allowed,
)

router = APIRouter(prefix="/api/v1", tags=["员工微信登录"])


class BindConfirmRequest(BaseModel):
    bind_token: str | None = None
    session_id: str | None = None
    code: str | None = None
    mock_openid: str | None = None


class WechatLoginRequest(BaseModel):
    code: str | None = None
    session_id: str | None = None
    account_id: str | None = None
    mock_openid: str | None = None


class DeviceLoginRequest(BaseModel):
    device_credential: str | None = None


class LogoutDeviceRequest(BaseModel):
    device_credential: str | None = None


def _frontend_base() -> str:
    return (settings.PUBLIC_BASE_URL or settings.H5_ORDER_BASE_URL or "").rstrip("/")


def _oauth_redirect_uri() -> str:
    configured = (settings.STAFF_WECHAT_OAUTH_REDIRECT_URI or "").strip()
    if configured:
        return configured
    return f"{_frontend_base().replace('/staff-bind', '')}/api/v1/staff/wechat/oauth/callback"


def _cookie_name() -> str:
    return settings.STAFF_DEVICE_COOKIE_NAME or "staff_device"


def _cookie_path() -> str:
    return settings.STAFF_DEVICE_COOKIE_PATH or "/api"


def _cookie_secure() -> bool:
    env = (settings.APP_ENV or "").strip().lower()
    return env in ("production", "prod")


def _set_device_cookie(response: Response, credential: str) -> None:
    if not settings.STAFF_DEVICE_COOKIE_ENABLED or not credential:
        return
    max_age = max(1, int(settings.STAFF_TRUST_DEVICE_DAYS or 30)) * 86400
    response.set_cookie(
        key=_cookie_name(),
        value=credential,
        max_age=max_age,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path=_cookie_path(),
    )


def _clear_device_cookie(response: Response) -> None:
    # Clear configured path; also clear legacy Path=/ from earlier builds.
    for path in {_cookie_path(), "/"}:
        response.delete_cookie(key=_cookie_name(), path=path)


def _read_device_credential(request: Request, body_cred: str | None) -> str | None:
    """Cookie mode and JS credential mode are mutually exclusive."""
    if settings.STAFF_DEVICE_COOKIE_ENABLED:
        cookie = request.cookies.get(_cookie_name())
        return cookie.strip() if cookie else None
    if body_cred:
        return body_cred.strip()
    return None


def _public_auth_payload(result: dict) -> dict:
    """Strip long-lived device secret from JSON when Cookie mode is on."""
    data = {k: v for k, v in result.items() if k != "ok"}
    if settings.STAFF_DEVICE_COOKIE_ENABLED:
        data.pop("device_credential", None)
    return data


def _deliver_device_credential(response: Response, result: dict) -> dict:
    cred = result.get("device_credential")
    if settings.STAFF_DEVICE_COOKIE_ENABLED:
        if cred:
            _set_device_cookie(response, cred)
        # Never put secret in JSON when cookie mode is configured — no silent fallback.
        return _public_auth_payload(result)
    # JS credential mode only.
    return _public_auth_payload(result)


def _ua(request: Request) -> str | None:
    return request.headers.get("user-agent")


async def _identity_from_request(
    *,
    code: str | None,
    mock_openid: str | None,
    session_id: str | None,
) -> tuple[WechatIdentity | None, dict | None, str | None]:
    """Returns (identity, oauth_session, error_msg)."""
    if session_id:
        sess = await bind_tokens.get_oauth_session(session_id)
        if not sess or not sess.get("openid"):
            return None, None, "微信登录会话已失效，请重新尝试"
        identity = WechatIdentity(
            app_id=sess["app_id"],
            openid=sess["openid"],
            unionid=sess.get("unionid"),
        )
        return identity, sess, None

    if mock_openid and staff_wechat_mock_allowed():
        provider = get_staff_wechat_provider()
        app_id = getattr(provider, "app_id", None) or settings.STAFF_WECHAT_APP_ID or "mock_staff_app"
        return WechatIdentity(app_id=app_id, openid=mock_openid.strip()), None, None

    if code:
        try:
            identity = await get_staff_wechat_provider().exchange_code(code)
            return identity, None, None
        except Exception:
            return None, None, "微信登录失败，请重新尝试"

    return None, None, "缺少微信身份凭证"


@router.get("/staff/wechat/status")
async def staff_wechat_status():
    return success_response(data=staff_wechat_config_status())


@router.get("/staff/wechat/oauth/start")
async def staff_wechat_oauth_start(
    request: Request,
    purpose: str = "login",
    t: str | None = None,
    return_url: str | None = None,
):
    purpose = (purpose or "login").strip().lower()
    if purpose not in ("login", "bind"):
        return error_response(code=400, msg="无效的 OAuth 用途")
    if purpose == "bind" and not t:
        return error_response(code=400, msg="缺少绑定码")

    provider = get_staff_wechat_provider()
    status = staff_wechat_config_status()
    if not provider.is_configured() and not status["mock_allowed"]:
        return error_response(
            code=503,
            msg="微信员工登录尚未配置",
            data=status,
        )

    state_payload = {
        "purpose": purpose,
        "bind_token": t,
        "return_url": return_url or f"{_frontend_base()}/staff-bind",
    }
    try:
        state = await bind_tokens.create_oauth_state(state_payload, ttl=300)
    except StaffAuthStoreUnavailable as exc:
        return error_response(code=503, msg=exc.msg)
    redirect_uri = _oauth_redirect_uri()
    url = provider.build_oauth_url(redirect_uri=redirect_uri, state=state, scope="snsapi_base")
    if request.query_params.get("format") == "json":
        return success_response(data={"authorize_url": url, "state": state})
    return RedirectResponse(url, status_code=302)


@router.get("/staff/wechat/oauth/callback")
async def staff_wechat_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    front = _frontend_base()

    def _fail(msg: str) -> RedirectResponse:
        return RedirectResponse(f"{front}/login?oauth=1&reason={quote(msg)}", status_code=302)

    state_data = await bind_tokens.consume_oauth_state(state or "")
    if not state_data:
        return _fail("微信登录失败，请重新尝试")

    purpose = state_data.get("purpose") or "login"

    if not code:
        return _fail("微信授权取消")

    try:
        identity = await get_staff_wechat_provider().exchange_code(code)
    except Exception:
        return _fail("微信登录失败")

    try:
        sid = await bind_tokens.create_oauth_session(
            {
                "purpose": purpose,
                "bind_token": state_data.get("bind_token"),
                "app_id": identity.app_id,
                "openid": identity.openid,
                "unionid": identity.unionid,
            },
            ttl=300,
        )
    except StaffAuthStoreUnavailable:
        return _fail("员工微信绑定服务暂不可用，请稍后重试")

    if purpose == "bind":
        target = f"{front}/staff-bind?sid={sid}&t={state_data.get('bind_token') or ''}"
        return RedirectResponse(target, status_code=302)

    target = f"{front}/login?sid={sid}&oauth=1&mode=staff"
    return RedirectResponse(target, status_code=302)


@router.get("/staff/wechat/bind/preview")
async def staff_wechat_bind_preview(t: str, db: AsyncSession = Depends(get_db)):
    result = await StaffWechatAuthService(db).preview_bind(bind_token=t)
    if not result.get("ok"):
        return error_response(code=400, msg=result.get("msg") or "绑定码无效", data=result)
    return success_response(data=result)


@router.post("/staff/wechat/bind/confirm")
@login_limit()
async def staff_wechat_bind_confirm(
    body: BindConfirmRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    bind_token = (body.bind_token or "").strip()
    identity, sess, err = await _identity_from_request(
        code=body.code, mock_openid=body.mock_openid, session_id=body.session_id
    )
    if err or not identity:
        return error_response(code=400, msg=err or "微信身份无效")
    if not bind_token and sess:
        bind_token = (sess.get("bind_token") or "").strip()
    if not bind_token:
        return error_response(code=400, msg="缺少绑定码")

    result = await StaffWechatAuthService(db).confirm_bind(
        bind_token=bind_token,
        identity=identity,
        user_agent=_ua(request),
    )
    if body.session_id:
        await bind_tokens.delete_oauth_session(body.session_id)
    if not result.get("ok"):
        return error_response(code=400, msg=result.get("msg") or "绑定失败", data={"code": result.get("code")})

    return success_response(data=_deliver_device_credential(response, result), msg="绑定成功")


@router.post("/login/staff/wechat")
@login_limit()
async def staff_wechat_login(
    body: WechatLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    identity, sess, err = await _identity_from_request(
        code=body.code, mock_openid=body.mock_openid, session_id=body.session_id
    )
    if err or not identity:
        return error_response(code=400, msg=err or "微信身份无效")

    account_id = int(body.account_id) if body.account_id else None
    result = await StaffWechatAuthService(db).login_with_identity(
        identity=identity,
        account_id=account_id,
        user_agent=_ua(request),
    )
    if body.session_id:
        await bind_tokens.delete_oauth_session(body.session_id)

    if result.get("code") == "multiple_accounts":
        return success_response(
            data={
                "multiple_accounts": True,
                "accounts": result.get("accounts") or [],
                "session_id": body.session_id,
            },
            msg=result.get("msg") or "请选择工作门店",
        )
    if not result.get("ok"):
        return error_response(code=400, msg=result.get("msg") or "微信登录失败", data={"code": result.get("code")})

    return success_response(data=_deliver_device_credential(response, result), msg="登录成功")


@router.post("/login/staff/device")
@login_limit()
async def staff_device_login(
    body: DeviceLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    # Cookie mode ignores body credential (mutual exclusion).
    body_cred = None if settings.STAFF_DEVICE_COOKIE_ENABLED else body.device_credential
    cred = _read_device_credential(request, body_cred)
    device_id, secret = decode_device_credential(cred)
    if not device_id or not secret:
        return error_response(code=401, msg="设备登录已失效，请重新登录")

    result = await StaffWechatAuthService(db).refresh_device(
        device_id=device_id, secret=secret, user_agent=_ua(request)
    )
    if not result.get("ok"):
        _clear_device_cookie(response)
        return error_response(code=401, msg=result.get("msg") or "设备登录已失效")

    return success_response(data=_deliver_device_credential(response, result), msg="登录成功")


@router.post("/login/staff/logout-device")
async def staff_logout_device(
    body: LogoutDeviceRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    principal = get_request_principal(request)
    body_cred = None if settings.STAFF_DEVICE_COOKIE_ENABLED else body.device_credential
    cred = _read_device_credential(request, body_cred)
    device_id, _secret = decode_device_credential(cred)
    _clear_device_cookie(response)

    if principal and principal.account_id and device_id:
        await StaffTrustedDeviceService(db).revoke_device(
            tenant_id=principal.tenant_id,
            account_id=int(principal.account_id),
            device_id=device_id,
        )
    return success_response(msg="已退出此设备")
