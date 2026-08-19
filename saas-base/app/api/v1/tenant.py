from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel as PydanticBase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.entitlement_guard import require_capability_response
from app.core.plan_capabilities import CAP_KITCHEN_PRINT
from app.core.response import RespVo, error_response, success_response
from app.core.tenant_context import TenantContext
from app.schemas.tenant import ChangePasswordRequest, UpdateTenantProfileRequest
from app.services.tenant_service import TenantService

router = APIRouter(prefix="/api/v1/tenant", tags=["商家租户"])

PAYMENT_MODES = {"prepay", "postpay", "table_account"}

# 接受任意扁平字段，都存进 business_info


def _mask_mchid(mchid: str | None) -> str:
    value = (mchid or "").strip()
    if len(value) <= 6:
        return value or "-"
    return f"{value[:3]}****{value[-3:]}"


def _is_new_merchant(tenant) -> bool:
    created_at = getattr(tenant, "created_at", None)
    if not created_at:
        return True
    from datetime import datetime as _dt
    return (_dt.utcnow() - created_at).days <= 7


def _payment_status(tenant) -> str:
    if not getattr(tenant, "wx_mchid", None):
        return "unconfigured"
    if not getattr(tenant, "wx_pay_enabled", False):
        return "paused"
    if getattr(tenant, "receiver_verified", False):
        return "verified"
    return "pending"


def _payment_view(tenant) -> dict:
    verified_time = getattr(tenant, "verified_time", None)
    return {
        "receiver_name": getattr(tenant, "receiver_name", None) or tenant.name,
        "receiver_type": getattr(tenant, "receiver_type", None) or "enterprise",
        "receiver_verified": bool(getattr(tenant, "receiver_verified", False)),
        "payment_locked": bool(getattr(tenant, "payment_locked", True)),
        "payment_status": _payment_status(tenant),
        "verified_time": verified_time.strftime("%Y-%m-%d %H:%M") if verified_time else "",
        "wx_mchid_masked": _mask_mchid(getattr(tenant, "wx_mchid", "")),
    }


class FlatSettingsRequest(PydanticBase):
    model_config = {"extra": "allow"}


def serialize_settings(tenant, config):
    business_info = (config.business_info or {}) if config else {}
    return {
        "profile": {
            "tenant_id": tenant.tenant_id,
            "name": tenant.name,
            "phone": tenant.phone,
            "address": tenant.address,
            "logo_url": tenant.logo_url,
            "status": tenant.status,
            "payment_mode": getattr(tenant, "payment_mode", "prepay") or "prepay",
        },
        "member_rules": config.member_rules if config else None,
        "coupon_rules": config.coupon_rules if config else None,
        "business_info": business_info,
        "plugin_settings": config.plugin_settings if config else None,
    }


async def get_current_tenant(service: TenantService):
    tenant_id = TenantContext.get_current_tenant_id()
    if not tenant_id:
        return None, None, error_response(code=401, msg="未登录或登录已过期")

    tenant = await service.get_tenant(tenant_id)
    if not tenant:
        return tenant_id, None, error_response(code=404, msg="商家不存在")
    return tenant_id, tenant, None


@router.get("/profile", response_model=RespVo)
async def get_profile(db: AsyncSession = Depends(get_db)):
    service = TenantService(db)
    tenant_id, tenant, error = await get_current_tenant(service)
    if error:
        return error

    config = await service.ensure_tenant_config(tenant_id)
    data = serialize_settings(tenant, config)
    return success_response(
        data={
            **data["profile"],
            **_payment_view(tenant),
            # 把 business_info 里所有字段展开到顶层，方便前端直接读
            **(data["business_info"] or {}),
            "member_rules": data["member_rules"],
            "coupon_rules": data["coupon_rules"],
            "business_info": data["business_info"],
            "plugin_settings": data["plugin_settings"],
            "is_new_merchant": _is_new_merchant(tenant),
        },
        msg="ok",
    )


