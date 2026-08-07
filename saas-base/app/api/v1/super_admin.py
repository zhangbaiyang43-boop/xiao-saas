from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.database import get_db
from app.core.logger import logger
from app.core.rate_limiter import login_limit
from app.core.response import RespVo, error_response, success_response
from app.models.order import Order
from app.models.tenant import Tenant
from app.services.tenant_service import TenantService
from app.utils.id_generator import generate_tenant_id

router = APIRouter(prefix="/api/super", tags=["平台中控台"])

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


class WxPayConfigRequest(BaseModel):
    wx_mchid: str
    wx_api_key_v3: str
    wx_cert_serial: str
    wx_private_key: str
    wx_public_key_id: str | None = None
    wx_public_key: str | None = None
    wx_pay_enabled: bool = True
    receiver_name: str | None = None
    receiver_type: str | None = None


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


def _verify_super_token(x_super_token: str = Header(..., alias="X-Super-Token")) -> str:
    import jwt
    try:
        payload = jwt.decode(x_super_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "super_admin":
            raise ValueError
        return payload.get("sub", "")
    except Exception:
        raise __import__("fastapi").HTTPException(status_code=401, detail="中控台鉴权失败")


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
        return False, "商户号不能为空"
    if not re.match(r"^\d{10,15}$", tenant.wx_mchid):
        return False, "商户号格式错误，应为10-15位数字"

    if not api_key_v3:
        return False, "APIv3密钥不能为空"
    if len(api_key_v3) != 32:
        return False, "APIv3密钥必须为32位"

    if not tenant.wx_cert_serial:
        return False, "商户证书序列号不能为空"
    if not re.match(r"^[A-Fa-f0-9]{40,64}$", tenant.wx_cert_serial):
        return False, "商户证书序列号格式错误，应为40~64位十六进制"

    if not private_key_pem:
        return False, "商户私钥不能为空"
    try:
        private_key = private_key_pem.replace("\\n", "\n")
        serialization.load_pem_private_key(private_key.encode(), password=None, backend=default_backend())
    except Exception:
        return False, "商户私钥无法解析，请确认是 apiclient_key.pem 内容"

    if tenant.wx_public_key_id and tenant.wx_public_key:
        try:
            public_key = tenant.wx_public_key.replace("\\n", "\n")
            serialization.load_pem_public_key(public_key.encode(), backend=default_backend())
        except Exception:
            return False, "微信支付公钥无法解析，请确认格式正确"
    elif not tenant.wx_public_key_id and not tenant.wx_public_key:
        pass
    else:
        return False, "微信支付公钥ID和公钥内容必须同时填写"

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
            return False, "微信支付 SDK 初始化失败，请检查凭证或依赖"
        for method_name in ("certificates", "get_certificates"):
            method = getattr(client, method_name, None)
            if callable(method):
                code, body = method()
                if int(code) in (200, 204):
                    return True, "微信接口验证通过"
                return False, f"微信接口验证失败：{body}"
        return True, "微信支付凭证格式验证通过"
    except Exception as exc:
        return False, f"微信支付验证失败：{exc}"


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

    data = []
    for t in tenants:
        data.append({
            "id": str(t.id),
            "tenant_id": t.tenant_id,
            "name": t.name,
            "phone": t.phone or "",
            "status": t.status,
            "today_orders": today_orders.get(t.tenant_id, 0),
            "wx_pay_enabled": getattr(t, "wx_pay_enabled", False) or False,
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
            **_payment_view(t),
        })
    return success_response(data=data, msg="ok")


@router.post("/merchants", response_model=RespVo, dependencies=[Depends(_verify_super_token)])
async def create_merchant(request: Request, data: CreateMerchantRequest, db: AsyncSession = Depends(get_db)):
    service = TenantService(db)
    existing = await service.get_tenant_by_phone(data.phone)
    if existing:
        return error_response(code=400, msg="该手机号已注册")
    tenant_id = generate_tenant_id()
    tenant = await service.create_tenant(
        tenant_id=tenant_id,
        name=data.name,
        password_hash="",
        phone=data.phone,
        address=None,
        logo_url=None,
    )
    _audit("create_merchant", request, tenant_id, detail=f"name={data.name}")
    return success_response(
        data={"tenant_id": tenant.tenant_id, "name": tenant.name, "phone": tenant.phone, "login_code": data.initial_code},
        msg="商家创建成功",
    )


@router.patch("/merchants/{tenant_id}/wxpay", response_model=RespVo, dependencies=[Depends(_verify_super_token)])
async def config_merchant_wxpay(tenant_id: str, request: Request, data: WxPayConfigRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        return error_response(code=404, msg="商家不存在")

    next_mchid = data.wx_mchid.strip()
    if getattr(tenant, "payment_locked", False) and tenant.wx_mchid and tenant.wx_mchid != next_mchid:
        return error_response(code=403, msg="收款账户已锁定，不能修改微信支付商户号")

    encrypted_api_key = encrypt_secret(data.wx_api_key_v3.strip())
    encrypted_private_key = encrypt_secret(data.wx_private_key.strip())
    # 加密后是密文，比明文长；防止极少数超长私钥（罕见的 4096 位商户证书）加密后超出列宽被静默截断，
    # 截断的私钥会直接导致这个商户的支付全部失效且不容易发现，所以这里宁可拒绝也不要保存坏数据。
    if len(encrypted_api_key or "") > 256 or len(encrypted_private_key or "") > 4096:
        return error_response(code=400, msg="密钥内容过长，请联系技术支持处理")

    old_identity = (tenant.wx_mchid or "", tenant.wx_cert_serial or "")
    tenant.wx_mchid = next_mchid
    tenant.wx_api_key_v3 = encrypted_api_key
    tenant.wx_cert_serial = data.wx_cert_serial.strip()
    tenant.wx_private_key = encrypted_private_key
    tenant.wx_public_key_id = data.wx_public_key_id.strip() if data.wx_public_key_id else None
    tenant.wx_public_key = data.wx_public_key.strip() if data.wx_public_key else None
    tenant.wx_pay_enabled = data.wx_pay_enabled
    tenant.receiver_name = (data.receiver_name or tenant.receiver_name or tenant.name).strip()
    tenant.receiver_type = data.receiver_type if data.receiver_type in ("enterprise", "individual") else (tenant.receiver_type or "enterprise")
    tenant.payment_locked = True
    if old_identity != (tenant.wx_mchid or "", tenant.wx_cert_serial or ""):
        tenant.receiver_verified = False
        tenant.verified_time = None
    await db.commit()
    await db.refresh(tenant)
    action = "已保存" if data.wx_pay_enabled else "已暂停"
    _audit("wxpay_save", request, tenant_id, detail=f"mchid_changed={old_identity != (tenant.wx_mchid or '', tenant.wx_cert_serial or '')}")
    return success_response(
        data={"tenant_id": tenant_id, "wx_mchid": tenant.wx_mchid, "wx_pay_enabled": tenant.wx_pay_enabled, **_payment_view(tenant)},
        msg=f"{action}微信支付配置",
    )


@router.post("/merchants/{tenant_id}/wxpay/copy-from", response_model=RespVo, dependencies=[Depends(_verify_super_token)])
async def copy_merchant_wxpay(tenant_id: str, request: Request, data: CopyWxPayRequest, db: AsyncSession = Depends(get_db)):
    if not _verify_totp_code(data.totp_code):
        _audit("wxpay_copy_denied", request, tenant_id, detail="动态口令校验失败")
        return error_response(code=401, msg="动态口令错误或已过期，复制配置需要重新验证")
    if tenant_id == data.source_tenant_id:
        return error_response(code=400, msg="源商户和目标商户不能是同一个")

    source_result = await db.execute(select(Tenant).where(Tenant.tenant_id == data.source_tenant_id))
    source = source_result.scalar_one_or_none()
    if not source:
        return error_response(code=404, msg="源商户不存在")
    if not source.wx_mchid:
        return error_response(code=400, msg="源商户还没有配置支付信息，无法复制")

    target_result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    target = target_result.scalar_one_or_none()
    if not target:
        return error_response(code=404, msg="目标商户不存在")

    if getattr(target, "payment_locked", False) and target.wx_mchid and target.wx_mchid != source.wx_mchid:
        return error_response(code=403, msg="目标商户的收款账户已锁定，不能覆盖为其它商户号")

    old_identity = (target.wx_mchid or "", target.wx_cert_serial or "")
    target.wx_mchid = source.wx_mchid
    target.wx_api_key_v3 = source.wx_api_key_v3
    target.wx_cert_serial = source.wx_cert_serial
    target.wx_private_key = source.wx_private_key
    target.wx_public_key_id = source.wx_public_key_id
    target.wx_public_key = source.wx_public_key
    target.wx_pay_enabled = True
    target.receiver_name = source.receiver_name or source.name
    target.receiver_type = source.receiver_type or "enterprise"
    target.payment_locked = True
    if old_identity != (target.wx_mchid or "", target.wx_cert_serial or ""):
        target.receiver_verified = False
        target.verified_time = None
    await db.commit()
    await db.refresh(target)
    _audit("wxpay_copy", request, tenant_id, detail=f"source={data.source_tenant_id}")
    return success_response(
        data={"tenant_id": tenant_id, **_payment_view(target)},
        msg=f"已从「{source.name}」复制支付配置，请继续验证配置",
    )


@router.post("/merchants/{tenant_id}/wxpay/verify", response_model=RespVo, dependencies=[Depends(_verify_super_token)])
async def verify_merchant_wxpay(tenant_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    from fastapi import HTTPException
    result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail={"success": False, "code": "MERCHANT_NOT_FOUND", "message": "商家不存在"})
    ok, msg = _validate_wxpay_client(tenant)
    if not ok:
        tenant.receiver_verified = False
        await db.commit()
        _audit("wxpay_verify_failed", request, tenant_id, detail=msg)
        if "无法解析" in msg:
            raise HTTPException(status_code=422, detail={"success": False, "code": "CERT_PARSE_ERROR", "message": msg})
        if "微信接口验证失败" in msg:
            raise HTTPException(status_code=502, detail={"success": False, "code": "WXPAY_VERIFY_FAILED", "message": msg})
        raise HTTPException(status_code=400, detail={"success": False, "code": "CONFIG_INVALID", "message": msg})
    tenant.receiver_name = tenant.receiver_name or tenant.name
    tenant.receiver_type = tenant.receiver_type or "enterprise"
    tenant.receiver_verified = True
    tenant.payment_locked = True
    tenant.wx_pay_enabled = True
    tenant.verified_time = datetime.utcnow()
    await db.commit()
    await db.refresh(tenant)
    _audit("wxpay_verify_success", request, tenant_id)
    return success_response(data={"tenant_id": tenant_id, **_payment_view(tenant)}, msg=msg)


@router.patch("/merchants/{tenant_id}/wxpay/pause", response_model=RespVo, dependencies=[Depends(_verify_super_token)])
async def pause_merchant_wxpay(tenant_id: str, request: Request, data: StepUpRequest = StepUpRequest(), db: AsyncSession = Depends(get_db)):
    if not _verify_totp_code(data.totp_code):
        _audit("wxpay_pause_denied", request, tenant_id, detail="动态口令校验失败")
        return error_response(code=401, msg="动态口令错误或已过期，暂停操作需要重新验证")
    result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        return error_response(code=404, msg="商家不存在")
    tenant.wx_pay_enabled = False
    await db.commit()
    await db.refresh(tenant)
    _audit("wxpay_pause", request, tenant_id)
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

