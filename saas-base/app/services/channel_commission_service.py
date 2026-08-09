import calendar
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.billing import BillingInvoice, BillingPayment
from app.models.channel_revenue import (
    ChannelCommissionLedger,
    ChannelLead,
    ChannelPartnerTenantBinding,
)
from app.services.base_service import BaseService
from app.services.channel_commission_policy import invoice_is_commission_eligible
from app.services.channel_partner_service import ACTIVE_LEAD_STATUSES, BINDING_STATUS_ACTIVE


ENTRY_TYPE_EARN = "EARN"
ENTRY_TYPE_REVERSAL = "REVERSAL"
ENTRY_TYPE_ADJUSTMENT = "ADJUSTMENT"

SOURCE_EVENT_BILLING_PAYMENT_SUCCESS = "BILLING_PAYMENT_SUCCESS"
SOURCE_EVENT_BILLING_REFUND = "BILLING_REFUND"

CHANNEL_COMMISSION_STATUS_PENDING = "PENDING"
CHANNEL_COMMISSION_STATUS_AVAILABLE = "AVAILABLE"
CHANNEL_COMMISSION_STATUS_SETTLED = "SETTLED"
CHANNEL_COMMISSION_STATUS_REVERSED = "REVERSED"


def add_calendar_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def calculate_commission_cents(base_amount_cents: int, rate_bps: int) -> int:
    amount = Decimal(int(base_amount_cents)) * Decimal(int(rate_bps)) / Decimal(10000)
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def serialize_ledger(item: ChannelCommissionLedger) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "partner_id": str(item.partner_id),
        "tenant_id": item.tenant_id,
        "binding_id": str(item.binding_id),
        "billing_invoice_id": str(item.billing_invoice_id) if item.billing_invoice_id else None,
        "billing_payment_id": str(item.billing_payment_id) if item.billing_payment_id else None,
        "entry_type": item.entry_type,
        "source_event_type": item.source_event_type,
        "source_event_id": item.source_event_id,
        "base_amount_cents": item.base_amount_cents,
        "commission_rate_bps": item.commission_rate_bps,
        "commission_amount_cents": item.commission_amount_cents,
        "status": item.status,
        "earned_at": item.earned_at.isoformat() if item.earned_at else None,
        "available_at": item.available_at.isoformat() if item.available_at else None,
        "source_ledger_id": str(item.source_ledger_id) if item.source_ledger_id else None,
    }


