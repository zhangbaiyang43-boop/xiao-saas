import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.lock import redis_lock
from app.core.response import RespVo, error_response, success_response
from app.core.tenant_context import TenantContext
from app.services.anti_fraud_service import AntiFraudService
from app.services.tenant_service import TenantService
from app.services.verify_service import VerifyService

POS_VERIFY_PATH = "/api/v1/open/pos/verify"
POS_API_KEY_FIELD = "pos_api_key"

router = APIRouter(prefix="/api/v1", tags=["pos"])


class PosVerifyRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=64)
    api_key: str = Field(..., min_length=8, max_length=128)
    code: str = Field(..., min_length=1, max_length=1024)
    device_id: Optional[str] = Field(default=None, max_length=64)
    request_id: Optional[str] = Field(default=None, max_length=64)


def generate_pos_api_key() -> str:
    return secrets.token_urlsafe(24)


def mask_api_key(api_key: str) -> str:
    value = api_key or ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def build_pos_config_payload(tenant_id: str, api_key: str, base_url: str) -> dict:
    normalized_base = (base_url or "").rstrip("/")
    verify_url = f"{normalized_base}{POS_VERIFY_PATH}"
    return {
        "tenant_id": tenant_id,
        "api_key": api_key,
        "masked_api_key": mask_api_key(api_key),
        "verify_url": verify_url,
        "example": {
            "tenant_id": tenant_id,
            "api_key": api_key,
            "code": "顾客优惠券核销码",
            "device_id": "cashier-01",
        },
    }


def get_public_base_url(request: Request) -> str:
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    if host:
        return f"{proto}://{host}"
    return str(request.base_url)


def _business_info_with_api_key(config) -> tuple[dict, str]:
    business_info = dict(getattr(config, "business_info", None) or {})
    api_key = business_info.get(POS_API_KEY_FIELD)
    if not api_key:
        api_key = generate_pos_api_key()
        business_info[POS_API_KEY_FIELD] = api_key
    return business_info, api_key


async def _get_current_tenant_config(db: AsyncSession):
    tenant_id = TenantContext.get_current_tenant_id()
    if not tenant_id:
        return None, None, None, error_response(code=401, msg="缺少登录租户")

    service = TenantService(db)
    tenant = await service.get_tenant(tenant_id)
    if not tenant:
        return tenant_id, None, None, error_response(code=404, msg="商家不存在")

    config = await service.ensure_tenant_config(tenant_id)
    return tenant_id, tenant, config, None


@router.get("/pos/config", response_model=RespVo)
async def get_pos_config(request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id, _tenant, config, error = await _get_current_tenant_config(db)
    if error:
        return error

    business_info, api_key = _business_info_with_api_key(config)
    config.business_info = business_info
    await db.commit()
    await db.refresh(config)

    return success_response(
        data=build_pos_config_payload(tenant_id, api_key, get_public_base_url(request)),
        msg="收银系统 API 核销配置已生成",
    )


@router.post("/pos/api-key/reset", response_model=RespVo)
async def reset_pos_api_key(request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id, _tenant, config, error = await _get_current_tenant_config(db)
    if error:
        return error

    business_info = dict(config.business_info or {})
    api_key = generate_pos_api_key()
    business_info[POS_API_KEY_FIELD] = api_key
    config.business_info = business_info
    await db.commit()
    await db.refresh(config)

    return success_response(
        data=build_pos_config_payload(tenant_id, api_key, get_public_base_url(request)),
        msg="收银系统 API Key 已重置",
    )


@router.post("/open/pos/verify", response_model=RespVo)
async def open_pos_verify(data: PosVerifyRequest, request: Request, db: AsyncSession = Depends(get_db)):
    service = TenantService(db)
    tenant = await service.get_tenant(data.tenant_id)
    if not tenant:
        return error_response(code=404, msg="商家不存在")

    config = await service.ensure_tenant_config(data.tenant_id)
    business_info, saved_api_key = _business_info_with_api_key(config)
    if not saved_api_key or data.api_key != saved_api_key:
        return error_response(code=401, msg="收银系统 API Key 无效")

    if business_info != (config.business_info or {}):
        config.business_info = business_info
        await db.commit()

    TenantContext.set_tenant_id(data.tenant_id)
    verify_service = VerifyService(db)
    verify_service.set_tenant_id(data.tenant_id)
    lock_key = f"pos_verify:{data.tenant_id}:{data.code.strip().upper()}"
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
    if not await AntiFraudService.allow_frequency(
        "pos_verify",
        f"{data.tenant_id}:{data.device_id or ip}",
        {"tenant_id": data.tenant_id, "device_id": data.device_id, "ip": ip, "request_id": data.request_id},
    ):
        return error_response(code=429, msg="收银系统核销过于频繁，请稍后再试")

    async def do_verify():
        result = await verify_service.verify_coupon_with_result(data.code)
        if not result["success"]:
            return error_response(
                code=400,
                msg=result["message"],
                data={
                    "reason": result["reason"],
                    "coupon": result["coupon"],
                    "request_id": data.request_id,
                    "device_id": data.device_id,
                },
            )
        return success_response(
            data={
                "coupon": result["coupon"],
                "request_id": data.request_id,
                "device_id": data.device_id,
                "verified_at": datetime.utcnow().isoformat(),
            },
            msg="核销成功",
        )

    try:
        async with redis_lock(lock_key, timeout=10) as acquired:
            if not acquired:
                return error_response(code=400, msg="操作过于频繁，请稍后再试")
            return await do_verify()
    except RuntimeError:
        return await do_verify()
