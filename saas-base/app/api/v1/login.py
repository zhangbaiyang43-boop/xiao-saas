from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.core.logger import logger
from app.core.rate_limiter import login_limit, public_limit
from app.core.response import RespVo, error_response, success_response
from app.core.permissions import ROLE_OWNER, permission_list
from app.core.security import create_access_token
from app.schemas.tenant import LoginRequest, RegisterCodeRequest, RegisterRequest, normalize_phone
from app.services.merchant_provisioning_service import (
    MerchantProvisioningService,
    PhoneAlreadyRegisteredError,
    ProvisioningSource,
)
from app.services.tencent_sms_service import SmsPurpose, TencentSmsService
from app.services.tenant_service import TenantService

router = APIRouter(prefix="/api/v1", tags=["认证"])

ACCOUNT_NOT_FOUND_MSG = "账号不存在，请联系服务商：15936889988"


class LoginCodeRequest(BaseModel):
    phone: str = Field(..., description="手机号")

    @field_validator("phone")
    @classmethod
    def phone_format(cls, value):
        return normalize_phone(value)


def serialize_tenant_session(tenant, token: str | None = None) -> dict:
    data = {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "phone": tenant.phone,
        "role": ROLE_OWNER,
        "account_id": None,
        "permissions": permission_list(ROLE_OWNER),
        "home_path": "/",
    }
    if token:
        data.update({"token": token, "token_type": "bearer"})
    return data


@router.post("/login/code", response_model=RespVo)
@login_limit()
async def send_login_code(request: Request, data: LoginCodeRequest, db: AsyncSession = Depends(get_db)):
    service = TenantService(db)
    tenant = await service.get_tenant_by_phone(data.phone)

    if not tenant:
        return error_response(code=404, msg=ACCOUNT_NOT_FOUND_MSG)
    if not tenant.status:
        return error_response(code=403, msg="商家账号已停用")

    ok, msg, payload = await TencentSmsService().request_login_code(data.phone)
    if not ok:
        return error_response(code=400, msg=msg, data=payload or None)
    return success_response(data=payload, msg=msg)


@router.post("/login", response_model=RespVo)
@login_limit()
async def login(request: Request, data: LoginRequest, db: AsyncSession = Depends(get_db)):
    service = TenantService(db)
    tenant = await service.get_tenant_by_phone(data.phone)

    if not tenant:
        return error_response(code=404, msg=ACCOUNT_NOT_FOUND_MSG)
    if not tenant.status:
        return error_response(code=403, msg="商家账号已停用")
    if not await TencentSmsService().verify_login_code(data.phone, data.code):
        return error_response(code=400, msg="验证码错误或已过期")

    token = create_access_token(tenant.tenant_id, role=ROLE_OWNER)
    return success_response(data=serialize_tenant_session(tenant, token), msg="登录成功")


@router.post("/register/code", response_model=RespVo)
@public_limit()
async def send_register_code(request: Request, data: RegisterCodeRequest, db: AsyncSession = Depends(get_db)):
    expected_key = settings.PLATFORM_REGISTER_KEY
    if not expected_key or data.platform_key != expected_key:
        return error_response(code=403, msg="注册暂未开放，请联系平台开通")

    service = TenantService(db)
    existing = await service.get_tenant_by_phone(data.phone)
    if existing:
        return error_response(code=400, msg="手机号已注册，请直接登录")

    ok, msg, payload = await TencentSmsService().request_login_code(data.phone, purpose=SmsPurpose.REGISTER)
    if not ok:
        return error_response(code=400, msg=msg, data=payload or None)
    return success_response(data=payload, msg=msg)


@router.post("/register", response_model=RespVo)
@public_limit()
async def register(request: Request, data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    expected_key = settings.PLATFORM_REGISTER_KEY
    if not expected_key or data.platform_key != expected_key:
        return error_response(code=403, msg="注册暂未开放，请联系平台开通")

    # Registration must prove phone ownership the same way login does --
    # a REGISTER-purpose code, never a LOGIN one (SmsPurpose keeps the two
    # namespaces disjoint, so a login code cannot be replayed here).
    if not await TencentSmsService().verify_login_code(data.phone, data.code, purpose=SmsPurpose.REGISTER):
        return error_response(code=400, msg="验证码错误或已过期")

    # MerchantProvisioningService owns the whole Tenant + TenantConfig + trial
    # Subscription transaction, including the commit -- this router no longer
    # orchestrates multiple domain services or manages the transaction itself.
    try:
        result = await MerchantProvisioningService(db).provision_merchant(
            name=data.name,
            phone=data.phone,
            source=ProvisioningSource.SELF_REGISTER,
            address=data.address,
            logo_url=data.logo_url,
        )
    except PhoneAlreadyRegisteredError:
        return error_response(code=400, msg="手机号已注册，请直接登录")
    except Exception:
        logger.error(f"registration provisioning failed, phone={data.phone}")
        return error_response(code=500, msg="注册失败，请稍后重试")

    tenant = result.tenant
    token = create_access_token(tenant.tenant_id, role=ROLE_OWNER)
    return success_response(data=serialize_tenant_session(tenant, token), msg="注册成功")