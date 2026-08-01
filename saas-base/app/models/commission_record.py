from sqlalchemy import BigInteger, Column, DateTime, DECIMAL, Index, Integer, String, UniqueConstraint

from app.models.base import BaseModel


class CommissionRecord(BaseModel):
    __tablename__ = "commission_record"

    user_id = Column(BigInteger, nullable=False)
    order_id = Column(String(64))
    amount = Column(DECIMAL(10, 2), nullable=False, default=0)
    level = Column(Integer, nullable=False)
    receiver_id = Column(BigInteger, nullable=False)
    # receiver_id 指向谁：'customer'（默认，老数据 NULL 一律按 customer 处理）| 'staff'——
    # staff 类型的记录不走发券逻辑，只是记一笔待商家线下结算的现金。
    receiver_type = Column(String(16), nullable=True)
    commission_amount = Column(DECIMAL(10, 2), nullable=False, default=0)
    status = Column(String(16), nullable=False, default="PENDING")
    source_type = Column(String(32), nullable=False, default="VERIFY")
    source_coupon_id = Column(BigInteger)
    settled_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint("tenant_id", "source_coupon_id", "level", name="uq_commission_coupon_level"),
        Index("idx_commission_tenant_receiver", "tenant_id", "receiver_id"),
        Index("idx_commission_tenant_user", "tenant_id", "user_id"),
        Index("idx_commission_tenant_status", "tenant_id", "status"),
        Index("idx_commission_tenant_created_at", "tenant_id", "created_at"),
    )
