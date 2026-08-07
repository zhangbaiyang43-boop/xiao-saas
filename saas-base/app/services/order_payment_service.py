import json
from collections.abc import Coroutine
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, TYPE_CHECKING, TypedDict, cast

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from starlette.requests import Request

from app.config import settings
from app.core.logger import logger
from app.core.response import RespVo, success_response
from app.core.tenant_context import TenantContext
from app.models.order import Order
from app.services.base_service import BaseService
from app.services.coupon_service import CouponService
from app.services.order_print_service import _print_paid_order_ticket

if TYPE_CHECKING:
    from app.api.v1.orders import MockPayBody, WxPayBody


class RefundResult(TypedDict):
    success: bool
    amount: float
    error: str | None


class PostPaymentCouponData(TypedDict, total=False):
    id: Any
    name: str
    amount: Any
    min_amount: Any
    expired_at: Any
    is_second_order: bool


ApiResponse = RespVo[Any]


def _numeric_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def _numeric_float(value: object) -> float:
    return float(str(value or 0))


class OrderPaymentService(BaseService):
    async def _recover_wxpay_order_if_paid(self, order: Order) -> bool:
        """Recover paid orders when WeChat callback is delayed or lost."""
        if not order or order.status != "pending_payment":
            return False
        try:
            from app.models.tenant import Tenant
            from app.services.wxpay_service import WxPayService

            tenant_result = await self.db.execute(select(Tenant).where(Tenant.tenant_id == str(order.tenant_id)))
            tenant = tenant_result.scalar_one_or_none()
            svc = WxPayService(tenant) if tenant else None
            if not svc or not svc.enabled:
                return False

            pay_resource = await svc.query_order_by_out_trade_no(str(order.id))
            if not pay_resource or pay_resource.get("trade_state") != "SUCCESS":
                return False

            locked_result = await self.db.execute(select(Order).where(Order.id == order.id).with_for_update())
            locked_order = locked_result.scalar_one_or_none()
            if not locked_order or locked_order.status != "pending_payment":
                return False

            await self._on_payment_success(locked_order, payment_method="wxpay")
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


    async def _on_payment_success(
        self,
        order: Order,
        payment_method: str = "wxpay",
    ) -> tuple[PostPaymentCouponData | None, float]:
        """Run shared post-payment logic."""
        from app.models.coupon import Coupon

        if getattr(order, "payment_status", None) == "paid":
            return None, 0.0

        customer_id = order.customer_id
        TenantContext.set_tenant_id(str(order.tenant_id))
        coupon_data = None

        # Coupon write-off
        if order.coupon_id and customer_id:
            locked_coupon_result = await self.db.execute(
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

                    template_result = await self.db.execute(
                        select(CouponTemplate).where(CouponTemplate.id == locked_coupon.template_id)
                    )
                    coupon_template = template_result.scalar_one_or_none()
                    commission_svc = CommissionService(self.db)
                    commission_svc.set_tenant_id(str(order.tenant_id))
                    await commission_svc.record_after_verify(locked_coupon, coupon_template)
                    # record_after_verify 内部会 commit，之后同一 session 里所有对象（包括
                    # order）的属性都会被标记过期；显式 refresh 一次，避免下面继续读写
                    # order 时触发 SQLAlchemy 异步会话下的懒加载报错。
                    await self.db.refresh(order)
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
        await self.db.flush()


        # Coupon issuance and points are post-payment side effects.
        if customer_id:
            try:
                svc = CouponService(self.db)
                prior_paid_count_result = await self.db.execute(
                    select(func.count(Order.id)).where(
                        Order.tenant_id == order.tenant_id,
                        Order.customer_id == int(customer_id),
                        Order.payment_status == "paid",
                        Order.id != order.id,
                    )
                )
                prior_paid_count = int(prior_paid_count_result.scalar() or 0)
                # 第二单是"首单到复购"这条转化漏斗里最关键的一步——比第三单、第十单都更值得
                # 单独识别出来，用来在客户端给一句专属文案（"欢迎回来，这是你的第二次光临"），
                # 而不是把所有复购场景都用同一句"又送你一张券"糊弄过去。
                is_second_order = prior_paid_count == 1
                rule_type = await svc.resolve_consumption_coupon_rule_type(
                    int(customer_id),
                    exclude_order_id=int(order.id),
                )
                issue_result = await svc.issue_auto_coupon(
                    int(customer_id), rule_type, consumption_amount=float(order.total or 0)
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
                membership_svc = MembershipService(self.db)
                customer_obj = await CustomerService(self.db).get_customer(int(customer_id))
                if customer_obj:
                    await membership_svc.apply_consumption(
                        customer_obj, float(order.total or 0), consumption_id=int(order.id or 0)
                    )
            except Exception as e:
                logger.warning(f"post-payment points failed: {e}")

        # Print order ticket after payment. Printing failures are recoverable and must not affect payment state.
        await _print_paid_order_ticket(order, self.db, reason="payment_success")

        # 点餐成功订阅消息：依赖顾客支付前 requestSubscribeMessage 授权；失败不影响支付主流程。
        try:
            from app.services.subscribe_message_service import send_order_success_subscribe
            await send_order_success_subscribe(self.db, order)
        except Exception as e:
            logger.warning(f"post-payment order success subscribe failed: {e}")

        return cast(PostPaymentCouponData | None, coupon_data), 0.0


    async def _apply_paid_order_member_assets_once(self, order: Order) -> None:
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
        customer_id = int(order.customer_id or 0)
        existing_result = await self.db.execute(
            select(PointLedger.id).where(
                PointLedger.tenant_id == tenant_id,
                PointLedger.customer_id == customer_id,
                PointLedger.event_type == "consumption",
                PointLedger.ref_id == str(order.id),
            )
        )
        if existing_result.scalar_one_or_none():
            return

        customer_result = await self.db.execute(
            select(Customer).where(
                Customer.tenant_id == tenant_id,
                Customer.id == customer_id,
                Customer.status == 1,
            )
        )
        customer = customer_result.scalar_one_or_none()
        if not customer:
            return

        membership_svc = MembershipService(self.db)
        membership_svc.set_tenant_id(tenant_id)
        await membership_svc.apply_consumption(customer, float(order.total or 0), consumption_id=int(order.id or 0))

        # 新客券/复购券：prepay 支付成功（_on_payment_success）会发，但 postpay/table_account
        # 结账走的是这个函数，之前完全没有这一段——商户后台"复购券"卡片的文案明确写的是
        # "每次下单后自动推送下次用的券"，不是"微信支付后"，postpay/table_account 静默漏发
        # 与文案承诺不符。同一套 rule_type 判定逻辑（按已支付订单数区分新客/复购），
        # 发放本身的去重交给 issue_auto_coupon 自己的幂等保护（_dedup_issue_lock）。
        try:
            coupon_svc = CouponService(self.db)
            coupon_svc.set_tenant_id(tenant_id)
            rule_type = await coupon_svc.resolve_consumption_coupon_rule_type(
                customer_id,
                exclude_order_id=int(order.id or 0),
            )
            await coupon_svc.issue_auto_coupon(customer_id, rule_type, consumption_amount=float(order.total or 0))
        except Exception as e:
            logger.warning(f"postpay/table_account settlement coupon reward failed: {e}")


    async def _refund_order_payment(self, order: Order, reason: str) -> RefundResult:
        """Refund a paid order's money before flipping it to a terminal cancelled/rejected state.

        Must be called with `order` already locked (with_for_update) in the current transaction.
        Restores the balance-paid portion directly; submits a WeChat refund request for the
        WeChat-charged portion. Uses a deterministic out_refund_no so retrying this call is safe
        (WeChat treats a repeated out_refund_no as the same refund request, not a new one).

        Returns {"success": bool, "amount": float, "error": str | None}.
        """
        if getattr(order, "payment_status", None) != "paid":
            return RefundResult(success=True, amount=0.0, error=None)
        if getattr(order, "refund_status", None) == "success":
            return RefundResult(success=True, amount=float(order.refund_amount or 0), error=None)

        total = float(order.total or 0)
        balance_portion = float(order.balance_deduct_requested or 0)
        if balance_portion <= 0 and order.payment_method == "balance":
            # Legacy orders paid before balance_deduct_requested tracked the actual amount.
            balance_portion = total
        wechat_portion = max(total - balance_portion, 0.0)
        refunded_amount = 0.0

        if balance_portion > 0 and order.customer_id:
            from app.models.member_account import MemberAccount

            acc_result = await self.db.execute(
                select(MemberAccount).where(
                    MemberAccount.tenant_id == str(order.tenant_id),
                    MemberAccount.customer_id == int(order.customer_id),
                ).with_for_update()
            )
            acc = acc_result.scalar_one_or_none()
            if acc:
                acc.balance = cast(Any, _numeric_decimal(acc.balance) + _numeric_decimal(balance_portion))
                refunded_amount += balance_portion

        if wechat_portion > 0 and order.payment_method == "wxpay":
            try:
                from app.models.tenant import Tenant
                from app.services.wxpay_service import WxPayService

                tenant_result = await self.db.execute(select(Tenant).where(Tenant.tenant_id == str(order.tenant_id)))
                tenant = tenant_result.scalar_one_or_none()
                svc = WxPayService(tenant) if tenant else None
                if not svc or not svc.enabled:
                    raise RuntimeError("merchant wxpay not configured, cannot auto-refund")
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
                return RefundResult(success=False, amount=refunded_amount, error=str(exc))

        # 退款后回滚这一单在支付成功时记的账：优惠券和积分/消费额，否则顾客能靠
        # "付款->拿到积分/等级/优惠券->自己或商家取消退款"反复刷积分和等级。
        if order.coupon_id:
            from app.models.coupon import Coupon

            coupon_result = await self.db.execute(
                select(Coupon).where(Coupon.id == order.coupon_id).with_for_update()
            )
            coupon = coupon_result.scalar_one_or_none()
            if coupon and coupon.status in ("LOCKED", "USED"):
                coupon.status = "UNUSED"
                coupon.use_time = None

        if order.customer_id:
            try:
                from app.services.membership_service import MembershipService

                membership_svc = MembershipService(self.db)
                membership_svc.set_tenant_id(str(order.tenant_id))
                await membership_svc.reverse_consumption(
                    int(order.customer_id), total, consumption_id=int(order.id or 0)
                )
            except Exception as exc:
                logger.warning("[REFUND_POINTS_REVERSAL_FAILED] order_id=%s error=%s", order.id, exc)

        order.refund_status = "success"
        order.refund_amount = cast(Any, _numeric_decimal(refunded_amount))
        order.refunded_at = datetime.now(timezone.utc)
        order.refund_error = None
        logger.info(
            "[REFUND_SUCCESS] order_id=%s amount=%s balance_portion=%s wechat_portion=%s reason=%s",
            order.id, refunded_amount, balance_portion, wechat_portion, reason,
        )
        return RefundResult(success=True, amount=refunded_amount, error=None)


    async def _refund_orphaned_wxpay_payment(self, order: Order) -> RefundResult:
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

            tenant_result = await self.db.execute(select(Tenant).where(Tenant.tenant_id == str(order.tenant_id)))
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
            return RefundResult(success=False, amount=0.0, error=str(exc))

        order.refund_status = "success"
        order.refund_amount = cast(Any, _numeric_decimal(order.total))
        order.refunded_at = datetime.now(timezone.utc)
        order.refund_error = None
        logger.error(
            "[WXPAY_NOTIFY_RACE_AUTO_REFUNDED] order_id=%s amount=%s order_status=%s",
            order.id, order.refund_amount, order.status,
        )
        return RefundResult(success=True, amount=float(order.refund_amount or 0), error=None)


    async def mock_pay_order(
            self,
            order_id: str,
            body: "MockPayBody",
            request: Request,
        ) -> ApiResponse:
        """Mock payment for development only."""
        import traceback

        from app.models.order import OrderItem

        from app.core.response import error_response, success_response

        if not settings.ALLOW_MOCK_MONEY_ENDPOINTS:
            return error_response(code=403, msg="mock pay is only available in debug mode")
        try:
            customer_id = getattr(request.state, "customer_id", None)
            result = await self.db.execute(select(Order).where(Order.id == int(order_id)).with_for_update())
            order = result.scalar_one_or_none()
            if not order:
                return error_response(code=404, msg="order not found")
            if order.status != "pending_payment":
                return error_response(code=400, msg="该订单已支付或已取消")
            if order.customer_id:
                if not customer_id or int(customer_id) != int(order.customer_id):
                    return error_response(code=403, msg="forbidden")
            elif order.participant_id:
                from app.models.dining import DiningParticipant
                from app.services.dining_session_service import hash_participant_token

                owns_order = False
                if body.participant_token:
                    participant_result = await self.db.execute(
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


            coupon_data, _ = await self._on_payment_success(order, payment_method="mock")
            await self.db.commit()
            await self.db.refresh(order)

            items_result = await self.db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
            order_items = list(items_result.scalars().all())

            from app.api.v1.orders import serialize_order

            return success_response(
                data={**serialize_order(order, order_items), "coupon": coupon_data},
                msg="支付成功",
            )
        except Exception as e:
            logger.error(f"mock_pay_order error: {e}\n{traceback.format_exc()}")
            return error_response(code=500, msg=f"支付处理失败: {str(e)}")


    async def create_wxpay_order(
            self,
            order_id: str,
            body: "WxPayBody",
            request: Request,
        ) -> ApiResponse:
        """Create a WeChat JSAPI payment order for direct merchant mode."""
        import traceback

        from fastapi import HTTPException

        from app.core.response import success_response

        try:
            from app.models.tenant import Tenant
            from app.services.wxpay_service import WxPayService

            customer_id = getattr(request.state, "customer_id", None)
            openid = getattr(request.state, "openid", None)

            result = await self.db.execute(select(Order).where(Order.id == int(order_id)))
            order = result.scalar_one_or_none()
            if not order:
                raise HTTPException(status_code=404, detail={"success": False, "code": "ORDER_NOT_FOUND", "message": "order not found"})
            if getattr(order, "payment_mode", "prepay") != "prepay":
                raise HTTPException(status_code=400, detail={"success": False, "code": "PAYMENT_NOT_REQUIRED", "message": "该订单无需在线支付"})
            if order.status != "pending_payment":
                raise HTTPException(status_code=400, detail={"success": False, "code": "ORDER_ALREADY_PAID", "message": "该订单已支付或已取消"})
            if order.customer_id:
                if not customer_id or int(customer_id) != int(order.customer_id):
                    raise HTTPException(status_code=403, detail={"success": False, "code": "FORBIDDEN", "message": "forbidden"})
            elif order.participant_id:
                from app.models.dining import DiningParticipant
                from app.services.dining_session_service import hash_participant_token

                owns_order = False
                if body.participant_token:
                    participant_result = await self.db.execute(
                        select(DiningParticipant).where(
                            DiningParticipant.id == order.participant_id,
                            DiningParticipant.guest_token_hash == hash_participant_token(body.participant_token),
                        )
                    )
                    owns_order = participant_result.scalar_one_or_none() is not None
                if not owns_order:
                    raise HTTPException(status_code=403, detail={"success": False, "code": "FORBIDDEN", "message": "forbidden"})
            else:
                raise HTTPException(status_code=403, detail={"success": False, "code": "FORBIDDEN", "message": "forbidden"})

            tenant_result = await self.db.execute(select(Tenant).where(Tenant.tenant_id == order.tenant_id))
            tenant = tenant_result.scalar_one_or_none()

            pay_amount = float(order.total or 0)

            if pay_amount <= 0:
                locked_order_result = await self.db.execute(
                    select(Order).where(Order.id == int(order_id)).with_for_update()
                )
                order = locked_order_result.scalar_one_or_none()
                if not order or order.status != "pending_payment":
                    raise HTTPException(status_code=400, detail={"success": False, "code": "ORDER_ALREADY_PAID", "message": "order already paid or cancelled"})

                free_coupon_data, _ = await self._on_payment_success(order, payment_method="free")
                await self.db.commit()
                await self.db.refresh(order)
                from app.models.order import OrderItem

                free_items_result = await self.db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
                free_order_items = list(free_items_result.scalars().all())
                from app.api.v1.orders import serialize_order

                return success_response(
                    data={
                        **serialize_order(order, free_order_items),
                        "free": True,
                        "coupon": free_coupon_data,
                    },
                    msg="订单已完成，无需支付",
                )

            svc = WxPayService(tenant) if tenant else None
            if svc and svc.enabled:
                locked_order_result = await self.db.execute(
                    select(Order).where(Order.id == int(order_id)).with_for_update()
                )
                order = locked_order_result.scalar_one_or_none()
                if not order or order.status != "pending_payment":
                    raise HTTPException(status_code=400, detail={"success": False, "code": "ORDER_ALREADY_PAID", "message": "order already paid or cancelled"})
                await self.db.commit()

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
                    description=f"{tenant.name if tenant else 'order'}-点餐订单",
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


    async def wxpay_notify(self, request: Request) -> dict[str, str]:
        """Handle WeChat Pay notify for direct merchant mode."""
        import traceback

        from app.models.tenant import Tenant
        from app.services.wxpay_service import WxPayService

        try:
            headers = dict(request.headers)
            raw_body = await request.body()

            resource = None
            tenant_id = request.query_params.get("tenant_id")
            matched_tenant = None
            if tenant_id:
                tenant_result = await self.db.execute(
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

            if not resource:
                tenant_result = await self.db.execute(
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

            result = await self.db.execute(select(Order).where(Order.id == int(out_trade_no)).with_for_update())
            order = result.scalar_one_or_none()
            if not order:
                return {"code": "SUCCESS", "message": "ok"}
            if order.status not in ("pending_payment", "cancelled", "rejected"):
                return {"code": "SUCCESS", "message": "ok"}
            if matched_tenant and str(order.tenant_id) != str(matched_tenant.tenant_id):
                logger.warning(
                    f"wxpay notify tenant mismatch: order_id={out_trade_no} "
                    f"order_tenant_id={order.tenant_id} notify_tenant_id={matched_tenant.tenant_id}"
                )
                return {"code": "FAIL", "message": "tenant mismatch"}

            paid_fen = resource.get("amount", {}).get("total")
            if paid_fen is not None:
                expected_fen = round(float(order.total or 0) * 100)
                if int(paid_fen) != expected_fen:
                    logger.error(
                        "[WXPAY_AMOUNT_MISMATCH] order_id=%s expected_fen=%s paid_fen=%s",
                        out_trade_no, expected_fen, paid_fen,
                    )
                    return {"code": "FAIL", "message": "amount mismatch"}

            if order.status == "pending_payment":
                await self._on_payment_success(order, payment_method="wxpay")
                await self.db.commit()
                logger.info(f"微信支付回调成功: order_id={out_trade_no}")
                return {"code": "SUCCESS", "message": "ok"}

            if getattr(order, "refund_status", None) == "success":
                return {"code": "SUCCESS", "message": "ok"}
            logger.error(
                "[WXPAY_NOTIFY_RACE_WITH_CANCEL] order_id=%s order_status=%s -- WeChat confirmed "
                "payment after this order was already %s locally; auto-refunding instead of fulfilling",
                out_trade_no, order.status, order.status,
            )

            await self._refund_orphaned_wxpay_payment(order)
            await self.db.commit()
            return {"code": "SUCCESS", "message": "ok"}

        except Exception as e:
            logger.error(f"wxpay_notify error: {e}\n{traceback.format_exc()}")
            return {"code": "FAIL", "message": str(e)}
