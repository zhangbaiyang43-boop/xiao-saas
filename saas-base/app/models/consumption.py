from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, DECIMAL, Index
from app.models.base import BaseModel

class Consumption(BaseModel):
    __tablename__ = 'consumption'
    
    customer_id = Column(BigInteger, ForeignKey('customer.id'), nullable=False)
    project = Column(String(64), nullable=False)
    amount = Column(DECIMAL(10, 2), nullable=False)
    consume_time = Column(DateTime, nullable=False)
    remark = Column(String(255))
    
    __table_args__ = (
        Index('idx_consumption_customer_time', 'customer_id', 'consume_time'),
        Index('idx_consumption_tenant_customer_time', 'tenant_id', 'customer_id', 'consume_time'),
        Index('idx_consumption_tenant_created_at', 'tenant_id', 'created_at'),
    )
