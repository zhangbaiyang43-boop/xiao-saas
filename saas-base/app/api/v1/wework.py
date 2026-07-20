from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import build_page, normalize_pagination
from app.core.rate_limiter import tenant_limit
from app.core.response import RespVo, error_response, success_response
from app.services.wework_callback_service import WeworkCallbackService
from app.services.wework_service import WeworkService

router = APIRouter(prefix="/api/v1/wework", tags=["企业微信"])


class ContactWayRequest(BaseModel):
    userid: str | None = None
    scene: str | None = "member_entry"
    remark: str | None = "会员运营二维码"
    skip_verify: bool = True


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