@router.put("/profile", response_model=RespVo)
async def update_profile(data: UpdateTenantProfileRequest, db: AsyncSession = Depends(get_db)):
    service = TenantService(db)
    tenant_id, tenant, error = await get_current_tenant(service)
    if error:
        return error

    payload = data.model_dump(exclude_unset=True)
    if "logo_url" in payload:
        from app.core.cos import is_allowed_cos_url
        if not is_allowed_cos_url(payload.get("logo_url")):
            return error_response(code=400, msg="门店 Logo 仅支持本项目 COS 地址，请先上传图片")

    updated = await service.update_tenant_profile(tenant, **payload)
    return success_response(
        data={
            "tenant_id": updated.tenant_id,
            "name": updated.name,
            "phone": updated.phone,
            "address": updated.address,
            "logo_url": updated.logo_url,
            "status": updated.status,
        },
        msg="更新成功",
    )


@router.post("/upload-logo", response_model=RespVo)
async def upload_shop_logo(
    request: Request,
    file: UploadFile = File(...),
):
    """上传门店 Logo 到 COS（最长边 512，WebP），返回公开 URL；需再调 profile 保存。"""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id or getattr(request.state, "token_type", None) != "merchant":
        return error_response(code=401, msg="请先登录")
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
        return error_response(code=400, msg="仅支持 jpg/png/webp/gif")
    content = await file.read()
    if len(content) > 3 * 1024 * 1024:
        return error_response(code=400, msg="图片不能超过 3MB")
    from starlette.concurrency import run_in_threadpool
    from app.core.cos import IMAGE_LOGO_MAX_DIMENSION, process_image, sniff_image_content_type, upload_image
    if not sniff_image_content_type(content):
        return error_response(code=400, msg="文件内容不是有效图片")
    try:
        processed = await run_in_threadpool(process_image, content, IMAGE_LOGO_MAX_DIMENSION)
    except ValueError:
        return error_response(code=400, msg="图片内容无效或已损坏")
    except RuntimeError as e:
        return error_response(code=500, msg=str(e))
    try:
        url = upload_image(processed, "logo.webp", "image/webp", folder="logo_images")
        return success_response(data={"url": url}, msg="上传成功")
    except Exception as e:
        return error_response(code=500, msg=f"上传失败：{str(e)}")


@router.get("/marketing-preview", response_model=RespVo)
async def get_marketing_preview(db: AsyncSession = Depends(get_db)):
    """返回系统为该商户计算的动态营销参数，供后台展示（只读）。"""
    from app.services.coupon_service import CouponService
    from app.models.coupon import Coupon
    from sqlalchemy.future import select as sa_select
    from sqlalchemy import func as sa_func
    from datetime import datetime as _dt, timedelta as _td

    service = TenantService(db)
    tenant_id, tenant, error = await get_current_tenant(service)
    if error:
        return error

    TenantContext.set_tenant_id(tenant_id)
    cs = CouponService(db)
    aov = await cs.get_merchant_aov()
    rules = await cs.get_coupon_rules()
    intensity_outcomes = await cs.estimate_intensity_outcomes()

    # 本月已发券数
    month_start = _dt.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    issued_result = await db.execute(
        sa_select(sa_func.count(Coupon.id)).where(
            Coupon.tenant_id == tenant_id,
            Coupon.created_at >= month_start,
        )
    )
    issued_this_month = int(issued_result.scalar() or 0)

    # 本月发出的券里，有多少已经被核销——这是商家判断"发券到底有没有效果"的关键指标，
    # 光看发了多少张说明不了问题，发了不用等于白发。
    redeemed_result = await db.execute(
        sa_select(sa_func.count(Coupon.id)).where(
            Coupon.tenant_id == tenant_id,
            Coupon.created_at >= month_start,
            Coupon.status == "USED",
        )
    )
    redeemed_this_month = int(redeemed_result.scalar() or 0)
    redemption_rate = round(redeemed_this_month / issued_this_month, 4) if issued_this_month > 0 else None

    def fmt_rule(key):
        r = rules.get(key, {})
        wc = r.get("weighted_coupons", [])
        return {
            "enabled": r.get("enabled", True),
            "weighted_coupons": [
                {"name": w.get("name"), "amount": w.get("amount"), "threshold": w.get("threshold"), "weight": w.get("weight"), "valid_days": w.get("valid_days")}
                for w in wc
            ] if wc else [],
            "amount": r.get("amount"),
            "threshold": r.get("threshold"),
            "valid_days": r.get("valid_days"),
        }

    return success_response(data={
        "aov": round(aov, 1) if aov else None,
        "issued_this_month": issued_this_month,
        "redeemed_this_month": redeemed_this_month,
        "redemption_rate": redemption_rate,
        "new_customer_coupon": fmt_rule("new_customer_coupon"),
        "consumption_coupon": fmt_rule("consumption_coupon"),
        "recall_coupon": fmt_rule("recall_coupon"),
        "entry_coupon": fmt_rule("entry_coupon"),
        "points_reward_coupon": fmt_rule("points_reward_coupon"),
        # 阶段二：三档强度（保守/标准/激进）各自的预测结果，
        # 后台"选强度"卡片直接用这个字段渲染，不需要自己再算。
        "intensity_outcomes": intensity_outcomes,
    })


