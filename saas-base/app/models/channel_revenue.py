from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint

from app.models.base import Base
from app.utils.id_generator import generate_snowflake_id


class ChannelPartner(Base):
    __tablename__ = "channel_partners"

    id = Column(BigInteger, primary_key=True, index=True, default=generate_snowflake_id)
    partner_code = Column(String(64), nullable=False)
    name = Column(String(128), nullable=False)
    mobile = Column(String(32), nullable=False)
    mobile_normalized = Column(String(32), nullable=False)
    partner_type = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("partner_code", name="ux_channel_partner_code"),
        UniqueConstraint("mobile_normalized", name="ux_channel_partner_mobile_normalized"),
        Index("idx_channel_partner_status", "status"),
        Index("idx_channel_partner_mobile", "mobile"),
    )


class ChannelLeadMobileLock(Base):
    __tablename__ = "channel_lead_mobile_locks"

    id = Column(BigInteger, primary_key=True, index=True, default=generate_snowflake_id)
    merchant_mobile_normalized = Column(String(32), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("merchant_mobile_normalized", name="ux_channel_lead_mobile_lock"),
    )


class ChannelLead(Base):
    __tablename__ = "channel_leads"

    id = Column(BigInteger, primary_key=True, index=True, default=generate_snowflake_id)
    partner_id = Column(BigInteger, ForeignKey("channel_partners.id"), nullable=False)
    merchant_name = Column(String(128), nullable=False)
    merchant_mobile = Column(String(32), nullable=False)
    merchant_mobile_normalized = Column(String(32), nullable=False)
    contact_name = Column(String(64), nullable=False, default="")
    status = Column(String(32), nullable=False, default="PROTECTED")
    protected_at = Column(DateTime, nullable=False)
    protected_until = Column(DateTime, nullable=False)
    tenant_id = Column(String(32), nullable=True)
    converted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_channel_lead_partner_status", "partner_id", "status"),
        Index("idx_channel_lead_mobile_status", "merchant_mobile_normalized", "status", "protected_until"),
        Index("idx_channel_lead_tenant", "tenant_id"),
    )


class ChannelPartnerTenantBinding(Base):
    __tablename__ = "channel_partner_tenant_bindings"

    id = Column(BigInteger, primary_key=True, index=True, default=generate_snowflake_id)
    tenant_id = Column(String(32), nullable=False)
    partner_id = Column(BigInteger, ForeignKey("channel_partners.id"), nullable=False)
    source_lead_id = Column(BigInteger, ForeignKey("channel_leads.id"), nullable=True)
    status = Column(String(32), nullable=False, default="ACTIVE")
    commission_rate_bps = Column(Integer, nullable=False)
    commission_term_months = Column(Integer, nullable=False)
    commission_started_at = Column(DateTime, nullable=True)
    commission_ends_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", name="ux_channel_binding_tenant"),
        Index("idx_channel_binding_partner_status", "partner_id", "status"),
        Index("idx_channel_binding_tenant_status", "tenant_id", "status"),
    )


class ChannelCommissionLedger(Base):
    __tablename__ = "channel_commission_ledger"

    id = Column(BigInteger, primary_key=True, index=True, default=generate_snowflake_id)
    partner_id = Column(BigInteger, ForeignKey("channel_partners.id"), nullable=False)
    tenant_id = Column(String(32), nullable=False)
    binding_id = Column(BigInteger, ForeignKey("channel_partner_tenant_bindings.id"), nullable=False)
    billing_invoice_id = Column(BigInteger, ForeignKey("billing_invoices.id"), nullable=True)
    billing_payment_id = Column(BigInteger, ForeignKey("billing_payments.id"), nullable=True)
    entry_type = Column(String(32), nullable=False)
    source_event_type = Column(String(64), nullable=False)
    source_event_id = Column(String(128), nullable=False)
    base_amount_cents = Column(Integer, nullable=False)
    commission_rate_bps = Column(Integer, nullable=False)
    commission_amount_cents = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False)
    earned_at = Column(DateTime, nullable=False)
    available_at = Column(DateTime, nullable=False)
    source_ledger_id = Column(BigInteger, ForeignKey("channel_commission_ledger.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("source_event_type", "source_event_id", name="ux_channel_ledger_source_event"),
        Index("idx_channel_ledger_partner_status", "partner_id", "status"),
        Index("idx_channel_ledger_tenant", "tenant_id"),
        Index("idx_channel_ledger_binding", "binding_id"),
        Index("idx_channel_ledger_payment", "billing_payment_id"),
        Index("idx_channel_ledger_available", "status", "available_at"),
    )


class ChannelCommissionSettlement(Base):
    __tablename__ = "channel_commission_settlements"

    id = Column(BigInteger, primary_key=True, index=True, default=generate_snowflake_id)
    partner_id = Column(BigInteger, ForeignKey("channel_partners.id"), nullable=False)
    settlement_no = Column(String(64), nullable=False)
    amount_cents = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, default="SETTLED")
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    settled_at = Column(DateTime, nullable=True)
    operator = Column(String(64), nullable=False, default="")
    transaction_reference = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("settlement_no", name="ux_channel_settlement_no"),
        Index("idx_channel_settlement_partner_status", "partner_id", "status"),
    )


class ChannelCommissionSettlementItem(Base):
    __tablename__ = "channel_commission_settlement_items"

    id = Column(BigInteger, primary_key=True, index=True, default=generate_snowflake_id)
    settlement_id = Column(BigInteger, ForeignKey("channel_commission_settlements.id"), nullable=False)
    ledger_id = Column(BigInteger, ForeignKey("channel_commission_ledger.id"), nullable=False)
    partner_id = Column(BigInteger, ForeignKey("channel_partners.id"), nullable=False)
    amount_cents = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("ledger_id", name="ux_channel_settlement_item_ledger"),
        Index("idx_channel_settlement_item_settlement", "settlement_id"),
        Index("idx_channel_settlement_item_partner", "partner_id"),
    )
