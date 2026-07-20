from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, String

from app.models.base import BaseModel


class CustomerIdentity(BaseModel):
    __tablename__ = "customer_identity"

    customer_id = Column(BigInteger, ForeignKey("customer.id"), nullable=False)
    channel = Column(String(32), nullable=False)
    channel_user_id = Column(String(128), nullable=False)
    phone = Column(String(20))
    unionid = Column(String(128))
    bind_time = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_customer_identity_channel", "tenant_id", "channel", "channel_user_id", unique=True),
        Index("idx_customer_identity_customer", "tenant_id", "customer_id"),
        Index("idx_customer_identity_phone", "tenant_id", "phone"),
    )
