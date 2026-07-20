from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, Index
from app.models.base import BaseModel

class Coupon(BaseModel):
    __tablename__ = 'coupon'

    template_id = Column(BigInteger, ForeignKey('coupon_template.id'), nullable=False)
    customer_id = Column(BigInteger, ForeignKey('customer.id'), nullable=False)
    code = Column(String(64), unique=True, nullable=False)
    verify_code = Column(String(8), nullable=True)
    status = Column(String(16), default='UNUSED')
    use_time = Column(DateTime)
    expire_time = Column(DateTime, nullable=False)
    revoke_time = Column(DateTime)
    revoke_reason = Column(String(255))
    abnormal_reason = Column(String(255))

    __table_args__ = (
        Index('idx_coupon_code', 'code'),
        Index('idx_coupon_customer', 'customer_id'),
        Index('idx_coupon_tenant_customer', 'tenant_id', 'customer_id'),
        Index('idx_coupon_tenant_status', 'tenant_id', 'status'),
        Index('idx_coupon_tenant_created_at', 'tenant_id', 'created_at'),
        Index('idx_coupon_tenant_verify_code', 'tenant_id', 'verify_code'),
    )