@router.get("/settings", response_model=RespVo)
async def get_settings(db: AsyncSession = Depends(get_db)):
    service = TenantService(db)
    tenant_id, tenant, error = await get_current_tenant(service)
    if error:
        return error

    config = await service.ensure_tenant_config(tenant_id)
    return success_response(data=serialize_settings(tenant, config), msg="ok")


@router.put("/settings", response_model=RespVo)
async def update_settings(data: FlatSettingsRequest, db: AsyncSession = Depends(get_db)):
    service = TenantService(db)
    tenant_id, tenant, error = await get_current_tenant(service)
    if error:
        return error

    config = await service.ensure_tenant_config(tenant_id)
    # 把所有字段存入 business_info（保留已有的嵌套字段如 member_rules/plugin_settings）
    flat = data.model_dump()
    nested_keys = {"profile", "member_rules", "coupon_rules", "business_info", "plugin_settings"}
    profile = flat.pop("profile", None)
    member_rules = flat.pop("member_rules", None)
    coupon_rules = flat.pop("coupon_rules", None)
    explicit_business_info = flat.pop("business_info", None)
    plugin_settings = flat.pop("plugin_settings", None)
    payment_mode = flat.pop("payment_mode", None)
    if payment_mode is not None:
        payment_mode = str(payment_mode or "").strip()
        if payment_mode not in PAYMENT_MODES:
            return error_response(code=400, msg="不支持的支付模式")
        tenant.payment_mode = payment_mode
    # 剩余所有扁平字段合入 business_info
    merged_business_info = {**(explicit_business_info or {}), **flat}
    tenant, config = await service.update_tenant_settings(
        tenant,
        config,
        profile=profile,
        member_rules=member_rules,
        coupon_rules=coupon_rules,
        business_info=merged_business_info if merged_business_info else None,
        plugin_settings=plugin_settings,
    )
    s = serialize_settings(tenant, config)
    return success_response(data={**s["profile"], **(s["business_info"] or {})}, msg="保存成功")


@router.post("/logout", response_model=RespVo)
async def logout():
    return success_response(msg="退出成功")


@router.put("/password", response_model=RespVo)
async def change_password(data: ChangePasswordRequest, db: AsyncSession = Depends(get_db)):
    return error_response(code=400, msg="当前已改为手机号验证码登录，暂不支持修改密码")


class PrinterConfigRequest(PydanticBase):
    printer_provider: str = "feieyun"
    feieyun_sn: str = ""
    feieyun_key: str = ""
    kuaimai_app_id: str = ""
    kuaimai_app_secret: str = ""
    kuaimai_share_code: str = ""
    kuaimai_sn: str = ""
    kuaimai_device_key: str = ""
    queue_query_enabled: bool = True
    queue_ticket_qrcode_enabled: bool = True
    queue_qrcode_tip: str = "\u626b\u7801\u67e5\u770b\u5b9e\u65f6\u6392\u961f\u8fdb\u5ea6"


