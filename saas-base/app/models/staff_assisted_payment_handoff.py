from sqlalchemy import BigInteger, Column, DateTime, Index, String

from app.models.base import BaseModel


class StaffAssistedPaymentHandoff(BaseModel):
    __tablename__ = "staff_assisted_payment_handoffs"

    order_id = Column(BigInteger, nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(String(32), nullable=False, default="PENDING_SCAN")
    created_by_account_id = Column(BigInteger, nullable=True)
    created_by_role = Column(String(32), nullable=True)
    claimed_customer_id = Column(BigInteger, nullable=True)
    claimed_openid = Column(String(128), nullable=True)
    expires_at = Column(DateTime, nullable=False)
    claimed_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_saph_tenant_order", "tenant_id", "order_id"),
        Index("idx_saph_tenant_status", "tenant_id", "status"),
    )
