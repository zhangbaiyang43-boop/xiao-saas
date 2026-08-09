from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint

from app.models.base import BaseModel


class BillingInvoice(BaseModel):
    __tablename__ = "billing_invoices"

    invoice_no = Column(String(64), nullable=False)
    charge_type = Column(String(32), nullable=False)
    description = Column(String(255), nullable=False, default="")
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(8), nullable=False, default="CNY")
    status = Column(String(32), nullable=False, default="PENDING")
    metadata_json = Column(JSON, nullable=True)
    commission_eligible = Column(Boolean, nullable=False, default=False)
    commission_policy_version = Column(String(64), nullable=False, default="PRE_CHANNEL")
    paid_at = Column(DateTime, nullable=True)
    expired_at = Column(DateTime, nullable=True)
    success_processed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("invoice_no", name="ux_billing_invoice_no"),
        Index("idx_billing_invoice_tenant_status", "tenant_id", "status"),
        Index("idx_billing_invoice_tenant_created", "tenant_id", "created_at"),
    )


class BillingPayment(BaseModel):
    __tablename__ = "billing_payments"

    invoice_id = Column(BigInteger, ForeignKey("billing_invoices.id"), nullable=False, index=True)
    payment_no = Column(String(64), nullable=False)
    out_trade_no = Column(String(64), nullable=False)
    provider = Column(String(32), nullable=False, default="FAKE")
    provider_mchid = Column(String(64), nullable=True)
    provider_appid = Column(String(64), nullable=True)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(8), nullable=False, default="CNY")
    status = Column(String(32), nullable=False, default="PENDING")
    transaction_id = Column(String(128), nullable=True)
    paid_at = Column(DateTime, nullable=True)
    anomaly_reason = Column(String(64), nullable=True)
    provider_metadata = Column(JSON, nullable=True)
    failure_reason = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("payment_no", name="ux_billing_payment_no"),
        UniqueConstraint("out_trade_no", name="ux_billing_payment_out_trade_no"),
        UniqueConstraint("transaction_id", name="ux_billing_payment_transaction_id"),
        Index("idx_billing_payment_tenant_status", "tenant_id", "status"),
        Index("idx_billing_payment_tenant_invoice", "tenant_id", "invoice_id"),
    )
