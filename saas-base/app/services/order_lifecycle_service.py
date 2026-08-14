import json
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING, Optional

from sqlalchemy import String, and_, cast, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.response import RespVo, error_response, success_response
from app.core.tenant_context import TenantContext
from app.models.order import Order, OrderItem
from app.services.base_service import BaseService

if TYPE_CHECKING:
    from app.api.v1.orders import OrderStatusUpdate

ApiResponse = RespVo[Any]


def _mark_order_offline_paid(order: Order, payment_method: str = "offline") -> bool:
    if getattr(order, "payment_status", None) == "paid":
        return False
    order.payment_status = "paid"
    order.payment_method = payment_method
    order.payment_time = datetime.now(timezone.utc).isoformat()
    return True


class OrderLifecycleService(BaseService):
    async def update_order_pickup_no(self, order_id: int, pickup_no_raw: str) -> ApiResponse:
        from app.services.pickup_no_service import PickupNoService

        tenant_id = self.require_tenant_id()
        service = PickupNoService(self.db)
        result = await service.assign_for_order(
            tenant_id=tenant_id,
            order_id=int(order_id),
            pickup_no_raw=pickup_no_raw,
        )
        # 分牌成功后、在事务外触发厨房票（防重复打印由 print_service 幂等保证）
        if getattr(result, "code", None) == 200 and (result.data or {}).get("should_print_after"):
            try:
                from app.services.order_print_service import _print_paid_order_ticket

                order_ids = (result.data or {}).get("order_ids") or []
                for oid in order_ids:
                    order_result = await self.db.execute(
                        select(Order).where(Order.id == int(oid), Order.tenant_id == tenant_id)
                    )
                    order = order_result.scalar_one_or_none()
                    if not order:
                        continue
                    await _print_paid_order_ticket(order, self.db, reason="pickup_no_assigned")
                await self.db.commit()
            except Exception:
                # 打印失败不回滚桌牌分配
                import logging
                logging.getLogger(__name__).exception(
                    "pickup_no assigned but print failed order_id=%s", order_id
                )
        return result

    async def update_merchant_note(self, order_id: int, note: str) -> ApiResponse:
        from app.services.order_print_service import (
            _compose_merchant_note_with_print_meta,
            _split_merchant_note_and_print_meta,
        )

        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(Order).where(Order.id == order_id, Order.tenant_id == tenant_id)
        )
        order = result.scalar_one_or_none()
        if not order:
            return error_response(code=404, msg="order not found")
        _, meta = _split_merchant_note_and_print_meta(order.merchant_note)
        order.merchant_note = _compose_merchant_note_with_print_meta(note.strip() or None, meta)
        await self.db.commit()
        display_note, _ = _split_merchant_note_and_print_meta(order.merchant_note)
        return success_response(data={"id": str(order.id), "merchant_note": display_note}, msg="merchant note updated")

    async def cancel_order(
        self,
        order_id: int,
        *,
        customer_id: int | None,
        participant_token: str | None,
    ) -> ApiResponse:
        from app.models.coupon import Coupon as _Coupon

        from app.services.order_payment_service import OrderPaymentService
        from app.services.order_stock_service import _restore_order_stock

        payment_svc = OrderPaymentService(self.db)
        result = await self.db.execute(select(Order).where(Order.id == order_id).with_for_update())
        order = result.scalar_one_or_none()
        if not order:
            return error_response(code=404, msg="order not found")
        if order.customer_id:
            if not customer_id or int(customer_id) != int(order.customer_id):
                return error_response(code=403, msg="forbidden")
        elif order.participant_id:
            from app.models.dining import DiningParticipant
            from app.services.dining_session_service import hash_participant_token

            owns_order = False
            if participant_token:
                participant_result = await self.db.execute(
                    select(DiningParticipant).where(
                        DiningParticipant.id == order.participant_id,
                        DiningParticipant.guest_token_hash == hash_participant_token(participant_token),
                    )
                )
                owns_order = participant_result.scalar_one_or_none() is not None
            if not owns_order:
                return error_response(code=403, msg="forbidden")
        if order.status == "pending_payment" and getattr(order, "payment_mode", "prepay") == "prepay":
            if await payment_svc._recover_wxpay_order_if_paid(order):
                await self.db.commit()
                return error_response(code=400, msg="订单已支付，请刷新查看最新状态")
        if order.status not in ("pending_payment", "pending"):
            return error_response(code=400, msg="订单已支付或已完成，无法取消")
        if getattr(order, "payment_status", None) == "paid":
            refund_result = await payment_svc._refund_order_payment(order, reason="customer_cancel")
            if not refund_result["success"]:
                await self.db.rollback()
                return error_response(code=502, msg=f"取消失败，退款处理异常，请稍后重试或联系客服：{refund_result['error']}")
        await _restore_order_stock(order, self.db)
        order.status = "cancelled"
        if order.coupon_id:
            coupon = await self.db.get(_Coupon, order.coupon_id)
            if coupon and coupon.status == "LOCKED":
                coupon.status = "UNUSED"
        # 桌牌属 DiningSession：仅当会话内已无有效履约订单时释放租约
        if order.dining_session_id:
            from app.models.dining import DiningSession
            from app.services.pickup_no_service import PickupNoService

            session = await self.db.get(DiningSession, order.dining_session_id)
            await PickupNoService(self.db).release_if_no_holding_orders(
                str(order.tenant_id), session
            )
        await self.db.commit()
        return success_response(data={"id": str(order.id), "status": "cancelled"}, msg="order cancelled")

    async def get_my_order(
        self,
        order_id: int,
        *,
        customer_id: int | None,
        participant_token: str | None,
    ) -> ApiResponse:
        from app.services.order_payment_service import OrderPaymentService

        payment_svc = OrderPaymentService(self.db)
        result = await self.db.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()
        if not order:
            return error_response(code=404, msg="order not found")

        if order.customer_id:
            if not customer_id or int(customer_id) != int(order.customer_id):
                return error_response(code=403, msg="forbidden")
        elif order.participant_id:
            from app.models.dining import DiningParticipant
            from app.services.dining_session_service import hash_participant_token

            owns_order = False
            if participant_token:
                participant_result = await self.db.execute(
                    select(DiningParticipant).where(
                        DiningParticipant.id == order.participant_id,
                        DiningParticipant.guest_token_hash == hash_participant_token(participant_token),
                    )
                )
                owns_order = participant_result.scalar_one_or_none() is not None
            if not owns_order:
                return error_response(code=403, msg="forbidden")

        recovered = await payment_svc._recover_wxpay_order_if_paid(order)
        if recovered:
            await self.db.commit()
            await self.db.refresh(order)

        reward_coupon = None
        if order.reward_coupon_snapshot:
            try:
                reward_coupon = json.loads(str(order.reward_coupon_snapshot))
            except Exception:
                reward_coupon = None

        return success_response(data={
            "id": str(order.id),
            "status": order.status,
            "payment_status": order.payment_status,
            "merchant_note": order.merchant_note,
            "reward_coupon": reward_coupon,
            "pickup_no": getattr(order, "pickup_no", None),
            "table_no": getattr(order, "table_no", None),
        })

    async def list_orders(
        self,
        *,
        date_str: Optional[str] = None,
        keyword: Optional[str] = None,
        order_no: Optional[str] = None,
        order_tail: Optional[str] = None,
        tail_no: Optional[str] = None,
        table_no: Optional[str] = None,
        status: Optional[str] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> ApiResponse:
        from datetime import timedelta as _td

        from app.api.v1.orders import (
            TABLE_CLOSE_BLOCKING_STATUSES,
            serialize_order,
        )
        from app.services.order_payment_service import OrderPaymentService
        from app.services.order_print_service import reconcile_print_orders

        tenant_id = self.require_tenant_id()
        TenantContext.set_tenant_id(tenant_id)

        query = select(Order).where(Order.tenant_id == tenant_id)

        if date_str == "today" or not date_str:
            utc8_now = datetime.now(timezone.utc) + _td(hours=8)
            today_local = utc8_now.date()
            day_start_utc = datetime(today_local.year, today_local.month, today_local.day) - _td(hours=8)
            day_end_utc = day_start_utc + _td(hours=24)
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
            total_result = await self.db.execute(select(func.count()).select_from(query.order_by(None).subquery()))
            total = int(total_result.scalar_one() or 0)
            query = query.order_by(Order.created_at.desc()).offset((safe_page - 1) * safe_page_size).limit(safe_page_size)
        else:
            query = query.order_by(Order.created_at.desc())

        result = await self.db.execute(query)
        orders = result.scalars().all()

        recovered_any = False
        payment_svc = OrderPaymentService(self.db)
        for order in orders:
            if order.status == "pending_payment":
                recovered_any = (await payment_svc._recover_wxpay_order_if_paid(order)) or recovered_any
        print_recovered = await reconcile_print_orders(
            self.db, orders, trigger="merchant_list_recovery"
        )
        if print_recovered:
            recovered_any = True
        if recovered_any:
            await self.db.commit()
            for order in orders:
                await self.db.refresh(order)

        order_ids = [o.id for o in orders]
        items_by_order: dict[int, list[OrderItem]] = {}
        if order_ids:
            items_result = await self.db.execute(
                select(OrderItem).where(OrderItem.order_id.in_(order_ids))
            )
            all_items = items_result.scalars().all()
            for item in all_items:
                if item.order_id is not None:
                    items_by_order.setdefault(item.order_id, []).append(item)

        session_ids = {o.dining_session_id for o in orders if getattr(o, "dining_session_id", None)}
        checkout_requested_by_session = {}
        sessions_by_id = {}
        if session_ids:
            from app.models.dining import DiningSession

            sessions_result = await self.db.execute(
                select(DiningSession).where(DiningSession.id.in_(session_ids))
            )
            for session in sessions_result.scalars().all():
                sessions_by_id[session.id] = session
                if session.checkout_requested_at:
                    checkout_requested_by_session[session.id] = session.checkout_requested_at.isoformat()

        from app.services.dining_session_service import DiningSessionService
        from app.services.pickup_no_service import load_pickup_settings

        participant_ordinals = await DiningSessionService.get_participant_ordinals(self.db, tenant_id, list(session_ids))
        pickup_settings = await load_pickup_settings(self.db, tenant_id)

        rows = [
            serialize_order(
                o,
                items_by_order.get(o.id or 0, []),
                checkout_requested_at=checkout_requested_by_session.get(getattr(o, "dining_session_id", None)),
                participant_no=participant_ordinals.get(getattr(o, "participant_id", None)),
                pickup_settings=pickup_settings,
                dining_session=sessions_by_id.get(getattr(o, "dining_session_id", None)),
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

    async def create_review(self, order_id: int, *, customer_id: int, rating: int, content: str | None) -> ApiResponse:
        from datetime import datetime as _dt

        from app.models.order_review import OrderReview

        if not 1 <= rating <= 5:
            return error_response(code=400, msg="评分需在1-5之间")

        result = await self.db.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()
        if not order:
            return error_response(code=404, msg="order not found")
        if int(order.customer_id or 0) != int(customer_id):
            return error_response(code=403, msg="forbidden")
        if order.status not in ("done", "settled"):
            return error_response(code=400, msg="order not completed")

        exists = await self.db.execute(
            select(OrderReview).where(OrderReview.order_id == order_id)
        )
        if exists.scalar_one_or_none():
            return error_response(code=400, msg="order already reviewed")

        review = OrderReview(
            tenant_id=order.tenant_id,
            order_id=order.id,
            customer_id=int(customer_id) if customer_id else None,
            rating=rating,
            content=content,
            created_at=_dt.utcnow(),
        )
        self.db.add(review)
        await self.db.commit()
        return success_response(data={"id": str(review.id), "rating": review.rating}, msg="review submitted")

    async def list_reviews(self) -> ApiResponse:
        from app.models.order_review import OrderReview

        tenant_id = self.require_tenant_id()
        TenantContext.set_tenant_id(tenant_id)
        result = await self.db.execute(
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

    async def update_order_status(self, order_id: int, body: "OrderStatusUpdate") -> ApiResponse:
        from app.api.v1.orders import (
            ORDER_ALLOWED_TRANSITIONS,
            ORDER_MERCHANT_TARGET_STATUSES,
        )
        from app.services.order_payment_service import OrderPaymentService
        from app.services.consumption_service import _record_order_consumption
        from app.services.coupon_service import (
            _mark_order_coupon_used_if_locked,
            _unlock_order_coupon_if_locked,
        )
        from app.services.order_stock_service import _restore_order_stock

        tenant_id = self.require_tenant_id()
        if body.status not in ORDER_MERCHANT_TARGET_STATUSES:
            return error_response(code=400, msg="invalid status")
        TenantContext.set_tenant_id(tenant_id)
        payment_svc = OrderPaymentService(self.db)
        result = await self.db.execute(
            select(Order).where(Order.id == order_id, Order.tenant_id == tenant_id).with_for_update()
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
        payment_mode = getattr(order, "payment_mode", "prepay") or "prepay"
        requires_table_settlement = payment_mode == "table_account" or (
            payment_mode == "postpay" and getattr(order, "dining_session_id", None) is not None
        )
        if body.status == "settled" and requires_table_settlement:
            return error_response(code=409, msg="后付/桌台账单请通过整桌结账完成")
        if body.status not in ORDER_ALLOWED_TRANSITIONS.get(current_status, set()):
            return error_response(code=409, msg=f"illegal status transition: {current_status}->{body.status}")
        entered_done = body.status == "done"

        if (
            body.status in ("rejected", "cancelled")
            and current_status == "pending_payment"
            and getattr(order, "payment_mode", "prepay") == "prepay"
        ):
            if await payment_svc._recover_wxpay_order_if_paid(order):
                await self.db.commit()
                return error_response(code=409, msg="订单已支付，请刷新查看最新状态")

        if body.status in ("rejected", "cancelled") and getattr(order, "payment_status", None) == "paid":
            refund_result = await payment_svc._refund_order_payment(order, reason=f"merchant_{body.status}")
            if not refund_result["success"]:
                await self.db.rollback()
                return error_response(code=502, msg=f"操作失败，退款处理异常，请稍后重试：{refund_result['error']}")
        if body.status in ("rejected", "cancelled") and getattr(order, "payment_status", None) != "paid":
            await _unlock_order_coupon_if_locked(order, self.db)
        if body.status in ("rejected", "cancelled"):
            await _restore_order_stock(order, self.db)

        order.status = body.status
        # Phase R2: kitchen complete must NOT auto-serve. Waiter/Owner call serve_order.
        just_settled = body.status == "settled" and not getattr(order, "completed_at", None)
        if just_settled:
            order.completed_at = datetime.utcnow()
            marked_offline_paid = False
            if getattr(order, "payment_mode", "prepay") == "postpay":
                marked_offline_paid = _mark_order_offline_paid(order)
            await _mark_order_coupon_used_if_locked(order, self.db)
            if marked_offline_paid:
                await payment_svc._apply_paid_order_member_assets_once(order)
        if body.status in ("rejected", "cancelled") and order.dining_session_id:
            from app.models.dining import DiningSession
            from app.services.pickup_no_service import PickupNoService

            session = await self.db.get(DiningSession, order.dining_session_id)
            await PickupNoService(self.db).release_if_no_holding_orders(tenant_id, session)
        await self.db.commit()
        await self.db.refresh(order)
        if just_settled:
            await _record_order_consumption(order, self.db)
        if entered_done:
            # 取餐提醒：仅首次切入 done 时发（idempotent 早退已挡住重复）；失败不影响改状态。
            try:
                from app.services.subscribe_message_service import send_pickup_reminder_subscribe
                await send_pickup_reminder_subscribe(self.db, order)
            except Exception:
                from app.core.logger import logger
                logger.exception(f"pickup reminder subscribe failed order_id={order.id}")
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

    async def serve_order(
        self,
        order_id: int,
        *,
        account_id: int | None,
        role: str | None,
    ) -> ApiResponse:
        """Mark kitchen-done order as served. Independent of payment/print/pickup.

        Idempotent: repeat serve keeps first served_by_* audit.
        """
        tenant_id = self.require_tenant_id()
        TenantContext.set_tenant_id(tenant_id)
        result = await self.db.execute(
            select(Order).where(Order.id == order_id, Order.tenant_id == tenant_id).with_for_update()
        )
        order = result.scalar_one_or_none()
        if not order:
            return error_response(code=404, msg="order not found")

        if (order.status or "") != "done":
            return error_response(code=409, msg="仅制作完成的订单可确认上菜")

        if getattr(order, "served_at", None):
            return success_response(
                data={
                    "id": str(order.id),
                    "status": order.status,
                    "served_at": order.served_at.isoformat() if order.served_at else None,
                    "idempotent": True,
                },
                msg="已上菜",
            )

        now = datetime.utcnow()
        order.served_at = now
        order.updated_at = now
        role_value = (role or "").strip().lower()
        if role_value == "owner" or account_id is None:
            order.served_by_account_id = None
            order.served_by_role = "owner"
        else:
            order.served_by_account_id = int(account_id)
            order.served_by_role = role_value or "waiter"

        await self.db.commit()
        await self.db.refresh(order)
        return success_response(
            data={
                "id": str(order.id),
                "status": order.status,
                "served_at": order.served_at.isoformat() if order.served_at else None,
                "idempotent": False,
            },
            msg="已确认上菜",
        )

    async def settle_table(self, body: dict[str, Any], *, closed_by: str) -> ApiResponse:
        from app.api.v1.orders import (
            TABLE_CLOSE_BLOCKING_STATUSES,
            TABLE_CLOSE_DONE_STATUSES,
        )
        from app.services.order_payment_service import OrderPaymentService
        from app.models.dining import DiningSession
        from app.services.consumption_service import _record_order_consumption
        from app.services.coupon_service import _mark_order_coupon_used_if_locked

        tenant_id = self.require_tenant_id()
        table_no = (body.get("table_no") or "").strip()
        if not table_no:
            return error_response(code=400, msg="缺少桌号")
        TenantContext.set_tenant_id(tenant_id)

        non_terminal_result = await self.db.execute(
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

        active_session = None
        if session_id:
            session_result = await self.db.execute(
                select(DiningSession).where(DiningSession.id == session_id).with_for_update()
            )
            active_session = session_result.scalar_one_or_none()

        if active_session:
            result = await self.db.execute(
                select(Order).where(
                    Order.tenant_id == tenant_id,
                    Order.dining_session_id == active_session.id,
                )
            )
            table_orders = list(result.scalars().all())
        else:
            # 没有挂 dining_session 的订单（比如超管"填充测试数据"生成的演示订单——见
            # test_data_seed.py，那批订单从建单起就没有 session；理论上老版本直连 H5
            # 下单也可能落在这里）永远不会被上面按 session 的查询捞到，但桌台视图仍然
            # 会把它们按桌号分组展示成"可结账"。不给这类订单一条结账路径，商家会永远
            # 卡在"本桌没有进行中的会话"上——刷新、重试、换设备、无痕模式都没用，因为
            # 这压根不是缓存过期，是这批订单从建单起就没有 session 可关。这里退化成
            # 纯按租户+桌号找非终态订单，跳过所有 DiningSession 专属步骤（没有 session
            # 可关、没有桌牌租约可释放）。
            orphan_result = await self.db.execute(
                select(Order).where(
                    Order.tenant_id == tenant_id,
                    Order.table_no == table_no,
                    Order.dining_session_id.is_(None),
                    Order.status.notin_(("settled", "cancelled", "rejected")),
                )
            )
            table_orders = list(orphan_result.scalars().all())
            if not table_orders:
                return error_response(code=404, msg="本桌没有进行中的会话")

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
                    "dining_session_id": str(active_session.id) if active_session else None,
                    "blocking_order_ids": [str(o.id) for o in blocking_orders],
                    "blocking_statuses": sorted({o.status for o in blocking_orders}),
                },
            )

        if active_session:
            active_session.status = "CLOSED"
            active_session.closed_at = datetime.utcnow()
            active_session.closed_by = closed_by
            active_session.active_key = None
            # 释放当前桌牌租约；历史 Order.pickup_no 保留作快照
            from app.services.pickup_no_service import PickupNoService
            await PickupNoService(self.db).release_session_assignment(
                tenant_id, active_session, clear_session_field=True
            )

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
        payment_svc = OrderPaymentService(self.db)
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
                    await payment_svc._apply_paid_order_member_assets_once(o)
            await _mark_order_coupon_used_if_locked(o, self.db)
            total += float(o.total or 0)
        await self.db.commit()
        for o in newly_settled_orders:
            await _record_order_consumption(o, self.db)
        return success_response(
            data={
                "table_no": table_no,
                "dining_session_id": str(active_session.id) if active_session else None,
                "settled_count": settled_count,
                "paid_synced_count": paid_synced_count,
                "payment_status": "paid",
                "payment_method": "offline",
                "closed": True,
                "total": total,
            },
            msg="结桌成功",
        )
