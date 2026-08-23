import json
from collections.abc import Coroutine
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, TYPE_CHECKING, TypedDict, cast

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from starlette.requests import Request

from app.config import settings
from app.core.logger import logger, safe_log
from app.core.plan_capabilities import CAP_COUPONS, CAP_DISTRIBUTION_REFERRAL, CAP_MEMBERSHIP
from app.core.response import RespVo, success_response
from app.core.tenant_context import TenantContext
from app.models.order import Order
from app.services.base_service import BaseService
from app.services.coupon_service import CouponService
from app.services.optional_entitlement import optional_capability_enabled
from app.services.order_print_service import _print_paid_order_ticket

if TYPE_CHECKING:
    from app.api.v1.orders import MockPayBody, WxPayBody

# P1-WXPAY-RECOVERY-GATE: (connect, read) timeout, applied ONLY to the recovery-query
# WxPayService construction below -- create_jsapi_order/wxpay_notify verification/refund
# elsewhere in this file are untouched (timeout=None, today's existing unbounded behavior).
# wechatpayv3's Core accepts this exact (connect, read) tuple shape. Value grounded on this
# repo's own established precedent for calling WeChat's APIs -- wechat_service.py (the
# official-account/mini-program WeChat API, same vendor) uses a flat 10s timeout on 4 of 5
# of its urllib.request.urlopen call sites (one uses 12s); no repo precedent or SDK default
# exists specifically for connect-vs-read split, so 5s connect is a conservative fraction of
# that same ~10s budget, not an independently invented number.
WXPAY_RECOVERY_QUERY_TIMEOUT = (5, 10)


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


class PaymentFactError(ValueError):
    pass


class PaymentTransactionConflict(PaymentFactError):
    pass


def _numeric_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def _numeric_float(value: object) -> float:
    return float(str(value or 0))


def _encode_reward_snapshot(coupon_data: PostPaymentCouponData | None) -> str:
    """Persist the reward tri-state without collapsing JSON null into SQL NULL.

    Call only after reward applicability/resolution is known: ``None`` becomes
    JSON ``null`` (known none), while a coupon becomes its JSON object snapshot.
    SQL NULL is deliberately reserved for historical or unresolved attribution.
    """
    return json.dumps(coupon_data, ensure_ascii=False, default=str)


