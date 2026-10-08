import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, TypeAlias

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.core.crypto import (
    SecretEncryptionUnavailable,
    decrypt_secret,
    encrypt_secret_strict,
)
from app.core.database import get_db
from app.core.logger import logger
from app.core.rate_limiter import login_limit
from app.core.response import RespVo, error_response, success_response
from app.models.order import Order
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.services.fulfilment_mode import (
    FULFILMENT_MODE_KEY,
    FULFILMENT_MODES,
    fulfilment_mode_from_business_info,
)
from app.services.merchant_provisioning_service import (
    MerchantProvisioningService,
    PhoneAlreadyRegisteredError,
    ProvisioningSource,
)

router = APIRouter(prefix="/api/super", tags=["平台中控台"])
ApiResponse: TypeAlias = RespVo[Any]

SUPER_TOKEN_EXPIRE_HOURS = 12


class SuperLoginRequest(BaseModel):
    password: str
    totp_code: str | None = None


class CreateMerchantRequest(BaseModel):
    name: str
    phone: str
    initial_code: str = "123456"


class CopyWxPayRequest(BaseModel):
    source_tenant_id: str
    totp_code: str | None = None


class StepUpRequest(BaseModel):
    totp_code: str | None = None
    reason: str | None = None
    confirmed: bool = False
    emergency_password: str | None = None
    emergency_confirmation: str | None = None


class WxPayConfigRequest(BaseModel):
    wx_mchid: str | None = None
    wx_api_key_v3: str | None = None
    wx_cert_serial: str | None = None
    wx_private_key: str | None = None
    wx_public_key_id: str | None = None
    wx_public_key: str | None = None
    wx_pay_enabled: bool | None = None
    receiver_name: str | None = None
    receiver_type: str | None = None
    totp_code: str | None = None
    reason: str | None = None
    confirmed: bool = False


class FulfilmentModeUpdateRequest(BaseModel):
    mode: str
    reason: str


def _totp_configured() -> bool:
    return bool((settings.SUPER_ADMIN_TOTP_SECRET or "").strip())


def _verify_totp_code(code: str | None) -> bool:
    """未配置动态口令时直接放行（还没走完 P2 设置流程，不阻塞现有使用）。"""
    if not _totp_configured():
        return True
    if not code:
        return False
    import pyotp
    totp = pyotp.TOTP(settings.SUPER_ADMIN_TOTP_SECRET.strip())
    return totp.verify(code.strip(), valid_window=1)


def _audit(action: str, request: Request | None, tenant_id: str = "", detail: str = "") -> None:
    """最基础的操作审计：谁（IP）在什么时候对哪个商户做了什么。没有独立操作人身份，
    只能定位到 IP，但至少留下痕迹，比现在完全没有日志强。"""
    ip = "unknown"
    if request is not None:
        ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (request.client.host if request.client else "unknown")
    logger.info(f"[SUPER_AUDIT] action={action} tenant={tenant_id or '-'} ip={ip} detail={detail}")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or "unknown"


def _request_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def _wxpay_error(request: Request, status_code: int, reason_code: str, msg: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_response(
            code=status_code,
            msg=msg,
            data={"reason_code": reason_code, "request_id": _request_id(request)},
        ).model_dump(),
    )


def _step_up_error(request: Request, data: StepUpRequest | WxPayConfigRequest) -> JSONResponse | None:
    if not _totp_configured():
        return _wxpay_error(request, 503, "WXPAY_STEP_UP_UNAVAILABLE", "动态口令未配置，危险操作已拒绝")
    reason = (data.reason or "").strip()
    if not data.totp_code or not reason or not data.confirmed:
        return _wxpay_error(request, 400, "WXPAY_STEP_UP_REQUIRED", "需要动态口令、操作原因和明确确认")
    if len(reason) > 200:
        return _wxpay_error(request, 400, "WXPAY_STEP_UP_REQUIRED", "操作原因不能超过200个字符")
    if not _verify_totp_code(data.totp_code):
        return _wxpay_error(request, 401, "WXPAY_STEP_UP_INVALID", "动态口令错误或已过期")
    return None


