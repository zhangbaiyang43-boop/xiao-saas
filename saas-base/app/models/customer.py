from sqlalchemy import BigInteger, Column, Integer, String, DateTime, JSON, Index
from app.models.base import BaseModel

class Customer(BaseModel):
    __tablename__ = 'customer'
    
    openid = Column(String(64), nullable=False)
    external_userid = Column(String(64))
    name = Column(String(64))
    phone = Column(String(20))
    tags = Column(JSON, default=[])
    inviter_id = Column(BigInteger)
    inviter_parent_id = Column(BigInteger)
    last_consume_time = Column(DateTime)
    status = Column(Integer, default=1, nullable=False)
    deleted_at = Column(DateTime)
    # 短邀请码：6 位大写字母+数字，用于小程序展示和分享链接
    short_invite_code = Column(String(8), nullable=True)

    __table_args__ = (
        Index('idx_customer_tenant_openid', 'tenant_id', 'openid', unique=True),
        Index('idx_customer_tenant_phone', 'tenant_id', 'phone'),
        Index('idx_customer_tenant_inviter', 'tenant_id', 'inviter_id'),
        Index('idx_customer_tenant_status', 'tenant_id', 'status'),
        Index('idx_customer_tenant_created_at', 'tenant_id', 'created_at'),
        Index('idx_customer_tenant_short_invite_code', 'tenant_id', 'short_invite_code'),
    )
