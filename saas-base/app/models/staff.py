from sqlalchemy import BigInteger, Column, Index, Integer, String

from app.models.base import BaseModel


class Staff(BaseModel):
    """员工推荐用的极简身份：员工不需要登录，只需要一个专属推荐码，
    用来在 customer.inviter_id / inviter_type 上标记"这个新顾客是这位员工带来的"。"""
    __tablename__ = "staff"

    name = Column(String(64), nullable=False)
    invite_code = Column(String(8), nullable=True)
    status = Column(Integer, nullable=False, default=1)

    __table_args__ = (
        Index("idx_staff_tenant_status", "tenant_id", "status"),
        Index("idx_staff_tenant_invite_code", "tenant_id", "invite_code"),
    )
