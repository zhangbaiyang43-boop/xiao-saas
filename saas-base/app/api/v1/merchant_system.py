from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import RespVo, error_response, success_response
from app.core.tenant_context import TenantContext
from app.services.tenant_service import TenantService


router = APIRouter(prefix="/api/v1/merchant", tags=["商家系统状态"])


def _payment_status(tenant) -> tuple[str, str]:
    if not getattr(tenant, "wx_mchid", None):
        return "warning", "支付服务未配置，暂时无法使用微信支付"
    if not getattr(tenant, "wx_pay_enabled", False):
        return "warning", "支付服务未启用，请完成收款配置"
    return "ok", "支付服务正常"


def _printer_status(tenant, config) -> tuple[str, str]:
    business_info = (getattr(config, "business_info", None) or {}) if config else {}
    provider = business_info.get("printer_provider") or "feieyun"
    kuaimai = business_info.get("kuaimai_printer") or {}
    feieyun_configured = bool(getattr(tenant, "feieyun_sn", None) and getattr(tenant, "feieyun_key", None))
    kuaimai_configured = bool(kuaimai.get("app_id") and kuaimai.get("app_secret") and kuaimai.get("sn"))
    configured = kuaimai_configured if provider == "kuaimai" else feieyun_configured
    if configured:
        return "ok", "打印服务正常"
    return "warning", "打印服务异常，请检查打印机或手动处理订单"


@router.get("/system-status", response_model=RespVo)
async def get_merchant_system_status(db: AsyncSession = Depends(get_db)):
    tenant_id = TenantContext.get_current_tenant_id()
    if not tenant_id:
        return error_response(code=401, msg="未登录或登录已过期")

    database_status = "ok"
    database_message = "数据库连接正常"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        database_status = "error"
        database_message = "数据库连接异常，请联系技术支持"

    if database_status != "ok":
        return success_response(
            data={
                "api": "ok",
                "database": database_status,
                "order": "error",
                "payment": "warning",
                "printer": "warning",
                "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "message": database_message,
            },
            msg="ok",
        )

    service = TenantService(db)
    tenant = await service.get_tenant(tenant_id)
    if not tenant:
        return error_response(code=404, msg="商家不存在")
    config = await service.ensure_tenant_config(tenant_id)

    payment_status, payment_message = _payment_status(tenant)
    printer_status, printer_message = _printer_status(tenant, config)
    order_status = "ok" if database_status == "ok" else "error"

    messages = [database_message, payment_message, printer_message]
    if database_status == "ok" and payment_status == "ok" and printer_status == "ok":
        message = "系统运行正常"
    else:
        message = next((item for item in messages if "异常" in item), messages[0])

    return success_response(
        data={
            "api": "ok",
            "database": database_status,
            "order": order_status,
            "payment": payment_status,
            "printer": printer_status,
            "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "message": message,
        },
        msg="ok",
    )