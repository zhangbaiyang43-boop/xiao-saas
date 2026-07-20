from sqlalchemy import BigInteger, Column, DateTime, DECIMAL, Index, Integer, String

from app.models.base import BaseModel


class MemberAccount(BaseModel):
    __tablename__ = "member_account"

    customer_id = Column(BigInteger, nullable=False)
    member_id = Column(String(64), nullable=False)
    level_code = Column(String(16), nullable=False, default="LV1")
    level_name = Column(String(32), nullable=False, default="普通会员")
    total_consumption = Column(DECIMAL(10, 2), nullable=False, default=0)
    yearly_consumption = Column(DECIMAL(10, 2), nullable=False, default=0)
    points_balance = Column(Integer, nullable=False, default=0)
    balance = Column(DECIMAL(10, 2), nullable=False, default=0)
    last_consume_time = Column(DateTime)
    level_checked_at = Column(DateTime)

    __table_args__ = (
        Index("idx_member_account_tenant_customer", "tenant_id", "customer_id", unique=True),
        Index("idx_member_account_tenant_member", "tenant_id", "member_id", unique=True),
        Index("idx_member_account_tenant_level", "tenant_id", "level_code"),
    )
