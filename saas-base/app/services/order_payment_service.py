import json
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.logger import logger
from app.core.tenant_context import TenantContext
from app.models.order import Order
from app.services.coupon_service import CouponService
from app.services.order_print_service import _print_paid_order_ticket


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
