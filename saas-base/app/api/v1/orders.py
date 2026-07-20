from datetime import date, datetime, timezone
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel as PydanticBase
from sqlalchemy import String, cast, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import settings
from app.core.database import get_db
from app.core.logger import logger
from app.core.response import error_response, success_response
from app.core.tenant_context import TenantContext
from app.models.order import Order, OrderItem
from app.services.coupon_service import CouponService

router = APIRouter(prefix="/api/v1", tags=["订单"])


PENDING_PAYMENT_TIMEOUT_MINUTES = 15  # 待支付订单超时时长（分钟）
PRINT_META_MARKER = "\n__PRINT_META__="
MAX_PRINT_RETRY_ATTEMPTS = 3

ORDER_KNOWN_STATUSES = {"pending_payment", "pending", "preparing", "done", "settled", "rejected", "cancelled"}
ORDER_MERCHANT_TARGET_STATUSES = {"pending", "preparing", "done", "settled", "rejected", "cancelled"}
ORDER_TYPE_TEXT = {
    "INITIAL": "首单",
    "ADD_ON": "加菜单",
}

ORDER_STATUS_TEXT = {
    "pending_payment": "待支付",
    "pending": "等待接单",
    "preparing": "制作中",
    "done": "已上餐",
    "settled": "已完成",
    "rejected": "已拒单",
    "cancelled": "已取消",
}
ORDER_ALLOWED_TRANSITIONS = {
    "pending": {"preparing", "rejected", "cancelled"},
    "preparing": {"done"},
    "done": {"settled"},
}

class OrderItemSpecIn(PydanticBase):
    group: str
    value: str


class OrderItemIn(PydanticBase):
    dish_id: Optional[int] = None
    name: str
    price: float  # 仅用于无 dish_id 的自定义菜品
    qty: int = 1
    specifications: Optional[List[OrderItemSpecIn]] = None  # 单选规格（如辣度/份量），按商家配置的 price_delta 计费
    extras: Optional[List[str]] = None  # 多选附加项（如加料），按商家配置的 price_delta 计费


class OrderCreate(PydanticBase):
    shop: str
    table: Optional[str] = ""
    phone: Optional[str] = None
    items: List[OrderItemIn]
    total: float  # 前端传入仅用于显示参考，后端重新从 DB 计算
    remark: Optional[str] = None
    coupon_id: Optional[int] = None
    use_balance: bool = False
    dining_session_id: Optional[int] = None
    participant_token: Optional[str] = None
    client_id: Optional[str] = None
    source: Optional[str] = "miniprogram"


class MockPayBody(PydanticBase):
    use_balance: bool = False


def _split_merchant_note_and_print_meta(raw_note: str | None) -> tuple[str | None, dict]:
    raw = raw_note or ""
    if PRINT_META_MARKER not in raw:
        return (raw.strip() or None), {}
    note, meta_raw = raw.rsplit(PRINT_META_MARKER, 1)
    try:
        meta = json.loads(meta_raw) if meta_raw.strip() else {}
        if not isinstance(meta, dict):
            meta = {}
    except Exception:
        meta = {}
    return (note.strip() or None), meta


def _compose_merchant_note_with_print_meta(note: str | None, meta: dict | None) -> str | None:
    clean_note = (note or "").strip()
    if not meta:
        return clean_note or None
    meta = dict(meta)
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    return f"{clean_note}{PRINT_META_MARKER}{json.dumps(meta, ensure_ascii=False, separators=(',', ':'))}"


def _get_print_meta(order: Order) -> dict:
    _, meta = _split_merchant_note_and_print_meta(getattr(order, "merchant_note", None))
    return meta


def _set_print_meta(order: Order, meta: dict, note: str | None = None) -> dict:
    current_note, _ = _split_merchant_note_and_print_meta(getattr(order, "merchant_note", None))
    order.merchant_note = _compose_merchant_note_with_print_meta(current_note if note is None else note, meta)
    return meta



def _db_print_status_to_meta_status(order: Order) -> str | None:
    status = str(getattr(order, "print_status", "") or "").upper()
    if status == "SUCCESS":
        return "printed"
    if status == "FAILED":
        return "failed"
    return None

def _mark_order_print_state(order: Order, status: str, printed_at=None) -> None:
    if hasattr(order, "print_status"):
        order.print_status = status
    if status == "SUCCESS" and hasattr(order, "printed_at"):
        order.printed_at = printed_at or datetime.utcnow()

def _serialize_print_meta(order: Order) -> dict:
    note, meta = _split_merchant_note_and_print_meta(getattr(order, "merchant_note", None))
    status = _db_print_status_to_meta_status(order)
    if not status:
        status = meta.get("status") if meta else None
    if not status and getattr(order, "payment_status", None) == "paid":
        status = "not_started"
    return {
        "merchant_note": note,
        "print_status": status,
        "print_attempts": int(meta.get("attempts") or 0) if meta else 0,
        "print_error_code": meta.get("last_error_code") if meta else None,
        "print_error": meta.get("last_error") if meta else None,
        "print_provider_task_id": meta.get("provider_task_id") if meta else None,
        "print_manual_reprint": bool(meta.get("manual_reprint")) if meta else False,
        "print_last_reason": meta.get("last_reason") if meta else None,
    }

def serialize_order(order: Order, order_items: list):
    print_meta = _serialize_print_meta(order)
    return {
        "id": str(order.id),
        "table_no": order.table_no,
        "phone": order.phone,
        "total": float(order.total),
        "status": order.status,
        "status_text": ORDER_STATUS_TEXT.get(order.status, order.status),
        "remark": order.remark,
        **print_meta,
        "coupon_id": str(order.coupon_id) if order.coupon_id else None,
        "discount_amount": float(order.discount_amount) if order.discount_amount else None,
        "payment_status": getattr(order, "payment_status", "paid"),
        "payment_method": getattr(order, "payment_method", None),
        "dining_session_id": str(order.dining_session_id) if getattr(order, "dining_session_id", None) else None,
        "participant_id": str(order.participant_id) if getattr(order, "participant_id", None) else None,
        "order_type": getattr(order, "order_type", None),
        "order_type_text": ORDER_TYPE_TEXT.get(getattr(order, "order_type", None), ""),
        "parent_order_id": str(order.parent_order_id) if getattr(order, "parent_order_id", None) else None,
        "source": getattr(order, "source", "miniprogram"),
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "items": [
            {
                "dish_id": str(i.dish_id) if i.dish_id else None,
                "name": i.name,
                "price": float(i.price),
                "qty": i.qty,
            }
            for i in order_items
        ],
    }

