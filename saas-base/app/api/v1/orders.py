from datetime import date, datetime, timezone
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel as PydanticBase
from sqlalchemy import String, and_, cast, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import settings
from app.core.database import get_db
from app.core.logger import logger
from app.core.platform_rules import cap_discount_amount
from app.core.response import error_response, success_response
from app.core.tenant_context import TenantContext
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
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
    "pending_payment": {"cancelled"},
    "pending": {"preparing", "rejected", "cancelled"},
    "preparing": {"done"},
    "done": {"settled"},
}
ORDER_NEXT_ACTIONS = {
    "prepay": "pay",
    "postpay": "order_success",
    "table_account": "table_order_success",
}


def build_order_next_action(payment_mode: str) -> str:
    if payment_mode not in ORDER_NEXT_ACTIONS:
        raise ValueError("unsupported payment mode")
    return ORDER_NEXT_ACTIONS[payment_mode]


def _mark_order_offline_paid(order: Order, payment_method: str = "offline") -> bool:
    if getattr(order, "payment_status", None) == "paid":
        return False
    order.payment_status = "paid"
    order.payment_method = payment_method
    order.payment_time = datetime.now(timezone.utc).isoformat()
    return True


def can_reprint_order(order: Order, print_type: str = "kitchen") -> tuple[bool, str | None]:
    status = getattr(order, "status", None)
    payment_mode = getattr(order, "payment_mode", "prepay") or "prepay"
    payment_status = getattr(order, "payment_status", None)
    if status in ("cancelled", "rejected"):
        return False, "order cancelled"
    if print_type == "receipt":
        return (payment_status == "paid", None if payment_status == "paid" else "order not paid")
    if print_type == "kitchen":
        if payment_mode == "prepay":
            return (payment_status == "paid", None if payment_status == "paid" else "order not paid")
        if payment_mode in ("postpay", "table_account"):
            return True, None
    return False, "unsupported print type"

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
    dining_session_id: Optional[int] = None
    participant_token: Optional[str] = None
    client_id: Optional[str] = None
    source: Optional[str] = "miniprogram"
    staff_note: Optional[str] = None
    pickup_no: Optional[str] = None  # 代客加单时前台已经知道要发哪个取餐牌号，可以直接带上
    request_id: Optional[str] = None  # 幂等键：同一次提交的双击/弱网重试携带同一个值，重复提交返回同一张订单


class MockPayBody(PydanticBase):
    participant_token: Optional[str] = None


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
    if status == "UNKNOWN":
        return "unknown"
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
        "print_manual_reprint_by": meta.get("manual_reprint_by") if meta else None,
        "print_manual_reprint_at": meta.get("manual_reprint_at") if meta else None,
        "print_last_reason": meta.get("last_reason") if meta else None,
    }

async def _set_order_coupon_status_if_locked(order: Order, db: AsyncSession, status: str) -> None:
    if not getattr(order, "coupon_id", None):
        return
    from app.models.coupon import Coupon

    coupon_result = await db.execute(
        select(Coupon).where(Coupon.id == order.coupon_id).with_for_update()
    )
    coupon = coupon_result.scalar_one_or_none()
    if coupon and coupon.status == "LOCKED":
        coupon.status = status


async def _unlock_order_coupon_if_locked(order: Order, db: AsyncSession) -> None:
    await _set_order_coupon_status_if_locked(order, db, "UNUSED")


async def _mark_order_coupon_used_if_locked(order: Order, db: AsyncSession) -> None:
    await _set_order_coupon_status_if_locked(order, db, "USED")

async def _apply_paid_order_member_assets_once(order: Order, db: AsyncSession) -> None:
    """Apply member consumption assets for one paid order at most once.

    Offline payment modes do not go through the WeChat payment callback, so they
    need the same member-account side effect when the merchant marks the order
    paid. PointLedger.ref_id already stores order.id for paid-order consumption,
    so use it as the narrow idempotency guard without changing schema.
    """
    if not getattr(order, "customer_id", None):
        return

    from app.models.customer import Customer
    from app.models.point_ledger import PointLedger
    from app.services.membership_service import MembershipService

    tenant_id = str(order.tenant_id)
    customer_id = int(order.customer_id)
    existing_result = await db.execute(
        select(PointLedger.id).where(
            PointLedger.tenant_id == tenant_id,
            PointLedger.customer_id == customer_id,
            PointLedger.event_type == "consumption",
            PointLedger.ref_id == str(order.id),
        )
    )
    if existing_result.scalar_one_or_none():
        return

    customer_result = await db.execute(
        select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.id == customer_id,
            Customer.status == 1,
        )
    )
    customer = customer_result.scalar_one_or_none()
    if not customer:
        return

    membership_svc = MembershipService(db)
    membership_svc.set_tenant_id(tenant_id)
    await membership_svc.apply_consumption(customer, float(order.total or 0), consumption_id=order.id)

    # 新客券/复购券：prepay 支付成功（_on_payment_success）会发，但 postpay/table_account
    # 结账走的是这个函数，之前完全没有这一段——商户后台"复购券"卡片的文案明确写的是
    # "每次下单后自动推送下次用的券"，不是"微信支付后"，postpay/table_account 静默漏发
    # 与文案承诺不符。同一套 rule_type 判定逻辑（按已支付订单数区分新客/复购），
    # 发放本身的去重交给 issue_auto_coupon 自己的幂等保护（_dedup_issue_lock）。
    try:
        prior_paid_count_result = await db.execute(
            select(func.count(Order.id)).where(
                Order.tenant_id == order.tenant_id,
                Order.customer_id == customer_id,
                Order.payment_status == "paid",
                Order.id != order.id,
            )
        )
        prior_paid_count = int(prior_paid_count_result.scalar() or 0)
        rule_type = "new_customer_coupon" if prior_paid_count == 0 else "consumption_coupon"
        coupon_svc = CouponService(db)
        coupon_svc.set_tenant_id(tenant_id)
        await coupon_svc.issue_auto_coupon(customer_id, rule_type, consumption_amount=float(order.total or 0))
    except Exception as e:
        logger.warning(f"postpay/table_account settlement coupon reward failed: {e}")

