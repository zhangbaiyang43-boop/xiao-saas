from sqlalchemy import BigInteger, Column, Index, JSON, String

from app.models.base import BaseModel


class CustomerOperationLog(BaseModel):
    __tablename__ = "customer_operation_log"

    customer_id = Column(BigInteger, nullable=True, index=True)
    action = Column(String(64), nullable=False, index=True)
    source = Column(String(32), nullable=False, default="merchant")
    actor_type = Column(String(32), nullable=False, default="system")
    actor_id = Column(String(64))
    actor_name = Column(String(64))
    phone = Column(String(20))
    openid = Column(String(64))
    detail = Column(JSON, default={})
    ip = Column(String(64))
    user_agent = Column(String(255))

    __table_args__ = (
        Index("idx_customer_log_tenant_customer", "tenant_id", "customer_id"),
        Index("idx_customer_log_tenant_action", "tenant_id", "action"),
        Index("idx_customer_log_tenant_created", "tenant_id", "created_at"),
    )
