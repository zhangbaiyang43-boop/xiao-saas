from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.logger import logger
from app.models.billing import BillingInvoice, BillingPayment
from app.models.tenant import Tenant
from app.services.base_service import BaseService
from app.services.billing_payment_provider import (
    BillingPaymentNotification,
    BillingPaymentRequest,
    MANUAL_PAYMENT_BLOCKED_REASON,
    REAL_PAYMENT_BLOCKED_REASON,
    get_billing_payment_provider,
    manual_payment_config_audit,
    platform_payment_config_audit,
)
from app.services.channel_commission_policy import invoice_commission_snapshot
from app.utils.id_generator import generate_snowflake_id


INVOICE_STATUS_PENDING = "PENDING"
INVOICE_STATUS_PAID = "PAID"
INVOICE_STATUS_CANCELLED = "CANCELLED"
INVOICE_STATUS_EXPIRED = "EXPIRED"
INVOICE_STATUS_REFUNDED = "REFUNDED"
INVOICE_STATUS_PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"

PAYMENT_STATUS_PENDING = "PENDING"
PAYMENT_STATUS_PAID = "PAID"
PAYMENT_STATUS_FAILED = "FAILED"
PAYMENT_STATUS_CANCELLED = "CANCELLED"
PAYMENT_STATUS_REFUNDED = "REFUNDED"

CHARGE_TYPES = {
    "SAAS_SUBSCRIPTION",
    "SETUP_SERVICE",
    "MINIPROGRAM_CERTIFICATION",
    "HARDWARE",
    "SMS_TOPUP",
    "ADDON",
    "OTHER",
}

PAYMENT_PROVIDERS = {"FAKE", "WXPAY", "MANUAL"}
DUPLICATE_INVOICE_PAYMENT = "DUPLICATE_INVOICE_PAYMENT"

# F1G-CM: manual-review workflow state for provider="MANUAL" payments.
# Deliberately NOT a "NONE" string -- manual_review_status is NULL until the
# merchant's first claim, so "no claim yet" and "explicitly some other
# state" are never confusable.
MANUAL_REVIEW_WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
MANUAL_REVIEW_REJECTED = "REJECTED"
MANUAL_REVIEW_CONFIRMED = "CONFIRMED"


class MockPaymentDisabledError(RuntimeError):
    """Raised when a caller (payment-attempt creation OR the public provider
    callback) tries to use the FAKE billing provider while
    settings.ALLOW_MOCK_MONEY_ENDPOINTS is not explicitly true (F1G-CF-A).

    FAKE's "signature" is the static header value x-billing-fake-signature:
    valid -- not a real cryptographic check -- so unlike WXPAY (which is
    blocked by having no working implementation at all), FAKE is fully
    functional and must be gated by policy, the same way every other
    mock-money endpoint in this codebase already is (app/api/v1/member.py's
    /recharge, order_payment_service.py's mock_pay_order). Subclasses
    RuntimeError so it funnels through the SAME `except RuntimeError` branch
    POST /api/v1/billing/invoices/{id}/payments already has for the WXPAY
    block, instead of leaking as an unhandled 500."""

    pass


class ManualPaymentDisabledError(RuntimeError):
    """Raised when a caller tries to create a MANUAL billing payment while
    settings.SAAS_MANUAL_PAYMENT_ENABLED (or the payee-name/QR-URL presence
    it also requires) is not satisfied (F1G-CM). Independent of
    MockPaymentDisabledError/ALLOW_MOCK_MONEY_ENDPOINTS -- MANUAL is a real
    V1 payment path, not a test/mock one, so it is never gated by that flag.
    Subclasses RuntimeError so it funnels through the SAME `except
    RuntimeError` branch the WXPAY block already uses."""

    pass


class ManualPaymentStateError(ValueError):
    """Raised when a manual-payment claim/confirm/reject is attempted
    against a payment that is not in the state that action requires (F1G-CM)
    -- e.g. confirming a payment that was never claimed, or claiming one
    that's already PAID. A client-input problem (400), not a server fault."""

    pass


