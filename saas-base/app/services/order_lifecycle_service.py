import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, and_, cast, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.response import error_response, success_response
from app.core.tenant_context import TenantContext
from app.models.order import Order, OrderItem
from app.services.base_service import BaseService


def _mark_order_offline_paid(order: Order, payment_method: str = "offline") -> bool:
    if getattr(order, "payment_status", None) == "paid":
        return False
    order.payment_status = "paid"
    order.payment_method = payment_method
    order.payment_time = datetime.now(timezone.utc).isoformat()
    return True


class OrderLifecycleService(BaseService):
    async def update_order_pickup_no(self, order_id: int, pickup_no_raw: str) -> dict:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(Order).where(Order.id == order_id, Order.tenant_id == tenant_id)
        )
        order = result.scalar_one_or_none()
        if not order:
            return error_response(code=404, msg="order not found")

        pickup_no = pickup_no_raw.strip()[:16] or None
        affected_ids = [order.id]

        if order.dining_session_id:
            from app.models.dining import DiningSession

            session = await self.db.get(DiningSession, order.dining_session_id)
            if session:
                session.pickup_no = pickup_no
                siblings_result = await self.db.execute(
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

        await self.db.commit()
        return success_response(
            data={"pickup_no": pickup_no, "order_ids": [str(i) for i in affected_ids]},
            msg="取餐牌号已更新",
        )

    async def update_merchant_note(self, order_id: int, note: str) -> dict:
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
    ) -> dict:
        from app.models.coupon import Coupon as _Coupon

        from app.api.v1.orders import _recover_wxpay_order_if_paid, _refund_order_payment
        from app.services.order_stock_service import _restore_order_stock

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
            if await _recover_wxpay_order_if_paid(order, self.db):
                await self.db.commit()
                return error_response(code=400, msg="订单已支付，请刷新查看最新状态")
        if order.status not in ("pending_payment", "pending"):
            return error_response(code=400, msg="订单已支付或已完成，无法取消")
        if getattr(order, "payment_status", None) == "paid":
            refund_result = await _refund_order_payment(order, self.db, reason="customer_cancel")
            if not refund_result["success"]:
                await self.db.rollback()
                return error_response(code=502, msg=f"取消失败，退款处理异常，请稍后重试或联系客服：{refund_result['error']}")
        await _restore_order_stock(order, self.db)
        order.status = "cancelled"
        if order.coupon_id:
            coupon = await self.db.get(_Coupon, order.coupon_id)
            if coupon and coupon.status == "LOCKED":
                coupon.status = "UNUSED"
        await self.db.commit()
        return success_response(data={"id": str(order.id), "status": "cancelled"}, msg="order cancelled")

    async def get_my_order(
        self,
        order_id: int,
        *,
        customer_id: int | None,
        participant_token: str | None,
    ) -> dict:
        from app.api.v1.orders import _recover_wxpay_order_if_paid

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

        recovered = await _recover_wxpay_order_if_paid(order, self.db)
        if recovered:
            await self.db.commit()
            await self.db.refresh(order)

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
    ) -> dict:
        from datetime import timedelta as _td

        from app.api.v1.orders import (
            TABLE_CLOSE_BLOCKING_STATUSES,
            _recover_wxpay_order_if_paid,
            serialize_order,
        )
        from app.services.order_print_service import (
            MAX_PRINT_RETRY_ATTEMPTS,
            _get_print_meta,
            _print_paid_order_ticket,
        )

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
        for order in orders:
            if order.status == "pending_payment":
                recovered_any = (await _recover_wxpay_order_if_paid(order, self.db)) or recovered_any
            print_meta = _get_print_meta(order)
            if (
                getattr(order, "payment_status", None) == "paid"
                and print_meta.get("status") == "failed"
                and int(print_meta.get("attempts") or 0) < MAX_PRINT_RETRY_ATTEMPTS
            ):
                await _print_paid_order_ticket(order, self.db, reason="merchant_list_recovery")
                recovered_any = True
        if recovered_any:
            await self.db.commit()
            for order in orders:
                await self.db.refresh(order)

        order_ids = [o.id for o in orders]
        items_by_order = {}
        if order_ids:
            items_result = await self.db.execute(
                select(OrderItem).where(OrderItem.order_id.in_(order_ids))
            )
            all_items = items_result.scalars().all()
            for item in all_items:
                items_by_order.setdefault(item.order_id, []).append(item)

        session_ids = {o.dining_session_id for o in orders if getattr(o, "dining_session_id", None)}
        checkout_requested_by_session = {}
        if session_ids:
            from app.models.dining import DiningSession

            sessions_result = await self.db.execute(
                select(DiningSession.id, DiningSession.checkout_requested_at).where(
                    DiningSession.id.in_(session_ids)
                )
            )
            for session_id, checkout_requested_at in sessions_result.all():
                if checkout_requested_at:
                    checkout_requested_by_session[session_id] = checkout_requested_at.isoformat()

        from app.services.dining_session_service import DiningSessionService

        participant_ordinals = await DiningSessionService.get_participant_ordinals(self.db, tenant_id, list(session_ids))

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

    async def create_review(self, order_id: int, *, customer_id: int, rating: int, content: str | None) -> dict:
        from datetime import datetime as _dt

        from app.models.order_review import OrderReview

        if not 1 <= rating <= 5:
            return error_response(code=400, msg="璇勫垎闇€鍦?-5涔嬮棿")

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

    async def list_reviews(self) -> dict:
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

    async def update_order_status(self, order_id: int, body) -> dict:
        from app.api.v1.orders import (
            ORDER_ALLOWED_TRANSITIONS,
            ORDER_MERCHANT_TARGET_STATUSES,
            _apply_paid_order_member_assets_once,
            _recover_wxpay_order_if_paid,
            _refund_order_payment,
        )
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
        if body.status not in ORDER_ALLOWED_TRANSITIONS.get(current_status, set()):
            return error_response(code=409, msg=f"illegal status transition: {current_status}->{body.status}")

        if (
            body.status in ("rejected", "cancelled")
            and current_status == "pending_payment"
            and getattr(order, "payment_mode", "prepay") == "prepay"
        ):
            if await _recover_wxpay_order_if_paid(order, self.db):
                await self.db.commit()
                return error_response(code=409, msg="订单已支付，请刷新查看最新状态")

        if body.status in ("rejected", "cancelled") and getattr(order, "payment_status", None) == "paid":
            refund_result = await _refund_order_payment(order, self.db, reason=f"merchant_{body.status}")
            if not refund_result["success"]:
                await self.db.rollback()
                return error_response(code=502, msg=f"操作失败，退款处理异常，请稍后重试：{refund_result['error']}")
        if body.status in ("rejected", "cancelled") and getattr(order, "payment_status", None) != "paid":
            await _unlock_order_coupon_if_locked(order, self.db)
        if body.status in ("rejected", "cancelled"):
            await _restore_order_stock(order, self.db)

        order.status = body.status
        if body.status == "done" and not getattr(order, "served_at", None):
            order.served_at = datetime.utcnow()
        just_settled = body.status == "settled" and not getattr(order, "completed_at", None)
        if just_settled:
            order.completed_at = datetime.utcnow()
            marked_offline_paid = False
            if getattr(order, "payment_mode", "prepay") == "postpay":
                marked_offline_paid = _mark_order_offline_paid(order)
            await _mark_order_coupon_used_if_locked(order, self.db)
            if marked_offline_paid:
                await _apply_paid_order_member_assets_once(order, self.db)
        await self.db.commit()
        await self.db.refresh(order)
        if just_settled:
            await _record_order_consumption(order, self.db)
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

    async def settle_table(self, body: dict, *, closed_by: str) -> dict:
        from app.api.v1.orders import (
            TABLE_CLOSE_BLOCKING_STATUSES,
            TABLE_CLOSE_DONE_STATUSES,
            _apply_paid_order_member_assets_once,
        )
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
        if not session_id:
            return error_response(code=404, msg="本桌没有进行中的会话")

        session_result = await self.db.execute(
            select(DiningSession).where(DiningSession.id == session_id).with_for_update()
        )
        active_session = session_result.scalar_one_or_none()
        if not active_session:
            return error_response(code=404, msg="本桌没有进行中的会话")

        result = await self.db.execute(
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
        active_session.closed_by = closed_by
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
                    await _apply_paid_order_member_assets_once(o, self.db)
            await _mark_order_coupon_used_if_locked(o, self.db)
            total += float(o.total or 0)
        await self.db.commit()
        for o in newly_settled_orders:
            await _record_order_consumption(o, self.db)
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
