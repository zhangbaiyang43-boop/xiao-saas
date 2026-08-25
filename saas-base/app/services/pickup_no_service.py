"""实体桌牌号（pickup_no）占用租约与分配规则。

DiningSession.pickup_no = 当前就餐占用的号
Order.pickup_no = 历史快照（结账后保留）
pickup_no_assignments = 当前活跃租约（UNIQUE tenant+pickup_no）
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import error_response, success_response
from app.models.dining import DiningSession
from app.models.order import Order
from app.models.pickup_no_assignment import PickupNoAssignment
from app.models.tenant_config import TenantConfig

logger = logging.getLogger(__name__)

# 拒单/取消时：这些状态不再占用桌牌；其余非终态仍占用
ORDER_STATUSES_HOLDING_PICKUP = frozenset({"pending_payment", "pending", "preparing", "done"})
ORDER_TERMINAL_STATUSES = frozenset({"cancelled", "rejected", "settled"})
# 首次「发桌牌」UI：可履约中
ORDER_FULFILLMENT_STATUSES = frozenset({"pending", "preparing", "done"})
ACTIVE_ORDER_STATUSES_EXCLUDED = frozenset({"cancelled", "rejected"})
TERMINAL_SESSION_STATUSES = frozenset({"CLOSED", "EXPIRED"})
DEFAULT_PICKUP_COUNT = 30
MAX_PICKUP_COUNT = 999


def normalize_pickup_no(raw: str | None) -> str | None:
    value = (raw or "").strip()[:16]
    return value or None


def parse_pickup_settings(business_info: dict | None) -> dict[str, Any]:
    info = business_info or {}
    enabled = bool(info.get("pickup_no_enabled", False))
    try:
        count = int(info.get("pickup_no_count") or DEFAULT_PICKUP_COUNT)
    except (TypeError, ValueError):
        count = DEFAULT_PICKUP_COUNT
    count = max(1, min(MAX_PICKUP_COUNT, count))
    # 启用桌牌时默认要求分牌后才打厨房票；关闭桌牌时该开关无意义
    if "pickup_no_required_before_print" in info:
        required = bool(info.get("pickup_no_required_before_print"))
    else:
        required = True
    return {
        "enabled": enabled,
        "count": count,
        "required_before_print": bool(required) if enabled else False,
    }


async def load_pickup_settings(db: AsyncSession, tenant_id: str) -> dict[str, Any]:
    result = await db.execute(select(TenantConfig).where(TenantConfig.tenant_id == tenant_id))
    config = result.scalar_one_or_none()
    return parse_pickup_settings(getattr(config, "business_info", None) if config else None)


def should_defer_kitchen_print(order: Order, settings: dict[str, Any]) -> bool:
    """启用桌牌且要求分牌后打印时，未分牌则暂缓厨房票。"""
    if not settings.get("enabled") or not settings.get("required_before_print"):
        return False
    return not normalize_pickup_no(getattr(order, "pickup_no", None))


def can_assign_pickup_no(
    order: Any,
    settings: dict[str, Any],
    session: DiningSession | None = None,
) -> bool:
    """商家「首次发桌牌」资格。必须基于 order.payment_mode，禁止用租户默认模式代替。

    已有 pickup_no 时返回 False（前端走「更换」，仍由 PATCH 校验）。
    """
    if not settings.get("enabled"):
        return False
    if normalize_pickup_no(getattr(order, "pickup_no", None)):
        return False

    status = (getattr(order, "status", None) or "").strip()
    if status in ORDER_TERMINAL_STATUSES or status == "pending_payment":
        return False
    if status not in ORDER_FULFILLMENT_STATUSES:
        return False

    mode = (getattr(order, "payment_mode", None) or "prepay").strip()
    if mode == "prepay" and getattr(order, "payment_status", None) != "paid":
        return False

    if session is not None:
        sess_status = (getattr(session, "status", None) or "").upper()
        if sess_status in TERMINAL_SESSION_STATUSES:
            return False
    elif mode == "table_account":
        # 桌台账单必须以 OPEN session 为履约载体
        return False

    return True


class PickupNoService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_occupied(self, tenant_id: str) -> list[dict[str, str]]:
        result = await self.db.execute(
            select(PickupNoAssignment).where(PickupNoAssignment.tenant_id == tenant_id)
        )
        rows = list(result.scalars().all())
        occupied = [
            {
                "pickup_no": row.pickup_no,
                "dining_session_id": str(row.dining_session_id),
            }
            for row in rows
        ]
        # 无 session 的孤儿订单（见 assign_for_order 的 session is None 分支）不写
        # PickupNoAssignment 租约表，选号器之前完全看不到它们占了哪个号——店员会把
        # 同一个号又发给另一桌不相关的顾客。这里把它们也纳入"使用中"列表，
        # dining_session_id 留空（前端 PickupNoPicker.vue 的 occupiedSet 对空
        # dining_session_id 就是当成"别人占的"处理，不需要改前端）。
        orphan_result = await self.db.execute(
            select(Order.pickup_no)
            .where(
                Order.tenant_id == tenant_id,
                Order.dining_session_id.is_(None),
                Order.pickup_no.is_not(None),
                Order.status.in_(list(ORDER_STATUSES_HOLDING_PICKUP)),
            )
            .distinct()
        )
        for (pickup_no,) in orphan_result.all():
            if pickup_no:
                occupied.append({"pickup_no": pickup_no, "dining_session_id": ""})
        return occupied

    async def release_session_assignment(
        self,
        tenant_id: str,
        session: DiningSession,
        *,
        clear_session_field: bool = True,
    ) -> None:
        """删除会话租约；可选清空 session.pickup_no。不碰历史 Order.pickup_no。幂等。"""
        if not session or not getattr(session, "id", None):
            return
        result = await self.db.execute(
            select(PickupNoAssignment).where(
                PickupNoAssignment.tenant_id == tenant_id,
                PickupNoAssignment.dining_session_id == session.id,
            )
        )
        assignment = result.scalar_one_or_none()
        if assignment:
            await self.db.delete(assignment)
        if clear_session_field:
            session.pickup_no = None

    async def release_if_no_holding_orders(
        self,
        tenant_id: str,
        session: DiningSession | None,
    ) -> bool:
        """session 内已无占用桌牌的有效订单时释放租约。返回是否执行了释放。幂等。"""
        if not session or not getattr(session, "id", None):
            return False
        count_result = await self.db.execute(
            select(func.count(Order.id)).where(
                Order.tenant_id == tenant_id,
                Order.dining_session_id == session.id,
                Order.status.in_(list(ORDER_STATUSES_HOLDING_PICKUP)),
            )
        )
        holding = int(count_result.scalar() or 0)
        if holding > 0:
            return False
        await self.release_session_assignment(tenant_id, session, clear_session_field=True)
        return True

    async def ensure_session_assignment(
        self,
        *,
        tenant_id: str,
        session: DiningSession,
        pickup_no: str,
    ) -> None:
        """在创建订单继承/显式写牌时确保租约存在（同号冲突抛 IntegrityError）。"""
        pickup_no = normalize_pickup_no(pickup_no)
        if not pickup_no or not session.id:
            return
        existing = await self.db.execute(
            select(PickupNoAssignment).where(
                PickupNoAssignment.tenant_id == tenant_id,
                PickupNoAssignment.dining_session_id == session.id,
            )
        )
        current = existing.scalar_one_or_none()
        if current:
            if current.pickup_no == pickup_no:
                return
            await self.db.delete(current)
            await self.db.flush()
        self.db.add(
            PickupNoAssignment(
                tenant_id=tenant_id,
                pickup_no=pickup_no,
                dining_session_id=session.id,
            )
        )
        await self.db.flush()

    def _payment_allows_assign(self, order: Order, settings: dict[str, Any]) -> tuple[bool, str | None]:
        if not settings.get("enabled"):
            return True, None
        mode = (getattr(order, "payment_mode", None) or "prepay").strip()
        if mode == "prepay" and getattr(order, "payment_status", None) != "paid":
            return False, "该订单尚未支付，暂不能分配桌牌"
        return True, None

    def _session_allows_assign(self, session: DiningSession | None) -> tuple[bool, str | None]:
        if session is None:
            return True, None
        status = (session.status or "").upper()
        if status in TERMINAL_SESSION_STATUSES:
            return False, "该就餐已结束，不能再分配桌牌"
        return True, None

    async def assign_for_order(
        self,
        *,
        tenant_id: str,
        order_id: int,
        pickup_no_raw: str,
        settings: dict[str, Any] | None = None,
    ):
        settings = settings or await load_pickup_settings(self.db, tenant_id)
        pickup_no = normalize_pickup_no(pickup_no_raw)

        result = await self.db.execute(
            select(Order).where(Order.id == order_id, Order.tenant_id == tenant_id)
        )
        order = result.scalar_one_or_none()
        if not order:
            return error_response(code=404, msg="order not found")

        if (order.status or "") in ORDER_TERMINAL_STATUSES:
            return error_response(code=422, msg="当前订单状态不能分配桌牌")

        ok, msg = self._payment_allows_assign(order, settings)
        if not ok:
            return error_response(code=422, msg=msg or "当前订单状态不能分配桌牌")

        session: DiningSession | None = None
        if order.dining_session_id:
            session = await self.db.get(DiningSession, order.dining_session_id)
            if session and session.tenant_id != tenant_id:
                session = None

        ok, msg = self._session_allows_assign(session)
        if not ok:
            return error_response(code=422, msg=msg or "当前订单状态不能分配桌牌")

        if settings.get("enabled") and pickup_no:
            count = int(settings.get("count") or DEFAULT_PICKUP_COUNT)
            if pickup_no.isdigit():
                num = int(pickup_no)
                if num < 1 or num > count:
                    return error_response(code=422, msg=f"桌牌号须在 1-{count} 之间")

        affected_ids = [order.id]
        previous_pickup = normalize_pickup_no(getattr(session, "pickup_no", None) if session else order.pickup_no)
        should_print_after = False

        try:
            if session is None:
                # 无会话（孤儿订单，见 2026-08-25 P0 审计：postpay/prepay 建单时如果
                # 客户端没带 dining_session_id，后端不会拒单，订单就会长期没有
                # session）。这类订单原来在这里被一律拒绝分配桌牌，导致顾客已经在
                # 现场却始终发不出桌牌。这里改成允许占用，但要跟真实 session 租约
                # 和其它孤儿订单做同号冲突检查——旧逻辑走的是"直接拒绝"，从没做过
                # 这个检查，不能假装反正没人会用到这条路径。
                if settings.get("enabled") and pickup_no:
                    occupied_nos = {row["pickup_no"] for row in await self.list_occupied(tenant_id)}
                    occupied_nos.discard(normalize_pickup_no(order.pickup_no))  # 换号：自己原来占的号不算冲突
                    if pickup_no in occupied_nos:
                        return error_response(code=409, msg=f"{pickup_no}号桌牌正在使用中，请选择其他号码")
                order.pickup_no = pickup_no
            else:
                if pickup_no is None:
                    await self.release_session_assignment(tenant_id, session, clear_session_field=True)
                else:
                    existing = await self.db.execute(
                        select(PickupNoAssignment).where(
                            PickupNoAssignment.tenant_id == tenant_id,
                            PickupNoAssignment.dining_session_id == session.id,
                        )
                    )
                    current = existing.scalar_one_or_none()
                    if current and current.pickup_no != pickup_no:
                        await self.db.delete(current)
                        await self.db.flush()
                    if not current or current.pickup_no != pickup_no:
                        self.db.add(
                            PickupNoAssignment(
                                tenant_id=tenant_id,
                                pickup_no=pickup_no,
                                dining_session_id=session.id,
                            )
                        )
                        await self.db.flush()
                    session.pickup_no = pickup_no

                siblings_result = await self.db.execute(
                    select(Order).where(
                        Order.tenant_id == tenant_id,
                        Order.dining_session_id == session.id,
                        Order.status.notin_(list(ACTIVE_ORDER_STATUSES_EXCLUDED)),
                    )
                )
                siblings = list(siblings_result.scalars().all())
                for sibling in siblings:
                    sibling.pickup_no = pickup_no
                affected_ids = [o.id for o in siblings] or affected_ids

            should_print_after = bool(
                pickup_no
                and previous_pickup is None
                and settings.get("enabled")
                and settings.get("required_before_print")
            )
            if should_print_after:
                from app.services.order_print_service import mark_initial_print_eligible

                for affected_order in siblings if session is not None else [order]:
                    mark_initial_print_eligible(
                        affected_order,
                        reason="pickup_no_assigned",
                    )
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            label = pickup_no or ""
            return error_response(code=409, msg=f"{label}号桌牌正在使用中，请选择其他号码")
        except Exception:
            await self.db.rollback()
            logger.exception("assign pickup_no failed order_id=%s", order_id)
            return error_response(code=500, msg="分配桌牌失败，请重试")

        # 仅「首次分牌」触发正式厨房票；换号不自动重打（走现有补打）
        return success_response(
            data={
                "pickup_no": pickup_no,
                "order_ids": [str(i) for i in affected_ids],
                "should_print_after": should_print_after,
            },
            msg="桌牌号已更新",
        )

    async def release_if_session_ended(self, tenant_id: str, session: DiningSession) -> None:
        status = (session.status or "").upper()
        if status in TERMINAL_SESSION_STATUSES:
            await self.release_session_assignment(tenant_id, session, clear_session_field=True)