class SubscriptionSnapshotIntegrityError(ValueError):
    """Raised when a SAAS_SUBSCRIPTION invoice has exactly one of
    plan_code/billing_period set (Phase F1C) -- a malformed purchase
    snapshot, not a legacy pre-F1A invoice (which has BOTH null). Raising
    here aborts _on_billing_payment_success before invoice.success_processed_at
    is assigned, so the caller's local transaction never durably commits a
    "success" that didn't actually apply an entitlement; the invoice is left
    for authoritative recovery rather than guessed at."""

    pass


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def serialize_invoice(invoice: BillingInvoice) -> dict[str, Any]:
    return {
        "id": str(invoice.id),
        "tenant_id": invoice.tenant_id,
        "invoice_no": invoice.invoice_no,
        "charge_type": invoice.charge_type,
        "description": invoice.description,
        "plan_code": invoice.plan_code,
        "billing_period": invoice.billing_period,
        "amount_cents": invoice.amount_cents,
        "currency": invoice.currency,
        "status": invoice.status,
        "metadata": invoice.metadata_json or {},
        "commission_eligible": bool(getattr(invoice, "commission_eligible", False)),
        "commission_policy_version": getattr(invoice, "commission_policy_version", None),
        "paid_at": _iso(invoice.paid_at),
        "expired_at": _iso(invoice.expired_at),
        "success_processed_at": _iso(invoice.success_processed_at),
        "created_at": _iso(invoice.created_at),
        "updated_at": _iso(invoice.updated_at),
    }


def serialize_payment(payment: BillingPayment) -> dict[str, Any]:
    return {
        "id": str(payment.id),
        "tenant_id": payment.tenant_id,
        "invoice_id": str(payment.invoice_id),
        "payment_no": payment.payment_no,
        "out_trade_no": payment.out_trade_no,
        "provider": payment.provider,
        "provider_mchid": payment.provider_mchid,
        "provider_appid": payment.provider_appid,
        "amount_cents": payment.amount_cents,
        "currency": payment.currency,
        "status": payment.status,
        "transaction_id": payment.transaction_id,
        "paid_at": _iso(payment.paid_at),
        "anomaly_reason": payment.anomaly_reason,
        "provider_metadata": payment.provider_metadata or {},
        "failure_reason": payment.failure_reason,
        "manual_review_status": payment.manual_review_status,
        "manual_claimed_at": _iso(payment.manual_claimed_at),
        "manual_reviewed_at": _iso(payment.manual_reviewed_at),
        "created_at": _iso(payment.created_at),
        "updated_at": _iso(payment.updated_at),
    }


