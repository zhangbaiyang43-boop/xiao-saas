"""Neutral staff session HTTP APIs: device restore + logout.

Paths must stay stable for admin-h5:
  POST /api/v1/login/staff/device
  POST /api/v1/login/staff/logout-device
"""

# NOTE: Do NOT use `from __future__ import annotations` here.
# FastAPI + Pydantic must resolve endpoint body models at route-registration time.

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.core.merchant_auth import get_request_principal
from app.core.rate_limiter import login_limit
from app.core.response import error_response, success_response
from app.services.staff_session_cookie import (
    clear_device_cookie,
    deliver_device_credential,
    read_device_credential,
)
from app.services.staff_session_service import StaffSessionService
from app.services.staff_trusted_device_service import (
    StaffTrustedDeviceService,
    decode_device_credential,
)

router = APIRouter(prefix="/api/v1", tags=["员工会话"])


class DeviceLoginRequest(BaseModel):
    device_credential: str | None = None


class LogoutDeviceRequest(BaseModel):
    device_credential: str | None = None


def _ua(request: Request) -> str | None:
    return request.headers.get("user-agent")


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
    cred = read_device_credential(request, body_cred)
    device_id, secret = decode_device_credential(cred)
    if not device_id or not secret:
        return error_response(code=401, msg="设备登录已失效，请重新登录")

    result = await StaffSessionService(db).refresh_device(
        device_id=device_id, secret=secret, user_agent=_ua(request)
    )
    if not result.get("ok"):
        clear_device_cookie(response)
        return error_response(code=401, msg=result.get("msg") or "设备登录已失效")

    return success_response(data=deliver_device_credential(response, result), msg="登录成功")


@router.post("/login/staff/logout-device")
async def staff_logout_device(
    body: LogoutDeviceRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    principal = get_request_principal(request)
    body_cred = None if settings.STAFF_DEVICE_COOKIE_ENABLED else body.device_credential
    cred = read_device_credential(request, body_cred)
    device_id, _secret = decode_device_credential(cred)
    clear_device_cookie(response)

    if principal and principal.account_id and device_id:
        await StaffTrustedDeviceService(db).revoke_device(
            tenant_id=principal.tenant_id,
            account_id=int(principal.account_id),
            device_id=device_id,
        )
    return success_response(msg="已退出此设备")