def serialize_order(order: Order, order_items: list, checkout_requested_at: str | None = None, participant_no: int | None = None):
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
        "payment_mode": getattr(order, "payment_mode", "prepay"),
        "payment_method": getattr(order, "payment_method", None),
        "checkout_requested_at": checkout_requested_at,
        "dining_session_id": str(order.dining_session_id) if getattr(order, "dining_session_id", None) else None,
        "participant_id": str(order.participant_id) if getattr(order, "participant_id", None) else None,
        # 这一单是这一桌第几位加入的人点的（从1开始），拼桌场景下商户端接单页
        # 用来展示"这道菜是哪位点的"，纯展示用，跟真实身份无关。
        "participant_no": participant_no,
        "order_type": getattr(order, "order_type", None),
        "order_type_text": ORDER_TYPE_TEXT.get(getattr(order, "order_type", None), ""),
        "parent_order_id": str(order.parent_order_id) if getattr(order, "parent_order_id", None) else None,
        "source": getattr(order, "source", "miniprogram"),
        "staff_note": getattr(order, "staff_note", None),
        "pickup_no": getattr(order, "pickup_no", None),
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

    tenant_result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        return error_response(code=404, msg="商户不存在")
    if not tenant.status:
        return error_response(code=403, msg="商户已停业，暂不接受点餐")
    from app.models.tenant_config import TenantConfig

    config_result = await db.execute(select(TenantConfig).where(TenantConfig.tenant_id == tenant_id))
    tenant_config = config_result.scalar_one_or_none()
    business_info = (tenant_config.business_info or {}) if tenant_config else {}
    if not business_info.get("is_open", True):
        return error_response(code=400, msg="门店休息中，暂不接受点餐")

    request_id = (body.request_id or "").strip() or None
    if request_id:
        replay_result = await db.execute(
            select(Order).where(Order.tenant_id == tenant_id, Order.client_request_id == request_id)
        )
        replay_order = replay_result.scalar_one_or_none()
        if replay_order:
            replay_items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == replay_order.id))
            replay_items = list(replay_items_result.scalars().all())
            replay_data = serialize_order(replay_order, replay_items)
            replay_payment_mode = getattr(replay_order, "payment_mode", "prepay")
            return success_response(
                data={
                    **replay_data,
                    "order_id": replay_data["id"],
                    "need_payment": replay_payment_mode == "prepay" and replay_order.payment_status != "paid",
                    "next_action": build_order_next_action(replay_payment_mode),
                    "pay_amount": float(replay_order.total),
                    "payment_mode": replay_payment_mode,
                },
                msg="order already created, please pay",
            )

    payment_mode = (tenant.payment_mode if tenant else "prepay")
    table_no_for_zone = (body.table or "").strip()
    if table_no_for_zone:
        from app.models.entrance_code import EntranceCode

        zone_result = await db.execute(
            select(EntranceCode.zone_type)
            .where(
                EntranceCode.tenant_id == tenant_id,
                EntranceCode.table_no == table_no_for_zone,
                EntranceCode.entry_type == "table",
                EntranceCode.status == 1,
            )
            .order_by(EntranceCode.created_at.desc())
            .limit(1)
        )
        zone_type = zone_result.scalar_one_or_none()
        # zone_type 为空（没配置分区）时保持原来的 tenant.payment_mode，老商户/老桌码行为不变。
        if zone_type == "quick":
            payment_mode = "prepay"
        elif zone_type == "full":
            payment_mode = "table_account"
    payment_mode = payment_mode if payment_mode in ("prepay", "postpay", "table_account") else "prepay"
    is_postpay = payment_mode == "postpay"
    is_table_account = payment_mode == "table_account"
    pay_later_mode = is_postpay or is_table_account

    customer_id = getattr(request.state, "customer_id", None)
    if customer_id:
        customer_id = int(customer_id)

    # 服务员在 admin-h5 用商户登录态代客加单：不需要顾客身份（participant_token/customer_id），
    # 只按桌号挂到这一桌当前的桌台会话下，跟顾客自己点的单一起累计进桌台总账。
    is_staff_order = getattr(request.state, "token_type", None) == "merchant"

    dining_session_id = None
    dining_participant_id = None
    order_type = None
    parent_order_id = None
    session_for_pickup = None  # 解析出来的 DiningSession，用来读/写这一桌共享的取餐牌号
    if is_staff_order:
        merchant_tenant_id = getattr(request.state, "tenant_id", None)
        if not merchant_tenant_id or merchant_tenant_id != tenant_id:
            return error_response(code=403, msg="无权为该门店下单")
        if payment_mode not in ("postpay", "table_account"):
            return error_response(code=400, msg="预付模式暂不支持代客加单")
        if body.coupon_id:
            return error_response(code=400, msg="代客加单不支持使用优惠券")
        table_no = (body.table or "").strip()
        if not table_no:
            return error_response(code=400, msg="缺少桌号")

        from app.services.dining_session_service import DiningSessionService

        try:
            session = await DiningSessionService(db).get_or_create_open_session_for_staff(tenant_id, table_no)
        except ValueError as exc:
            return error_response(code=400, msg=str(exc))

        dining_session_id = session.id
        session_for_pickup = session
        existing_order_result = await db.execute(
            select(Order)
            .where(
                Order.tenant_id == tenant_id,
                Order.dining_session_id == session.id,
                Order.status.notin_(["cancelled", "rejected"]),
            )
            .order_by(Order.created_at.asc())
            .limit(1)
        )
        parent_order = existing_order_result.scalar_one_or_none()
        order_type = "ADD_ON" if parent_order else "INITIAL"
        parent_order_id = parent_order.id if parent_order else None
    elif body.dining_session_id:
        from app.models.dining import DiningParticipant, DiningSession
        from app.services.dining_session_service import hash_participant_token

        # 加行锁跟 settle_table 的锁互斥，防止"结账"和"追加点单"并发时，这边拿着还没
        # 提交的旧快照（session 还是 OPEN）继续挂单，等结账那边先提交、这边才提交，
        # 挂出来的这条新订单就落在一个已经结完账关闭的 session 下——以后任何结账逻辑
        # 都不会再找到它，商家做了这道菜却收不到这笔钱。加锁后这个查询会等 settle_table
        # 的事务提交，然后用最新数据重新判断 status == "OPEN"，过期了就走下面的 404。
        session_result = await db.execute(
            select(DiningSession).where(
                DiningSession.id == int(body.dining_session_id),
                DiningSession.tenant_id == tenant_id,
                DiningSession.table_no == (body.table or ""),
                DiningSession.status == "OPEN",
            ).with_for_update()
        )
        session = session_result.scalar_one_or_none()
        if not session:
            return error_response(code=400, msg="dining session not found")
        session_for_pickup = session

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
            # 409 而不是 403：本桌匿名身份没对上，跟"会员登录过期"是两码事。401/403 在这个
            # 项目里全局约定代表"需要重新登录"，小程序端的通用拦截器会把它们当成会员登录
            # 失效处理（清掉 customer_token、弹微信授权框），如果这里复用 403 会把一次可以
            # 静默重试的本桌身份问题误导成"你必须先注册会员"，这正是历史上真实发生过的 bug。
            return error_response(code=409, msg="本桌身份已失效，请重新扫码")

        dining_session_id = session.id
        dining_participant_id = participant.id
        payment_status_filter = [Order.payment_status == "paid"] if payment_mode == "prepay" else []
        existing_order_result = await db.execute(
            select(Order)
            .where(
                Order.tenant_id == tenant_id,
                Order.dining_session_id == session.id,
                *payment_status_filter,
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

    if is_table_account and not dining_session_id:
        return error_response(code=400, msg="桌台账单模式需要重新扫码进入本桌")

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
        await _restore_order_stock(stale, db)
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
                return error_response(code=400, msg=f"菜品不存在:{item_in.name}")
            if not dish.available:
                return error_response(code=400, msg=f"菜品已下架:{dish.name}")
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
            # 同一道菜在这一单里可能拆成好几行（比如同一道菜点了不同辣度），库存扣减必须
            # 在这一行处理完就立刻生效，而不是等所有行都校验完再统一扣——SQLAlchemy 对
            # 同一个 dish_id 的重复查询会拿到同一个已加锁的对象，如果扣减延后到循环外，
            # 每一行各自拿着这道菜"还没扣减过"的库存去比较，加总起来就能绕过库存上限，
            # 在单笔订单内造成超卖。
            if dish.stock is not None:
                dish.stock -= item_in.qty
        else:
            return error_response(code=400, msg=f"缺少菜品ID:{item_in.name}")
        real_total += unit_price * item_in.qty
        order_items_data.append((item_in.dish_id, name, unit_price, item_in.qty))

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
            .with_for_update()
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

        if tpl.type == "PERCENT":
            raw_discount = real_total * float(tpl.value or 0) / 100
        else:
            raw_discount = float(tpl.value or 0)
        # 红线兜底：不管模板配置得对不对，实际减免不超过这一单实付金额的安全比例
        coupon_discount = Decimal(str(cap_discount_amount(raw_discount, real_total)))
        coupon.status = "LOCKED"
        applied_coupon_id = coupon.id

    final_total = max(real_total - float(coupon_discount), 0)

    # 取餐牌号跟着"这一桌这次吃饭"走，不是跟着"这一单"走：显式传了就用显式的（顺便把这个
    # 号同步成这一桌接下来所有加单共享的值），没传就继承这一桌已经登记过的号，避免同一桌
    # 每加一单都要前台重新填一遍。
    explicit_pickup_no = (body.pickup_no or "").strip()[:16] or None
    if explicit_pickup_no and session_for_pickup is not None:
        session_for_pickup.pickup_no = explicit_pickup_no
    resolved_pickup_no = explicit_pickup_no or (session_for_pickup.pickup_no if session_for_pickup else None)

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
        status="pending" if payment_mode in ("postpay", "table_account") else "pending_payment",
        payment_status="unpaid",
        payment_mode=payment_mode,
        remark=body.remark,
        coupon_id=applied_coupon_id,
        discount_amount=float(coupon_discount) if coupon_discount > 0 else None,
        source="staff" if is_staff_order else (body.source or "miniprogram"),
        staff_note=(body.staff_note or "").strip()[:64] or None if is_staff_order else None,
        pickup_no=resolved_pickup_no,
        client_request_id=request_id,
    )
    db.add(order)
    try:
        await db.flush()
    except IntegrityError:
        # 前面查重的那一刻还没有这张订单，但几乎同一时间的第二个请求已经抢先建好了
        # （真正意义上的并发重复提交）——这里接住唯一索引冲突，直接把已建好的那张
        # 订单返回，而不是让这次请求报错或者绕过约束硬插入第二张。
        await db.rollback()
        if request_id:
            replay_result = await db.execute(
                select(Order).where(Order.tenant_id == tenant_id, Order.client_request_id == request_id)
            )
            replay_order = replay_result.scalar_one_or_none()
            if replay_order:
                replay_items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == replay_order.id))
                replay_items = list(replay_items_result.scalars().all())
                replay_data = serialize_order(replay_order, replay_items)
                replay_payment_mode = getattr(replay_order, "payment_mode", "prepay")
                return success_response(
                    data={
                        **replay_data,
                        "order_id": replay_data["id"],
                        "need_payment": replay_payment_mode == "prepay" and replay_order.payment_status != "paid",
                        "next_action": build_order_next_action(replay_payment_mode),
                        "pay_amount": float(replay_order.total),
                        "payment_mode": replay_payment_mode,
                    },
                    msg="order already created, please pay",
                )
        return error_response(code=409, msg="订单提交冲突，请重试")

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

    await db.flush()
    if pay_later_mode:
        await _print_paid_order_ticket(order, db, reason="order_created_pay_later")

    await db.commit()
    await db.refresh(order)

    order_data = serialize_order(order, order_items)
    return success_response(
        data={
            **order_data,
            "order_id": order_data["id"],
            "need_payment": payment_mode == "prepay",
            "next_action": build_order_next_action(payment_mode),
            "pay_amount": float(final_total),
            "payment_mode": payment_mode,
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

        await _on_payment_success(locked_order, db, payment_method="wxpay")
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

class PrintResultUnknownError(RuntimeError):
    """飞鹅云请求超时/网络异常导致没拿到响应——不知道这次到底有没有打印成功，跟"服务端
    明确说打印失败"是两码事，调用方必须分开处理（不能自动重试，见 print_order 的说明）。"""


async def _print_paid_order_ticket(
    order: Order,
    db: AsyncSession,
    *,
    manual: bool = False,
    reason: str = "auto",
    operator: str | None = None,
) -> dict:
    """Print an order ticket and persist recoverable print state in existing order metadata."""
    if not order:
        return {"success": False, "skipped": True, "code": "ORDER_NOT_FOUND"}
    allow_unpaid_print = reason in ("order_created_pay_later", "manual_reprint") and getattr(order, "payment_mode", "prepay") in ("postpay", "table_account")
    if not allow_unpaid_print and getattr(order, "payment_status", None) != "paid":
        return {"success": False, "skipped": True, "code": "ORDER_NOT_PAID"}

    locked_result = await db.execute(select(Order).where(Order.id == order.id).with_for_update())
    locked_order = locked_result.scalar_one_or_none()
    if locked_order:
        order = locked_order
    allow_unpaid_print = reason in ("order_created_pay_later", "manual_reprint") and getattr(order, "payment_mode", "prepay") in ("postpay", "table_account")
    if not allow_unpaid_print and getattr(order, "payment_status", None) != "paid":
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
    if manual and operator:
        meta["manual_reprint_by"] = operator
        meta["manual_reprint_at"] = datetime.now(timezone.utc).isoformat()
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
            items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
            order_items = list(items_result.scalars().all())
            ticket = build_order_ticket(order, order_items)
            result = await print_order(tenant_obj.feieyun_sn, tenant_obj.feieyun_key, ticket)
            if result == "unknown":
                raise PrintResultUnknownError("FEIEYUN_PRINT_RESULT_UNKNOWN")
            if result != "success":
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
        # 结果不明（网络超时/异常，没拿到打印服务商的响应）和明确失败（服务商回了响应说没
        # 打印成功）分开处理："失败"允许后续自动重试（merchant_list_recovery 那条路），
        # "未知"绝不能自动重试——如果这次其实已经打印成功了，自动重试会造成重复出票，
        # 必须交给能实际看到打印机的人来判断要不要手动补打。
        is_unknown = isinstance(exc, PrintResultUnknownError)
        status_label = "unknown" if is_unknown else "failed"
        db_status = "UNKNOWN" if is_unknown else "FAILED"
        error_code = getattr(exc, "code", None) or str(exc) or type(exc).__name__
        meta.update({
            "status": status_label,
            "last_error_code": error_code,
            "last_error": str(exc),
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "manual_reprint": bool(meta.get("manual_reprint")) or manual,
        })
        _mark_order_print_state(order, db_status)
        _set_print_meta(order, meta)
        logger.warning(
            "[PRINT_ORDER_%s_RECOVERABLE] order_id=%s attempts=%s error_code=%s manual=%s reason=%s",
            db_status,
            order.id,
            meta.get("attempts"),
            error_code,
            manual,
            reason,
        )
        return {"success": False, "status": status_label, "attempts": meta.get("attempts"), "code": error_code}

async def _on_payment_success(
    order: Order,
    db: AsyncSession,
    payment_method: str = "wxpay",
) -> tuple:
    """Run shared post-payment logic."""
    from app.models.coupon import Coupon

    if getattr(order, "payment_status", None) == "paid":
        return None, 0.0

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
            # 老带新双边奖励的发放判定（CommissionService.record_after_verify）之前只挂在
            # 店员手动核销（verify.py/pos.py）上；自助点餐支付在这里核销优惠券却从没调用
            # 过它，导致走小程序自助下单支付（PRODUCT_RULES.md 里明确的主路径）的被邀请
            # 人，邀请人和他自己永远拿不到这份奖励。这里补上同一次调用——两条核销路径
            # 共用 record_after_verify 内部按 customer_id+FIRST_VERIFY 加锁去重的判定，
            # 不会因为走两条路径而重复发放。
            try:
                from app.models.coupon_template import CouponTemplate
                from app.services.commission_service import CommissionService

                template_result = await db.execute(
                    select(CouponTemplate).where(CouponTemplate.id == locked_coupon.template_id)
                )
                coupon_template = template_result.scalar_one_or_none()
                commission_svc = CommissionService(db)
                commission_svc.set_tenant_id(str(order.tenant_id))
                await commission_svc.record_after_verify(locked_coupon, coupon_template)
                # record_after_verify 内部会 commit，之后同一 session 里所有对象（包括
                # order）的属性都会被标记过期；显式 refresh 一次，避免下面继续读写
                # order 时触发 SQLAlchemy 异步会话下的懒加载报错。
                await db.refresh(order)
            except Exception as e:
                logger.warning(f"post-payment invite reward failed: {e}")
        elif locked_coupon and locked_coupon.status != "USED":
            order.coupon_id = None
            order.discount_amount = None
    elif order.coupon_id:
        order.coupon_id = None
        order.discount_amount = None

    # 标记支付成功
    effective_method = payment_method
    order.payment_status = "paid"
    order.payment_method = effective_method
    order.payment_time = datetime.now(timezone.utc).isoformat()
    order.status = "pending"
    await db.flush()


    # Coupon issuance and points are post-payment side effects.
    if customer_id:
        try:
            svc = CouponService(db)
            prior_paid_count_result = await db.execute(
                select(func.count(Order.id)).where(
                    Order.tenant_id == order.tenant_id,
                    Order.customer_id == int(customer_id),
                    Order.payment_status == "paid",
                    Order.id != order.id,
                )
            )
            prior_paid_count = int(prior_paid_count_result.scalar() or 0)
            is_new_customer = prior_paid_count == 0
            # 第二单是"首单到复购"这条转化漏斗里最关键的一步——比第三单、第十单都更值得
            # 单独识别出来，用来在客户端给一句专属文案（"欢迎回来，这是你的第二次光临"），
            # 而不是把所有复购场景都用同一句"又送你一张券"糊弄过去。
            is_second_order = prior_paid_count == 1
            rule_type = "new_customer_coupon" if is_new_customer else "consumption_coupon"
            issue_result = await svc.issue_auto_coupon(
                int(customer_id), rule_type, consumption_amount=float(order.total)
            )
            # issue_auto_coupon() 的返回值是内部服务间约定的形状（success_count/sent/
            # weighted_coupon 嵌套），不是给客户端消费的。这里只在真的发出新券时才
            # 拍平成小程序端认识的 {id,name,amount,min_amount,expired_at}（和入会接口
            # 的欢迎券是同一套字段），没发新券（未达门槛、规则关闭、已持有同类未用券）
            # 一律给 None——不然前端只要判断"coupon 字段存在"就会把 success_count:0
            # 这种失败/跳过结果误当成"又送了一张券"展示出去。
            coupon_data = None
            if issue_result and issue_result.get("success_count", 0) > 0:
                sent_item = (issue_result.get("sent") or [{}])[0]
                wc = issue_result.get("weighted_coupon") or {}
                coupon_data = {
                    "id": sent_item.get("id"),
                    "name": wc.get("name") or "优惠券",
                    "amount": wc.get("amount", 0),
                    "min_amount": wc.get("threshold", 0),
                    "expired_at": sent_item.get("expire_time"),
                    "is_second_order": is_second_order,
                }
            # 落库这份快照：微信支付的真实发券走的是 wxpay_notify 异步回调，回调结果
            # 只回给微信、回不到小程序客户端。存到订单上，客户端支付成功后轮询
            # /orders/my 就能把这次实际发放的奖励券（或者"这次没发"）拿回来，而不是
            # 依赖 createWxPayOrder 那个支付前就返回、结构上根本不含 coupon 的旧响应。
            order.reward_coupon_snapshot = json.dumps(coupon_data, ensure_ascii=False) if coupon_data else None
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
    return coupon_data, 0.0


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

    # 退款后回滚这一单在支付成功时记的账：优惠券和积分/消费额，否则顾客能靠
    # "付款->拿到积分/等级/优惠券->自己或商家取消退款"反复刷积分和等级。
    if order.coupon_id:
        from app.models.coupon import Coupon

        coupon_result = await db.execute(
            select(Coupon).where(Coupon.id == order.coupon_id).with_for_update()
        )
        coupon = coupon_result.scalar_one_or_none()
        if coupon and coupon.status in ("LOCKED", "USED"):
            coupon.status = "UNUSED"
            coupon.use_time = None

    if order.customer_id:
        try:
            from app.services.membership_service import MembershipService

            membership_svc = MembershipService(db)
            membership_svc.set_tenant_id(str(order.tenant_id))
            await membership_svc.reverse_consumption(int(order.customer_id), total, consumption_id=order.id)
        except Exception as exc:
            logger.warning("[REFUND_POINTS_REVERSAL_FAILED] order_id=%s error=%s", order.id, exc)

    order.refund_status = "success"
    order.refund_amount = refunded_amount
    order.refunded_at = datetime.now(timezone.utc)
    order.refund_error = None
    logger.info(
        "[REFUND_SUCCESS] order_id=%s amount=%s balance_portion=%s wechat_portion=%s reason=%s",
        order.id, refunded_amount, balance_portion, wechat_portion, reason,
    )
    return {"success": True, "amount": refunded_amount, "error": None}


async def _refund_orphaned_wxpay_payment(order: Order, db: AsyncSession) -> dict:
    """WeChat confirms a payment succeeded for an order that's already cancelled/rejected
    locally (see wxpay_notify) -- the callback arrived after cancel_order/update_order_status
    had already committed the terminal state, so _on_payment_success never ran for this order:
    no points, no consumption tracking, no coupon issuance, no kitchen ticket. There is nothing
    on our side to reverse, only the money that actually landed in the merchant's WeChat
    account to send back. Deliberately does not touch order.status or print anything -- the
    kitchen was already told this order is off.

    Must be called with `order` already locked (with_for_update) in the current transaction.
    """
    total_fen = max(1, round(float(order.total or 0) * 100))
    try:
        from app.models.tenant import Tenant
        from app.services.wxpay_service import WxPayService

        tenant_result = await db.execute(select(Tenant).where(Tenant.tenant_id == str(order.tenant_id)))
        tenant = tenant_result.scalar_one_or_none()
        svc = WxPayService(tenant) if tenant else None
        if not svc or not svc.enabled:
            raise RuntimeError("merchant wxpay not configured, cannot auto-refund")
        await svc.refund(
            out_trade_no=str(order.id),
            out_refund_no=f"RF{order.id}",
            refund_fen=total_fen,
            total_fen=total_fen,
            reason="race_with_cancel_auto_refund",
        )
    except Exception as exc:
        order.refund_status = "failed"
        order.refund_error = str(exc)[:500]
        logger.error(
            "[WXPAY_NOTIFY_RACE_AUTO_REFUND_FAILED] order_id=%s error=%s -- needs manual refund",
            order.id, exc,
        )
        return {"success": False, "amount": 0.0, "error": str(exc)}

    order.refund_status = "success"
    order.refund_amount = float(order.total or 0)
    order.refunded_at = datetime.now(timezone.utc)
    order.refund_error = None
    logger.error(
        "[WXPAY_NOTIFY_RACE_AUTO_REFUNDED] order_id=%s amount=%s order_status=%s",
        order.id, order.refund_amount, order.status,
    )
    return {"success": True, "amount": float(order.refund_amount), "error": None}


async def _restore_order_stock(order: Order, db: AsyncSession) -> None:
    """Give back whatever stock create_order deducted (see its item loop, dish.stock -=)
    when an order ends up cancelled/rejected/timed-out without ever being fulfilled -- otherwise
    a dish that was never actually cooked/sold stays wrongly marked "sold out" forever, and
    the shortfall only grows with every abandoned order. Locks each MenuItem row first so a
    concurrent order for the same dish can't race the restore.

    Must be called with `order` already locked (with_for_update) in the current transaction,
    before the order's status is flipped away from pending_payment/pending.
    """
    from app.models.menu_item import MenuItem

    items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    order_items = items_result.scalars().all()
    qty_by_dish_id: dict = {}
    for item in order_items:
        if item.dish_id:
            qty_by_dish_id[item.dish_id] = qty_by_dish_id.get(item.dish_id, 0) + item.qty
    if not qty_by_dish_id:
        return

    dishes_result = await db.execute(
        select(MenuItem).where(MenuItem.id.in_(qty_by_dish_id.keys())).with_for_update()
    )
    for dish in dishes_result.scalars().all():
        if dish.stock is not None:
            dish.stock = dish.stock + qty_by_dish_id.get(dish.id, 0)


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
        # 归属校验：已登录订单核对 customer_id；匿名拼桌订单没有 customer_id，
        # 必须靠 participant_token 核对身份，否则任何人拿到 order_id 就能替别人下单/免单。
        if order.customer_id:
            if not customer_id or int(customer_id) != int(order.customer_id):
                return error_response(code=403, msg="forbidden")
        elif order.participant_id:
            from app.models.dining import DiningParticipant
            from app.services.dining_session_service import hash_participant_token

            owns_order = False
            if body.participant_token:
                participant_result = await db.execute(
                    select(DiningParticipant).where(
                        DiningParticipant.id == order.participant_id,
                        DiningParticipant.guest_token_hash == hash_participant_token(body.participant_token),
                    )
                )
                owns_order = participant_result.scalar_one_or_none() is not None
            if not owns_order:
                return error_response(code=403, msg="forbidden")
        else:
            return error_response(code=403, msg="forbidden")

        coupon_data, _ = await _on_payment_success(order, db, payment_method="mock")
        await db.commit()
        await db.refresh(order)

        items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
        order_items = list(items_result.scalars().all())

        return success_response(
            data={**serialize_order(order, order_items), "coupon": coupon_data},
            msg="支付成功",
        )
    except Exception as e:
        logger.error(f"mock_pay_order error: {e}\n{traceback.format_exc()}")
        return error_response(code=500, msg=f"支付处理失败: {str(e)}")


class WxPayBody(PydanticBase):
    js_code: Optional[str] = None
    participant_token: Optional[str] = None


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
        if getattr(order, "payment_mode", "prepay") != "prepay":
            raise HTTPException(status_code=400, detail={"success": False, "code": "PAYMENT_NOT_REQUIRED", "message": "该订单无需在线支付"})
        if order.status != "pending_payment":
            raise HTTPException(status_code=400, detail={"success": False, "code": "ORDER_ALREADY_PAID", "message": "该订单已支付或已取消"})
        # 归属校验：已登录订单核对 customer_id；匿名拼桌订单没有 customer_id，
        # 必须靠 participant_token 核对身份，否则任何人拿到 order_id 就能替别人发起支付/免单。
        if order.customer_id:
            if not customer_id or int(customer_id) != int(order.customer_id):
                raise HTTPException(status_code=403, detail={"success": False, "code": "FORBIDDEN", "message": "forbidden"})
        elif order.participant_id:
            from app.models.dining import DiningParticipant
            from app.services.dining_session_service import hash_participant_token

            owns_order = False
            if body.participant_token:
                participant_result = await db.execute(
                    select(DiningParticipant).where(
                        DiningParticipant.id == order.participant_id,
                        DiningParticipant.guest_token_hash == hash_participant_token(body.participant_token),
                    )
                )
                owns_order = participant_result.scalar_one_or_none() is not None
            if not owns_order:
                raise HTTPException(status_code=403, detail={"success": False, "code": "FORBIDDEN", "message": "forbidden"})
        else:
            # 预付订单必须落到"已登录会员"或"本桌 dining participant"两种身份之一才能建
            # 出来；如果两者都没有（比如绕开正常入口直接拿着 order_id 调接口），没有任何
            # 凭证可核对，一律拒绝，不能让在线支付/免单在零身份的情况下被任何人触发。
            raise HTTPException(status_code=403, detail={"success": False, "code": "FORBIDDEN", "message": "forbidden"})

        # Load merchant payment config
        tenant_result = await db.execute(select(Tenant).where(Tenant.tenant_id == order.tenant_id))
        tenant = tenant_result.scalar_one_or_none()

        pay_amount = float(order.total)

        # 订单实际应付金额已被优惠券抵扣到 0，无需发起微信支付（不再强行收 1 分钱），也不依赖商家是否配置了微信支付
        if pay_amount <= 0:
            locked_order_result = await db.execute(
                select(Order).where(Order.id == int(order_id)).with_for_update()
            )
            order = locked_order_result.scalar_one_or_none()
            if not order or order.status != "pending_payment":
                raise HTTPException(status_code=400, detail={"success": False, "code": "ORDER_ALREADY_PAID", "message": "order already paid or cancelled"})
            free_coupon_data, _ = await _on_payment_success(order, db, payment_method="free")
            await db.commit()
            await db.refresh(order)
            free_items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
            free_order_items = list(free_items_result.scalars().all())
            return success_response(
                data={
                    **serialize_order(order, free_order_items),
                    "free": True,
                    "coupon": free_coupon_data,
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
        if not order:
            return {"code": "SUCCESS", "message": "ok"}
        # pending_payment 是正常路径；cancelled/rejected 是"顾客/商家取消跟这次回调赛跑，
        # 取消先落地"的窗口——之前这两种情况在这里被一并静默丢弃，导致钱已经从顾客账户
        # 划走、商户微信账户也确实收到了，但订单永远停在"已取消"，没有任何机制会再去
        # 发现或退还这笔钱。其余终态（paid 之后的 pending/done/settled 等）维持原样丢弃，
        # 那些要么是已经处理过的重复回调，要么不属于这里要处理的场景。
        if order.status not in ("pending_payment", "cancelled", "rejected"):
            return {"code": "SUCCESS", "message": "ok"}
        if matched_tenant and str(order.tenant_id) != str(matched_tenant.tenant_id):
            logger.warning(
                f"wxpay notify tenant mismatch: order_id={out_trade_no} "
                f"order_tenant_id={order.tenant_id} notify_tenant_id={matched_tenant.tenant_id}"
            )
            return {"code": "FAIL", "message": "tenant mismatch"}

        # 金额核对：验签只证明这份回调确实来自微信、内容没被篡改，不代表金额就是这笔订单
        # 该收的钱——微信侧实际扣款金额必须跟下单时算出的 order.total 对得上，否则宁可
        # 拒绝这次回调也不能把订单标记为已支付，避免商户之间/订单之间任何账务错位被悄悄放过。
        paid_fen = resource.get("amount", {}).get("total")
        if paid_fen is not None:
            expected_fen = round(float(order.total) * 100)
            if int(paid_fen) != expected_fen:
                logger.error(
                    "[WXPAY_AMOUNT_MISMATCH] order_id=%s expected_fen=%s paid_fen=%s",
                    out_trade_no, expected_fen, paid_fen,
                )
                return {"code": "FAIL", "message": "amount mismatch"}

        if order.status == "pending_payment":
            await _on_payment_success(order, db, payment_method="wxpay")
            await db.commit()
            logger.info(f"微信支付回调成功: order_id={out_trade_no}")
            return {"code": "SUCCESS", "message": "ok"}

        # order.status in ("cancelled", "rejected"): raced with a cancel/reject that already
        # committed before this callback arrived. Don't resurrect the order or print a
        # kitchen ticket -- just get the customer's money back automatically.
        if getattr(order, "refund_status", None) == "success":
            return {"code": "SUCCESS", "message": "ok"}  # already reconciled by a prior retry
        logger.error(
            "[WXPAY_NOTIFY_RACE_WITH_CANCEL] order_id=%s order_status=%s -- WeChat confirmed "
            "payment after this order was already %s locally; auto-refunding instead of fulfilling",
            out_trade_no, order.status, order.status,
        )
        await _refund_orphaned_wxpay_payment(order, db)
        await db.commit()
        return {"code": "SUCCESS", "message": "ok"}

    except Exception as e:
        logger.error(f"wxpay_notify error: {e}\n{traceback.format_exc()}")
        return {"code": "FAIL", "message": str(e)}


async def _record_order_consumption(order: Order, db: AsyncSession) -> None:
    """订单结账后转成一条消费记录，供顾客端"消费记录"页展示。
    没有 customer_id（匿名/未登录下单）就跳过；记录失败不影响结账本身。"""
    if not order.customer_id:
        return
    try:
        from app.services.consumption_service import ConsumptionService

        items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
        items = items_result.scalars().all()
        if items:
            names = "、".join(i.name for i in items[:3])
            if len(items) > 3:
                names += f"等{len(items)}件"
            project = names
        else:
            project = "堂食点餐"

        consumption_service = ConsumptionService(db)
        consumption_service.set_tenant_id(order.tenant_id)
        await consumption_service.create_consumption(
            customer_id=order.customer_id,
            project=project,
            amount=float(order.total or 0),
            consume_time=order.completed_at or datetime.utcnow(),
            remark=f"订单 #{order.id}" + (f" · {order.table_no}桌" if order.table_no else ""),
        )
    except Exception as e:
        logger.error(f"结账后生成消费记录失败 - order_id: {order.id}, error: {e}")


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

    # 拒单/取消前先跟微信核实一下：顾客可能刚好在微信那边已经付款成功、回调只是还没
    # 送达，直接放行拒单会导致钱已经进商户账户但订单却显示已拒绝/已取消，没人会再去
    # 处理这笔钱（跟 cancel_order 的同一处理）。
    if (
        body.status in ("rejected", "cancelled")
        and current_status == "pending_payment"
        and getattr(order, "payment_mode", "prepay") == "prepay"
    ):
        if await _recover_wxpay_order_if_paid(order, db):
            await db.commit()
            return error_response(code=409, msg="订单已支付，请刷新查看最新状态")

    if body.status in ("rejected", "cancelled") and getattr(order, "payment_status", None) == "paid":
        refund_result = await _refund_order_payment(order, db, reason=f"merchant_{body.status}")
        if not refund_result["success"]:
            await db.rollback()
            return error_response(code=502, msg=f"操作失败，退款处理异常，请稍后重试：{refund_result['error']}")
    if body.status in ("rejected", "cancelled") and getattr(order, "payment_status", None) != "paid":
        await _unlock_order_coupon_if_locked(order, db)
    if body.status in ("rejected", "cancelled"):
        await _restore_order_stock(order, db)

    order.status = body.status
    if body.status == "done" and not getattr(order, "served_at", None):
        order.served_at = datetime.utcnow()
    just_settled = body.status == "settled" and not getattr(order, "completed_at", None)
    if just_settled:
        order.completed_at = datetime.utcnow()
        marked_offline_paid = False
        if getattr(order, "payment_mode", "prepay") == "postpay":
            marked_offline_paid = _mark_order_offline_paid(order)
        await _mark_order_coupon_used_if_locked(order, db)
        if marked_offline_paid:
            await _apply_paid_order_member_assets_once(order, db)
    await db.commit()
    await db.refresh(order)
    if just_settled:
        await _record_order_consumption(order, db)
    return success_response(
        data={
            "id": str(order.id),
            "status": order.status,
            "payment_status": getattr(order, "payment_status", None),
            "payment_method": getattr(order, "payment_method", None),
            "payment_time": getattr(order, "payment_time", None),
        },
        msg="状态已更新",
    )

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

    # 找"这一桌还有活儿要处理"的会话，按订单状态找，不按 DiningSession.status=="OPEN" 找。
    # 历史上出现过会话被标成 CLOSED/EXPIRED，订单却还卡在 done 没跟着推进到 settled 的情况
    # （旧版本结账联动没做全，或者过期扫描踩中竞态）——一旦发生，这一桌就再也找不到
    # status=="OPEN" 的会话，桌台视图上却因为订单还是 done 状态、一直显示"可结账"，
    # 商家怎么点都是这句"本桌没有进行中的会话"，成了清不掉的幽灵桌台。改成按这一桌名下
    # 还有没到终态(settled/cancelled/rejected)订单的那个会话来找，不管它自己的 status
    # 字段写的是什么——找到了照常走后面"有没有卡着的订单"这一关，正常结账；这样哪怕历史
    # 数据已经出现过这种不一致，下一次点结账也能把它带回正轨，不需要人工修数据库。
    non_terminal_result = await db.execute(
        select(Order.dining_session_id)
        .join(DiningSession, DiningSession.id == Order.dining_session_id)
        .where(
            DiningSession.tenant_id == tenant_id,
            DiningSession.table_no == table_no,
            Order.status.notin_(("settled", "cancelled", "rejected")),
        )
        .order_by(DiningSession.created_at.desc())
        .limit(1)
    )
    session_id = non_terminal_result.scalar_one_or_none()
    if not session_id:
        return error_response(code=404, msg="本桌没有进行中的会话")

    session_result = await db.execute(
        select(DiningSession).where(DiningSession.id == session_id).with_for_update()
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
            msg="本桌还有未完成的订单，无法结账",
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
    paid_synced_count = 0
    newly_settled_orders = []
    # 这里不能再按 payment_status=="unpaid" 过滤：先付后厨的订单到 done 的时候早就已经
    # payment_status=="paid" 了，之前只结未付款订单会把先付后厨的订单永远漏在 done 状态，
    # 既拿不到"已结账"的消费记录（顾客端"消费记录"页永远看不到这笔），这一桌在商家后台也会
    # 变成清不掉的"幽灵桌台"——结账按钮点了以后（因为 session 已经关闭）下次点就直接 404。
    # 只要是 done 就该跟着这次结账一起推进到 settled，是否需要补标线下已付款交给下面
    # payment_mode 的判断去管，不应该影响"要不要把它算作已结账"这件事。
    settlement_orders = [o for o in table_orders if o.status == "done"]
    for o in settlement_orders:
        o.status = "settled"
        settled_count += 1
        newly_settled_orders.append(o)
        if not getattr(o, "completed_at", None):
            o.completed_at = datetime.utcnow()
        # 桌台视图的"结账"是餐后付款和桌台账单共用的唯一批量结账入口（小程序下单时不分模式都会建
        # dining_session，两种模式的订单都会被这里的桌台分组捞到），所以线下已付款的标记不能只认
        # table_account——postpay 订单结账时同样要在这里补上，否则会留下"已结账却仍显示未支付"的订单。
        if getattr(o, "payment_mode", "prepay") in ("table_account", "postpay"):
            if _mark_order_offline_paid(o):
                paid_synced_count += 1
                await _apply_paid_order_member_assets_once(o, db)
        await _mark_order_coupon_used_if_locked(o, db)
        total += float(o.total or 0)
    await db.commit()
    for o in newly_settled_orders:
        await _record_order_consumption(o, db)
    return success_response(
        data={
            "table_no": table_no,
            "dining_session_id": str(active_session.id),
            "settled_count": settled_count,
            "paid_synced_count": paid_synced_count,
            "payment_status": "paid",
            "payment_method": "offline",
            "closed": True,
            "total": total,
        },
        msg="结桌成功",
    )
class MerchantNoteUpdate(PydanticBase):
    note: str = ""


class OrderPickupNoUpdate(PydanticBase):
    pickup_no: str = ""


@router.patch("/orders/{order_id}/pickup-no")
async def update_order_pickup_no(
    order_id: str,
    body: OrderPickupNoUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """前台把实体取餐牌号登记到这一桌（顾客到店核实付款、领牌子的时候填）。牌子管的是"这一次
    开桌"而不是"这一单菜"，所以落地到这单所在的 DiningSession 上，并同步给这一桌当前所有
    未取消/拒单的订单——前台只需要在任意一单上填一次，同一桌后面的加单不用再重复填。没有
    会话的单（比如没有走桌台流程的订单）就还是只更新这一单自己。"""
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

    pickup_no = body.pickup_no.strip()[:16] or None
    affected_ids = [order.id]

    if order.dining_session_id:
        from app.models.dining import DiningSession

        session = await db.get(DiningSession, order.dining_session_id)
        if session:
            session.pickup_no = pickup_no
            siblings_result = await db.execute(
                select(Order).where(
                    Order.tenant_id == tenant_id,
                    Order.dining_session_id == session.id,
                    Order.status.notin_(["cancelled", "rejected"]),
                )
            )
            siblings = siblings_result.scalars().all()
            for sibling in siblings:
                sibling.pickup_no = pickup_no
            affected_ids = [o.id for o in siblings] or affected_ids
        else:
            order.pickup_no = pickup_no
    else:
        order.pickup_no = pickup_no

    await db.commit()
    return success_response(
        data={"pickup_no": pickup_no, "order_ids": [str(i) for i in affected_ids]},
        msg="取餐牌号已更新",
    )


class OrderReprintBody(PydanticBase):
    print_type: str = "kitchen"


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
    body: Optional[OrderReprintBody] = None,
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
    print_type = (body.print_type if body else "kitchen") or "kitchen"
    allowed, reason = can_reprint_order(order, print_type=print_type)
    if not allowed:
        return error_response(code=400, msg=reason or "order cannot reprint")
    print_result = await _print_paid_order_ticket(order, db, manual=True, reason="manual_reprint", operator=tenant_id)
    await db.commit()
    await db.refresh(order)
    return success_response(
        data={"id": str(order.id), **_serialize_print_meta(order), "print_result": print_result},
        msg="reprint submitted" if print_result.get("success") else "reprint failed",
    )

@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    request: Request,
    participant_token: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Cancel current customer order."""
    from app.models.coupon import Coupon as _Coupon
    from datetime import datetime as _dt

    customer_id = getattr(request.state, "customer_id", None)
    result = await db.execute(select(Order).where(Order.id == int(order_id)).with_for_update())
    order = result.scalar_one_or_none()
    if not order:
        return error_response(code=404, msg="order not found")
    # 归属校验：已登录的订单必须是同一个客户；匿名拼桌顾客下的单没有 customer_id，
    # 必须靠 participant_token 核对身份——否则任何人拿到 order_id 就能取消别人的挂单
    # （同一桌台其他人能在"本桌已点菜品"里直接看到这个 order_id）。
    if order.customer_id:
        if not customer_id or int(customer_id) != int(order.customer_id):
            return error_response(code=403, msg="forbidden")
    elif order.participant_id:
        from app.models.dining import DiningParticipant
        from app.services.dining_session_service import hash_participant_token

        owns_order = False
        if participant_token:
            participant_result = await db.execute(
                select(DiningParticipant).where(
                    DiningParticipant.id == order.participant_id,
                    DiningParticipant.guest_token_hash == hash_participant_token(participant_token),
                )
            )
            owns_order = participant_result.scalar_one_or_none() is not None
        if not owns_order:
            return error_response(code=403, msg="forbidden")
    # 取消前先跟微信核实一下：如果顾客刚好在微信那边已经付款成功、回调只是还没送达，
    # 直接放行取消会导致钱已经进商户账户但订单却显示已取消——没人会再去处理这笔钱。
    if order.status == "pending_payment" and getattr(order, "payment_mode", "prepay") == "prepay":
        if await _recover_wxpay_order_if_paid(order, db):
            await db.commit()
            return error_response(code=400, msg="订单已支付，请刷新查看最新状态")
    if order.status not in ("pending_payment", "pending"):
        return error_response(code=400, msg="订单已支付或已完成，无法取消")
    if getattr(order, "payment_status", None) == "paid":
        refund_result = await _refund_order_payment(order, db, reason="customer_cancel")
        if not refund_result["success"]:
            await db.rollback()
            return error_response(code=502, msg=f"取消失败，退款处理异常，请稍后重试或联系客服：{refund_result['error']}")
    await _restore_order_stock(order, db)
    order.status = "cancelled"
    # P0 修复：恢复被 LOCKED 的优惠券
    if order.coupon_id:
        coupon = await db.get(_Coupon, order.coupon_id)
        if coupon and coupon.status == "LOCKED":
            coupon.status = "UNUSED"
    await db.commit()
    return success_response(data={"id": str(order.id), "status": "cancelled"}, msg="order cancelled")


@router.get("/orders/my")
async def get_my_order(
    order_id: str,
    request: Request,
    participant_token: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get current customer order status."""
    result = await db.execute(select(Order).where(Order.id == int(order_id)))
    order = result.scalar_one_or_none()
    if not order:
        return error_response(code=404, msg="order not found")

    # 所有权校验：按 ID 就能查到别人订单的状态/备注，之前只凭 order_id 不做任何校验。
    # 已登录顾客按 customer_id 核对；匿名同桌顾客按 dining participant 的令牌核对。
    customer_id = getattr(request.state, "customer_id", None)
    if order.customer_id:
        if not customer_id or int(customer_id) != int(order.customer_id):
            return error_response(code=403, msg="forbidden")
    elif order.participant_id:
        from app.models.dining import DiningParticipant
        from app.services.dining_session_service import hash_participant_token

        owns_order = False
        if participant_token:
            participant_result = await db.execute(
                select(DiningParticipant).where(
                    DiningParticipant.id == order.participant_id,
                    DiningParticipant.guest_token_hash == hash_participant_token(participant_token),
                )
            )
            owns_order = participant_result.scalar_one_or_none() is not None
        if not owns_order:
            return error_response(code=403, msg="forbidden")

    recovered = await _recover_wxpay_order_if_paid(order, db)
    if recovered:
        await db.commit()
        await db.refresh(order)

    reward_coupon = None
    if order.reward_coupon_snapshot:
        try:
            reward_coupon = json.loads(order.reward_coupon_snapshot)
        except Exception:
            reward_coupon = None

    return success_response(data={
        "id": str(order.id),
        "status": order.status,
        "payment_status": order.payment_status,
        "merchant_note": order.merchant_note,
        "reward_coupon": reward_coupon,
    })


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
        # A dining session that stays open past midnight still has orders from
        # "yesterday" blocking settle-table today. Always surface still-open
        # orders regardless of created_at, or they become invisible in this
        # list while still blocking checkout (same class of bug as the
        # pending_payment table-grouping fix above). "done" orders don't block
        # settle_table (they get finalized during closing), but they still
        # haven't been paid/settled yet -- surface those across days too, or a
        # table that finished cooking right before an idle dining_session
        # rolled over to a new day silently drops out of the merchant's
        # default view with no indication anything is owed.
        query = query.where(
            or_(
                and_(Order.created_at >= day_start_utc, Order.created_at < day_end_utc),
                Order.status.in_(TABLE_CLOSE_BLOCKING_STATUSES),
                Order.status == "done",
            )
        )

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

    session_ids = {o.dining_session_id for o in orders if getattr(o, "dining_session_id", None)}
    checkout_requested_by_session = {}
    if session_ids:
        from app.models.dining import DiningSession

        sessions_result = await db.execute(
            select(DiningSession.id, DiningSession.checkout_requested_at).where(
                DiningSession.id.in_(session_ids)
            )
        )
        for session_id, checkout_requested_at in sessions_result.all():
            if checkout_requested_at:
                checkout_requested_by_session[session_id] = checkout_requested_at.isoformat()

    # 拼桌场景下接单页要能看出"这道菜是哪位点的"——跟顾客端"已点菜品"用的是
    # 同一套编号算法（DiningSessionService.get_participant_ordinals），两边永远对得上。
    from app.services.dining_session_service import DiningSessionService
    participant_ordinals = await DiningSessionService.get_participant_ordinals(db, tenant_id, list(session_ids))

    rows = [
        serialize_order(
            o,
            items_by_order.get(o.id, []),
            checkout_requested_at=checkout_requested_by_session.get(getattr(o, "dining_session_id", None)),
            participant_no=participant_ordinals.get(getattr(o, "participant_id", None)),
        )
        for o in orders
    ]
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
    if not customer_id:
        return error_response(code=401, msg="请先登录")
    if not 1 <= body.rating <= 5:
        return error_response(code=400, msg="璇勫垎闇€鍦?-5涔嬮棿")

    result = await db.execute(select(Order).where(Order.id == int(order_id)))
    order = result.scalar_one_or_none()
    if not order:
        return error_response(code=404, msg="order not found")
    if int(order.customer_id or 0) != int(customer_id):
        return error_response(code=403, msg="forbidden")
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