def _audit_wxpay(
    operation: str,
    request: Request,
    *,
    tenant_id: str,
    operator_id: str,
    reason: str,
    result: str,
    changed_field_names: list[str] | None = None,
    verification_invalidated: bool = False,
    emergency_pause: bool = False,
    source_tenant_id: str | None = None,
) -> None:
    safe_reason = " ".join(reason.split())[:200]
    logger.info(
        "WXPAY_SECURITY_OPERATION",
        extra={
            "event": "WXPAY_SECURITY_OPERATION",
            "operation": operation,
            "operator_id": operator_id or "super_admin",
            "tenant_id": tenant_id,
            "source_tenant_id": source_tenant_id,
            "request_id": _request_id(request),
            "reason": safe_reason,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "changed_field_names": sorted(changed_field_names or []),
            "verification_invalidated": verification_invalidated,
            "emergency_pause": emergency_pause,
            "ip": _request_ip(request),
        },
    )


def _verify_super_token(x_super_token: str = Header(..., alias="X-Super-Token")) -> str:
    import jwt
    try:
        payload = jwt.decode(x_super_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "super_admin":
            raise ValueError
        return payload.get("sub", "")
    except Exception:
        raise HTTPException(status_code=401, detail="中控台鉴权失败")


def _verify_payment_readiness_super_token(
    x_super_token: str | None = Header(default=None, alias="X-Super-Token"),
) -> str:
    """Keep legacy Super auth intact while owning this endpoint's 401/403 contract."""
    import jwt

    if not x_super_token or not x_super_token.strip():
        raise HTTPException(status_code=401, detail="中控台鉴权失败")
    try:
        payload = jwt.decode(
            x_super_token.strip(),
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="中控台鉴权失败") from exc
    if payload.get("type") != "super_admin":
        raise HTTPException(status_code=403, detail="无权查看收款体检")
    return _verify_super_token(x_super_token.strip())


def _verify_fulfilment_super_token(
    x_super_token: str | None = Header(default=None, alias="X-Super-Token"),
) -> str:
    """Fulfilment control owns its explicit 401/403 contract without changing other Super APIs."""
    import jwt

    if not x_super_token or not x_super_token.strip():
        raise HTTPException(status_code=401, detail="中控台鉴权失败")
    try:
        payload = jwt.decode(
            x_super_token.strip(),
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="中控台鉴权失败") from exc
    if payload.get("type") != "super_admin":
        raise HTTPException(status_code=403, detail="无权修改接单方式")
    return payload.get("sub", "")


def _mask_mchid(mchid: str | None) -> str:
    value = (mchid or "").strip()
    if len(value) <= 6:
        return value or "-"
    return f"{value[:3]}****{value[-3:]}"


def _receiver_type_label(receiver_type: str | None) -> str:
    return {"enterprise": "企业", "individual": "个体"}.get(receiver_type or "", "企业")


def _payment_status(tenant: Tenant) -> str:
    if not getattr(tenant, "wx_mchid", None):
        return "unconfigured"
    if not getattr(tenant, "wx_pay_enabled", False):
        return "paused"
    if getattr(tenant, "receiver_verified", False):
        return "verified"
    return "pending"


def _payment_view(tenant: Tenant) -> dict:
    receiver_name = getattr(tenant, "receiver_name", None) or tenant.name
    receiver_type = getattr(tenant, "receiver_type", None) or "enterprise"
    verified_time = getattr(tenant, "verified_time", None)
    return {
        "receiver_name": receiver_name,
        "receiver_type": receiver_type,
        "receiver_type_label": _receiver_type_label(receiver_type),
        "receiver_verified": bool(getattr(tenant, "receiver_verified", False)),
        "payment_locked": bool(getattr(tenant, "payment_locked", True)),
        "verified_time": verified_time.strftime("%Y-%m-%d %H:%M") if verified_time else "",
        "payment_status": _payment_status(tenant),
        "wx_mchid_masked": _mask_mchid(getattr(tenant, "wx_mchid", "")),
    }


def _validate_wxpay_client(tenant: Tenant) -> tuple[bool, str]:
    import re
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend

    api_key_v3 = decrypt_secret(tenant.wx_api_key_v3)
    private_key_pem = decrypt_secret(tenant.wx_private_key)

    if not tenant.wx_mchid:
        return False, "WXPAY_CONFIG_MCHID_REQUIRED"
    if not re.match(r"^\d{10,15}$", tenant.wx_mchid):
        return False, "WXPAY_CONFIG_MCHID_INVALID"

    if not api_key_v3:
        return False, "WXPAY_CONFIG_API_KEY_REQUIRED"
    if len(api_key_v3) != 32:
        return False, "WXPAY_CONFIG_API_KEY_INVALID"

    if not tenant.wx_cert_serial:
        return False, "WXPAY_CONFIG_CERT_SERIAL_REQUIRED"
    if not re.match(r"^[A-Fa-f0-9]{40,64}$", tenant.wx_cert_serial):
        return False, "WXPAY_CONFIG_CERT_SERIAL_INVALID"

    if not private_key_pem:
        return False, "WXPAY_CONFIG_PRIVATE_KEY_REQUIRED"
    try:
        private_key = private_key_pem.replace("\\n", "\n")
        serialization.load_pem_private_key(private_key.encode(), password=None, backend=default_backend())
    except Exception:
        return False, "WXPAY_CONFIG_PRIVATE_KEY_INVALID"

    if tenant.wx_public_key_id and tenant.wx_public_key:
        try:
            public_key = tenant.wx_public_key.replace("\\n", "\n")
            serialization.load_pem_public_key(public_key.encode(), backend=default_backend())
        except Exception:
            return False, "WXPAY_CONFIG_PUBLIC_KEY_INVALID"
    elif not tenant.wx_public_key_id and not tenant.wx_public_key:
        pass
    else:
        return False, "WXPAY_CONFIG_PUBLIC_KEY_PAIR_REQUIRED"

    try:
        from app.services.wxpay_service import _build_client
        client = _build_client(
            mchid=tenant.wx_mchid,
            api_key_v3=api_key_v3,
            cert_serial=tenant.wx_cert_serial,
            private_key_pem=private_key_pem,
            public_key_id=tenant.wx_public_key_id,
            public_key_pem=tenant.wx_public_key,
        )
        if not client:
            return False, "WXPAY_SDK_INIT_FAILED"
        for method_name in ("certificates", "get_certificates"):
            method = getattr(client, method_name, None)
            if callable(method):
                code, body = method()
                if int(code) in (200, 204):
                    return True, "OK"
                return False, "WXPAY_VERIFICATION_FAILED"
        return True, "OK"
    except Exception:
        return False, "WXPAY_VERIFICATION_FAILED"


@router.post("/login", response_model=RespVo)
@login_limit()
async def super_login(request: Request, data: SuperLoginRequest):
    if not settings.SUPER_ADMIN_PASSWORD:
        return error_response(code=403, msg="中控台未启用，请先配置 SUPER_ADMIN_PASSWORD")
    if data.password != settings.SUPER_ADMIN_PASSWORD:
        _audit("login_failed", request, detail="密码错误")
        return error_response(code=401, msg="密码错误")

    if _totp_configured():
        if not data.totp_code:
            return error_response(code=401, msg="请输入动态口令", data={"require_totp": True})
        if not _verify_totp_code(data.totp_code):
            _audit("login_failed", request, detail="动态口令错误")
            return error_response(code=401, msg="动态口令错误或已过期", data={"require_totp": True})

    import jwt
    expire = datetime.now(timezone.utc) + timedelta(hours=SUPER_TOKEN_EXPIRE_HOURS)
    token = jwt.encode(
        {"sub": "super_admin", "type": "super_admin", "exp": expire},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    _audit("login_success", request)
    return success_response(data={"token": token, "expires_in": SUPER_TOKEN_EXPIRE_HOURS * 3600, "totp_enabled": _totp_configured()}, msg="登录成功")


@router.get("/merchants", response_model=RespVo, dependencies=[Depends(_verify_super_token)])
async def list_merchants(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    tenants = result.scalars().all()

    tz8 = timezone(timedelta(hours=8))
    today = datetime.now(tz8).date()
    today_start = datetime(today.year, today.month, today.day, tzinfo=tz8).astimezone(timezone.utc).replace(tzinfo=None)

    order_result = await db.execute(
        select(Order.tenant_id, func.count(Order.id).label("cnt"))
        .where(Order.created_at >= today_start)
        .group_by(Order.tenant_id)
    )
    today_orders = {row.tenant_id: row.cnt for row in order_result}

    config_result = await db.execute(
        select(TenantConfig.tenant_id, TenantConfig.business_info)
    )
    fulfilment_modes = {
        row.tenant_id: fulfilment_mode_from_business_info(row.business_info)
        for row in config_result
    }

    data = []
    for t in tenants:
        data.append({
            "id": str(t.id),
            "tenant_id": t.tenant_id,
            "name": t.name,
            "phone": t.phone or "",
            "status": t.status,
            "today_orders": today_orders.get(t.tenant_id, 0),
            "fulfilment_mode": fulfilment_modes.get(t.tenant_id, "WORKBENCH"),
            "wx_pay_enabled": getattr(t, "wx_pay_enabled", False) or False,
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
            **_payment_view(t),
        })
    return success_response(data=data, msg="ok")


@router.patch("/merchants/{tenant_id}/fulfilment-mode", response_model=RespVo)
async def update_merchant_fulfilment_mode(
    tenant_id: str,
    data: FulfilmentModeUpdateRequest,
    request: Request,
    operator: str = Depends(_verify_fulfilment_super_token),
    db: AsyncSession = Depends(get_db),
):
    mode = data.mode.strip()
    reason = " ".join(data.reason.split())
    if mode not in FULFILMENT_MODES:
        return error_response(code=400, msg="不支持的接单方式")
    if not reason:
        return error_response(code=400, msg="请填写调整原因")
    if len(reason) > 200:
        return error_response(code=400, msg="调整原因不能超过200个字符")

    tenant = await db.scalar(select(Tenant).where(Tenant.tenant_id == tenant_id))
    if tenant is None:
        return error_response(code=404, msg="商家不存在")

    config = await db.scalar(
        select(TenantConfig)
        .where(TenantConfig.tenant_id == tenant_id)
        .with_for_update()
    )
    if config is None:
        return error_response(code=409, msg="商户配置缺失，无法调整接单方式")

    before_mode = fulfilment_mode_from_business_info(config.business_info)
    if before_mode == mode:
        return success_response(
            data={
                "tenant_id": tenant_id,
                "fulfilment_mode": mode,
                "idempotent": True,
            },
            msg="接单方式未变化",
        )

    business_info = dict(config.business_info or {})
    business_info[FULFILMENT_MODE_KEY] = mode
    config.business_info = business_info
    flag_modified(config, "business_info")
    await db.commit()

    request_id = getattr(request.state, "request_id", None) or "unknown"
    _audit(
        "fulfilment_mode_change",
        request,
        tenant_id,
        detail=(
            f"before_mode={before_mode} after_mode={mode} reason={reason} "
            f"operator={operator or 'super_admin'} request_id={request_id}"
        ),
    )
    return success_response(
        data={
            "tenant_id": tenant_id,
            "fulfilment_mode": mode,
            "idempotent": False,
        },
        msg="接单方式已更新",
    )


@router.get(
    "/merchants/{tenant_id}/payment-readiness",
    response_model=RespVo,
    dependencies=[Depends(_verify_payment_readiness_super_token)],
)
async def get_merchant_payment_readiness(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse | JSONResponse:
    """Read one tenant's local-only customer WeChat collection readiness."""
    result = await db.execute(
        select(Tenant).where(Tenant.tenant_id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        return JSONResponse(
            status_code=404,
            content=error_response(code=404, msg="商家不存在").model_dump(),
        )

    from app.services.payment_readiness_service import evaluate_payment_readiness

    return success_response(
        data=evaluate_payment_readiness(tenant, settings),
        msg="ok",
    )


@router.post("/merchants", response_model=RespVo, dependencies=[Depends(_verify_super_token)])
async def create_merchant(request: Request, data: CreateMerchantRequest, db: AsyncSession = Depends(get_db)):
    # Delegates to the same Domain Authority self-registration uses
    # (MerchantProvisioningService) -- Super Admin and self-signup must never
    # grow two independent "create a tenant" implementations again. Response
    # shape (tenant_id/name/phone/login_code) is unchanged for backward
    # compatibility with the existing admin-h5 caller; login_code remains the
    # pre-existing cosmetic echo of data.initial_code (real owner auth is
    # SMS-OTP, not this code -- unrelated to this phase, left as-is).
    try:
        result = await MerchantProvisioningService(db).provision_merchant(
            name=data.name,
            phone=data.phone,
            source=ProvisioningSource.SUPER_ADMIN,
        )
    except PhoneAlreadyRegisteredError:
        return error_response(code=400, msg="该手机号已注册")

    tenant = result.tenant
    _audit("create_merchant", request, tenant.tenant_id, detail=f"name={data.name}")
    return success_response(
        data={"tenant_id": tenant.tenant_id, "name": tenant.name, "phone": tenant.phone, "login_code": data.initial_code},
        msg="商家创建成功",
    )


@router.patch("/merchants/{tenant_id}/wxpay", response_model=RespVo)
@login_limit()
async def config_merchant_wxpay(
    tenant_id: str,
    request: Request,
    data: WxPayConfigRequest,
    db: AsyncSession = Depends(get_db),
    operator: str = Depends(_verify_super_token),
):
    step_up_error = _step_up_error(request, data)
    if step_up_error:
        return step_up_error

    fields_set = set(data.model_fields_set)
    config_fields = fields_set - {"totp_code", "reason", "confirmed"}
    secret_fields = {"wx_api_key_v3", "wx_private_key"}
    for field in secret_fields & config_fields:
        value = getattr(data, field)
        if value is None or not value.strip():
            return _wxpay_error(request, 400, "WXPAY_SECRET_CLEAR_NOT_ALLOWED", "敏感凭证不能通过空值清除")

    encrypted_secrets: dict[str, str] = {}
    try:
        for field in secret_fields & config_fields:
            encrypted_secrets[field] = encrypt_secret_strict(getattr(data, field).strip())
    except SecretEncryptionUnavailable:
        return _wxpay_error(
            request,
            503,
            "WXPAY_SECRET_ENCRYPTION_UNAVAILABLE",
            "支付密钥安全存储暂不可用，未保存任何修改",
        )
    if len(encrypted_secrets.get("wx_api_key_v3", "")) > 256 or len(encrypted_secrets.get("wx_private_key", "")) > 4096:
        return _wxpay_error(request, 400, "WXPAY_SECRET_TOO_LONG", "密钥内容过长，请联系技术支持处理")

    result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id).with_for_update())
    tenant = result.scalar_one_or_none()
    if not tenant:
        await db.rollback()
        return _wxpay_error(request, 404, "MERCHANT_NOT_FOUND", "商家不存在")

    if "wx_pay_enabled" in config_fields and data.wx_pay_enabled != tenant.wx_pay_enabled:
        await db.rollback()
        return _wxpay_error(
            request,
            409,
            "WXPAY_PAYMENT_STATE_ENDPOINT_REQUIRED",
            "支付启停必须使用验证或暂停接口",
        )

    changed_fields: list[str] = []
    credential_changed = False
    credential_fields = {
        "wx_mchid",
        "wx_api_key_v3",
        "wx_cert_serial",
        "wx_private_key",
        "wx_public_key_id",
        "wx_public_key",
    }

    scalar_updates: dict[str, str | None] = {}
    for field in {"wx_mchid", "wx_cert_serial", "wx_public_key_id", "wx_public_key", "receiver_name"} & config_fields:
        raw_value = getattr(data, field)
        value = raw_value.strip() if isinstance(raw_value, str) else None
        if field == "receiver_name" and not value:
            value = tenant.name
        scalar_updates[field] = value or None
    if "receiver_type" in config_fields:
        if data.receiver_type not in ("enterprise", "individual"):
            await db.rollback()
            return _wxpay_error(request, 400, "WXPAY_RECEIVER_TYPE_INVALID", "开户类型无效")
        scalar_updates["receiver_type"] = data.receiver_type

    next_mchid = scalar_updates.get("wx_mchid", tenant.wx_mchid)
    if "wx_mchid" in config_fields and (not next_mchid or not next_mchid.isdigit() or not 10 <= len(next_mchid) <= 15):
        await db.rollback()
        return _wxpay_error(request, 400, "WXPAY_CONFIG_MCHID_INVALID", "商户号格式无效")
    if "wx_api_key_v3" in config_fields and len(data.wx_api_key_v3.strip()) != 32:
        await db.rollback()
        return _wxpay_error(request, 400, "WXPAY_CONFIG_API_KEY_INVALID", "APIv3 密钥格式无效")
    if "wx_cert_serial" in config_fields:
        import re
        cert_serial = scalar_updates.get("wx_cert_serial") or ""
        if not re.fullmatch(r"[A-Fa-f0-9]{40,64}", cert_serial):
            await db.rollback()
            return _wxpay_error(request, 400, "WXPAY_CONFIG_CERT_SERIAL_INVALID", "证书序列号格式无效")
    if "wx_private_key" in config_fields:
        from cryptography.hazmat.primitives import serialization
        try:
            serialization.load_pem_private_key(data.wx_private_key.strip().replace("\\n", "\n").encode(), password=None)
        except Exception:
            await db.rollback()
            return _wxpay_error(request, 400, "WXPAY_CONFIG_PRIVATE_KEY_INVALID", "商户私钥格式无效")
    next_public_key_id = scalar_updates.get("wx_public_key_id", tenant.wx_public_key_id)
    next_public_key = scalar_updates.get("wx_public_key", tenant.wx_public_key)
    if bool(next_public_key_id) != bool(next_public_key):
        await db.rollback()
        return _wxpay_error(request, 400, "WXPAY_CONFIG_PUBLIC_KEY_PAIR_REQUIRED", "微信支付公钥 ID 与公钥必须同时填写")
    if "wx_public_key" in config_fields and next_public_key:
        from cryptography.hazmat.primitives import serialization
        try:
            serialization.load_pem_public_key(next_public_key.replace("\\n", "\n").encode())
        except Exception:
            await db.rollback()
            return _wxpay_error(request, 400, "WXPAY_CONFIG_PUBLIC_KEY_INVALID", "微信支付公钥格式无效")

    if getattr(tenant, "payment_locked", False) and tenant.wx_mchid and next_mchid != tenant.wx_mchid:
        await db.rollback()
        return _wxpay_error(request, 403, "WXPAY_RECEIVER_LOCKED", "收款账户已锁定，不能修改微信支付商户号")

    for field, value in scalar_updates.items():
        if getattr(tenant, field) != value:
            setattr(tenant, field, value)
            changed_fields.append(field)
            credential_changed = credential_changed or field in credential_fields

    for field, encrypted_value in encrypted_secrets.items():
        clear_value = getattr(data, field).strip()
        if decrypt_secret(getattr(tenant, field)) != clear_value:
            setattr(tenant, field, encrypted_value)
            changed_fields.append(field)
            credential_changed = True

    if credential_changed:
        tenant.receiver_verified = False
        tenant.verified_time = None
        tenant.wx_pay_enabled = False
    tenant.payment_locked = True

    try:
        await db.commit()
        await db.refresh(tenant)
    except Exception:
        await db.rollback()
        _audit_wxpay(
            "wxpay_config_patch",
            request,
            tenant_id=tenant_id,
            operator_id=operator,
            reason=data.reason or "",
            result="failed",
            changed_field_names=changed_fields,
            verification_invalidated=credential_changed,
        )
        return _wxpay_error(request, 500, "WXPAY_CONFIG_SAVE_FAILED", "微信支付配置保存失败")

    _audit_wxpay(
        "wxpay_config_patch",
        request,
        tenant_id=tenant_id,
        operator_id=operator,
        reason=data.reason or "",
        result="success",
        changed_field_names=changed_fields,
        verification_invalidated=credential_changed,
    )
    return success_response(
        data={
            "tenant_id": tenant_id,
            "wx_mchid": tenant.wx_mchid,
            "wx_pay_enabled": tenant.wx_pay_enabled,
            "changed_field_names": sorted(changed_fields),
            "verification_invalidated": credential_changed,
            **_payment_view(tenant),
        },
        msg="微信支付配置已保存",
    )


@router.post("/merchants/{tenant_id}/wxpay/copy-from", response_model=RespVo)
@login_limit()
async def copy_merchant_wxpay(
    tenant_id: str,
    request: Request,
    data: CopyWxPayRequest,
    operator: str = Depends(_verify_super_token),
):
    _audit_wxpay(
        "wxpay_copy_disabled",
        request,
        tenant_id=tenant_id,
        source_tenant_id=data.source_tenant_id,
        operator_id=operator,
        reason="cross-tenant secret copy disabled",
        result="denied",
    )
    return _wxpay_error(request, 409, "WXPAY_SECRET_COPY_DISABLED", "跨商户复制支付密钥已停用")


@router.post("/merchants/{tenant_id}/wxpay/verify", response_model=RespVo)
@login_limit()
async def verify_merchant_wxpay(
    tenant_id: str,
    request: Request,
    data: StepUpRequest,
    db: AsyncSession = Depends(get_db),
    operator: str = Depends(_verify_super_token),
):
    step_up_error = _step_up_error(request, data)
    if step_up_error:
        return step_up_error
    result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id).with_for_update())
    tenant = result.scalar_one_or_none()
    if not tenant:
        await db.rollback()
        return _wxpay_error(request, 404, "MERCHANT_NOT_FOUND", "商家不存在")

    ok, validation_code = _validate_wxpay_client(tenant)
    if not ok:
        await db.rollback()
        _audit_wxpay(
            "wxpay_verify",
            request,
            tenant_id=tenant_id,
            operator_id=operator,
            reason=data.reason or "",
            result=validation_code,
        )
        status_code = 502 if validation_code in {"WXPAY_SDK_INIT_FAILED", "WXPAY_VERIFICATION_FAILED"} else 400
        return _wxpay_error(request, status_code, validation_code, "微信支付配置验证失败")

    tenant.receiver_name = tenant.receiver_name or tenant.name
    tenant.receiver_type = tenant.receiver_type or "enterprise"
    tenant.receiver_verified = True
    tenant.payment_locked = True
    tenant.wx_pay_enabled = True
    tenant.verified_time = datetime.utcnow()
    try:
        await db.commit()
        await db.refresh(tenant)
    except Exception:
        await db.rollback()
        return _wxpay_error(request, 500, "WXPAY_VERIFY_COMMIT_FAILED", "微信支付配置验证未完成")
    _audit_wxpay(
        "wxpay_verify",
        request,
        tenant_id=tenant_id,
        operator_id=operator,
        reason=data.reason or "",
        result="success",
        changed_field_names=["receiver_verified", "verified_time", "wx_pay_enabled"],
    )
    return success_response(data={"tenant_id": tenant_id, **_payment_view(tenant)}, msg="微信支付配置验证通过")


@router.patch("/merchants/{tenant_id}/wxpay/pause", response_model=RespVo)
@login_limit()
async def pause_merchant_wxpay(
    tenant_id: str,
    request: Request,
    data: StepUpRequest,
    db: AsyncSession = Depends(get_db),
    operator: str = Depends(_verify_super_token),
):
    emergency_pause = bool(data.emergency_password is not None or data.emergency_confirmation is not None)
    reason = (data.reason or "").strip()
    if emergency_pause:
        if not reason or not data.confirmed:
            return _wxpay_error(request, 400, "WXPAY_STEP_UP_REQUIRED", "需要操作原因和明确确认")
        expected_confirmation = f"PAUSE_WXPAY:{tenant_id}"
        if data.emergency_confirmation != expected_confirmation:
            return _wxpay_error(request, 400, "WXPAY_EMERGENCY_CONFIRMATION_INVALID", "紧急暂停确认短语不正确")
        expected_password = settings.SUPER_ADMIN_PASSWORD or ""
        supplied_password = data.emergency_password or ""
        if not expected_password or not secrets.compare_digest(supplied_password, expected_password):
            return _wxpay_error(request, 401, "WXPAY_EMERGENCY_PASSWORD_INVALID", "紧急暂停密码校验失败")
    else:
        step_up_error = _step_up_error(request, data)
        if step_up_error:
            return step_up_error

    result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id).with_for_update())
    tenant = result.scalar_one_or_none()
    if not tenant:
        await db.rollback()
        return _wxpay_error(request, 404, "MERCHANT_NOT_FOUND", "商家不存在")
    changed = bool(tenant.wx_pay_enabled)
    if changed:
        tenant.wx_pay_enabled = False
        try:
            await db.commit()
            await db.refresh(tenant)
        except Exception:
            await db.rollback()
            return _wxpay_error(request, 500, "WXPAY_PAUSE_FAILED", "暂停微信支付失败")
    else:
        await db.rollback()
    _audit_wxpay(
        "wxpay_emergency_pause" if emergency_pause else "wxpay_pause",
        request,
        tenant_id=tenant_id,
        operator_id=operator,
        reason=reason,
        result="success",
        changed_field_names=["wx_pay_enabled"] if changed else [],
        emergency_pause=emergency_pause,
    )
    return success_response(data={"tenant_id": tenant_id, "wx_pay_enabled": False, **_payment_view(tenant)}, msg="已暂停微信支付")


