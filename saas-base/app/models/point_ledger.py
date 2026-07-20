from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String

from app.models.base import BaseModel


class PointLedger(BaseModel):
    __tablename__ = "point_ledger"

    customer_id = Column(BigInteger, nullable=False)
    member_id = Column(String(64), nullable=False)
    event_type = Column(String(32), nullable=False)
    points = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False)
    source_channel = Column(String(32), nullable=False, default="STORE")
    ref_id = Column(String(64))
    expire_at = Column(DateTime)
    remark = Column(String(255))

    __table_args__ = (
        Index("idx_point_ledger_tenant_customer", "tenant_id", "customer_id"),
        Index("idx_point_ledger_tenant_member", "tenant_id", "member_id"),
        Index("idx_point_ledger_tenant_expire", "tenant_id", "expire_at"),
        Index("idx_point_ledger_tenant_created_at", "tenant_id", "created_at"),
    )
