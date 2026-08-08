"""Staff WeChat OAuth + bind + trusted device login APIs."""

# NOTE: Do NOT use `from __future__ import annotations` here.
# FastAPI + Pydantic must resolve endpoint body models (e.g. BindConfirmRequest)
# at route-registration time; postponed annotations break uvicorn import on prod.

from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.core.rate_limiter import login_limit
from app.core.response import error_response, success_response
from app.services import staff_bind_token_service as bind_tokens
from app.services.staff_bind_token_service import StaffAuthStoreUnavailable
from app.services.staff_session_cookie import deliver_device_credential
from app.services.staff_wechat_auth_service import StaffWechatAuthService
from app.services.staff_miniprogram_provider import staff_official_account_oauth_enabled
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


def _frontend_base() -> str:
    return (settings.PUBLIC_BASE_URL or settings.H5_ORDER_BASE_URL or "").rstrip("/")


def _oauth_redirect_uri() -> str:
    configured = (settings.STAFF_WECHAT_OAUTH_REDIRECT_URI or "").strip()
    if configured:
        return configured
    return f"{_frontend_base().replace('/staff-bind', '')}/api/v1/staff/wechat/oauth/callback"


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
    from app.services.staff_miniprogram_provider import staff_miniprogram_auth_enabled

    status = staff_wechat_config_status()
    status["official_account_oauth_enabled"] = staff_official_account_oauth_enabled()
    status["miniprogram_auth_enabled"] = staff_miniprogram_auth_enabled()
    status["primary_provider"] = (
        "official_account_oauth" if staff_official_account_oauth_enabled() else "miniprogram"
    )
    return success_response(data=status)


def _oa_oauth_disabled():
    return error_response(
        code=403,
        msg="公众号员工登录已停用，请从「开心点单」小程序进入员工工作台",
        data={"code": "official_account_oauth_disabled"},
    )


@router.get("/staff/wechat/oauth/start")
async def staff_wechat_oauth_start(
    request: Request,
    purpose: str = "login",
    t: str | None = None,
    return_url: str | None = None,
):
    if not staff_official_account_oauth_enabled():
        return _oa_oauth_disabled()
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
    if not staff_official_account_oauth_enabled():
        return _oa_oauth_disabled()
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
    if not staff_official_account_oauth_enabled():
        return _oa_oauth_disabled()
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
    if not staff_official_account_oauth_enabled():
        return _oa_oauth_disabled()
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

    return success_response(data=deliver_device_credential(response, result), msg="绑定成功")


@router.post("/login/staff/wechat")
@login_limit()
async def staff_wechat_login(
    body: WechatLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    if not staff_official_account_oauth_enabled():
        return _oa_oauth_disabled()
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

    return success_response(data=deliver_device_credential(response, result), msg="登录成功")