@router.patch("/merchants/{tenant_id}/status", response_model=RespVo, dependencies=[Depends(_verify_super_token)])
async def toggle_merchant_status(tenant_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        return error_response(code=404, msg="商家不存在")
    tenant.status = not tenant.status
    await db.commit()
    action = "恢复" if tenant.status else "停用"
    _audit("merchant_status_toggle", request, tenant_id, detail=action)
    return success_response(data={"tenant_id": tenant_id, "status": tenant.status}, msg=f"已{action}该商家")


@router.get("/stats", response_model=RespVo, dependencies=[Depends(_verify_super_token)])
async def platform_stats(db: AsyncSession = Depends(get_db)):
    tz8 = timezone(timedelta(hours=8))
    today = datetime.now(tz8).date()
    today_start = datetime(today.year, today.month, today.day, tzinfo=tz8).astimezone(timezone.utc).replace(tzinfo=None)

    total_merchants = (await db.execute(select(func.count(Tenant.id)))).scalar() or 0
    active_merchants = (await db.execute(select(func.count(Tenant.id)).where(Tenant.status == True))).scalar() or 0

    today_order_count = (
        await db.execute(select(func.count(Order.id)).where(Order.created_at >= today_start))
    ).scalar() or 0

    today_revenue = (
        await db.execute(
            select(func.sum(Order.total)).where(
                Order.created_at >= today_start,
                Order.status.in_(["preparing", "done", "settled"]),
            )
        )
    ).scalar() or 0

    return success_response(data={
        "total_merchants": total_merchants,
        "active_merchants": active_merchants,
        "today_orders": today_order_count,
        "today_revenue": float(today_revenue),
    }, msg="ok")


@router.get("/perf-stats", response_model=RespVo, dependencies=[Depends(_verify_super_token)])
async def perf_stats(db: AsyncSession = Depends(get_db), days: int = 7):
    from datetime import datetime, timedelta

    from sqlalchemy import select

    from app.models.perf_sample import PerfSample

    since = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(PerfSample.metric, PerfSample.ms)
        .where(PerfSample.created_at >= since)
    )
    by_metric: dict[str, list[int]] = {}
    for metric, ms in result.all():
        by_metric.setdefault(metric, []).append(ms)

    def percentile(sorted_ms, p):
        if not sorted_ms:
            return 0
        idx = min(len(sorted_ms) - 1, max(0, -(-int(p) * len(sorted_ms) // 100) - 1))
        return sorted_ms[idx]

    stats = []
    for metric, values in by_metric.items():
        values.sort()
        stats.append({
            "metric": metric,
            "count": len(values),
            "avg": round(sum(values) / len(values)),
            "p50": percentile(values, 50),
            "p95": percentile(values, 95),
            "min": values[0],
            "max": values[-1],
        })
    stats.sort(key=lambda s: s["metric"])
    return success_response(data={"days": days, "stats": stats}, msg="ok")


@router.post("/merchants/{tenant_id}/seed-test-data", response_model=RespVo, dependencies=[Depends(_verify_super_token)])
async def seed_merchant_test_data(tenant_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    from app.services.test_data_seed import seed_test_data
    try:
        summary = await seed_test_data(db, tenant_id)
    except ValueError as e:
        _audit("seed_test_data_rejected", request, tenant_id, detail=str(e))
        return error_response(code=400, msg=str(e))
    _audit("seed_test_data", request, tenant_id)
    return success_response(data=summary, msg="测试数据已填充")