class OrderPaymentService(BaseService):
    @staticmethod
    def _build_reward_coupon_data(
        issue_result: dict[str, Any] | None,
        *,
        is_second_order: bool,
    ) -> PostPaymentCouponData | None:
        """Normalize every payment mode to the existing order reward snapshot shape."""
        if not issue_result or issue_result.get("success_count", 0) <= 0:
            return None
        sent_item = (issue_result.get("sent") or [{}])[0]
        weighted_coupon = issue_result.get("weighted_coupon") or {}
        return {
            "id": sent_item.get("id"),
            "name": weighted_coupon.get("name") or "优惠券",
            "amount": weighted_coupon.get("amount", 0),
            "min_amount": weighted_coupon.get("threshold", 0),
            "expired_at": sent_item.get("expire_time"),
            "is_second_order": is_second_order,
        }

    @staticmethod
    def _validate_confirmed_wx_payment(order: Order, resource: dict[str, Any]) -> str:
        if resource.get("trade_state") != "SUCCESS":
            raise PaymentFactError("payment not successful")
        if str(resource.get("out_trade_no") or "") != str(order.id):
            raise PaymentFactError("out_trade_no mismatch")
        transaction_id = str(resource.get("transaction_id") or "").strip()
        if not transaction_id or len(transaction_id) > 64:
            raise PaymentFactError("invalid transaction_id")
        amount = resource.get("amount")
        if not isinstance(amount, dict) or amount.get("total") is None:
            raise PaymentFactError("missing amount")
        if amount.get("currency") != "CNY":
            raise PaymentFactError("currency mismatch")
        expected_fen = int((_numeric_decimal(order.total) * Decimal("100")).quantize(Decimal("1")))
        try:
            paid_fen = int(amount["total"])
        except (TypeError, ValueError) as exc:
            raise PaymentFactError("invalid amount") from exc
        if paid_fen != expected_fen:
            safe_log(
                logger.warning,
                "PAYMENT_VALIDATION_FAILED order_id=%s out_trade_no=%s wx_transaction_id=%s "
                "expected_amount_fen=%s provider_amount_fen=%s reason=amount_mismatch",
                order.id, resource.get("out_trade_no"), transaction_id, expected_fen, paid_fen,
            )
            raise PaymentFactError("amount mismatch")
        safe_log(
            logger.info,
            "PAYMENT_VALIDATED order_id=%s out_trade_no=%s wx_transaction_id=%s amount_fen=%s",
            order.id, resource.get("out_trade_no"), transaction_id, paid_fen,
        )
        return transaction_id

    async def _claim_wx_transaction(self, order: Order, transaction_id: str) -> str:
        current = str(order.wx_transaction_id or "")
        if current:
            if current == transaction_id:
                return "duplicate"
            raise PaymentTransactionConflict("order transaction conflict")

        owner_result = await self.db.execute(
            select(Order)
            .where(
                Order.tenant_id == str(order.tenant_id),
                Order.wx_transaction_id == transaction_id,
                Order.id != order.id,
            )
            .with_for_update()
        )
        if owner_result.scalar_one_or_none():
            raise PaymentTransactionConflict("transaction already claimed")
        order.wx_transaction_id = transaction_id
        try:
            await self.db.flush()
        except IntegrityError as exc:
            raise PaymentTransactionConflict("transaction already claimed") from exc
        return "bound"

    async def _apply_confirmed_wx_payment(
        self,
        order: Order,
        resource: dict[str, Any],
    ) -> tuple[bool, PostPaymentCouponData | None, bool]:
        transaction_id = self._validate_confirmed_wx_payment(order, resource)
        claim = await self._claim_wx_transaction(order, transaction_id)
        if order.payment_status == "paid":
            return False, None, claim == "bound"
        if order.payment_mode != "prepay" or order.status != "pending_payment":
            raise PaymentFactError("order cannot accept online payment")
        coupon_data, _ = await self._on_payment_success(order, payment_method="wxpay")
        return True, coupon_data, claim == "bound"

    async def _reconcile_confirmed_payment_for_terminal_order(
        self,
        order: Order,
        resource: dict[str, Any],
    ) -> tuple[bool, bool]:
        """Persist a verified late payment without resurrecting or fulfilling the order.

        The caller must hold the tenant-scoped Order row lock.  This intentionally
        performs no print, member, points, commission, reward-coupon, or refund action.
        The paid + cancelled/rejected combination is exposed as ``refund_required`` by
        the DTO capability builder until a future provider-confirmed refund phase exists.
        """
        if order.status not in ("cancelled", "rejected"):
            raise PaymentFactError("order is not terminal")
        transaction_id = self._validate_confirmed_wx_payment(order, resource)
        claim = await self._claim_wx_transaction(order, transaction_id)
        transitioned = order.payment_status != "paid"
        if transitioned:
            order.payment_status = "paid"
            order.payment_method = "wxpay"
            order.payment_time = datetime.now(timezone.utc).isoformat()

        from app.services.payment_handoff_service import PaymentHandoffService

        await PaymentHandoffService(self.db)._cancel_active_handoffs(
            str(order.tenant_id), int(order.id)
        )
        await self.db.flush()
        return transitioned, claim == "bound"

    async def _run_post_commit_payment_effects(self, order: Order) -> None:
        await _print_paid_order_ticket(order, self.db, reason="payment_success")
        try:
            from app.services.subscribe_message_service import send_order_success_subscribe

            await send_order_success_subscribe(self.db, order)
        except Exception as exc:
            logger.warning(f"post-payment order success subscribe failed: {exc}")

    async def _recover_wxpay_order_if_paid(self, order: Order, source: str = "unspecified") -> bool:
        """Recover paid orders when WeChat callback is delayed or lost."""
        if not order or order.payment_mode != "prepay":
            return False
        order_id = order.id
        try:
            from app.models.tenant import Tenant
            from app.services.wxpay_service import WxPayService

            tenant_result = await self.db.execute(select(Tenant).where(Tenant.tenant_id == str(order.tenant_id)))
            tenant = tenant_result.scalar_one_or_none()
            svc = WxPayService(tenant, timeout=WXPAY_RECOVERY_QUERY_TIMEOUT) if tenant else None
            if not svc or not svc.enabled:
                return False

            pay_resource = await svc.query_order_by_out_trade_no(str(order.id))
            if not pay_resource:
                return False

            locked_result = await self.db.execute(
                select(Order)
                .where(
                    Order.id == order.id,
                    Order.tenant_id == str(order.tenant_id),
                )
                .with_for_update()
            )
            locked_order = locked_result.scalar_one_or_none()
            if not locked_order:
                return False

            if locked_order.status in ("cancelled", "rejected"):
                terminal_tenant_id = str(locked_order.tenant_id)
                terminal_order_id = int(locked_order.id)
                transitioned, binding_changed = (
                    await self._reconcile_confirmed_payment_for_terminal_order(
                        locked_order, pay_resource
                    )
                )
                terminal_reconciliation = True
            else:
                terminal_tenant_id = None
                terminal_order_id = None
                transitioned, _, binding_changed = await self._apply_confirmed_wx_payment(
                    locked_order,
                    pay_resource,
                )
                terminal_reconciliation = False
            if transitioned or binding_changed:
                await self.db.commit()
            else:
                await self.db.rollback()
            if terminal_reconciliation and terminal_order_id is not None:
                await self._refund_after_terminal_wx_capture(
                    order_id=terminal_order_id,
                    tenant_id=str(terminal_tenant_id),
                )
            if transitioned and not terminal_reconciliation:
                await self._run_post_commit_payment_effects(locked_order)
            safe_log(
                logger.warning,
                "[WXPAY_ORDER_RECOVERED] order_id=%s transaction_id=%s out_trade_no=%s source=%s",
                order_id,
                pay_resource.get("transaction_id") or "",
                pay_resource.get("out_trade_no") or str(order_id),
                source,
            )
            return True
        except Exception as exc:
            await self.db.rollback()
            safe_log(
                logger.warning,
                "[WXPAY_ORDER_RECOVERY_FAILED] order_id=%s error=%s source=%s",
                order_id, exc, source,
            )
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

                    if await optional_capability_enabled(str(order.tenant_id), CAP_DISTRIBUTION_REFERRAL):
                        template_result = await self.db.execute(
                            select(CouponTemplate).where(CouponTemplate.id == locked_coupon.template_id)
                        )
                        coupon_template = template_result.scalar_one_or_none()
                        commission_svc = CommissionService(self.db)
                        commission_svc.set_tenant_id(str(order.tenant_id))
                        await commission_svc.record_after_verify(
                            locked_coupon,
                            coupon_template,
                            auto_commit=False,
                        )
                    # Payment transition uses flush-only mode; refresh keeps the
                    # shared session state explicit before the remaining writes.
                    await self.db.refresh(order)
                except Exception as e:
                    logger.warning(f"post-payment invite reward failed: {e}")
                    raise
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
        try:
            from app.services.order_print_service import ensure_initial_print_intent
        except ImportError:  # compatibility for isolated legacy contract harnesses
            ensure_initial_print_intent = None
        if ensure_initial_print_intent is not None:
            from app.services.pickup_no_service import load_pickup_settings, should_defer_kitchen_print

            pickup_settings = await load_pickup_settings(self.db, str(order.tenant_id))
            defer = should_defer_kitchen_print(order, pickup_settings)
            await ensure_initial_print_intent(
                order,
                self.db,
                eligible=not defer,
                reason="payment_success",
            )
        await self.db.flush()


        # DB-only coupon/member effects remain inside the outer payment transaction.
        if customer_id:
            coupons_enabled = await optional_capability_enabled(str(order.tenant_id), CAP_COUPONS)
            if not coupons_enabled:
                # Capability policy proves this order cannot issue a reward. That
                # is known-none, not an unresolved/historical SQL NULL.
                order.reward_coupon_snapshot = _encode_reward_snapshot(None)
            else:
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
                        int(customer_id),
                        rule_type,
                        consumption_amount=float(order.total or 0),
                        auto_commit=False,
                    )
                    # issue_auto_coupon() 的返回值是内部服务间约定的形状（success_count/sent/
                    # weighted_coupon 嵌套），不是给客户端消费的。这里只在真的发出新券时才
                    # 拍平成小程序端认识的 {id,name,amount,min_amount,expired_at}（和入会接口
                    # 的欢迎券是同一套字段），没发新券（未达门槛、规则关闭、已持有同类未用券）
                    # 一律给 None——不然前端只要判断"coupon 字段存在"就会把 success_count:0
                    # 这种失败/跳过结果误当成"又送了一张券"展示出去。
                    coupon_data = self._build_reward_coupon_data(
                        issue_result,
                        is_second_order=is_second_order,
                    )
                    # JSON null is an explicit processed-with-no-reward marker.
                    # SQL NULL stays reserved for unresolved or historical rows.
                    order.reward_coupon_snapshot = _encode_reward_snapshot(coupon_data)
                except Exception as e:
                    logger.warning(f"post-payment coupon failed: {e}")
                    raise

        if customer_id and await optional_capability_enabled(str(order.tenant_id), CAP_MEMBERSHIP):
            try:
                from app.services.membership_service import MembershipService
                from app.services.customer_service import CustomerService
                membership_svc = MembershipService(self.db)
                customer_obj = await CustomerService(self.db).get_customer(int(customer_id))
                if customer_obj:
                    await membership_svc.apply_consumption(
                        customer_obj,
                        float(order.total or 0),
                        consumption_id=int(order.id or 0),
                        auto_commit=False,
                    )
            except Exception as e:
                logger.warning(f"post-payment points failed: {e}")
                raise

        from app.services.payment_handoff_service import PaymentHandoffService

        await PaymentHandoffService(self.db).mark_order_paid(int(order.id))

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

        if await optional_capability_enabled(tenant_id, CAP_MEMBERSHIP):
            membership_svc = MembershipService(self.db)
            membership_svc.set_tenant_id(tenant_id)
            await membership_svc.apply_consumption(
                customer,
                float(order.total or 0),
                consumption_id=int(order.id or 0),
                auto_commit=False,
            )

        # 新客券/复购券：prepay 支付成功（_on_payment_success）会发，但 postpay/table_account
        # 结账走的是这个函数，之前完全没有这一段——商户后台"复购券"卡片的文案明确写的是
        # "每次下单后自动推送下次用的券"，不是"微信支付后"，postpay/table_account 静默漏发
        # 与文案承诺不符。同一套 rule_type 判定逻辑（按已支付订单数区分新客/复购），
        # 发放本身的去重交给 issue_auto_coupon 自己的幂等保护（_dedup_issue_lock）。
        if await optional_capability_enabled(tenant_id, CAP_COUPONS):
            try:
                coupon_svc = CouponService(self.db)
                coupon_svc.set_tenant_id(tenant_id)
                prior_paid_count_result = await self.db.execute(
                    select(func.count(Order.id)).where(
                        Order.tenant_id == order.tenant_id,
                        Order.customer_id == customer_id,
                        Order.payment_status == "paid",
                        Order.id != order.id,
                    )
                )
                is_second_order = int(prior_paid_count_result.scalar() or 0) == 1
                rule_type = await coupon_svc.resolve_consumption_coupon_rule_type(
                    customer_id,
                    exclude_order_id=int(order.id or 0),
                )
                issue_result = await coupon_svc.issue_auto_coupon(
                    customer_id,
                    rule_type,
                    consumption_amount=float(order.total or 0),
                    auto_commit=False,
                )
                coupon_data = self._build_reward_coupon_data(
                    issue_result,
                    is_second_order=is_second_order,
                )
                order.reward_coupon_snapshot = _encode_reward_snapshot(coupon_data)
            except Exception as e:
                logger.warning(f"postpay/table_account settlement coupon reward failed: {e}")
        else:
            order.reward_coupon_snapshot = _encode_reward_snapshot(None)


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
                select(Coupon)
                .where(
                    Coupon.id == order.coupon_id,
                    Coupon.tenant_id == str(order.tenant_id),
                )
                .with_for_update()
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
        if getattr(order, "refund_status", None) == "success":
            return RefundResult(success=True, amount=float(order.refund_amount or 0), error=None)
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

    async def _refund_after_terminal_wx_capture(self, *, order_id: int, tenant_id: str) -> None:
        """After a terminal paid fact is committed, send the orphaned WeChat capture back.

        Re-locks the row so refund fields persist independently of the payment-fact
        commit. Failures are recorded on the order; they must not raise into notify.
        """
        locked_result = await self.db.execute(
            select(Order)
            .where(Order.id == order_id, Order.tenant_id == tenant_id)
            .with_for_update()
        )
        order = locked_result.scalar_one_or_none()
        if not order:
            return
        if order.status not in ("cancelled", "rejected"):
            return
        if order.payment_status != "paid":
            return
        if getattr(order, "refund_status", None) == "success":
            return
        await self._refund_orphaned_wxpay_payment(order)
        await self.db.commit()


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
            tenant_id = getattr(request.state, "tenant_id", None)
            order_query = select(Order).where(Order.id == int(order_id))
            if tenant_id:
                order_query = order_query.where(Order.tenant_id == str(tenant_id))
            result = await self.db.execute(order_query.with_for_update())
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
            await self._run_post_commit_payment_effects(order)
            await self.db.refresh(order)

            items_result = await self.db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
            order_items = list(items_result.scalars().all())

            from app.api.v1.orders import serialize_order

            return success_response(
                data={**serialize_order(order, order_items), "coupon": coupon_data},
                msg="支付成功",
            )
        except Exception as e:
            await self.db.rollback()
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

            tenant_id = getattr(request.state, "tenant_id", None)
            order_query = select(Order).where(Order.id == int(order_id))
            if tenant_id:
                order_query = order_query.where(Order.tenant_id == str(tenant_id))
            result = await self.db.execute(order_query)
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
                    select(Order)
                    .where(
                        Order.id == int(order_id),
                        Order.tenant_id == str(order.tenant_id),
                    )
                    .with_for_update()
                )
                order = locked_order_result.scalar_one_or_none()
                if not order or order.status != "pending_payment":
                    raise HTTPException(status_code=400, detail={"success": False, "code": "ORDER_ALREADY_PAID", "message": "order already paid or cancelled"})

                free_coupon_data, _ = await self._on_payment_success(order, payment_method="free")
                await self.db.commit()
                await self._run_post_commit_payment_effects(order)
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
                    select(Order)
                    .where(
                        Order.id == int(order_id),
                        Order.tenant_id == str(order.tenant_id),
                    )
                    .with_for_update()
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
                safe_log(
                    logger.info,
                    "PAYMENT_REQUESTED order_id=%s tenant_id=%s amount_fen=%s client_request_id=%s",
                    order.id, order.tenant_id, amount_fen, getattr(order, "client_request_id", None),
                )
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
            safe_log(
                logger.info,
                "WXPAY_CALLBACK_RECEIVED tenant_id=%s out_trade_no=%s trade_state=%s",
                getattr(matched_tenant, "tenant_id", None), out_trade_no, trade_state,
            )
            if trade_state != "SUCCESS":
                return {"code": "SUCCESS", "message": "ok"}

            try:
                order_id = int(out_trade_no)
            except (TypeError, ValueError):
                return {"code": "FAIL", "message": "invalid out_trade_no"}
            result = await self.db.execute(
                select(Order)
                .where(
                    Order.id == order_id,
                    Order.tenant_id == str(matched_tenant.tenant_id),
                )
                .with_for_update()
            )
            order = result.scalar_one_or_none()
            if not order:
                return {"code": "SUCCESS", "message": "ok"}
            if matched_tenant and str(order.tenant_id) != str(matched_tenant.tenant_id):
                logger.warning(
                    f"wxpay notify tenant mismatch: order_id={out_trade_no} "
                    f"order_tenant_id={order.tenant_id} notify_tenant_id={matched_tenant.tenant_id}"
                )
                return {"code": "FAIL", "message": "tenant mismatch"}

            if order.status in ("cancelled", "rejected"):
                terminal_status = str(order.status)
                tenant_id = str(order.tenant_id)
                order_pk = int(order.id)
                transitioned, binding_changed = (
                    await self._reconcile_confirmed_payment_for_terminal_order(order, resource)
                )
                if transitioned or binding_changed:
                    await self.db.commit()
                else:
                    await self.db.rollback()
                await self._refund_after_terminal_wx_capture(
                    order_id=order_pk,
                    tenant_id=tenant_id,
                )
                logger.error(
                    "[WXPAY_LATE_PAYMENT_REQUIRES_REFUND] order_id=%s order_status=%s",
                    out_trade_no,
                    terminal_status,
                )
                return {"code": "SUCCESS", "message": "ok"}

            transaction_id = self._validate_confirmed_wx_payment(order, resource)
            claim = await self._claim_wx_transaction(order, transaction_id)

            if order.payment_status == "paid":
                if claim == "bound":
                    await self.db.commit()
                else:
                    await self.db.rollback()
                return {"code": "SUCCESS", "message": "ok"}

            if order.status == "pending_payment" and order.payment_mode == "prepay":
                await self._on_payment_success(order, payment_method="wxpay")
                await self.db.commit()
                await self._run_post_commit_payment_effects(order)
                logger.info(f"微信支付回调成功: order_id={out_trade_no}")
                return {"code": "SUCCESS", "message": "ok"}

            raise PaymentFactError("order cannot accept online payment")

        except Exception as e:
            await self.db.rollback()
            logger.error(f"wxpay_notify error: {e}\n{traceback.format_exc()}")
            return {"code": "FAIL", "message": str(e)}