@router.post("/orders")
async def create_order(body: OrderCreate, request: Request, db: AsyncSession = Depends(get_db)):
    from datetime import datetime as _dt, timedelta
    from decimal import Decimal
    from app.models.menu_item import MenuItem
    from app.models.coupon import Coupon
    from app.models.coupon_template import CouponTemplate
    from app.api.v1.menu import load_menu_specs

    tenant_id = body.shop
    if not tenant_id:
        return error_response(code=400, msg="缺少shop参数")
    TenantContext.set_tenant_id(tenant_id)

    customer_id = getattr(request.state, "customer_id", None)
    if customer_id:
        customer_id = int(customer_id)

    dining_session_id = None
    dining_participant_id = None
    order_type = None
    parent_order_id = None
    if body.dining_session_id:
        from app.models.dining import DiningParticipant, DiningSession
        from app.services.dining_session_service import hash_participant_token

        session_result = await db.execute(
            select(DiningSession).where(
                DiningSession.id == int(body.dining_session_id),
                DiningSession.tenant_id == tenant_id,
                DiningSession.table_no == (body.table or ""),
                DiningSession.status == "OPEN",
            )
        )
        session = session_result.scalar_one_or_none()
        if not session:
            return error_response(code=400, msg="dining session not found")

        participant_filters = [
            DiningParticipant.tenant_id == tenant_id,
            DiningParticipant.session_id == session.id,
        ]
        if body.participant_token:
            participant_filters.append(DiningParticipant.guest_token_hash == hash_participant_token(body.participant_token))
        elif customer_id:
            participant_filters.append(DiningParticipant.customer_id == customer_id)
        elif body.client_id:
            participant_filters.append(DiningParticipant.client_id == body.client_id)
        else:
            return error_response(code=400, msg="缺少本桌身份，请重新扫码")

        participant_result = await db.execute(select(DiningParticipant).where(*participant_filters))
        participant = participant_result.scalar_one_or_none()
        if not participant:
            return error_response(code=403, msg="participant invalid")

        dining_session_id = session.id
        dining_participant_id = participant.id
        existing_order_result = await db.execute(
            select(Order)
            .where(
                Order.tenant_id == tenant_id,
                Order.dining_session_id == session.id,
                Order.payment_status == "paid",
                Order.status.notin_(["cancelled", "rejected"]),
            )
            .order_by(Order.created_at.asc())
            .limit(1)
        )
        parent_order = existing_order_result.scalar_one_or_none()
        order_type = "ADD_ON" if parent_order else "INITIAL"
        parent_order_id = parent_order.id if parent_order else None
        participant.last_active_at = _dt.utcnow()
        session.last_activity_at = _dt.utcnow()

    applied_coupon_id = None
    coupon_discount = Decimal("0")

    # BUG-4: 处理超时待支付订单，恢复优惠券
    timeout_threshold = _dt.utcnow() - timedelta(minutes=PENDING_PAYMENT_TIMEOUT_MINUTES)
    stale_result = await db.execute(
        select(Order).where(
            Order.tenant_id == tenant_id,
            Order.status == "pending_payment",
            Order.created_at < timeout_threshold,
        )
    )
    stale_orders = stale_result.scalars().all()
    for stale in stale_orders:
        recovered = await _recover_wxpay_order_if_paid(stale, db)
        if recovered:
            continue
        stale.status = "cancelled"
        if stale.coupon_id:
            stale_coupon = await db.get(Coupon, stale.coupon_id)
            if stale_coupon and stale_coupon.status == "LOCKED":
                stale_coupon.status = "UNUSED"
    if stale_orders:
        await db.flush()

    # 从 DB 重新计算价格、检查客户归属/下架状态，检查并扣减库存（with_for_update 防超卖）
    if not body.items:
        return error_response(code=400, msg="订单商品不能为空")

    specs_map = await load_menu_specs(db, tenant_id)

    def _resolve_spec_delta(dish: "MenuItem", item_in: "OrderItemIn") -> float:
        """Recompute the spec/extra surcharge from the merchant-configured spec_groups
        (source of truth), never from the client-submitted price."""
        group_defs = specs_map.get(str(dish.id)) or []
        if not group_defs:
            if item_in.specifications or item_in.extras:
                raise ValueError(f"该商品不支持规格选择:{item_in.name}")
            return 0.0

        radio_lookup: dict[str, dict[str, float]] = {}
        checkbox_lookup: dict[str, float] = {}
        for g in group_defs:
            g_type = g.get("type") or ("multi" if g.get("multiple") else "single")
            options = g.get("options") or g.get("values") or []
            opt_map = {}
            for o in options:
                if isinstance(o, str):
                    opt_map[o] = 0.0
                else:
                    oname = o.get("name") or o.get("value") or o.get("label")
                    if oname:
                        opt_map[oname] = float(o.get("price_delta") or o.get("extra_price") or 0)
            if g_type in ("multi", "multiple", "checkbox"):
                checkbox_lookup.update(opt_map)
            else:
                radio_lookup[g.get("name") or g.get("group") or g.get("title") or ""] = opt_map

        delta = 0.0
        for spec_sel in (item_in.specifications or []):
            opt_map = radio_lookup.get(spec_sel.group)
            if opt_map is None or spec_sel.value not in opt_map:
                raise ValueError(f"无效的规格选择:{item_in.name}")
            delta += opt_map[spec_sel.value]
        for extra_name in (item_in.extras or []):
            if extra_name not in checkbox_lookup:
                raise ValueError(f"无效的附加选项:{item_in.name}")
            delta += checkbox_lookup[extra_name]
        return delta

    real_total = 0.0
    order_items_data = []
    stock_deductions = []  # [(dish, qty)]
    for item_in in body.items:
        if item_in.qty <= 0:
            return error_response(code=400, msg=f"商品数量必须大于0:{item_in.name}")

        if item_in.dish_id:
            dish_result = await db.execute(
                select(MenuItem)
                .where(MenuItem.id == item_in.dish_id, MenuItem.tenant_id == tenant_id)
                .with_for_update()
            )
            dish = dish_result.scalar_one_or_none()
            if not dish:
                return error_response(code=400, msg=f"鑿滃搧涓嶅瓨鍦?{item_in.name}")
            if not dish.available:
                return error_response(code=400, msg=f"鑿滃搧宸蹭笅鏋?{dish.name}")
            if dish.stock is not None and dish.stock <= 0:
                return error_response(code=400, msg=f"dish sold out: {dish.name}")
            if dish.stock is not None and dish.stock < item_in.qty:
                return error_response(code=400, msg=f"dish stock not enough: {dish.name}, left {dish.stock}")
            try:
                spec_delta = _resolve_spec_delta(dish, item_in)
            except ValueError as exc:
                return error_response(code=400, msg=str(exc))
            unit_price = float(dish.price) + spec_delta
            base_name = str(dish.name or "")
            submitted_name = str(item_in.name or "").strip()
            name = submitted_name[:64] if submitted_name and submitted_name.startswith(base_name) else base_name
            if dish.stock is not None:
                stock_deductions.append((dish, item_in.qty))
        else:
            return error_response(code=400, msg=f"缺少菜品ID:{item_in.name}")
        real_total += unit_price * item_in.qty
        order_items_data.append((item_in.dish_id, name, unit_price, item_in.qty))

    # 扣减库存
    for dish, qty in stock_deductions:
        dish.stock = max(0, dish.stock - qty)

    # BUG-2: 建单时仅验证优惠券，不标记 USED，改为 LOCKED（支付时再核销）
    if body.coupon_id:
        if not customer_id:
            return error_response(code=401, msg="请先登录后使用优惠券")
        coupon_result = await db.execute(
            select(Coupon).where(
                Coupon.id == body.coupon_id,
                Coupon.customer_id == customer_id,
                Coupon.tenant_id == tenant_id,
                Coupon.status == "UNUSED",
                Coupon.expire_time > _dt.utcnow(),
            )
        )
        coupon = coupon_result.scalar_one_or_none()
        if not coupon:
            return error_response(code=400, msg="优惠券不可用或已失效")

        tpl = await db.get(CouponTemplate, coupon.template_id)
        if not tpl:
            return error_response(code=400, msg="优惠券规则不存在")

        min_amount = float(tpl.min_amount or 0)
        if real_total < min_amount:
            return error_response(code=400, msg="未达到优惠券使用门槛")

        coupon_discount = Decimal(str(tpl.value or 0))
        coupon.status = "LOCKED"
        applied_coupon_id = coupon.id

    final_total = max(real_total - float(coupon_discount), 0)

    order = Order(
        tenant_id=tenant_id,
        customer_id=customer_id,
        dining_session_id=dining_session_id,
        participant_id=dining_participant_id,
        order_type=order_type,
        parent_order_id=parent_order_id,
        table_no=body.table or "",
        phone=body.phone,
        total=final_total,
        status="pending_payment",
        payment_status="unpaid",
        remark=body.remark,
        coupon_id=applied_coupon_id,
        discount_amount=float(coupon_discount) if coupon_discount > 0 else None,
        source=body.source or "miniprogram",
    )
    db.add(order)
    await db.flush()

    order_items = []
    for dish_id, name, unit_price, qty in order_items_data:
        oi = OrderItem(
            order_id=order.id,
            dish_id=dish_id,
            name=name,
            price=unit_price,
            qty=qty,
        )
        db.add(oi)
        order_items.append(oi)

    await db.commit()
    await db.refresh(order)

    # 余额可用数（仅显示，实际扣除在支付接口）
    balance_available = 0.0
    if customer_id and body.use_balance:
        from app.models.member_account import MemberAccount
        acc_result = await db.execute(
            select(MemberAccount).where(MemberAccount.tenant_id == tenant_id, MemberAccount.customer_id == customer_id)
        )
        acc = acc_result.scalar_one_or_none()
        if acc:
            balance_available = min(float(acc.balance), float(final_total))

    return success_response(
        data={
            **serialize_order(order, order_items),
            "need_payment": True,
            "pay_amount": float(final_total),
            "balance_available": balance_available,
        },
        msg="order created, please pay",
    )



