from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.models.billing import BillingInvoice, BillingPayment
from app.models.tenant import Tenant
from app.services.base_service import BaseService
from app.services.billing_payment_provider import (
    BillingPaymentNotification,
    BillingPaymentRequest,
    REAL_PAYMENT_BLOCKED_REASON,
    get_billing_payment_provider,
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

PAYMENT_PROVIDERS = {"FAKE", "WXPAY"}
DUPLICATE_INVOICE_PAYMENT = "DUPLICATE_INVOICE_PAYMENT"


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

    async def create_payment_attempt(self, invoice_id: int, provider_name: str = "FAKE") -> tuple[BillingPayment, dict[str, Any]]:
        tenant_id = self.require_tenant_id()
        provider_name = (provider_name or "FAKE").upper()
        if provider_name not in PAYMENT_PROVIDERS:
            raise ValueError("支付渠道不支持")
        if provider_name == "WXPAY":
            raise RuntimeError(REAL_PAYMENT_BLOCKED_REASON)

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
        provider = get_billing_payment_provider(provider_name)
        notice = provider.verify_notify(headers, body)
        if not notice:
            return {"code": "FAIL", "message": "验签失败"}
        if notice.trade_state != "SUCCESS":
            return {"code": "SUCCESS", "message": "ok"}

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

    @staticmethod
    def payment_config_status() -> dict[str, Any]:
        return platform_payment_config_audit()
