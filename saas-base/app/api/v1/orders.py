# mypy: disallow-untyped-defs=False, disallow-incomplete-defs=False, check-untyped-defs=False
from datetime import date, datetime, timezone
import json
from decimal import Decimal
from typing import Any, List, Optional, TypeAlias, cast as typing_cast

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
from app.core.response import RespVo, error_response, success_response
from app.core.tenant_context import TenantContext
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.services.consumption_service import _record_order_consumption
from app.services.coupon_service import (
    CouponService,
    _mark_order_coupon_used_if_locked,
    _set_order_coupon_status_if_locked,
    _unlock_order_coupon_if_locked,
)
from app.services.order_lifecycle_service import OrderLifecycleService
from app.services.order_payment_service import OrderPaymentService
from app.services.order_print_service import (
    _compose_merchant_note_with_print_meta,
    _get_print_meta,
    _print_paid_order_ticket,
    _print_paid_order_ticket_background,
    _serialize_print_meta,
    _spawn_background_print_task,
    _split_merchant_note_and_print_meta,
    build_staff_print_summary,
    can_reprint_order,
    reconcile_print_orders,
)
from app.services.order_stock_service import _restore_order_stock

OrderItemRow: TypeAlias = tuple[int, str, float, int]
ApiResponse: TypeAlias = RespVo[Any]
PrepareTenantReplayResult: TypeAlias = tuple[ApiResponse | None, Tenant | None, str | None]
PaymentModeFlags: TypeAlias = tuple[str, bool, bool, bool]
ValidateItemsResult: TypeAlias = tuple[ApiResponse | None, float | None, list[OrderItemRow] | None]
ApplyCouponResult: TypeAlias = tuple[ApiResponse | None, int | None, Decimal]


def _numeric_float(value: object) -> float:
    return float(str(value or 0))

router = APIRouter(prefix="/api/v1", tags=["订单"])


PENDING_PAYMENT_TIMEOUT_MINUTES = 15  # 待支付订单超时时长（分钟）

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


def serialize_order(
    order,
    order_items,
    checkout_requested_at=None,
    participant_no=None,
    *,
    pickup_settings=None,
    dining_session=None,
):
    from app.services.pickup_no_service import can_assign_pickup_no, parse_pickup_settings

    print_meta = _serialize_print_meta(order)
    settings = pickup_settings if pickup_settings is not None else parse_pickup_settings(None)
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
        "created_by_account_id": (
            str(order.created_by_account_id)
            if getattr(order, "created_by_account_id", None) is not None
            else None
        ),
        "created_by_role": getattr(order, "created_by_role", None),
        "staff_note": getattr(order, "staff_note", None),
        "pickup_no": getattr(order, "pickup_no", None),
        "can_assign_pickup_no": can_assign_pickup_no(order, settings, dining_session),
        "served_at": order.served_at.isoformat() if getattr(order, "served_at", None) else None,
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


async def _replay_order_response(
    db: AsyncSession, tenant_id: str, request_id: str | None
) -> ApiResponse | None:
    """Look up an existing order by client_request_id and build the create_order replay response."""
    if not request_id:
        return None
    replay_result = await db.execute(
        select(Order).where(Order.tenant_id == tenant_id, Order.client_request_id == request_id)
    )
    replay_order = replay_result.scalar_one_or_none()
    if not replay_order:
        return None
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
            "pay_amount": _numeric_float(replay_order.total),
            "payment_mode": replay_payment_mode,
        },
        msg="order already created, please pay",
    )


async def _prepare_create_order_tenant_and_replay(
    body: OrderCreate, db: AsyncSession
) -> PrepareTenantReplayResult:
    """Validate tenant/business hours and replay idempotent create_order requests.

    Returns (early_response, tenant, tenant_id). When early_response is not None,
    the caller must return it immediately and ignore tenant.
    """
    tenant_id = body.shop
    if not tenant_id:
        return error_response(code=400, msg="缺少shop参数"), None, tenant_id
    TenantContext.set_tenant_id(tenant_id)

    tenant_result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        return error_response(code=404, msg="商户不存在"), None, tenant_id
    if not tenant.status:
        return error_response(code=403, msg="商户已停业，暂不接受点餐"), None, tenant_id
    from app.models.tenant_config import TenantConfig

    config_result = await db.execute(select(TenantConfig).where(TenantConfig.tenant_id == tenant_id))
    tenant_config = config_result.scalar_one_or_none()
    business_info: dict[str, Any] = (tenant_config.business_info or {}) if tenant_config else {}
    if not business_info.get("is_open", True):
        return error_response(code=400, msg="门店休息中，暂不接受点餐"), None, tenant_id

    request_id = (body.request_id or "").strip() or None
    if request_id:
        replay_response = await _replay_order_response(db, tenant_id, request_id)
        if replay_response is not None:
            return replay_response, None, tenant_id

    return None, tenant, tenant_id


async def _resolve_create_order_payment_mode(
    tenant: Tenant, tenant_id: str, body: OrderCreate, db: AsyncSession
) -> PaymentModeFlags:
    """Resolve payment_mode and derived flags from tenant defaults and table zone."""
    payment_mode = str(tenant.payment_mode if tenant else "prepay")
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
    return payment_mode, is_postpay, is_table_account, pay_later_mode