async def _recover_wxpay_order_if_paid(order: Order, db: AsyncSession) -> bool:
    """Recover paid orders when WeChat callback is delayed or lost."""
    if not order or order.status != "pending_payment":
        return False
    try:
        from app.models.tenant import Tenant
        from app.services.wxpay_service import WxPayService

        tenant_result = await db.execute(select(Tenant).where(Tenant.tenant_id == str(order.tenant_id)))
        tenant = tenant_result.scalar_one_or_none()
        svc = WxPayService(tenant) if tenant else None
        if not svc or not svc.enabled:
            return False

        pay_resource = await svc.query_order_by_out_trade_no(str(order.id))
        if not pay_resource or pay_resource.get("trade_state") != "SUCCESS":
            return False

        locked_result = await db.execute(select(Order).where(Order.id == order.id).with_for_update())
        locked_order = locked_result.scalar_one_or_none()
        if not locked_order or locked_order.status != "pending_payment":
            return False

        _pending_balance = getattr(locked_order, "balance_deduct_requested", None)
        use_balance_flag = bool(_pending_balance and float(_pending_balance) > 0)
        await _on_payment_success(locked_order, db, use_balance=use_balance_flag, payment_method="wxpay")
        logger.warning(
            "[WXPAY_ORDER_RECOVERED] order_id=%s transaction_id=%s out_trade_no=%s",
            locked_order.id,
            pay_resource.get("transaction_id") or "",
            pay_resource.get("out_trade_no") or str(locked_order.id),
        )
        return True
    except Exception as exc:
        logger.warning("[WXPAY_ORDER_RECOVERY_FAILED] order_id=%s error=%s", getattr(order, "id", ""), exc)
        return False

