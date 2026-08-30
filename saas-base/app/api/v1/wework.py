from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import build_page, normalize_pagination
from app.core.rate_limiter import tenant_limit
from app.core.response import RespVo, error_response, success_response
from app.api.v1.super_admin import _verify_super_token
from app.schemas.tenant import normalize_phone
from app.services.wework_binding_service import WeworkBindingError, WeworkBindingService
from app.services.wework_callback_service import WeworkCallbackService
from app.services.wework_service import WeworkService

router = APIRouter(prefix="/api/v1/wework", tags=["企业微信"])


class ContactWayRequest(BaseModel):
    userid: str | None = None
    scene: str | None = "member_entry"
    remark: str | None = "会员运营二维码"
    skip_verify: bool = True


class BindingTokenRequest(BaseModel):
    wework_event_log_id: int = Field(..., description="可信企业微信事件日志 ID")


class BindingCodeRequest(BaseModel):
    binding_token: str = Field(..., min_length=20, description="一次性绑定 token")
    phone: str = Field(..., description="商户老板手机号")

    @field_validator("phone")
    @classmethod
    def phone_format(cls, value):
        return normalize_phone(value)


class BindingConfirmRequest(BindingCodeRequest):
    otp_code: str = Field(..., min_length=4, max_length=8, description="绑定验证码")


def _binding_error_response(exc: WeworkBindingError):
    return error_response(code=400, msg=exc.message, data={"error_code": exc.code})


def _require_wework_super_token(x_super_token: str | None = Header(None, alias="X-Super-Token")) -> str:
    if not x_super_token:
        raise HTTPException(status_code=401, detail="中控台鉴权失败")
    return _verify_super_token(x_super_token)


@router.get("/config/status", response_model=RespVo)
@tenant_limit()
async def config_status(request: Request):
    return success_response(data=WeworkService().config_status(), msg="ok")


@router.post("/access-token/test", response_model=RespVo)
@tenant_limit()
async def test_access_token(request: Request):
    try:
        return success_response(data=WeworkService().test_connection(), msg="企业微信连接成功")
    except RuntimeError as exc:
        return error_response(code=400, msg=str(exc))


@router.post("/contact-way", response_model=RespVo)
@tenant_limit()
async def create_contact_way(
    payload: ContactWayRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await WeworkService().create_contact_way(
            db,
            tenant_id=request.state.tenant_id,
            userid=payload.userid,
            scene=payload.scene,
            remark=payload.remark,
            skip_verify=payload.skip_verify,
        )
        return success_response(data=data, msg="企微二维码生成成功")
    except RuntimeError as exc:
        return error_response(code=400, msg=str(exc))


@router.get("/contact-way", response_model=RespVo)
@tenant_limit()
async def list_contact_ways(
    request: Request,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    skip, limit = normalize_pagination(skip, min(limit, 20))
    items, total = await WeworkService().list_contact_ways(db, request.state.tenant_id, skip, limit)
    return success_response(data=build_page(items, total, skip, limit), msg="ok")


@router.post("/bindings/tokens", response_model=RespVo)
@tenant_limit()
async def create_binding_token(
    payload: BindingTokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: str = Depends(_require_wework_super_token),
):
    del request
    del actor
    try:
        issue = await WeworkBindingService(db).create_binding_token(
            source_event_id=payload.wework_event_log_id,
        )
        return success_response(
            data={
                "binding_token": issue.token,
                "expires_at": issue.expires_at,
                "source_event_id": str(issue.source_event_id),
            },
            msg="绑定入口已生成",
        )
    except WeworkBindingError as exc:
        return _binding_error_response(exc)


@router.post("/bindings/code", response_model=RespVo)
@tenant_limit()
async def send_binding_code(
    payload: BindingCodeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    del request
    try:
        ok, msg, data = await WeworkBindingService(db).send_binding_code(
            binding_token=payload.binding_token,
            phone=payload.phone,
        )
        if not ok:
            return error_response(code=400, msg=msg, data=data or None)
        return success_response(data=data, msg=msg)
    except WeworkBindingError as exc:
        return _binding_error_response(exc)
    except ValueError:
        return error_response(code=400, msg="手机号格式不正确")


@router.post("/bindings/confirm", response_model=RespVo)
@tenant_limit()
async def confirm_binding(
    payload: BindingConfirmRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    del request
    try:
        data = await WeworkBindingService(db).confirm_binding(
            binding_token=payload.binding_token,
            phone=payload.phone,
            otp_code=payload.otp_code,
        )
        return success_response(data=data, msg="绑定成功")
    except WeworkBindingError as exc:
        return _binding_error_response(exc)
    except ValueError:
        return error_response(code=400, msg="手机号格式不正确")


@router.get("/callback")
async def verify_callback_url(
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
):
    try:
        plaintext = WeworkCallbackService().verify_url(msg_signature, timestamp, nonce, echostr)
        return PlainTextResponse(str(plaintext))
    except RuntimeError as exc:
        return PlainTextResponse(str(exc), status_code=400)


@router.post("/callback")
async def receive_callback_event(
    request: Request,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    try:
        await WeworkCallbackService(db).handle_event(msg_signature, timestamp, nonce, body)
        return PlainTextResponse("success")
    except RuntimeError as exc:
        return PlainTextResponse(str(exc), status_code=400)


@router.get("/events", response_model=RespVo)
@tenant_limit()
async def list_wework_events(
    request: Request,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    skip, limit = normalize_pagination(skip, min(limit, 20))
    items, total = await WeworkCallbackService(db).list_events(skip, limit, request.state.tenant_id)
    return success_response(data=build_page(items, total, skip, limit), msg="ok")