async def _resolve_create_order_dining_context(
    body: OrderCreate,
    request: Request,
    db: AsyncSession,
    tenant_id: str,
    payment_mode: str,
    is_table_account: bool,
) -> tuple[
    ApiResponse | None,
    int | None,
    int | None,
    int | None,
    str | None,
    int | None,
    Any,
]:
    """Resolve dining session, participant identity, and add-on parent for create_order.

    Returns (
        early_response,
        customer_id,
        dining_session_id,
        dining_participant_id,
        order_type,
        parent_order_id,
        session_for_pickup,
    ). When early_response is not None, the caller must return it immediately.
    """
    from datetime import datetime as _dt

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
        from app.core.permissions import parse_staff_role

        merchant_tenant_id = getattr(request.state, "tenant_id", None)
        if not merchant_tenant_id or merchant_tenant_id != tenant_id:
            return error_response(code=403, msg="无权为该门店下单"), customer_id, None, None, None, None, None
        if payment_mode not in ("postpay", "table_account"):
            return (
                error_response(code=400, msg="当前收款模式请由顾客扫码加单"),
                customer_id,
                None,
                None,
                None,
                None,
                None,
            )
        if body.coupon_id:
            return error_response(code=400, msg="代客加单不支持使用优惠券"), customer_id, None, None, None, None, None
        table_no = (body.table or "").strip()
        if not table_no:
            return error_response(code=400, msg="缺少桌号"), customer_id, None, None, None, None, None

        from app.services.dining_session_service import DiningSessionService

        staff_role = parse_staff_role(getattr(request.state, "role", None))
        session_id_raw = getattr(body, "dining_session_id", None)
        session_id = int(session_id_raw) if session_id_raw else None
        try:
            if staff_role:
                # Frontdesk/Waiter: never invent a new dining session.
                session = await DiningSessionService(db).get_open_session_for_staff(
                    tenant_id,
                    table_no,
                    dining_session_id=session_id,
                )
                if session is None:
                    return (
                        error_response(code=400, msg="当前桌台没有进行中的用餐订单"),
                        customer_id,
                        None,
                        None,
                        None,
                        None,
                        None,
                    )
            else:
                session = await DiningSessionService(db).get_or_create_open_session_for_staff(
                    tenant_id, table_no
                )
        except ValueError as exc:
            return error_response(code=400, msg=str(exc)), customer_id, None, None, None, None, None

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
        # Staff roles must add onto an existing table bill (ADD_ON), not open a blank table.
        if staff_role and parent_order is None:
            return (
                error_response(code=400, msg="当前桌台没有进行中的用餐订单"),
                customer_id,
                None,
                None,
                None,
                None,
                None,
            )
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
        locked_session = session_result.scalar_one_or_none()
        if locked_session is None:
            return error_response(code=400, msg="dining session not found"), customer_id, None, None, None, None, None
        session_for_pickup = locked_session

        participant_filters = [
            DiningParticipant.tenant_id == tenant_id,
            DiningParticipant.session_id == locked_session.id,
        ]
        if body.participant_token:
            participant_filters.append(DiningParticipant.guest_token_hash == hash_participant_token(body.participant_token))
        elif customer_id:
            participant_filters.append(DiningParticipant.customer_id == customer_id)
        elif body.client_id:
            participant_filters.append(DiningParticipant.client_id == body.client_id)
        else:
            return error_response(code=400, msg="缺少本桌身份，请重新扫码"), customer_id, None, None, None, None, None

        participant_result = await db.execute(select(DiningParticipant).where(*participant_filters))
        participant = participant_result.scalar_one_or_none()
        if not participant:
            # 409 而不是 403：本桌匿名身份没对上，跟"会员登录过期"是两码事。401/403 在这个
            # 项目里全局约定代表"需要重新登录"，小程序端的通用拦截器会把它们当成会员登录
            # 失效处理（清掉 customer_token、弹微信授权框），如果这里复用 403 会把一次可以
            # 静默重试的本桌身份问题误导成"你必须先注册会员"，这正是历史上真实发生过的 bug。
            return error_response(code=409, msg="本桌身份已失效，请重新扫码"), customer_id, None, None, None, None, None

        dining_session_id = locked_session.id
        dining_participant_id = participant.id
        payment_status_filter = [Order.payment_status == "paid"] if payment_mode == "prepay" else []
        existing_order_result = await db.execute(
            select(Order)
            .where(
                Order.tenant_id == tenant_id,
                Order.dining_session_id == locked_session.id,
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
        locked_session.last_activity_at = _dt.utcnow()

    if is_table_account and not dining_session_id:
        return error_response(code=400, msg="桌台账单模式需要重新扫码进入本桌"), customer_id, None, None, None, None, None

    return None, customer_id, dining_session_id, dining_participant_id, order_type, parent_order_id, session_for_pickup


async def _cleanup_stale_pending_payment_orders(tenant_id: str, db: AsyncSession) -> None:
    from datetime import datetime as _dt, timedelta

    from app.models.coupon import Coupon

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
    payment_svc = OrderPaymentService(db)
    for stale in stale_orders:
        recovered = await payment_svc._recover_wxpay_order_if_paid(stale)
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


async def _validate_create_order_items_and_compute_total(
    body: OrderCreate, db: AsyncSession, tenant_id: str
) -> ValidateItemsResult:
    """Validate menu items, deduct stock per line, and compute order total.

    Returns (early_response, real_total, order_items_data). When early_response is
    not None, the caller must return it immediately.
    """
    from app.api.v1.menu import load_menu_specs
    from app.models.menu_item import MenuItem

    # 从 DB 重新计算价格、检查客户归属/下架状态，检查并扣减库存（with_for_update 防超卖）
    if not body.items:
        return error_response(code=400, msg="订单商品不能为空"), None, None

    specs_map = await load_menu_specs(db, tenant_id)

    def _resolve_spec_delta(dish: MenuItem, item_in: OrderItemIn) -> float:
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
            group_opts = radio_lookup.get(spec_sel.group)
            if group_opts is None or spec_sel.value not in group_opts:
                raise ValueError(f"无效的规格选择:{item_in.name}")
            delta += group_opts[spec_sel.value]
        for extra_name in (item_in.extras or []):
            if extra_name not in checkbox_lookup:
                raise ValueError(f"无效的附加选项:{item_in.name}")
            delta += checkbox_lookup[extra_name]
        return delta

    real_total = 0.0
    order_items_data: list[OrderItemRow] = []
    for item_in in body.items:
        if item_in.qty <= 0:
            return error_response(code=400, msg=f"商品数量必须大于0:{item_in.name}"), None, None

        if item_in.dish_id:
            dish_result = await db.execute(
                select(MenuItem)
                .where(MenuItem.id == item_in.dish_id, MenuItem.tenant_id == tenant_id)
                .with_for_update()
            )
            dish = dish_result.scalar_one_or_none()
            if not dish:
                return error_response(code=400, msg=f"菜品不存在:{item_in.name}"), None, None
            if not dish.available:
                return error_response(code=400, msg=f"菜品已下架:{dish.name}"), None, None
            if dish.stock is not None and dish.stock <= 0:
                return error_response(code=400, msg=f"dish sold out: {dish.name}"), None, None
            if dish.stock is not None and dish.stock < item_in.qty:
                return error_response(code=400, msg=f"dish stock not enough: {dish.name}, left {dish.stock}"), None, None
            try:
                spec_delta = _resolve_spec_delta(dish, item_in)
            except ValueError as exc:
                return error_response(code=400, msg=str(exc)), None, None
            unit_price = _numeric_float(dish.price) + spec_delta
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
            return error_response(code=400, msg=f"缺少菜品ID:{item_in.name}"), None, None
        real_total += unit_price * item_in.qty
        order_items_data.append((item_in.dish_id, name, unit_price, item_in.qty))

    return None, real_total, order_items_data


async def _apply_create_order_coupon(
    body: OrderCreate,
    customer_id: int | None,
    tenant_id: str,
    real_total: float,
    db: AsyncSession,
) -> ApplyCouponResult:
    """Validate and lock a coupon for create_order.

    Returns (early_response, applied_coupon_id, coupon_discount). When early_response is
    not None, the caller must return it immediately.
    """
    from datetime import datetime as _dt
    from decimal import Decimal

    from app.models.coupon import Coupon
    from app.models.coupon_template import CouponTemplate

    applied_coupon_id = None
    coupon_discount = Decimal("0")

    # BUG-2: 建单时仅验证优惠券，不标记 USED，改为 LOCKED（支付时再核销）
    if body.coupon_id:
        if not customer_id:
            return error_response(code=401, msg="请先登录后使用优惠券"), applied_coupon_id, coupon_discount
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
            return error_response(code=400, msg="优惠券不可用或已失效"), applied_coupon_id, coupon_discount

        tpl = await db.get(CouponTemplate, coupon.template_id)
        if not tpl:
            return error_response(code=400, msg="优惠券规则不存在"), applied_coupon_id, coupon_discount

        min_amount = float(tpl.min_amount or 0)
        if real_total < min_amount:
            return error_response(code=400, msg="未达到优惠券使用门槛"), applied_coupon_id, coupon_discount

        if tpl.type == "PERCENT":
            raw_discount = real_total * float(tpl.value or 0) / 100
        else:
            raw_discount = float(tpl.value or 0)
        # 红线兜底：不管模板配置得对不对，实际减免不超过这一单实付金额的安全比例
        coupon_discount = Decimal(str(cap_discount_amount(raw_discount, real_total)))
        coupon.status = "LOCKED"
        applied_coupon_id = coupon.id

    return None, applied_coupon_id, coupon_discount


async def _persist_create_order_and_build_response(
    *,
    body: OrderCreate,
    db: AsyncSession,
    tenant_id: str,
    request_id: str | None,
    customer_id: int | None,
    dining_session_id: int | None,
    dining_participant_id: int | None,
    order_type: str | None,
    parent_order_id: int | None,
    session_for_pickup: Any,
    payment_mode: str,
    pay_later_mode: bool,
    is_staff_order: bool,
    created_by_account_id: int | None,
    created_by_role: str | None,
    applied_coupon_id: int | None,
    coupon_discount: Decimal,
    final_total: float,
    order_items_data: list[OrderItemRow],
) -> ApiResponse:
    """Persist order + items, schedule pay-later print, and build create_order response."""
    # 取餐牌号跟着"这一桌这次吃饭"走，不是跟着"这一单"走：显式传了就用显式的（顺便把这个
    # 号同步成这一桌接下来所有加单共享的值），没传就继承这一桌已经登记过的号，避免同一桌
    # 每加一单都要前台重新填一遍。
    explicit_pickup_no = (body.pickup_no or "").strip()[:16] or None
    from app.services.pickup_no_service import PickupNoService, load_pickup_settings

    pickup_settings = await load_pickup_settings(db, tenant_id)
    # prepay + 启用桌牌：创建时未支付不能新占号（仍可继承会话已有牌号）
    if (
        explicit_pickup_no
        and pickup_settings.get("enabled")
        and payment_mode == "prepay"
        and not (session_for_pickup and session_for_pickup.pickup_no)
    ):
        return error_response(code=422, msg="该订单尚未支付，暂不能分配桌牌")

    if explicit_pickup_no and session_for_pickup is not None:
        session_for_pickup.pickup_no = explicit_pickup_no
    resolved_pickup_no = explicit_pickup_no or (session_for_pickup.pickup_no if session_for_pickup else None)
    # 写入活跃租约；同号冲突时创建订单失败（由 UNIQUE 兜底）
    if resolved_pickup_no and session_for_pickup is not None and explicit_pickup_no:
        try:
            await PickupNoService(db).ensure_session_assignment(
                tenant_id=tenant_id,
                session=session_for_pickup,
                pickup_no=resolved_pickup_no,
            )
        except IntegrityError:
            await db.rollback()
            return error_response(code=409, msg=f"{resolved_pickup_no}号桌牌正在使用中，请选择其他号码")
    elif resolved_pickup_no and session_for_pickup is not None:
        # 继承已有会话牌号：确保租约存在（历史会话可能缺租约行）
        try:
            await PickupNoService(db).ensure_session_assignment(
                tenant_id=tenant_id,
                session=session_for_pickup,
                pickup_no=resolved_pickup_no,
            )
        except IntegrityError:
            # 继承场景下租约冲突极少见：会话已有号但租约被他桌占了——不阻断下单，只打日志
            logger.warning(
                "pickup assignment conflict on inherit tenant=%s session=%s pickup=%s",
                tenant_id,
                session_for_pickup.id,
                resolved_pickup_no,
            )

    order = Order(
        tenant_id=tenant_id,
        customer_id=customer_id,
        dining_session_id=dining_session_id,
        participant_id=dining_participant_id,
        order_type=order_type,
        parent_order_id=parent_order_id,
        table_no=body.table or "",
        phone=body.phone,
        total=typing_cast(Any, final_total),
        status="pending" if payment_mode in ("postpay", "table_account") else "pending_payment",
        payment_status="unpaid",
        payment_mode=payment_mode,
        remark=body.remark,
        coupon_id=applied_coupon_id,
        discount_amount=typing_cast(Any, float(coupon_discount)) if coupon_discount > 0 else None,
        source="staff" if is_staff_order else (body.source or "miniprogram"),
        created_by_account_id=created_by_account_id if is_staff_order else None,
        created_by_role=created_by_role if is_staff_order else None,
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
        replay_response = await _replay_order_response(db, tenant_id, request_id)
        if replay_response is not None:
            return replay_response
        return error_response(code=409, msg="订单提交冲突，请重试")

    order_items = []
    assert order.id is not None
    for dish_id, name, unit_price, qty in order_items_data:
        oi = OrderItem(
            order_id=order.id,
            dish_id=dish_id,
            name=name,
            price=typing_cast(Any, unit_price),
            qty=qty,
        )
        db.add(oi)
        order_items.append(oi)

    await db.flush()
    await db.commit()
    await db.refresh(order)
    # 出票挪到 commit 之后、且不 await——顾客提交订单不该等一次第三方打印机 API。
    # 必须在 commit 之后才调度：后台任务用的是独立 session，提前调度会因为这笔订单
    # 在别的 session 里还看不见（还没提交）而被 _print_paid_order_ticket 误判成
    # "订单不存在/还没付款"，直接跳过打印。
    if pay_later_mode:
        _spawn_background_print_task(
            _print_paid_order_ticket_background(int(order.id), str(order.tenant_id), reason="order_created_pay_later")
        )

    order_data = serialize_order(
        order,
        order_items,
        pickup_settings=pickup_settings,
        dining_session=session_for_pickup,
    )
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


@router.post("/orders")
async def create_order(
    body: OrderCreate, request: Request, db: AsyncSession = Depends(get_db)
) -> ApiResponse:
    early_response, tenant, tenant_id = await _prepare_create_order_tenant_and_replay(body, db)
    if early_response is not None:
        return early_response

    if tenant is None:
        return error_response(code=500, msg="tenant missing after validation")

    assert tenant_id is not None

    payment_mode, is_postpay, is_table_account, pay_later_mode = await _resolve_create_order_payment_mode(
        tenant, tenant_id, body, db
    )

    request_id = (body.request_id or "").strip() or None

    (
        early_response,
        customer_id,
        dining_session_id,
        dining_participant_id,
        order_type,
        parent_order_id,
        session_for_pickup,
    ) = await _resolve_create_order_dining_context(
        body, request, db, tenant_id, payment_mode, is_table_account
    )
    if early_response is not None:
        return early_response

    is_staff_order = getattr(request.state, "token_type", None) == "merchant"
    created_by_account_id = None
    created_by_role = None
    if is_staff_order:
        from app.core.permissions import ROLE_OWNER, parse_staff_role

        staff_role = parse_staff_role(getattr(request.state, "role", None))
        account_id = getattr(request.state, "account_id", None)
        if staff_role and account_id is not None:
            created_by_account_id = int(account_id)
            created_by_role = staff_role
        else:
            created_by_account_id = None
            created_by_role = ROLE_OWNER

    await _cleanup_stale_pending_payment_orders(tenant_id, db)

    early_response, real_total, order_items_data = await _validate_create_order_items_and_compute_total(
        body, db, tenant_id
    )
    if early_response is not None:
        return early_response

    assert tenant_id is not None
    assert real_total is not None
    assert order_items_data is not None

    early_response, applied_coupon_id, coupon_discount = await _apply_create_order_coupon(
        body, customer_id, tenant_id, real_total, db
    )
    if early_response is not None:
        return early_response

    final_total = max(real_total - float(coupon_discount), 0)

    return await _persist_create_order_and_build_response(
        body=body,
        db=db,
        tenant_id=tenant_id,
        request_id=request_id,
        customer_id=customer_id,
        dining_session_id=dining_session_id,
        dining_participant_id=dining_participant_id,
        order_type=order_type,
        parent_order_id=parent_order_id,
        session_for_pickup=session_for_pickup,
        payment_mode=payment_mode,
        pay_later_mode=pay_later_mode,
        is_staff_order=is_staff_order,
        created_by_account_id=created_by_account_id,
        created_by_role=created_by_role,
        applied_coupon_id=applied_coupon_id,
        coupon_discount=coupon_discount,
        final_total=final_total,
        order_items_data=order_items_data,
    )


@router.post("/orders/{order_id}/mock-pay")
async def mock_pay_order(
    order_id: str,
    body: MockPayBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Mock payment for development only."""
    return await OrderPaymentService(db).mock_pay_order(order_id, body, request)


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
    return await OrderPaymentService(db).create_wxpay_order(order_id, body, request)


@router.post("/orders/wxpay-notify")
async def wxpay_notify(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle WeChat Pay notify for direct merchant mode."""
    return await OrderPaymentService(db).wxpay_notify(request)


class OrderStatusUpdate(PydanticBase):
    status: str  # pending | preparing | done | settled


@router.patch("/orders/{order_id}/status")
async def update_order_status(
    order_id: str,
    body: OrderStatusUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    from app.core.merchant_auth import get_request_principal, require_order_status_permission
    from fastapi.responses import JSONResponse
    from app.core.response import RespVo

    principal = get_request_principal(request)
    if not principal:
        return error_response(code=401, msg="请先登录")
    if not require_order_status_permission(body.status, principal.role):
        return JSONResponse(
            status_code=403,
            content=RespVo(code=403, msg="当前账号无此权限").to_response(),
        )
    service = OrderLifecycleService(db)
    service.set_tenant_id(principal.tenant_id)
    return await service.update_order_status(int(order_id), body)

TABLE_CLOSE_BLOCKING_STATUSES = {"pending_payment", "pending", "preparing", "refunding", "refund_pending", "refund_requested"}
TABLE_CLOSE_DONE_STATUSES = {"done", "settled", "cancelled", "rejected"}


@router.post("/orders/settle-table")
async def settle_table(
    body: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Close the current open table session only after all payable orders are finished."""
    from app.core.merchant_auth import get_request_principal
    from app.core.permissions import PERM_FINANCE_SETTLE
    from fastapi.responses import JSONResponse
    from app.core.response import RespVo

    principal = get_request_principal(request)
    if not principal:
        return error_response(code=401, msg="请先登录")
    if not principal.can(PERM_FINANCE_SETTLE):
        return JSONResponse(
            status_code=403,
            content=RespVo(code=403, msg="当前账号无此权限").to_response(),
        )
    service = OrderLifecycleService(db)
    service.set_tenant_id(principal.tenant_id)
    closed_by = str(getattr(request.state, "user_id", "") or "merchant")
    return await service.settle_table(body, closed_by=closed_by)


class MerchantNoteUpdate(PydanticBase):
    note: str = ""


class OrderPickupNoUpdate(PydanticBase):
    pickup_no: str = ""


@router.get("/pickup-nos/status")
async def get_pickup_no_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """商家端号牌选择器：返回启用状态、数量与当前占用（仅本租户）。"""
    from app.core.merchant_auth import get_request_principal
    from app.core.permissions import PERM_PICKUP_VIEW
    from fastapi.responses import JSONResponse
    from app.core.response import RespVo

    principal = get_request_principal(request)
    if not principal:
        return error_response(code=401, msg="请先登录")
    if not principal.can(PERM_PICKUP_VIEW):
        return JSONResponse(
            status_code=403,
            content=RespVo(code=403, msg="当前账号无此权限").to_response(),
        )
    from app.services.pickup_no_service import PickupNoService, load_pickup_settings

    settings = await load_pickup_settings(db, principal.tenant_id)
    occupied = await PickupNoService(db).list_occupied(principal.tenant_id)
    return success_response(
        data={
            "enabled": settings["enabled"],
            "count": settings["count"],
            "required_before_print": settings["required_before_print"],
            "occupied": occupied,
        }
    )


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
    from app.core.merchant_auth import get_request_principal
    from app.core.permissions import PERM_PICKUP_ASSIGN, PERM_PICKUP_CHANGE
    from fastapi.responses import JSONResponse
    from app.core.response import RespVo

    principal = get_request_principal(request)
    if not principal:
        return error_response(code=401, msg="请先登录")
    if not (principal.can(PERM_PICKUP_ASSIGN) or principal.can(PERM_PICKUP_CHANGE)):
        return JSONResponse(
            status_code=403,
            content=RespVo(code=403, msg="当前账号无此权限").to_response(),
        )
    service = OrderLifecycleService(db)
    service.set_tenant_id(principal.tenant_id)
    return await service.update_order_pickup_no(int(order_id), body.pickup_no)


@router.post("/orders/{order_id}/serve")
async def serve_order(
    order_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Waiter/Owner: confirm dish served. Does not change order.status or print/payment."""
    from app.core.merchant_auth import get_request_principal
    from app.core.permissions import PERM_ORDER_SERVE
    from fastapi.responses import JSONResponse
    from app.core.response import RespVo

    principal = get_request_principal(request)
    if not principal:
        return error_response(code=401, msg="请先登录")
    if not principal.can(PERM_ORDER_SERVE):
        return JSONResponse(
            status_code=403,
            content=RespVo(code=403, msg="当前账号无此权限").to_response(),
        )
    service = OrderLifecycleService(db)
    service.set_tenant_id(principal.tenant_id)
    return await service.serve_order(
        int(order_id),
        account_id=principal.account_id,
        role=principal.role,
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
    service = OrderLifecycleService(db)
    service.set_tenant_id(tenant_id)
    return await service.update_merchant_note(int(order_id), body.note)


@router.post("/orders/{order_id}/reprint")
async def reprint_order_ticket(
    order_id: str,
    request: Request,
    body: Optional[OrderReprintBody] = None,
    db: AsyncSession = Depends(get_db),
):
    from app.core.merchant_auth import get_request_principal
    from app.core.permissions import PERM_KITCHEN_PRINT_REPRINT
    from fastapi.responses import JSONResponse
    from app.core.response import RespVo

    principal = get_request_principal(request)
    if not principal:
        return error_response(code=401, msg="请先登录")
    print_type = (body.print_type if body else "kitchen") or "kitchen"
    # Staff may only reprint kitchen tickets; owners keep full reprint capability.
    if not principal.is_owner:
        if print_type != "kitchen" or not principal.can(PERM_KITCHEN_PRINT_REPRINT):
            return JSONResponse(
                status_code=403,
                content=RespVo(code=403, msg="当前账号无此权限").to_response(),
            )
    result = await db.execute(
        select(Order).where(Order.id == int(order_id), Order.tenant_id == principal.tenant_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        return error_response(code=404, msg="order not found")
    allowed, reason = can_reprint_order(order, print_type=print_type)
    if not allowed:
        return error_response(code=400, msg=reason or "order cannot reprint")
    operator = str(principal.account_id) if principal.account_id else "owner"
    print_result = await _print_paid_order_ticket(
        order,
        db,
        manual=True,
        reason="manual_reprint",
        operator=operator,
        operator_role=principal.role,
    )
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
    customer_id = getattr(request.state, "customer_id", None)
    service = OrderLifecycleService(db)
    return await service.cancel_order(
        int(order_id),
        customer_id=int(customer_id) if customer_id else None,
        participant_token=participant_token,
    )


@router.get("/orders/my")
async def get_my_order(
    order_id: str,
    request: Request,
    participant_token: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get current customer order status."""
    customer_id = getattr(request.state, "customer_id", None)
    service = OrderLifecycleService(db)
    return await service.get_my_order(
        int(order_id),
        customer_id=int(customer_id) if customer_id else None,
        participant_token=participant_token,
    )


def serialize_fulfillment_order(
    order,
    order_items,
    *,
    can_assign_pickup: bool = False,
    defer_kitchen_print: bool = False,
) -> dict:
    """Minimal fulfillment DTO for staff workbenches — no money / customer PII."""
    data = {
        "id": str(order.id),
        "display_order_no": str(order.id)[-4:],
        "status": order.status,
        "status_text": ORDER_STATUS_TEXT.get(order.status, order.status),
        "table_no": order.table_no or "",
        "pickup_no": getattr(order, "pickup_no", None) or "",
        "served_at": order.served_at.isoformat() if getattr(order, "served_at", None) else None,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "remark": order.remark or "",
        "staff_note": getattr(order, "staff_note", None) or "",
        "dining_session_id": str(order.dining_session_id) if getattr(order, "dining_session_id", None) else None,
        "order_type": getattr(order, "order_type", None),
        "order_type_text": ORDER_TYPE_TEXT.get(getattr(order, "order_type", None), ""),
        "can_assign_pickup_no": bool(can_assign_pickup),
        "items": [
            {
                "name": i.name,
                "qty": i.qty,
            }
            for i in order_items
        ],
    }
    data.update(build_staff_print_summary(order, defer_kitchen_print=defer_kitchen_print))
    return data


def serialize_recent_served_order(order, order_items) -> dict:
    """Minimal waiter recent-served DTO — no money, payment, member, or customer data."""
    return {
        "order_id": str(order.id),
        "table_no": order.table_no or "",
        "pickup_no": getattr(order, "pickup_no", None) or "",
        "served_at": order.served_at.isoformat() if getattr(order, "served_at", None) else None,
        "served_by_role": getattr(order, "served_by_role", None) or "",
        "items": [
            {
                "name": i.name,
                "qty": i.qty,
            }
            for i in order_items
        ],
    }


@router.get("/orders/workbench/recent-served-by-me")
async def list_recent_served_by_me(
    request: Request,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Waiter: pure-read recent orders served by the current staff account only."""
    from app.core.merchant_auth import get_request_principal
    from app.core.permissions import PERM_ORDER_SERVE
    from app.services.workbench_sync_service import load_order_items_by_order_ids
    from fastapi.responses import JSONResponse

    principal = get_request_principal(request)
    if not principal:
        return error_response(code=401, msg="请先登录")
    if not principal.can(PERM_ORDER_SERVE):
        return JSONResponse(
            status_code=403,
            content=RespVo(code=403, msg="当前账号无此权限").to_response(),
        )
    if principal.account_id is None:
        return success_response(data=[])

    safe_limit = max(1, min(int(limit or 10), 10))
    result = await db.execute(
        select(Order)
        .where(
            Order.tenant_id == principal.tenant_id,
            Order.served_by_account_id == int(principal.account_id),
            Order.served_at.is_not(None),
        )
        .order_by(Order.served_at.desc(), Order.id.desc())
        .limit(safe_limit)
    )
    orders = list(result.scalars().all())
    items_by_order = await load_order_items_by_order_ids(db, [o.id for o in orders])
    return success_response(
        data=[
            serialize_recent_served_order(o, items_by_order.get(o.id or 0, []))
            for o in orders
        ]
    )


@router.get("/orders/workbench")
async def list_workbench_orders(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Staff fulfillment feed — role from token; minimal DTO (no finance/member fields).

    Response body stays a bare array (legacy contract). Cursor for Phase 4C delta is
    returned in the X-Workbench-Cursor response header (snapshot max updated_at/id).
    Full snapshot may still run bounded print reconciliation (Phase 4B).
    """
    from app.core.merchant_auth import get_request_principal
    from app.core.permissions import PERM_ORDER_VIEW_FULFILLMENT, PERM_PICKUP_ASSIGN
    from app.services.pickup_no_service import (
        can_assign_pickup_no,
        load_pickup_settings,
        should_defer_kitchen_print,
    )
    from app.services.workbench_sync_service import (
        WORKBENCH_CURSOR_HEADER,
        cursor_from_orders,
        is_order_visible_in_workbench,
        load_order_items_by_order_ids,
        load_workbench_candidate_orders,
    )
    from fastapi.responses import JSONResponse

    principal = get_request_principal(request)
    if not principal:
        return error_response(code=401, msg="请先登录")
    if not principal.can(PERM_ORDER_VIEW_FULFILLMENT):
        return JSONResponse(
            status_code=403,
            content=RespVo(code=403, msg="当前账号无此权限").to_response(),
        )

    tenant_id = principal.tenant_id
    role = principal.role
    candidates = await load_workbench_candidate_orders(db, tenant_id)
    pickup_settings = await load_pickup_settings(db, tenant_id)

    # Print recovery stays on FULL only (never on /workbench/changes).
    recovered = await reconcile_print_orders(
        db,
        candidates,
        trigger="reconcile",
        pickup_settings=pickup_settings,
    )
    if recovered:
        await db.commit()
        for order in candidates:
            await db.refresh(order)

    orders = [o for o in candidates if is_order_visible_in_workbench(o, role)]
    items_by_order = await load_order_items_by_order_ids(db, [o.id for o in orders])

    sessions_by_id = {}
    session_ids = {o.dining_session_id for o in orders if getattr(o, "dining_session_id", None)}
    if session_ids:
        from app.models.dining import DiningSession

        sessions_result = await db.execute(select(DiningSession).where(DiningSession.id.in_(session_ids)))
        sessions_by_id = {s.id: s for s in sessions_result.scalars().all()}

    allow_assign = principal.can(PERM_PICKUP_ASSIGN)
    rows = []
    for o in orders:
        dining_session = sessions_by_id.get(getattr(o, "dining_session_id", None))
        assignable = bool(
            allow_assign and can_assign_pickup_no(o, pickup_settings, dining_session)
        )
        rows.append(
            serialize_fulfillment_order(
                o,
                items_by_order.get(o.id or 0, []),
                can_assign_pickup=assignable,
                defer_kitchen_print=should_defer_kitchen_print(o, pickup_settings),
            )
        )

    cursor = cursor_from_orders(candidates, fallback_now=datetime.utcnow())
    response = JSONResponse(content=RespVo(code=200, msg="ok", data=rows).to_response())
    response.headers[WORKBENCH_CURSOR_HEADER] = cursor
    return response


@router.get("/orders/workbench/changes")
async def list_workbench_order_changes(
    request: Request,
    cursor: Optional[str] = None,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Pure-read workbench delta. No print reconciliation / provider calls."""
    from app.core.merchant_auth import get_request_principal
    from app.core.permissions import PERM_ORDER_VIEW_FULFILLMENT, PERM_PICKUP_ASSIGN
    from app.services.pickup_no_service import (
        can_assign_pickup_no,
        load_pickup_settings,
        should_defer_kitchen_print,
    )
    from app.services.workbench_sync_service import (
        WORKBENCH_CHANGES_LIMIT,
        get_workbench_changes,
    )
    from fastapi.responses import JSONResponse

    principal = get_request_principal(request)
    if not principal:
        return error_response(code=401, msg="请先登录")
    if not principal.can(PERM_ORDER_VIEW_FULFILLMENT):
        return JSONResponse(
            status_code=403,
            content=RespVo(code=403, msg="当前账号无此权限").to_response(),
        )

    try:
        packed = await get_workbench_changes(
            db,
            tenant_id=principal.tenant_id,
            role=principal.role,
            cursor=cursor,
            limit=limit or WORKBENCH_CHANGES_LIMIT,
        )
    except ValueError:
        logger.warning(
            "workbench_changes invalid_cursor tenant_id=%s",
            principal.tenant_id,
        )
        return JSONResponse(
            status_code=400,
            content=RespVo(code=400, msg="INVALID_CURSOR", data=None).to_response(),
        )

    if packed.get("bootstrap"):
        return success_response(
            data={
                "items": [],
                "removed_ids": [],
                "next_cursor": packed["next_cursor"],
                "has_more": False,
                "bootstrap": True,
            }
        )

    visible_orders = packed["orders"]
    items_by_order = packed["items_by_order"]
    pickup_settings = await load_pickup_settings(db, principal.tenant_id)

    sessions_by_id = {}
    session_ids = {
        o.dining_session_id for o in visible_orders if getattr(o, "dining_session_id", None)
    }
    if session_ids:
        from app.models.dining import DiningSession

        sessions_result = await db.execute(select(DiningSession).where(DiningSession.id.in_(session_ids)))
        sessions_by_id = {s.id: s for s in sessions_result.scalars().all()}

    allow_assign = principal.can(PERM_PICKUP_ASSIGN)
    items = []
    for o in visible_orders:
        dining_session = sessions_by_id.get(getattr(o, "dining_session_id", None))
        assignable = bool(
            allow_assign and can_assign_pickup_no(o, pickup_settings, dining_session)
        )
        items.append(
            serialize_fulfillment_order(
                o,
                items_by_order.get(o.id or 0, []),
                can_assign_pickup=assignable,
                defer_kitchen_print=should_defer_kitchen_print(o, pickup_settings),
            )
        )

    return success_response(
        data={
            "items": items,
            "removed_ids": packed["removed_ids"],
            "next_cursor": packed["next_cursor"],
            "has_more": bool(packed["has_more"]),
            "bootstrap": False,
        }
    )


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
    from app.core.merchant_auth import get_request_principal
    from fastapi.responses import JSONResponse

    principal = get_request_principal(request)
    if not principal:
        return error_response(code=401, msg="请先登录")
    # Full order list (money/member fields) is owner-only; staff use /orders/workbench.
    if not principal.is_owner:
        return JSONResponse(
            status_code=403,
            content=RespVo(code=403, msg="当前账号无此权限").to_response(),
        )
    service = OrderLifecycleService(db)
    service.set_tenant_id(principal.tenant_id)
    return await service.list_orders(
        date_str=date_str,
        keyword=keyword,
        order_no=order_no,
        order_tail=order_tail,
        tail_no=tail_no,
        table_no=table_no,
        status=status,
        page=page,
        page_size=page_size,
    )

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
    customer_id = getattr(request.state, "customer_id", None)
    if not customer_id:
        return error_response(code=401, msg="请先登录")
    service = OrderLifecycleService(db)
    return await service.create_review(
        int(order_id),
        customer_id=int(customer_id),
        rating=body.rating,
        content=body.content,
    )


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
    service = OrderLifecycleService(db)
    service.set_tenant_id(tenant_id)
    return await service.list_reviews()


