from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from app.models.base import BaseModel


class SubscriptionAdjustment(BaseModel):
    """Append-only audit fact for a non-money subscription expiry change."""

    __tablename__ = "subscription_adjustments"

    subscription_id = Column(
        BigInteger,
        ForeignKey("subscriptions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    plan_code = Column(String(32), nullable=False)
    target_field = Column(String(32), nullable=False)
    adjustment_type = Column(String(32), nullable=False)
    operation_type = Column(String(32), nullable=False)
    delta_days = Column(Integer, nullable=True)
    before_expiry = Column(DateTime, nullable=False)
    calculation_base_expiry = Column(DateTime, nullable=False)
    after_expiry = Column(DateTime, nullable=False)
    before_status = Column(String(32), nullable=False)
    after_status = Column(String(32), nullable=False)
    stored_subscription_status = Column(String(32), nullable=False)
    natural_expiry_recovery = Column(Boolean, nullable=False, default=False)
    reason = Column(String(255), nullable=False)
    note = Column(Text, nullable=True)
    operator_type = Column(String(32), nullable=False)
    operator_id = Column(String(128), nullable=True)
    operator_label = Column(String(64), nullable=False)
    operator_ip = Column(String(45), nullable=False)
    request_id = Column(String(64), nullable=False)
    idempotency_key = Column(String(36), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="ux_subscription_adjustment_tenant_idempotency",
        ),
        Index(
            "idx_subscription_adjustment_tenant_created",
            "tenant_id",
            "created_at",
            "id",
        ),
        Index(
            "idx_subscription_adjustment_subscription_created",
            "subscription_id",
            "created_at",
            "id",
        ),
    )