async def _print_paid_order_ticket(
    order: Order,
    db: AsyncSession,
    *,
    manual: bool = False,
    reason: str = "auto",
) -> dict:
    """Print a paid order and persist recoverable print state in existing order metadata."""
    if not order or getattr(order, "payment_status", None) != "paid":
        return {"success": False, "skipped": True, "code": "ORDER_NOT_PAID"}

    locked_result = await db.execute(select(Order).where(Order.id == order.id).with_for_update())
    locked_order = locked_result.scalar_one_or_none()
    if locked_order:
        order = locked_order
    if getattr(order, "payment_status", None) != "paid":
        return {"success": False, "skipped": True, "code": "ORDER_NOT_PAID"}

    meta = _get_print_meta(order)
    db_print_status = str(getattr(order, "print_status", "") or "").upper()
    if not manual and (db_print_status == "SUCCESS" or meta.get("status") == "printed"):
        logger.warning(
            "[PRINT_SKIPPED_ALREADY_SUCCESS] order_id=%s print_status=%s status=%s attempts=%s provider_task_id=%s",
            order.id,
            db_print_status or "",
            meta.get("status"),
            meta.get("attempts", 0),
            meta.get("provider_task_id"),
        )
        logger.warning(
            "[PRINT_IDEMPOTENT_HIT] order_id=%s reason=%s manual=%s",
            order.id,
            reason,
            manual,
        )
        return {"success": True, "skipped": True, "status": "printed"}

    attempts = int(meta.get("attempts") or 0)
    if not manual and attempts >= MAX_PRINT_RETRY_ATTEMPTS:
        logger.warning(
            "[PRINT_ORDER_RETRY_LIMIT] order_id=%s attempts=%s last_error_code=%s",
            order.id,
            attempts,
            meta.get("last_error_code"),
        )
        return {"success": False, "skipped": True, "code": "PRINT_RETRY_LIMIT"}

    if attempts == 0 and not manual:
        logger.warning(
            "[PRINT_FIRST_EXECUTION] order_id=%s attempts=%s reason=%s manual=%s",
            order.id,
            attempts + 1,
            reason,
            manual,
        )
    meta.update({
        "status": "printing",
        "attempts": attempts + 1,
        "last_reason": reason,
        "manual_reprint": bool(meta.get("manual_reprint")) or manual,
    })
    _mark_order_print_state(order, "PENDING")
    _set_print_meta(order, meta)
    await db.flush()

    try:
        from app.models.tenant import Tenant
        from app.models.tenant_config import TenantConfig
        from app.models.order import OrderItem
        from app.services.feieyun_service import build_order_ticket, print_order

        tenant_result = await db.execute(select(Tenant).where(Tenant.tenant_id == str(order.tenant_id)))
        tenant_obj = tenant_result.scalar_one_or_none()
        config_result = await db.execute(select(TenantConfig).where(TenantConfig.tenant_id == str(order.tenant_id)))
        config_obj = config_result.scalar_one_or_none()
        business_info = (config_obj.business_info or {}) if config_obj else {}
        provider = business_info.get("printer_provider") or "feieyun"
        provider_task_id = None

        if provider == "kuaimai":
            from app.services.kuaimai_service import (
                KUAIMAI_ORDER_TEMPLATE_ID,
                build_order_template_render_data,
                print_template_order,
                validate_order_template_render_data,
            )

            kuaimai = business_info.get("kuaimai_printer") or {}
            configured_template_id = str(kuaimai.get("order_template_id") or "").strip()
            kuaimai_template_id = configured_template_id or KUAIMAI_ORDER_TEMPLATE_ID
            logger.warning(
                "[ORDER_PRINT_TEMPLATE_ID_CHECK] order_id=%s tenant_id=%s configured_order_template_id=%s effective_template_id=%s default_order_template_id=%s manual=%s reason=%s",
                order.id,
                order.tenant_id,
                configured_template_id or "",
                kuaimai_template_id,
                KUAIMAI_ORDER_TEMPLATE_ID,
                manual,
                reason,
            )

            items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
            order_items = list(items_result.scalars().all())
            render_data = build_order_template_render_data(
                order,
                order_items,
                shop_name=getattr(tenant_obj, "name", "") if tenant_obj else "",
            )
            item_names = [item.get("goods_name") for item in render_data.get("items", [])]
            logger.warning(
                "[PRINT_ORDER_PAYLOAD] event=print_order_payload order_id=%s order_no=%s merchant_id=%s printer_id=%s template_id=%s items_count=%s item_names=%s total_amount=%s pay_amount=%s data_sources=%s manual=%s reason=%s",
                order.id,
                render_data.get("order_no"),
                order.tenant_id,
                kuaimai.get("sn") or "",
                kuaimai_template_id,
                len(render_data.get("items", [])),
                item_names,
                render_data.get("total_amount"),
                render_data.get("pay_amount"),
                ["items", "goods"],
                manual,
                reason,
            )

            valid, error_code = validate_order_template_render_data(render_data, order)
            if not valid:
                logger.warning(
                    "[PRINT_ORDER_VALIDATE_FAILED] order_id=%s order_no=%s merchant_id=%s printer_id=%s template_id=%s items_type=%s items_count=%s error_code=%s",
                    order.id,
                    render_data.get("order_no"),
                    order.tenant_id,
                    kuaimai.get("sn") or "",
                    kuaimai_template_id,
                    type(render_data.get("items")).__name__,
                    len(render_data.get("items", [])) if isinstance(render_data.get("items"), list) else "n/a",
                    error_code,
                )
                raise RuntimeError(error_code)

            result = await print_template_order(
                kuaimai.get("app_id") or "",
                kuaimai.get("app_secret") or "",
                kuaimai.get("sn") or "",
                kuaimai_template_id,
                render_data,
            )
            if not result or result.get("success") is not True:
                raise RuntimeError(result.get("code") or result.get("error") or "PRINT_PROVIDER_FAILED")
            provider_task_id = result.get("provider_task_id")
        elif tenant_obj and tenant_obj.feieyun_sn and tenant_obj.feieyun_key:
            ticket = build_order_ticket(order)
            result = await print_order(tenant_obj.feieyun_sn, tenant_obj.feieyun_key, ticket)
            if result is not True:
                raise RuntimeError("FEIEYUN_PRINT_FAILED")
        else:
            raise RuntimeError("PRINTER_CONFIG_INCOMPLETE")

        meta.update({
            "status": "printed",
            "last_error_code": None,
            "last_error": None,
            "provider_task_id": provider_task_id,
            "printed_at": datetime.now(timezone.utc).isoformat(),
            "manual_reprint": bool(meta.get("manual_reprint")) or manual,
        })
        _mark_order_print_state(order, "SUCCESS")
        _set_print_meta(order, meta)
        logger.warning(
            "[PRINT_ORDER_SUCCESS] order_id=%s attempts=%s provider_task_id=%s manual=%s reason=%s",
            order.id,
            meta.get("attempts"),
            provider_task_id,
            manual,
            reason,
        )
        return {"success": True, "status": "printed", "attempts": meta.get("attempts"), "provider_task_id": provider_task_id}
    except Exception as exc:
        error_code = getattr(exc, "code", None) or str(exc) or type(exc).__name__
        meta.update({
            "status": "failed",
            "last_error_code": error_code,
            "last_error": str(exc),
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "manual_reprint": bool(meta.get("manual_reprint")) or manual,
        })
        _mark_order_print_state(order, "FAILED")
        _set_print_meta(order, meta)
        logger.warning(
            "[PRINT_ORDER_FAILED_RECOVERABLE] order_id=%s attempts=%s error_code=%s manual=%s reason=%s",
            order.id,
            meta.get("attempts"),
            error_code,
            manual,
            reason,
        )
        return {"success": False, "status": "failed", "attempts": meta.get("attempts"), "code": error_code}

async def _on_payment_success(
    order: Order,
    db: AsyncSession,
    use_balance: bool = False,
    payment_method: str = "wxpay",
) -> tuple:
    """Run shared post-payment logic."""
    from app.models.coupon import Coupon

    customer_id = order.customer_id
    TenantContext.set_tenant_id(str(order.tenant_id))
    coupon_data = None

    # Coupon write-off
    if order.coupon_id and customer_id:
        locked_coupon_result = await db.execute(
            select(Coupon)
            .where(
                Coupon.id == order.coupon_id,
                Coupon.tenant_id == str(order.tenant_id),
                Coupon.customer_id == int(customer_id),
            )
            .with_for_update()
        )
        locked_coupon = locked_coupon_result.scalar_one_or_none()
        if locked_coupon and locked_coupon.status == "LOCKED":
            locked_coupon.status = "USED"
            locked_coupon.use_time = datetime.now(timezone.utc)
        elif locked_coupon and locked_coupon.status != "USED":
            order.coupon_id = None
            order.discount_amount = None
    elif order.coupon_id:
        order.coupon_id = None
        order.discount_amount = None

    # 余额抵扣
    balance_deducted = 0.0
    if use_balance and customer_id:
        from app.models.member_account import MemberAccount
        acc_result = await db.execute(
            select(MemberAccount).where(
                MemberAccount.tenant_id == str(order.tenant_id),
                MemberAccount.customer_id == int(customer_id)
            ).with_for_update()
        )
        acc = acc_result.scalar_one_or_none()
        if acc and float(acc.balance) > 0:
            cap = float(order.balance_deduct_requested) if getattr(order, "balance_deduct_requested", None) is not None else float(order.total)
            deduct = min(float(acc.balance), cap)
            acc.balance = float(acc.balance) - deduct
            balance_deducted = deduct

    # 支付成功后，这个字段从"计划抵扣多少余额"改为"实际抵扣了多少余额"，供退款时准确拆分微信/余额两部分。
    order.balance_deduct_requested = balance_deducted if balance_deducted > 0 else None

    # 标记支付成功
    effective_method = "balance" if balance_deducted >= float(order.total) else payment_method
    order.payment_status = "paid"
    order.payment_method = effective_method
    order.payment_time = datetime.now(timezone.utc).isoformat()
    order.status = "pending"
    await db.flush()


    # Coupon issuance and points are post-payment side effects.
    if customer_id:
        try:
            svc = CouponService(db)
            order_count_result = await db.execute(
                select(Order).where(
                    Order.tenant_id == order.tenant_id,
                    Order.customer_id == int(customer_id),
                    Order.payment_status == "paid",
                    Order.id != order.id,
                ).limit(1)
            )
            is_new_customer = order_count_result.scalar_one_or_none() is None
            rule_type = "new_customer_coupon" if is_new_customer else "consumption_coupon"
            coupon_data = await svc.issue_auto_coupon(
                int(customer_id), rule_type, consumption_amount=float(order.total)
            )
        except Exception as e:
            logger.warning(f"post-payment coupon failed: {e}")

        try:
            from app.services.membership_service import MembershipService
            from app.services.customer_service import CustomerService
            membership_svc = MembershipService(db)
            customer_obj = await CustomerService(db).get_customer(int(customer_id))
            if customer_obj:
                await membership_svc.apply_consumption(
                    customer_obj, float(order.total), consumption_id=order.id
                )
        except Exception as e:
            logger.warning(f"post-payment points failed: {e}")

    # Print order ticket after payment. Printing failures are recoverable and must not affect payment state.
    await _print_paid_order_ticket(order, db, reason="payment_success")
    return coupon_data, balance_deducted