class BillingService(BaseService):
    async def create_invoice(
        self,
        *,
        tenant_id: str,
        charge_type: str,
        description: str,
        amount_cents: int,
        currency: str = "CNY",
        expired_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        plan_code: str | None = None,
        billing_period: str | None = None,
    ) -> BillingInvoice:
        tenant_result = await self.db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
        tenant = tenant_result.scalar_one_or_none()
        if not tenant:
            raise ValueError("商户不存在")
        if charge_type not in CHARGE_TYPES:
            raise ValueError("收费类型不支持")
        if int(amount_cents or 0) <= 0:
            raise ValueError("账单金额必须大于0")
        invoice_id = generate_snowflake_id()
        commission_eligible, commission_policy_version = invoice_commission_snapshot(charge_type)
        invoice = BillingInvoice(
            id=invoice_id,
            tenant_id=tenant_id,
            invoice_no=f"BINV{invoice_id}",
            charge_type=charge_type,
            description=(description or "").strip()[:255],
            plan_code=plan_code,
            billing_period=billing_period,
            amount_cents=int(amount_cents),
            currency=(currency or "CNY").upper(),
            status=INVOICE_STATUS_PENDING,
            metadata_json=metadata or {},
            commission_eligible=commission_eligible,
            commission_policy_version=commission_policy_version,
            expired_at=expired_at,
        )
        self.db.add(invoice)
        await self.db.commit()
        await self.db.refresh(invoice)
        return invoice

    async def list_invoices_for_super(self, tenant_id: str | None = None) -> list[BillingInvoice]:
        query = select(BillingInvoice)
        if tenant_id:
            query = query.where(BillingInvoice.tenant_id == tenant_id)
        result = await self.db.execute(query.order_by(BillingInvoice.created_at.desc()))
        return list(result.scalars().all())

    async def list_invoices_for_tenant(self) -> list[BillingInvoice]:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(BillingInvoice)
            .where(BillingInvoice.tenant_id == tenant_id)
            .order_by(BillingInvoice.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_invoice_for_tenant(self, invoice_id: int) -> BillingInvoice | None:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(BillingInvoice).where(
                BillingInvoice.id == invoice_id,
                BillingInvoice.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_payment_for_tenant(self, payment_id: int) -> BillingPayment | None:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(BillingPayment).where(
                BillingPayment.id == payment_id,
                BillingPayment.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_payment_attempt(self, invoice_id: int, provider_name: str = "WXPAY") -> tuple[BillingPayment, dict[str, Any]]:
        tenant_id = self.require_tenant_id()
        provider_name = (provider_name or "WXPAY").upper()
        if provider_name not in PAYMENT_PROVIDERS:
            raise ValueError("支付渠道不支持")
        if provider_name == "WXPAY":
            raise RuntimeError(REAL_PAYMENT_BLOCKED_REASON)
        # F1G-CF-A: FAKE is a fully working provider (unlike WXPAY, which has
        # no real implementation to begin with) -- it must be gated by the
        # SAME policy every other mock-money endpoint in this codebase already
        # uses, not left reachable by default. Checked here, before any DB
        # row is touched, so a disabled attempt leaves nothing behind.
        if provider_name == "FAKE" and not settings.ALLOW_MOCK_MONEY_ENDPOINTS:
            raise MockPaymentDisabledError("模拟支付未启用")
        # F1G-CM: MANUAL is a real V1 payment path (not a test/mock one), so
        # it is gated by its OWN independent flag, never
        # ALLOW_MOCK_MONEY_ENDPOINTS. Checked here, before any DB row is
        # touched, mirroring the FAKE gate above exactly.
        if provider_name == "MANUAL" and not manual_payment_config_audit()["manual_payment_available"]:
            raise ManualPaymentDisabledError(MANUAL_PAYMENT_BLOCKED_REASON)

        invoice_result = await self.db.execute(
            select(BillingInvoice)
            .where(BillingInvoice.id == invoice_id, BillingInvoice.tenant_id == tenant_id)
            .with_for_update()
        )
        invoice = invoice_result.scalar_one_or_none()
        if not invoice:
            raise ValueError("账单不存在")
        if invoice.status != INVOICE_STATUS_PENDING:
            raise ValueError("账单当前状态不能发起支付")

        payment_id = generate_snowflake_id()
        provider = get_billing_payment_provider(provider_name)
        payment = BillingPayment(
            id=payment_id,
            tenant_id=tenant_id,
            invoice_id=invoice.id,
            payment_no=f"BPAY{payment_id}",
            out_trade_no=f"BPAY{payment_id}",
            provider=provider.provider,
            amount_cents=invoice.amount_cents,
            currency=invoice.currency,
            status=PAYMENT_STATUS_PENDING,
        )
        provider_result = await provider.create_payment(
            BillingPaymentRequest(
                out_trade_no=payment.out_trade_no,
                amount_cents=payment.amount_cents,
                currency=payment.currency,
                description=invoice.description or "开心点单SaaS服务费",
            )
        )
        payment.provider_mchid = provider_result.get("provider_mchid")
        payment.provider_appid = provider_result.get("provider_appid")
        self.db.add(payment)
        await self.db.commit()
        await self.db.refresh(payment)
        return payment, provider_result

    async def process_provider_notification(self, *, provider_name: str, headers: dict[str, str], body: bytes) -> dict[str, str]:
        provider_name = (provider_name or "WXPAY").upper()
        # F1G-CF-A: authoritative gate #2 (independent of create_payment_attempt's
        # gate #1) -- this route is public and unauthenticated by necessity
        # (real payment providers can't carry a merchant JWT), so an attacker
        # who never went through payment-attempt creation at all must still be
        # rejected here, before verify_notify() ever runs. Same message as a
        # genuine signature failure so a disabled-mock-money environment
        # doesn't leak that fact to an anonymous caller.
        if provider_name == "FAKE" and not settings.ALLOW_MOCK_MONEY_ENDPOINTS:
            logger.warning("[BILLING_FAKE_CALLBACK_BLOCKED] mock money disabled")
            return {"code": "FAIL", "message": "验签失败"}
        provider = get_billing_payment_provider(provider_name)
        notice = provider.verify_notify(headers, body)
        if not notice:
            return {"code": "FAIL", "message": "验签失败"}
        if notice.trade_state != "SUCCESS":
            return {"code": "SUCCESS", "message": "ok"}
        return await self.process_verified_payment_fact(notice)

    async def process_verified_payment_fact(self, notice: BillingPaymentNotification) -> dict[str, str]:
        """Shared verified-success core (F1G-CM Phase 14 / F1G-CF-B design).

        Callers MUST have already established that `notice` represents a
        genuinely trusted payment fact BEFORE calling this -- a real
        provider's verified+decrypted callback (process_provider_notification
        above), a real provider's signed order-query result (future
        WXPAY_ORDER_QUERY recovery), or a platform SuperAdmin's manual
        confirmation built from the server's own persisted Payment/Invoice
        rows (confirm_manual_payment below). This method does not know or
        care which of those produced `notice` -- it only ever re-derives
        truth from the DB rows it locks here via _validate_success_notice(),
        the same amount/currency/out_trade_no cross-check every provider
        goes through. MANUAL is not a special bypass of this core; it is
        one more trusted producer of the same verified-fact shape."""
        payment_result = await self.db.execute(
            select(BillingPayment)
            .where(BillingPayment.out_trade_no == notice.out_trade_no)
            .with_for_update()
        )
        payment = payment_result.scalar_one_or_none()
        if not payment:
            return {"code": "SUCCESS", "message": "ok"}

        invoice_result = await self.db.execute(
            select(BillingInvoice)
            .where(
                BillingInvoice.id == payment.invoice_id,
                BillingInvoice.tenant_id == payment.tenant_id,
            )
            .with_for_update()
        )
        invoice = invoice_result.scalar_one_or_none()
        if not invoice:
            logger.error("[BILLING_NOTIFY_ORPHAN_PAYMENT] payment_id=%s", payment.id)
            return {"code": "FAIL", "message": "账单不存在"}

        validation_error = self._validate_success_notice(payment, notice)
        if validation_error:
            return {"code": "FAIL", "message": validation_error}

        if payment.status == PAYMENT_STATUS_PAID:
            await self.db.commit()
            return {"code": "SUCCESS", "message": "ok"}

        payment.status = PAYMENT_STATUS_PAID
        payment.transaction_id = notice.transaction_id
        payment.paid_at = notice.paid_at or datetime.utcnow()
        payment.provider_mchid = notice.provider_mchid or payment.provider_mchid
        payment.provider_appid = notice.provider_appid or payment.provider_appid
        payment.provider_metadata = notice.metadata or {}

        if invoice.status != INVOICE_STATUS_PAID:
            invoice.status = INVOICE_STATUS_PAID
            invoice.paid_at = payment.paid_at
            if invoice.success_processed_at is None:
                await self._on_billing_payment_success(invoice, payment)
        else:
            payment.anomaly_reason = DUPLICATE_INVOICE_PAYMENT
            logger.warning(
                "[BILLING_DUPLICATE_PAYMENT] invoice_id=%s payment_id=%s transaction_id=%s",
                invoice.id,
                payment.id,
                payment.transaction_id,
            )

        await self.db.commit()
        return {"code": "SUCCESS", "message": "ok"}

    def _validate_success_notice(self, payment: BillingPayment, notice: BillingPaymentNotification) -> str | None:
        if not notice.out_trade_no or notice.out_trade_no != payment.out_trade_no:
            return "out_trade_no mismatch"
        if not notice.transaction_id:
            return "transaction_id missing"
        if int(notice.amount_cents or 0) != int(payment.amount_cents or 0):
            return "amount mismatch"
        if (notice.currency or "CNY").upper() != (payment.currency or "CNY").upper():
            return "currency mismatch"
        if notice.provider_mchid and payment.provider_mchid and notice.provider_mchid != payment.provider_mchid:
            return "provider merchant mismatch"
        if notice.provider_appid and payment.provider_appid and notice.provider_appid != payment.provider_appid:
            return "provider app mismatch"
        return None

    async def _on_billing_payment_success(self, invoice: BillingInvoice, payment: BillingPayment) -> None:
        from app.services.channel_commission_service import ChannelCommissionService

        await ChannelCommissionService(self.db).handle_billing_payment_success(invoice, payment)
        if invoice.charge_type == "SAAS_SUBSCRIPTION":
            await self._apply_saas_subscription_purchase(invoice, payment)
        invoice.success_processed_at = payment.paid_at or datetime.utcnow()
        logger.info(
            "[BILLING_PAYMENT_SUCCESS] invoice_id=%s payment_id=%s amount_cents=%s",
            invoice.id,
            payment.id,
            payment.amount_cents,
        )

    async def _apply_saas_subscription_purchase(self, invoice: BillingInvoice, payment: BillingPayment) -> None:
        """Bridge a verified SAAS_SUBSCRIPTION invoice into Subscription
        entitlement (Phase F1C, docs/saas-subscription-audit.md). Called only
        from _on_billing_payment_success(), inside the SAME local transaction
        and gated by the SAME invoice.success_processed_at authority that
        guards commission bookkeeping -- SubscriptionService.apply_paid_purchase()
        performs zero idempotency bookkeeping of its own by design (see its
        own docstring): this IS the one authority, not a second one.

        F1A's plan_code/billing_period columns are additive-nullable, so
        pre-F1A SAAS_SUBSCRIPTION invoices exist with BOTH null: legacy, no
        purchase snapshot survives to reconstruct from, so nothing is
        applied -- guessing a plan from amount_cents would fabricate a money
        contract that was never actually agreed. Exactly ONE of the two
        being set is a data integrity error, not a legacy case, and must
        not be guessed at either; see SubscriptionSnapshotIntegrityError.

        Deliberately does not pass amount -- Payment/Invoice amount
        verification already happened in process_provider_notification()
        before this is ever reached (_validate_success_notice); Subscription
        only consumes the already-verified purchase fact, never re-resolves
        price."""
        plan_code = invoice.plan_code
        billing_period = invoice.billing_period

        if plan_code is None and billing_period is None:
            logger.warning(
                "[BILLING_LEGACY_SUBSCRIPTION_INVOICE] invoice_id=%s tenant_id=%s",
                invoice.id,
                invoice.tenant_id,
            )
            return

        if plan_code is None or billing_period is None:
            logger.error(
                "[BILLING_SUBSCRIPTION_SNAPSHOT_MALFORMED] invoice_id=%s tenant_id=%s "
                "plan_code=%s billing_period=%s",
                invoice.id,
                invoice.tenant_id,
                plan_code,
                billing_period,
            )
            raise SubscriptionSnapshotIntegrityError(
                f"invoice {invoice.id} has a malformed SAAS_SUBSCRIPTION snapshot: "
                f"plan_code={plan_code!r} billing_period={billing_period!r}"
            )

        from app.services.subscription_service import SubscriptionService

        await SubscriptionService(self.db).apply_paid_purchase(
            tenant_id=invoice.tenant_id,
            plan_code=plan_code,
            billing_period=billing_period,
            paid_at=invoice.paid_at,
            commit=False,
        )

    # ---- F1G-CM: manual-verified payment (V1) -----------------------------

    async def claim_manual_payment(self, payment_id: int) -> BillingPayment:
        """Merchant '我已付款' action (F1G-CM Phase 8). This is a PAYMENT
        CLAIM, never a PAYMENT FACT: it only ever moves
        manual_review_status/manual_claimed_at. It must NEVER touch
        BillingInvoice.status, BillingPayment.status/paid_at, or call
        anything that applies a subscription -- only confirm_manual_payment()
        (SuperAdmin-only) can do that, via the shared
        process_verified_payment_fact() core."""
        tenant_id = self.require_tenant_id()
        payment_result = await self.db.execute(
            select(BillingPayment)
            .where(BillingPayment.id == payment_id, BillingPayment.tenant_id == tenant_id)
            .with_for_update()
        )
        payment = payment_result.scalar_one_or_none()
        if not payment:
            raise ValueError("支付记录不存在")
        if payment.provider != "MANUAL":
            raise ManualPaymentStateError("该支付方式不支持人工核账")
        if payment.status == PAYMENT_STATUS_PAID:
            raise ManualPaymentStateError("账单已支付")
        if payment.manual_review_status == MANUAL_REVIEW_WAITING_CONFIRMATION:
            # Idempotent: repeated "我已付款" clicks are a safe no-op --
            # report the current state, don't re-stamp manual_claimed_at.
            return payment
        # First claim, or a resubmit after a prior REJECTED review -- both
        # land here and transition to WAITING_CONFIRMATION identically.
        payment.manual_review_status = MANUAL_REVIEW_WAITING_CONFIRMATION
        payment.manual_claimed_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(payment)
        return payment

    async def list_manual_payments_for_super(
        self, review_status: str = MANUAL_REVIEW_WAITING_CONFIRMATION
    ) -> list[dict[str, Any]]:
        """SuperAdmin pending-manual-payments list (F1G-CM Phase 11). Only
        display fields a human reviewer needs to decide CONFIRM/REJECT --
        never a tenant payment secret, never an editable amount/plan/date
        (Phase 26: the confirm/reject actions below accept no such field
        either)."""
        result = await self.db.execute(
            select(BillingPayment, BillingInvoice, Tenant)
            .join(BillingInvoice, BillingInvoice.id == BillingPayment.invoice_id)
            .join(Tenant, Tenant.tenant_id == BillingPayment.tenant_id)
            .where(
                BillingPayment.provider == "MANUAL",
                BillingPayment.manual_review_status == review_status,
            )
            .order_by(BillingPayment.manual_claimed_at.asc())
        )
        return [
            {
                "payment_id": str(payment.id),
                "invoice_id": str(invoice.id),
                "out_trade_no": payment.out_trade_no,
                "tenant_id": payment.tenant_id,
                "tenant_name": tenant.name,
                "plan_code": invoice.plan_code,
                "billing_period": invoice.billing_period,
                "amount_cents": payment.amount_cents,
                "currency": payment.currency,
                "manual_claimed_at": _iso(payment.manual_claimed_at),
                "review_status": payment.manual_review_status,
            }
            for payment, invoice, tenant in result.all()
        ]

    async def confirm_manual_payment(
        self, payment_id: int, *, verified_by: str, note: str | None = None
    ) -> dict[str, str]:
        """Platform SuperAdmin confirms funds actually arrived (F1G-CM Phase
        12-13) -- the ONLY action that produces a MANUAL_VERIFIED_PAYMENT_FACT.
        Built entirely from this payment's own server-persisted amount_cents/
        currency/out_trade_no -- the request carries no amount/plan/tenant/
        date field for this to consume -- then handed to the SAME
        process_verified_payment_fact() core a real WXPAY callback or future
        order-query recovery would use."""
        payment_result = await self.db.execute(
            select(BillingPayment).where(BillingPayment.id == payment_id).with_for_update()
        )
        payment = payment_result.scalar_one_or_none()
        if not payment:
            raise ValueError("支付记录不存在")
        if payment.provider != "MANUAL":
            raise ManualPaymentStateError("不是人工核实支付")
        if payment.status == PAYMENT_STATUS_PAID:
            # Idempotent: a second confirm click (or two SuperAdmins racing
            # in) must not re-run success processing or extend the
            # subscription again.
            await self.db.commit()
            return {"code": "SUCCESS", "message": "ok", "already_processed": "true"}
        if payment.manual_review_status != MANUAL_REVIEW_WAITING_CONFIRMATION:
            raise ManualPaymentStateError("当前状态不允许确认到账")

        confirmed_at = datetime.utcnow()
        payment.manual_review_status = MANUAL_REVIEW_CONFIRMED
        payment.manual_reviewed_at = confirmed_at
        payment.manual_reviewed_by = verified_by
        if note:
            payment.manual_review_note = (note or "").strip()[:255]

        notice = BillingPaymentNotification(
            out_trade_no=payment.out_trade_no,
            # MANUAL has no real provider transaction id; payment.id is
            # already globally unique (snowflake), so this is trivially
            # unique too, satisfying transaction_id's UNIQUE constraint.
            transaction_id=f"MANUAL{payment.id}",
            amount_cents=payment.amount_cents,
            currency=payment.currency,
            trade_state="SUCCESS",
            # V1 MANUAL paid_at authority: the platform's confirmation
            # timestamp, NOT the merchant's claim time and NOT a WeChat
            # success_time (there is no real provider here) -- F1G-CM Phase
            # 18. A future real-WXPAY path replaces this with the
            # provider's own success_time.
            paid_at=confirmed_at,
            metadata={"event_type": "MANUAL_CONFIRMED", "provider": "MANUAL", "verified_by": verified_by},
        )
        return await self.process_verified_payment_fact(notice)

    async def reject_manual_payment(
        self, payment_id: int, *, verified_by: str, note: str | None = None
    ) -> BillingPayment:
        """SuperAdmin found no matching funds received (F1G-CM Phase 10).
        Leaves BillingInvoice/BillingPayment funds status untouched (still
        PENDING) -- only records the review outcome, so the merchant can
        submit a new claim and the SAME invoice can still be paid later; no
        expiry is invented here."""
        payment_result = await self.db.execute(
            select(BillingPayment).where(BillingPayment.id == payment_id).with_for_update()
        )
        payment = payment_result.scalar_one_or_none()
        if not payment:
            raise ValueError("支付记录不存在")
        if payment.provider != "MANUAL":
            raise ManualPaymentStateError("不是人工核实支付")
        if payment.status == PAYMENT_STATUS_PAID:
            raise ManualPaymentStateError("账单已支付，不能驳回")
        if payment.manual_review_status != MANUAL_REVIEW_WAITING_CONFIRMATION:
            raise ManualPaymentStateError("当前状态不允许驳回")

        payment.manual_review_status = MANUAL_REVIEW_REJECTED
        payment.manual_reviewed_at = datetime.utcnow()
        payment.manual_reviewed_by = verified_by
        if note:
            payment.manual_review_note = (note or "").strip()[:255]
        await self.db.commit()
        await self.db.refresh(payment)
        return payment

    @staticmethod
    def payment_config_status() -> dict[str, Any]:
        return platform_payment_config_audit()

    @staticmethod
    def manual_payment_config_status() -> dict[str, Any]:
        return manual_payment_config_audit()
