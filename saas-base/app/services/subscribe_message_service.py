"""小程序订阅消息：点餐成功 / 取餐提醒 / 排队叫号提醒。

字段名（character_string1 / amount2 …）必须与微信公众平台「我的模板」详情里的
xxxN.DATA 一致；改模板关键词顺序后只改本文件的 data 组装，不要散落到业务钩子里。

发送失败只打日志，绝不抛到支付/改状态/叫号主流程。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import settings
from app.core.logger import logger


def is_real_wechat_openid(openid: Optional[str]) -> bool:
    if not openid:
        return False
    value = str(openid).strip()
    if not value:
        return False
    # 后台代客 / 手机号登录合成的伪 openid，不能拿去调 subscribe/send
    if value.startswith("phone:") or value.startswith("manual-"):
        return False
    return True


def _clip(value: Any, max_len: int) -> str:
    text = str(value if value is not None else "").strip()
    if not text:
        return ""
    return text[:max_len]


def _format_amount(total: Any) -> str:
    try:
        return f"{float(total or 0):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _format_pay_time(payment_time: Any) -> str:
    """微信 time 字段常用 yyyy-MM-dd HH:mm:ss。"""
    if not payment_time:
        return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    raw = str(payment_time).strip()
    try:
        # 订单里存的是 ISO（可能带 Z / 偏移）
        normalized = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return _clip(raw.replace("T", " ")[:19], 20) or datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def resolve_pickup_no(order: Any) -> str:
    return _clip(getattr(order, "pickup_no", None) or getattr(order, "table_no", None) or "", 32) or "—"


def build_order_success_data(
    *,
    pickup_no: str,
    amount: Any,
    shop_name: str,
    status_text: str = "已支付",
    payment_time: Any = None,
) -> dict:
    # 关键词顺序：取餐号码 → 订单金额 → 门店名称 → 订单状态 → 支付时间
    return {
        "character_string1": {"value": _clip(pickup_no, 32) or "—"},
        "amount2": {"value": _format_amount(amount)},
        "thing3": {"value": _clip(shop_name, 20) or "门店"},
        "phrase4": {"value": _clip(status_text, 5) or "已支付"},
        "time5": {"value": _format_pay_time(payment_time)},
    }


def build_pickup_reminder_data(
    *,
    pickup_no: str,
    shop_name: str,
    status_text: str = "可取餐",
    product_name: str = "餐品",
    tip: str = "请到前台取餐",
) -> dict:
    # 关键词顺序：取餐号码 → 门店名称 → 订单状态 → 商品名称 → 温馨提示
    return {
        "character_string1": {"value": _clip(pickup_no, 32) or "—"},
        "thing2": {"value": _clip(shop_name, 20) or "门店"},
        "phrase3": {"value": _clip(status_text, 5) or "可取餐"},
        "thing4": {"value": _clip(product_name, 20) or "餐品"},
        "thing5": {"value": _clip(tip, 20) or "请到前台取餐"},
    }


async def _load_customer_openid(db: AsyncSession, order: Any) -> Optional[str]:
    customer_id = getattr(order, "customer_id", None)
    if not customer_id:
        return None
    from app.models.customer import Customer

    customer = await db.get(Customer, int(customer_id))
    if not customer:
        return None
    openid = getattr(customer, "openid", None)
    return openid if is_real_wechat_openid(openid) else None


async def _load_shop_name(db: AsyncSession, entity: Any) -> str:
    tenant_id = getattr(entity, "tenant_id", None)
    if not tenant_id:
        return "门店"
    from app.models.tenant import Tenant

    # 业务表存的是 Tenant.tenant_id（字符串），不是雪花主键 id
    result = await db.execute(select(Tenant).where(Tenant.tenant_id == str(tenant_id)).limit(1))
    tenant = result.scalar_one_or_none()
    return _clip(getattr(tenant, "name", None) if tenant else None, 20) or "门店"


async def _load_first_item_name(db: AsyncSession, order: Any) -> str:
    from app.models.order import OrderItem

    order_id = getattr(order, "id", None)
    if not order_id:
        return "餐品"
    result = await db.execute(
        select(OrderItem.name).where(OrderItem.order_id == int(order_id)).limit(1)
    )
    name = result.scalar_one_or_none()
    return _clip(name, 20) or "餐品"


async def _send(openid: str, template_id: str, data: dict, *, tag: str, order_id: Any) -> bool:
    if not template_id or not openid:
        return False
    try:
        from app.services.wechat_service import WechatService

        sent = await WechatService().send_subscribe_message(
            openid=openid,
            template_id=template_id,
            data=data,
        )
        if sent:
            logger.info(f"[{tag}] sent order_id={order_id}")
        else:
            logger.warning(f"[{tag}] send returned false order_id={order_id}")
        return bool(sent)
    except Exception:
        logger.exception(f"[{tag}] send failed order_id={order_id}")
        return False


async def send_order_success_subscribe(db: AsyncSession, order: Any) -> bool:
    """支付成功后发「点餐成功通知」。无模板 / 无真实 openid 时直接跳过。"""
    template_id = (settings.WECHAT_ORDER_SUCCESS_TEMPLATE_ID or "").strip()
    if not template_id:
        return False
    try:
        openid = await _load_customer_openid(db, order)
        if not openid:
            return False
        shop_name = await _load_shop_name(db, order)
        data = build_order_success_data(
            pickup_no=resolve_pickup_no(order),
            amount=getattr(order, "total", 0),
            shop_name=shop_name,
            status_text="已支付",
            payment_time=getattr(order, "payment_time", None),
        )
        return await _send(openid, template_id, data, tag="order_success_subscribe", order_id=getattr(order, "id", None))
    except Exception:
        logger.exception(f"[order_success_subscribe] unexpected order_id={getattr(order, 'id', None)}")
        return False


async def send_pickup_reminder_subscribe(db: AsyncSession, order: Any) -> bool:
    """订单进入 done（已上餐）后发「取餐提醒」。"""
    template_id = (settings.WECHAT_PICKUP_REMINDER_TEMPLATE_ID or "").strip()
    if not template_id:
        return False
    try:
        openid = await _load_customer_openid(db, order)
        if not openid:
            return False
        shop_name = await _load_shop_name(db, order)
        product_name = await _load_first_item_name(db, order)
        data = build_pickup_reminder_data(
            pickup_no=resolve_pickup_no(order),
            shop_name=shop_name,
            status_text="可取餐",
            product_name=product_name,
            tip="请到前台取餐",
        )
        return await _send(openid, template_id, data, tag="pickup_reminder_subscribe", order_id=getattr(order, "id", None))
    except Exception:
        logger.exception(f"[pickup_reminder_subscribe] unexpected order_id={getattr(order, 'id', None)}")
        return False


def build_queue_reminder_data(
    *,
    queue_no: str,
    status_text: str = "已叫号",
    current_called: str | None = None,
    shop_name: str = "门店",
    tip: str = "请尽快到前台就坐",
) -> dict:
    # 关键词顺序：排队号 → 排队状态 → 当前叫号 → 商家名称 → 备注
    called = _clip(current_called or queue_no, 32) or "—"
    return {
        "character_string1": {"value": _clip(queue_no, 32) or "—"},
        "phrase2": {"value": _clip(status_text, 5) or "已叫号"},
        "character_string3": {"value": called},
        "thing4": {"value": _clip(shop_name, 20) or "门店"},
        "thing5": {"value": _clip(tip, 20) or "请尽快到前台就坐"},
    }


async def send_queue_reminder_subscribe(db: AsyncSession, ticket: Any) -> bool:
    """叫号后发「排队提醒」。票上无真实 openid 时跳过（店员后台取号通常无 openid）。"""
    template_id = (settings.WECHAT_QUEUE_REMINDER_TEMPLATE_ID or "").strip()
    if not template_id:
        return False
    try:
        openid = getattr(ticket, "openid", None)
        if not is_real_wechat_openid(openid):
            return False
        shop_name = await _load_shop_name(db, ticket)
        data = build_queue_reminder_data(
            queue_no=getattr(ticket, "queue_no", "") or "—",
            status_text="已叫号",
            current_called=getattr(ticket, "queue_no", None),
            shop_name=shop_name,
            tip="请尽快到前台就坐",
        )
        return await _send(
            str(openid).strip(),
            template_id,
            data,
            tag="queue_reminder_subscribe",
            order_id=getattr(ticket, "id", None),
        )
    except Exception:
        logger.exception(f"[queue_reminder_subscribe] unexpected ticket_id={getattr(ticket, 'id', None)}")
        return False