async def _refund_order_payment(order: Order, db: AsyncSession, reason: str) -> dict:
    """Refund a paid order's money before flipping it to a terminal cancelled/rejected state.

    Must be called with `order` already locked (with_for_update) in the current transaction.
    Restores the balance-paid portion directly; submits a WeChat refund request for the
    WeChat-charged portion. Uses a deterministic out_refund_no so retrying this call is safe
    (WeChat treats a repeated out_refund_no as the same refund request, not a new one).

    Returns {"success": bool, "amount": float, "error": str | None}.
    """
    if getattr(order, "payment_status", None) != "paid":
        return {"success": True, "amount": 0.0, "error": None}
    if getattr(order, "refund_status", None) == "success":
        return {"success": True, "amount": float(order.refund_amount or 0), "error": None}

    total = float(order.total or 0)
    balance_portion = float(order.balance_deduct_requested or 0)
    if balance_portion <= 0 and order.payment_method == "balance":
        # Legacy orders paid before balance_deduct_requested tracked the actual amount.
        balance_portion = total
    wechat_portion = max(total - balance_portion, 0.0)
    refunded_amount = 0.0

    if balance_portion > 0 and order.customer_id:
        from app.models.member_account import MemberAccount

        acc_result = await db.execute(
            select(MemberAccount).where(
                MemberAccount.tenant_id == str(order.tenant_id),
                MemberAccount.customer_id == int(order.customer_id),
            ).with_for_update()
        )
        acc = acc_result.scalar_one_or_none()
        if acc:
            acc.balance = float(acc.balance) + balance_portion
            refunded_amount += balance_portion

    if wechat_portion > 0 and order.payment_method == "wxpay":
        try:
            from app.models.tenant import Tenant
            from app.services.wxpay_service import WxPayService

            tenant_result = await db.execute(select(Tenant).where(Tenant.tenant_id == str(order.tenant_id)))
            tenant = tenant_result.scalar_one_or_none()
            svc = WxPayService(tenant) if tenant else None
            if not svc or not svc.enabled:
                raise RuntimeError("shang hu wei pei zhi wei xin zhi fu, wu fa zi dong tui kuan")
            wechat_fen = max(1, round(wechat_portion * 100))
            await svc.refund(
                out_trade_no=str(order.id),
                out_refund_no=f"RF{order.id}",
                refund_fen=wechat_fen,
                total_fen=wechat_fen,
                reason=reason,
            )
            refunded_amount += wechat_portion
        except Exception as exc:
            order.refund_status = "failed"
            order.refund_error = str(exc)[:500]
            logger.error("[REFUND_FAILED] order_id=%s error=%s", order.id, exc)
            return {"success": False, "amount": refunded_amount, "error": str(exc)}

    order.refund_status = "success"
    order.refund_amount = refunded_amount
    order.refunded_at = datetime.now(timezone.utc)
    order.refund_error = None
    logger.info(
        "[REFUND_SUCCESS] order_id=%s amount=%s balance_portion=%s wechat_portion=%s reason=%s",
        order.id, refunded_amount, balance_portion, wechat_portion, reason,
    )
    return {"success": True, "amount": refunded_amount, "error": None}