@router.patch("/printer", response_model=RespVo)
async def update_printer_config(data: PrinterConfigRequest, db: AsyncSession = Depends(get_db)):
    from app.models.tenant import Tenant
    from sqlalchemy.orm.attributes import flag_modified
    service = TenantService(db)
    tenant_id, tenant, error = await get_current_tenant(service)
    if error:
        return error
    denial = await require_capability_response(db, tenant_id, CAP_KITCHEN_PRINT)
    if denial is not None:
        return denial
    from sqlalchemy import select as _select
    result = await db.execute(_select(Tenant).where(Tenant.tenant_id == tenant_id))
    t = result.scalar_one_or_none()
    if not t:
        return error_response(code=404, msg="商家不存在")
    t.feieyun_sn = data.feieyun_sn.strip() or None
    t.feieyun_key = data.feieyun_key.strip() or None
    config = await service.ensure_tenant_config(tenant_id)
    business_info = dict(config.business_info or {})
    provider = data.printer_provider if data.printer_provider in ("feieyun", "kuaimai") else "feieyun"
    business_info["printer_provider"] = provider
    business_info["kuaimai_printer"] = {
        "app_id": data.kuaimai_app_id.strip(),
        "app_secret": data.kuaimai_app_secret.strip(),
        "share_code": data.kuaimai_share_code.strip(),
        "sn": data.kuaimai_sn.strip(),
        "device_key": data.kuaimai_device_key.strip(),
    }
    business_info["queue_query_enabled"] = bool(data.queue_query_enabled)
    business_info["queue_ticket_qrcode_enabled"] = bool(data.queue_ticket_qrcode_enabled)
    business_info["queue_qrcode_tip"] = data.queue_qrcode_tip.strip() or "\u626b\u7801\u67e5\u770b\u5b9e\u65f6\u6392\u961f\u8fdb\u5ea6"
    config.business_info = business_info
    flag_modified(config, "business_info")
    await db.commit()
    return success_response(msg="打印机配置已保存")


@router.get("/printer", response_model=RespVo)
async def get_printer_config(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select as _select
    from app.models.tenant import Tenant
    service = TenantService(db)
    tenant_id, tenant, error = await get_current_tenant(service)
    if error:
        return error
    result = await db.execute(_select(Tenant).where(Tenant.tenant_id == tenant_id))
    t = result.scalar_one_or_none()
    config = await service.ensure_tenant_config(tenant_id)
    business_info = config.business_info or {}
    kuaimai = business_info.get("kuaimai_printer") or {}
    provider = business_info.get("printer_provider") or "feieyun"
    feieyun_configured = bool(t.feieyun_sn and t.feieyun_key)
    kuaimai_configured = bool(kuaimai.get("app_id") and kuaimai.get("app_secret") and kuaimai.get("sn"))
    return success_response(data={
        "printer_provider": provider,
        "feieyun_sn": t.feieyun_sn or "",
        "feieyun_key": t.feieyun_key or "",
        "kuaimai_app_id": kuaimai.get("app_id") or "",
        "kuaimai_app_secret": kuaimai.get("app_secret") or "",
        "kuaimai_share_code": kuaimai.get("share_code") or "",
        "kuaimai_sn": kuaimai.get("sn") or "",
        "kuaimai_device_key": kuaimai.get("device_key") or "",
        "feieyun_configured": feieyun_configured,
        "kuaimai_configured": kuaimai_configured,
        "configured": kuaimai_configured if provider == "kuaimai" else feieyun_configured,
        "queue_query_enabled": business_info.get("queue_query_enabled", True),
        "queue_ticket_qrcode_enabled": business_info.get("queue_ticket_qrcode_enabled", True),
        "queue_qrcode_tip": business_info.get("queue_qrcode_tip") or "\u626b\u7801\u67e5\u770b\u5b9e\u65f6\u6392\u961f\u8fdb\u5ea6",
    })