class ChannelCommissionService(BaseService):
    async def handle_billing_payment_success(
        self,
        invoice: BillingInvoice,
        payment: BillingPayment,
    ) -> ChannelCommissionLedger | None:
        if not invoice_is_commission_eligible(invoice):
            return None
        existing_invoice_earn = await self.db.execute(
            select(ChannelCommissionLedger).where(
                ChannelCommissionLedger.billing_invoice_id == invoice.id,
                ChannelCommissionLedger.entry_type == ENTRY_TYPE_EARN,
            )
        )
        existing = existing_invoice_earn.scalar_one_or_none()
        if existing:
            return existing

        binding_result = await self.db.execute(
            select(ChannelPartnerTenantBinding)
            .where(
                ChannelPartnerTenantBinding.tenant_id == invoice.tenant_id,
                ChannelPartnerTenantBinding.status == BINDING_STATUS_ACTIVE,
            )
            .with_for_update()
        )
        binding = binding_result.scalar_one_or_none()
        if not binding:
            return None

        paid_at = payment.paid_at or invoice.paid_at or datetime.utcnow()
        if binding.commission_started_at is None:
            binding.commission_started_at = paid_at
            binding.commission_ends_at = add_calendar_months(paid_at, binding.commission_term_months)
        elif not (binding.commission_started_at <= paid_at < binding.commission_ends_at):
            return None

        source_event_id = str(payment.id)
        existing_source = await self.db.execute(
            select(ChannelCommissionLedger).where(
                ChannelCommissionLedger.source_event_type == SOURCE_EVENT_BILLING_PAYMENT_SUCCESS,
                ChannelCommissionLedger.source_event_id == source_event_id,
            )
        )
        existing = existing_source.scalar_one_or_none()
        if existing:
            return existing

        amount = calculate_commission_cents(payment.amount_cents, binding.commission_rate_bps)
        ledger = ChannelCommissionLedger(
            partner_id=binding.partner_id,
            tenant_id=invoice.tenant_id,
            binding_id=binding.id,
            billing_invoice_id=invoice.id,
            billing_payment_id=payment.id,
            entry_type=ENTRY_TYPE_EARN,
            source_event_type=SOURCE_EVENT_BILLING_PAYMENT_SUCCESS,
            source_event_id=source_event_id,
            base_amount_cents=payment.amount_cents,
            commission_rate_bps=binding.commission_rate_bps,
            commission_amount_cents=amount,
            status=CHANNEL_COMMISSION_STATUS_PENDING,
            earned_at=paid_at,
            available_at=paid_at + timedelta(days=7),
        )
        try:
            async with self.db.begin_nested():
                self.db.add(ledger)
                await self.db.flush()
        except IntegrityError:
            result = await self.db.execute(
                select(ChannelCommissionLedger).where(
                    ChannelCommissionLedger.source_event_type == SOURCE_EVENT_BILLING_PAYMENT_SUCCESS,
                    ChannelCommissionLedger.source_event_id == source_event_id,
                )
            )
            return result.scalar_one_or_none()
        return ledger

    async def create_reversal(
        self,
        *,
        source_ledger_id: int,
        source_event_id: str,
        amount_cents: int,
    ) -> ChannelCommissionLedger:
        source_result = await self.db.execute(
            select(ChannelCommissionLedger).where(ChannelCommissionLedger.id == source_ledger_id)
        )
        source = source_result.scalar_one_or_none()
        if not source:
            raise ValueError("source ledger not found")
        existing_result = await self.db.execute(
            select(ChannelCommissionLedger).where(
                ChannelCommissionLedger.source_event_type == SOURCE_EVENT_BILLING_REFUND,
                ChannelCommissionLedger.source_event_id == source_event_id,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            return existing
        reversal = ChannelCommissionLedger(
            partner_id=source.partner_id,
            tenant_id=source.tenant_id,
            binding_id=source.binding_id,
            billing_invoice_id=source.billing_invoice_id,
            billing_payment_id=source.billing_payment_id,
            entry_type=ENTRY_TYPE_REVERSAL,
            source_event_type=SOURCE_EVENT_BILLING_REFUND,
            source_event_id=source_event_id,
            base_amount_cents=-abs(int(amount_cents)),
            commission_rate_bps=source.commission_rate_bps,
            commission_amount_cents=-abs(int(amount_cents)),
            status=CHANNEL_COMMISSION_STATUS_AVAILABLE,
            earned_at=datetime.utcnow(),
            available_at=datetime.utcnow(),
            source_ledger_id=source.id,
        )
        self.db.add(reversal)
        await self.db.flush()
        return reversal

    async def promote_available(self, now: datetime | None = None) -> None:
        now = now or datetime.utcnow()
        result = await self.db.execute(
            select(ChannelCommissionLedger)
            .where(
                ChannelCommissionLedger.status == CHANNEL_COMMISSION_STATUS_PENDING,
                ChannelCommissionLedger.available_at <= now,
            )
            .with_for_update()
        )
        for ledger in result.scalars().all():
            ledger.status = CHANNEL_COMMISSION_STATUS_AVAILABLE
        await self.db.flush()

    async def list_ledgers(
        self,
        partner_id: int | None = None,
        skip: int = 0,
        limit: int | None = None,
    ) -> list[ChannelCommissionLedger]:
        await self.promote_available()
        query = select(ChannelCommissionLedger)
        if partner_id:
            query = query.where(ChannelCommissionLedger.partner_id == partner_id)
        query = query.order_by(ChannelCommissionLedger.created_at.desc()).offset(skip)
        if limit is not None:
            query = query.limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_ledgers_for_partner(
        self,
        partner_id: int,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[ChannelCommissionLedger], int]:
        await self.promote_available()
        total = await self.db.scalar(
            select(func.count()).select_from(ChannelCommissionLedger).where(ChannelCommissionLedger.partner_id == partner_id)
        )
        rows = await self.list_ledgers(partner_id=partner_id, skip=skip, limit=limit)
        return rows, int(total or 0)

    async def get_ledger_for_partner(self, partner_id: int, ledger_id: int) -> ChannelCommissionLedger | None:
        await self.promote_available()
        result = await self.db.execute(
            select(ChannelCommissionLedger).where(
                ChannelCommissionLedger.id == ledger_id,
                ChannelCommissionLedger.partner_id == partner_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_net_earned_cents_by_binding_ids(
        self,
        *,
        partner_id: int,
        binding_ids: list[int],
    ) -> dict[int, int]:
        ids = sorted({int(item) for item in binding_ids if item})
        if not ids:
            return {}
        owned_result = await self.db.execute(
            select(ChannelPartnerTenantBinding.id).where(
                ChannelPartnerTenantBinding.partner_id == partner_id,
                ChannelPartnerTenantBinding.id.in_(ids),
            )
        )
        owned_ids = sorted({int(item) for item in owned_result.scalars().all()})
        if not owned_ids:
            return {}
        result = await self.db.execute(
            select(
                ChannelCommissionLedger.binding_id,
                func.coalesce(func.sum(ChannelCommissionLedger.commission_amount_cents), 0),
            )
            .where(
                ChannelCommissionLedger.partner_id == partner_id,
                ChannelCommissionLedger.binding_id.in_(owned_ids),
            )
            .group_by(ChannelCommissionLedger.binding_id)
        )
        totals = {int(binding_id): int(amount or 0) for binding_id, amount in result.all()}
        return {binding_id: totals.get(binding_id, 0) for binding_id in owned_ids}

    async def get_partner_earnings_summary(self, partner_id: int) -> dict[str, int]:
        await self.promote_available()
        ledger_result = await self.db.execute(
            select(ChannelCommissionLedger).where(ChannelCommissionLedger.partner_id == partner_id)
        )
        ledgers = list(ledger_result.scalars().all())
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        lead_count = await self.db.scalar(select(func.count()).select_from(ChannelLead).where(ChannelLead.partner_id == partner_id))
        binding_count = await self.db.scalar(
            select(func.count()).select_from(ChannelPartnerTenantBinding).where(ChannelPartnerTenantBinding.partner_id == partner_id)
        )
        gross_earned = sum(item.commission_amount_cents for item in ledgers if item.entry_type == ENTRY_TYPE_EARN)
        reversal_total = sum(abs(item.commission_amount_cents) for item in ledgers if item.entry_type == ENTRY_TYPE_REVERSAL)
        net_earned = sum(item.commission_amount_cents for item in ledgers)
        return {
            "gross_earned_cents": gross_earned,
            "reversed_cents": reversal_total,
            "net_earned_cents": net_earned,
            "total_earned_cents": net_earned,
            "today_net_earned_cents": sum(item.commission_amount_cents for item in ledgers if item.earned_at >= today_start),
            "month_net_earned_cents": sum(item.commission_amount_cents for item in ledgers if item.earned_at >= month_start),
            "month_earned_cents": sum(item.commission_amount_cents for item in ledgers if item.earned_at >= month_start),
            "pending_cents": sum(item.commission_amount_cents for item in ledgers if item.status == CHANNEL_COMMISSION_STATUS_PENDING),
            "available_cents": sum(item.commission_amount_cents for item in ledgers if item.status == CHANNEL_COMMISSION_STATUS_AVAILABLE),
            "settled_cents": sum(item.commission_amount_cents for item in ledgers if item.status == CHANNEL_COMMISSION_STATUS_SETTLED),
            "lead_count": int(lead_count or 0),
            "bound_tenant_count": int(binding_count or 0),
        }