@router.post("/orders/{order_id}/mock-pay")
async def mock_pay_order(
    order_id: str,
    body: MockPayBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Mock payment for development only."""
    import traceback
    # 不用 settings.DEBUG 判断：这个项目实际部署环境里 DEBUG=true，不能拿来当
    # "是否生产环境"的依据，必须用一个默认关闭、需要显式开启的独立开关。
    if not settings.ALLOW_MOCK_MONEY_ENDPOINTS:
        return error_response(code=403, msg="mock pay is only available in debug mode")
    try:
        customer_id = getattr(request.state, "customer_id", None)
        result = await db.execute(select(Order).where(Order.id == int(order_id)).with_for_update())
        order = result.scalar_one_or_none()
        if not order:
            return error_response(code=404, msg="order not found")
        if order.status != "pending_payment":
            return error_response(code=400, msg="该订单已支付或已取消")
        if order.customer_id and (not customer_id or int(customer_id) != int(order.customer_id)):
            return error_response(code=403, msg="forbidden")

        coupon_data, balance_deducted = await _on_payment_success(
            order, db, use_balance=body.use_balance, payment_method="mock"
        )
        await db.commit()
        await db.refresh(order)

        items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
        order_items = list(items_result.scalars().all())

        return success_response(
            data={**serialize_order(order, order_items), "coupon": coupon_data, "balance_deducted": balance_deducted},
            msg="支付成功",
        )
    except Exception as e:
        logger.error(f"mock_pay_order error: {e}\n{traceback.format_exc()}")
        return error_response(code=500, msg=f"支付处理失败: {str(e)}")


class WxPayBody(PydanticBase):
    use_balance: bool = False
    js_code: Optional[str] = None


@router.post("/orders/{order_id}/pay")
async def create_wxpay_order(
    order_id: str,
    body: WxPayBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a WeChat JSAPI payment order for direct merchant mode."""
    import traceback
    from fastapi import HTTPException
    try:
        from app.models.tenant import Tenant
        from app.services.wxpay_service import WxPayService

        customer_id = getattr(request.state, "customer_id", None)
        openid = getattr(request.state, "openid", None)

        result = await db.execute(select(Order).where(Order.id == int(order_id)))
        order = result.scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail={"success": False, "code": "ORDER_NOT_FOUND", "message": "order not found"})
        if order.status != "pending_payment":
            raise HTTPException(status_code=400, detail={"success": False, "code": "ORDER_ALREADY_PAID", "message": "该订单已支付或已取消"})
        if customer_id and order.customer_id and int(customer_id) != int(order.customer_id):
            raise HTTPException(status_code=403, detail={"success": False, "code": "FORBIDDEN", "message": "forbidden"})

        # Load merchant payment config
        tenant_result = await db.execute(select(Tenant).where(Tenant.tenant_id == order.tenant_id))
        tenant = tenant_result.scalar_one_or_none()

        pay_amount = float(order.total)

        # 尝试余额抵扣：若全额覆盖，直接走 mock 流程
        balance_cover = False
        partial_balance_amount = 0.0
        if body.use_balance and customer_id:
            from app.models.member_account import MemberAccount
            acc_result = await db.execute(
                select(MemberAccount).where(MemberAccount.tenant_id == str(order.tenant_id), MemberAccount.customer_id == int(customer_id))
            )
            acc = acc_result.scalar_one_or_none()
            if acc and float(acc.balance) > 0:
                if float(acc.balance) >= pay_amount:
                    balance_cover = True
                else:
                    partial_balance_amount = float(acc.balance)

        if balance_cover:
            locked_order_result = await db.execute(
                select(Order).where(Order.id == int(order_id)).with_for_update()
            )
            order = locked_order_result.scalar_one_or_none()
            if not order:
                raise HTTPException(status_code=404, detail={"success": False, "code": "ORDER_NOT_FOUND", "message": "order not found"})
            if order.status != "pending_payment":
                logger.warning("[PAYMENT_IDEMPOTENCY_BALANCE_ALREADY_HANDLED] order_id=%s status=%s", order_id, order.status)
                raise HTTPException(status_code=400, detail={"success": False, "code": "ORDER_ALREADY_PAID", "message": "该订单已支付或已取消"})
            coupon_data, balance_deducted = await _on_payment_success(
                order, db, use_balance=True, payment_method="balance"
            )
            await db.commit()
            await db.refresh(order)
            items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
            order_items = list(items_result.scalars().all())
            return success_response(
                data={
                    **serialize_order(order, order_items),
                    "free": True,
                    "coupon": coupon_data,
                    "balance_deducted": balance_deducted,
                },
                msg="余额支付成功",
            )

        if partial_balance_amount > 0:
            pay_amount = round(pay_amount - partial_balance_amount, 2)

        # 订单实际应付金额已被优惠券/余额抵扣到 0，无需发起微信支付（不再强行收 1 分钱），也不依赖商家是否配置了微信支付
        if pay_amount <= 0:
            locked_order_result = await db.execute(
                select(Order).where(Order.id == int(order_id)).with_for_update()
            )
            order = locked_order_result.scalar_one_or_none()
            if not order or order.status != "pending_payment":
                raise HTTPException(status_code=400, detail={"success": False, "code": "ORDER_ALREADY_PAID", "message": "order already paid or cancelled"})
            order.balance_deduct_requested = partial_balance_amount if partial_balance_amount > 0 else None
            free_coupon_data, free_balance_deducted = await _on_payment_success(
                order, db,
                use_balance=partial_balance_amount > 0,
                payment_method="balance" if partial_balance_amount > 0 else "free",
            )
            await db.commit()
            await db.refresh(order)
            free_items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
            free_order_items = list(free_items_result.scalars().all())
            return success_response(
                data={
                    **serialize_order(order, free_order_items),
                    "free": True,
                    "coupon": free_coupon_data,
                    "balance_deducted": free_balance_deducted,
                },
                msg="订单已完成，无需支付",
            )

        # 商家配置自己的微信支付
        svc = WxPayService(tenant) if tenant else None
        if svc and svc.enabled:
            locked_order_result = await db.execute(
                select(Order).where(Order.id == int(order_id)).with_for_update()
            )
            order = locked_order_result.scalar_one_or_none()
            if not order or order.status != "pending_payment":
                raise HTTPException(status_code=400, detail={"success": False, "code": "ORDER_ALREADY_PAID", "message": "order already paid or cancelled"})
            order.balance_deduct_requested = partial_balance_amount if partial_balance_amount > 0 else None
            await db.commit()

            if not openid and body.js_code:
                from app.services.wechat_service import WechatService
                wechat_result = await WechatService().code2session(body.js_code)
                openid = wechat_result.get("openid")
            if not openid:
                raise HTTPException(status_code=400, detail={"success": False, "code": "NEED_WECHAT_CODE", "message": "缺少微信支付身份，请重新发起支付"})
            amount_fen = max(1, round(pay_amount * 100))
            notify_url = f"{settings.H5_ORDER_BASE_URL}/api/v1/orders/wxpay-notify"
            pay_params = await svc.create_jsapi_order(
                openid=openid,
                out_trade_no=str(order.id),
                amount_fen=amount_fen,
                description=f"{tenant.name}-点餐订单",
                notify_url=notify_url,
            )
            required_fields = ["timeStamp", "nonceStr", "package", "signType", "paySign"]
            if not pay_params or any(f not in pay_params for f in required_fields):
                missing_fields = [f for f in required_fields if f not in (pay_params or {})]
                logger.error(
                    "[WXPAY_PARAMS_INVALID] order_id=%s tenant_id=%s pay_params_type=%s missing_fields=%s pay_params=%s",
                    order.id, order.tenant_id, type(pay_params).__name__, missing_fields, str(pay_params)[:500] if pay_params else None,
                )
                raise HTTPException(status_code=502, detail={"success": False, "code": "WXPAY_PARAMS_INVALID", "message": "微信支付参数生成失败"})
            return success_response(
                data={"pay_params": pay_params, "free": False, "order_id": str(order.id)},
                msg="please request WeChat payment",
            )

        logger.warning(
            "[WXPAY_NOT_CONFIGURED] tenant_id=%s order_id=%s debug=%s wx_pay_enabled=%s wx_mchid_configured=%s",
            order.tenant_id,
            order.id,
            settings.DEBUG,
            bool(getattr(tenant, "wx_pay_enabled", False)) if tenant else False,
            bool(getattr(tenant, "wx_mchid", None)) if tenant else False,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "code": "WXPAY_NOT_CONFIGURED",
                "message": "wechat pay not configured",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"create_wxpay_order error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail={"success": False, "code": "PAYMENT_INTERNAL_ERROR", "message": "支付服务异常，请稍后重试"})


@router.post("/orders/wxpay-notify")
async def wxpay_notify(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle WeChat Pay notify for direct merchant mode."""
    import traceback
    import json as _json
    from app.models.tenant import Tenant
    from app.services.wxpay_service import WxPayService
    try:
        headers = dict(request.headers)
        raw_body = await request.body()

        resource = None
        tenant_id = request.query_params.get("tenant_id")
        matched_tenant = None
        if tenant_id:
            tenant_result = await db.execute(
                select(Tenant).where(
                    Tenant.tenant_id == tenant_id,
                    Tenant.wx_pay_enabled == True,
                    Tenant.wx_mchid.isnot(None),
                )
            )
            matched_tenant = tenant_result.scalar_one_or_none()
            if matched_tenant:
                svc = WxPayService(matched_tenant)
                if svc.enabled:
                    resource = svc.verify_notify(headers, raw_body)

        # Backward compatibility for old notify_url without tenant_id.
        if not resource:
            tenant_result = await db.execute(
                select(Tenant).where(Tenant.wx_pay_enabled == True, Tenant.wx_mchid.isnot(None))
            )
            tenants = tenant_result.scalars().all()
            for t in tenants:
                svc = WxPayService(t)
                if not svc.enabled:
                    continue
                resource = svc.verify_notify(headers, raw_body)
                if resource:
                    matched_tenant = t
                    break
        if not resource:
            logger.warning("wxpay notify verify failed: no matched merchant cert")
            return {"code": "FAIL", "message": "验证失败"}

        out_trade_no = resource.get("out_trade_no", "")
        trade_state = resource.get("trade_state", "")
        if trade_state != "SUCCESS":
            return {"code": "SUCCESS", "message": "ok"}

        result = await db.execute(select(Order).where(Order.id == int(out_trade_no)).with_for_update())
        order = result.scalar_one_or_none()
        if not order or order.status != "pending_payment":
            return {"code": "SUCCESS", "message": "ok"}
        if matched_tenant and str(order.tenant_id) != str(matched_tenant.tenant_id):
            logger.warning(
                f"wxpay notify tenant mismatch: order_id={out_trade_no} "
                f"order_tenant_id={order.tenant_id} notify_tenant_id={matched_tenant.tenant_id}"
            )
            return {"code": "FAIL", "message": "tenant mismatch"}

        _pending_balance = getattr(order, "balance_deduct_requested", None)
        use_balance_flag = bool(_pending_balance and float(_pending_balance) > 0)
        await _on_payment_success(order, db, use_balance=use_balance_flag, payment_method="wxpay")
        await db.commit()
        logger.info(f"微信支付回调成功: order_id={out_trade_no}")
        return {"code": "SUCCESS", "message": "ok"}

    except Exception as e:
        logger.error(f"wxpay_notify error: {e}\n{traceback.format_exc()}")
        return {"code": "FAIL", "message": str(e)}


class OrderStatusUpdate(PydanticBase):
    status: str  # pending | preparing | done | settled


@router.patch("/orders/{order_id}/status")
async def update_order_status(
    order_id: str,
    body: OrderStatusUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    tenant_id = getattr(request.state, "tenant_id", None)
    token_type = getattr(request.state, "token_type", None)
    if not tenant_id or token_type != "merchant":
        return error_response(code=401, msg="请先登录")
    if body.status not in ORDER_MERCHANT_TARGET_STATUSES:
        return error_response(code=400, msg="invalid status")
    TenantContext.set_tenant_id(tenant_id)
    result = await db.execute(
        select(Order).where(Order.id == int(order_id), Order.tenant_id == tenant_id).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        return error_response(code=404, msg="order not found")

    current_status = order.status or "pending"
    if current_status == body.status:
        return success_response(
            data={"id": str(order.id), "status": order.status, "idempotent": True},
            msg="状态未变化",
        )
    if body.status not in ORDER_ALLOWED_TRANSITIONS.get(current_status, set()):
        return error_response(code=409, msg=f"illegal status transition: {current_status}->{body.status}")

    if body.status in ("rejected", "cancelled") and getattr(order, "payment_status", None) == "paid":
        refund_result = await _refund_order_payment(order, db, reason=f"merchant_{body.status}")
        if not refund_result["success"]:
            await db.rollback()
            return error_response(code=502, msg=f"操作失败，退款处理异常，请稍后重试：{refund_result['error']}")

    order.status = body.status
    if body.status == "done" and not getattr(order, "served_at", None):
        order.served_at = datetime.utcnow()
    if body.status == "settled" and not getattr(order, "completed_at", None):
        order.completed_at = datetime.utcnow()
    await db.commit()
    await db.refresh(order)
    return success_response(data={"id": str(order.id), "status": order.status}, msg="状态已更新")

TABLE_CLOSE_BLOCKING_STATUSES = {"pending_payment", "pending", "preparing", "refunding", "refund_pending", "refund_requested"}
TABLE_CLOSE_DONE_STATUSES = {"done", "settled", "cancelled", "rejected"}


@router.post("/orders/settle-table")
async def settle_table(
    body: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Close the current open table session only after all payable orders are finished."""
    tenant_id = getattr(request.state, "tenant_id", None)
    token_type = getattr(request.state, "token_type", None)
    if not tenant_id or token_type != "merchant":
        return error_response(code=401, msg="请先登录")
    table_no = (body.get("table_no") or "").strip()
    if not table_no:
        return error_response(code=400, msg="缺少桌号")
    TenantContext.set_tenant_id(tenant_id)

    from app.models.dining import DiningSession

    session_result = await db.execute(
        select(DiningSession).where(
            DiningSession.tenant_id == tenant_id,
            DiningSession.table_no == table_no,
            DiningSession.status == "OPEN",
        ).with_for_update()
    )
    active_session = session_result.scalar_one_or_none()
    if not active_session:
        return error_response(code=404, msg="本桌没有进行中的会话")

    result = await db.execute(
        select(Order).where(
            Order.tenant_id == tenant_id,
            Order.dining_session_id == active_session.id,
        )
    )
    table_orders = list(result.scalars().all())
    blocking_orders = [
        o for o in table_orders
        if (o.status or "") in TABLE_CLOSE_BLOCKING_STATUSES or (o.status or "") not in TABLE_CLOSE_DONE_STATUSES
    ]
    if blocking_orders:
        return error_response(
            code=409,
            msg="table has unfinished orders",
            data={
                "table_no": table_no,
                "dining_session_id": str(active_session.id),
                "blocking_order_ids": [str(o.id) for o in blocking_orders],
                "blocking_statuses": sorted({o.status for o in blocking_orders}),
            },
        )

    active_session.status = "CLOSED"
    active_session.closed_at = datetime.utcnow()
    active_session.closed_by = str(getattr(request.state, "user_id", "") or "merchant")
    active_session.active_key = None

    total = 0.0
    settled_count = 0
    for o in table_orders:
        if o.status == "done":
            o.status = "settled"
            settled_count += 1
        if o.status == "settled":
            if not getattr(o, "completed_at", None):
                o.completed_at = datetime.utcnow()
            total += float(o.total or 0)
    await db.commit()
    return success_response(
        data={
            "table_no": table_no,
            "dining_session_id": str(active_session.id),
            "settled_count": settled_count,
            "closed": True,
            "total": total,
        },
        msg="结桌成功",
    )
class MerchantNoteUpdate(PydanticBase):
    note: str = ""


@router.patch("/orders/{order_id}/note")
async def update_merchant_note(
    order_id: str,
    body: MerchantNoteUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Add merchant note to an order."""
    tenant_id = getattr(request.state, "tenant_id", None)
    token_type = getattr(request.state, "token_type", None)
    if not tenant_id or token_type != "merchant":
        return error_response(code=401, msg="请先登录")
    result = await db.execute(
        select(Order).where(Order.id == int(order_id), Order.tenant_id == tenant_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        return error_response(code=404, msg="order not found")
    _, meta = _split_merchant_note_and_print_meta(order.merchant_note)
    order.merchant_note = _compose_merchant_note_with_print_meta(body.note.strip() or None, meta)
    await db.commit()
    display_note, _ = _split_merchant_note_and_print_meta(order.merchant_note)
    return success_response(data={"id": str(order.id), "merchant_note": display_note}, msg="merchant note updated")


@router.post("/orders/{order_id}/reprint")
async def reprint_order_ticket(
    order_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    tenant_id = getattr(request.state, "tenant_id", None)
    token_type = getattr(request.state, "token_type", None)
    if not tenant_id or token_type != "merchant":
        return error_response(code=401, msg="请先登录")
    result = await db.execute(
        select(Order).where(Order.id == int(order_id), Order.tenant_id == tenant_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        return error_response(code=404, msg="order not found")
    if getattr(order, "payment_status", None) != "paid":
        return error_response(code=400, msg="order not paid")
    print_result = await _print_paid_order_ticket(order, db, manual=True, reason="manual_reprint")
    await db.commit()
    await db.refresh(order)
    return success_response(
        data={"id": str(order.id), **_serialize_print_meta(order), "print_result": print_result},
        msg="reprint submitted" if print_result.get("success") else "reprint failed",
    )

@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Cancel current customer order."""
    from app.models.coupon import Coupon as _Coupon
    from datetime import datetime as _dt

    customer_id = getattr(request.state, "customer_id", None)
    result = await db.execute(select(Order).where(Order.id == int(order_id)).with_for_update())
    order = result.scalar_one_or_none()
    if not order:
        return error_response(code=404, msg="order not found")
    # 归属校验：已登录的订单必须是同一个客户，匿名调用不能取消已登录客户的订单
    if order.customer_id and (not customer_id or int(customer_id) != int(order.customer_id)):
        return error_response(code=403, msg="forbidden")
    if order.status not in ("pending_payment", "pending"):
        return error_response(code=400, msg="订单已支付或已完成，无法取消")
    if getattr(order, "payment_status", None) == "paid":
        refund_result = await _refund_order_payment(order, db, reason="customer_cancel")
        if not refund_result["success"]:
            await db.rollback()
            return error_response(code=502, msg=f"取消失败，退款处理异常，请稍后重试或联系客服：{refund_result['error']}")
    order.status = "cancelled"
    # P0 修复：恢复被 LOCKED 的优惠券
    if order.coupon_id:
        coupon = await db.get(_Coupon, order.coupon_id)
        if coupon and coupon.status == "LOCKED":
            coupon.status = "UNUSED"
    await db.commit()
    return success_response(data={"id": str(order.id), "status": "cancelled"}, msg="order cancelled")


@router.get("/orders/my")
async def get_my_order(order_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Get current customer order status."""
    result = await db.execute(select(Order).where(Order.id == int(order_id)))
    order = result.scalar_one_or_none()
    if not order:
        return error_response(code=404, msg="order not found")
    recovered = await _recover_wxpay_order_if_paid(order, db)
    if recovered:
        await db.commit()
        await db.refresh(order)
    return success_response(data={"id": str(order.id), "status": order.status, "payment_status": order.payment_status, "merchant_note": order.merchant_note})


@router.get("/orders")
async def list_orders(
    request: Request,
    date_str: Optional[str] = None,
    keyword: Optional[str] = None,
    order_no: Optional[str] = None,
    order_tail: Optional[str] = None,
    tail_no: Optional[str] = None,
    table_no: Optional[str] = None,
    status: Optional[str] = None,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    tenant_id = getattr(request.state, "tenant_id", None)
    token_type = getattr(request.state, "token_type", None)
    if not tenant_id or token_type != "merchant":
        return error_response(code=401, msg="请先登录")
    TenantContext.set_tenant_id(tenant_id)

    query = select(Order).where(Order.tenant_id == tenant_id)

    if date_str == "today" or not date_str:
        # Use UTC+8 local day range for today order query.
        from datetime import timedelta as _td
        utc8_now = datetime.now(timezone.utc) + _td(hours=8)
        today_local = utc8_now.date()
        day_start_utc = datetime(today_local.year, today_local.month, today_local.day) - _td(hours=8)
        day_end_utc = day_start_utc + _td(hours=24)
        query = query.where(Order.created_at >= day_start_utc, Order.created_at < day_end_utc)

    normalized_order_no = (order_no or "").strip()
    normalized_tail = (order_tail or tail_no or "").strip()
    normalized_table = (table_no or "").strip()
    normalized_keyword = (keyword or "").strip()
    normalized_status = (status or "").strip()

    if normalized_order_no:
        if normalized_order_no.isdigit():
            query = query.where(Order.id == int(normalized_order_no))
        else:
            query = query.where(cast(Order.id, String).like(f"%{normalized_order_no}%"))
    if normalized_tail:
        query = query.where(cast(Order.id, String).like(f"%{normalized_tail}"))
    if normalized_table:
        query = query.where(Order.table_no == normalized_table)
    if normalized_status:
        query = query.where(Order.status == normalized_status)
    if normalized_keyword:
        keyword_conditions = [
            Order.table_no == normalized_keyword,
            Order.table_no.like(f"%{normalized_keyword}%"),
            cast(Order.id, String).like(f"%{normalized_keyword}"),
        ]
        if normalized_keyword.isdigit():
            keyword_conditions.append(Order.id == int(normalized_keyword))
        query = query.where(or_(*keyword_conditions))

    wants_pagination = page is not None or page_size is not None or any([
        normalized_order_no,
        normalized_tail,
        normalized_table,
        normalized_status,
        normalized_keyword,
    ])
    safe_page = max(int(page or 1), 1)
    safe_page_size = min(max(int(page_size or 20), 1), 100)

    total = None
    if wants_pagination:
        total_result = await db.execute(select(func.count()).select_from(query.order_by(None).subquery()))
        total = int(total_result.scalar_one() or 0)
        query = query.order_by(Order.created_at.desc()).offset((safe_page - 1) * safe_page_size).limit(safe_page_size)
    else:
        query = query.order_by(Order.created_at.desc())

    result = await db.execute(query)
    orders = result.scalars().all()

    recovered_any = False
    for order in orders:
        if order.status == "pending_payment":
            recovered_any = (await _recover_wxpay_order_if_paid(order, db)) or recovered_any
        print_meta = _get_print_meta(order)
        if (
            getattr(order, "payment_status", None) == "paid"
            and print_meta.get("status") == "failed"
            and int(print_meta.get("attempts") or 0) < MAX_PRINT_RETRY_ATTEMPTS
        ):
            await _print_paid_order_ticket(order, db, reason="merchant_list_recovery")
            recovered_any = True
    if recovered_any:
        await db.commit()
        for order in orders:
            await db.refresh(order)

    order_ids = [o.id for o in orders]
    items_by_order = {}
    if order_ids:
        items_result = await db.execute(
            select(OrderItem).where(OrderItem.order_id.in_(order_ids))
        )
        all_items = items_result.scalars().all()
        for item in all_items:
            items_by_order.setdefault(item.order_id, []).append(item)

    rows = [serialize_order(o, items_by_order.get(o.id, [])) for o in orders]
    if wants_pagination:
        return success_response(
            data={
                "items": rows,
                "total": total or 0,
                "page": safe_page,
                "page_size": safe_page_size,
            }
        )
    return success_response(data=rows)

class ReviewCreate(PydanticBase):
    rating: int  # 1-5
    content: Optional[str] = None


@router.post("/orders/{order_id}/review")
async def create_review(
    order_id: str,
    body: ReviewCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Submit customer review for a completed order."""
    from datetime import datetime as _dt
    from app.models.order_review import OrderReview

    customer_id = getattr(request.state, "customer_id", None)
    if not 1 <= body.rating <= 5:
        return error_response(code=400, msg="璇勫垎闇€鍦?-5涔嬮棿")

    result = await db.execute(select(Order).where(Order.id == int(order_id)))
    order = result.scalar_one_or_none()
    if not order:
        return error_response(code=404, msg="order not found")
    if order.status not in ("done", "settled"):
        return error_response(code=400, msg="order not completed")

    # 妫€鏌ユ槸鍚﹀凡璇勪环
    exists = await db.execute(
        select(OrderReview).where(OrderReview.order_id == int(order_id))
    )
    if exists.scalar_one_or_none():
        return error_response(code=400, msg="order already reviewed")

    review = OrderReview(
        tenant_id=order.tenant_id,
        order_id=order.id,
        customer_id=int(customer_id) if customer_id else None,
        rating=body.rating,
        content=body.content,
        created_at=_dt.utcnow(),
    )
    db.add(review)
    await db.commit()
    return success_response(data={"id": str(review.id), "rating": review.rating}, msg="review submitted")


@router.get("/orders/reviews")
async def list_reviews(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """List merchant order reviews."""
    tenant_id = getattr(request.state, "tenant_id", None)
    token_type = getattr(request.state, "token_type", None)
    if not tenant_id or token_type != "merchant":
        return error_response(code=401, msg="请先登录")
    from app.models.order_review import OrderReview

    TenantContext.set_tenant_id(tenant_id)
    result = await db.execute(
        select(OrderReview).where(OrderReview.tenant_id == tenant_id).order_by(OrderReview.created_at.desc())
    )
    reviews = result.scalars().all()
    return success_response(data=[
        {
            "id": str(r.id),
            "order_id": str(r.order_id),
            "rating": r.rating,
            "content": r.content,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reviews
    ])

















