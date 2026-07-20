from sqlalchemy import Column, Integer, String, DateTime, DECIMAL, Text, Index
from app.models.base import BaseModel

class CouponTemplate(BaseModel):
    __tablename__ = 'coupon_template'
    
    name = Column(String(64), nullable=False)
    type = Column(String(16), nullable=False)
    value = Column(DECIMAL(10, 2), nullable=False)
    min_amount = Column(DECIMAL(10, 2), default=0)
    total_stock = Column(Integer, default=100)
    used_stock = Column(Integer, default=0)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(Integer, default=1)
    description = Column(Text)

    __table_args__ = (
        Index('idx_coupon_template_tenant_status', 'tenant_id', 'status'),
        Index('idx_coupon_template_tenant_created_at', 'tenant_id', 'created_at'),
    )
