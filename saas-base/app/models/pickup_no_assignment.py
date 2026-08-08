from sqlalchemy import BigInteger, Column, ForeignKey, Index, String, UniqueConstraint

from app.models.base import BaseModel


class PickupNoAssignment(BaseModel):
    """当前活跃桌牌租约：同一商户下同一个号码同时只能被一个就餐会话占用。"""

    __tablename__ = "pickup_no_assignments"

    pickup_no = Column(String(16), nullable=False)
    dining_session_id = Column(
        BigInteger, ForeignKey("dining_sessions.id"), nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "pickup_no", name="ux_pickup_no_assignment_tenant_no"),
        UniqueConstraint("dining_session_id", name="ux_pickup_no_assignment_session"),
        Index("idx_pickup_no_assignment_tenant", "tenant_id"),
    )
