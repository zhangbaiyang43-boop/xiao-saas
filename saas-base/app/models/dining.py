from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, String

from app.models.base import BaseModel


class DiningSession(BaseModel):
    __tablename__ = "dining_sessions"

    table_no = Column(String(32), nullable=False, default="")
    status = Column(String(16), nullable=False, default="OPEN")
    active_key = Column(String(96), nullable=True)
    started_at = Column(DateTime, nullable=False)
    last_activity_at = Column(DateTime, nullable=False)
    closed_at = Column(DateTime, nullable=True)
    closed_by = Column(String(64), nullable=True)

    __table_args__ = (
        Index("ux_dining_session_active_key", "active_key", unique=True),
        Index("idx_dining_session_tenant_table_status", "tenant_id", "table_no", "status"),
        Index("idx_dining_session_tenant_table_created", "tenant_id", "table_no", "created_at"),
    )


class DiningParticipant(BaseModel):
    __tablename__ = "dining_participants"

    session_id = Column(BigInteger, ForeignKey("dining_sessions.id"), nullable=False, index=True)
    customer_id = Column(BigInteger, ForeignKey("customer.id"), nullable=True)
    openid = Column(String(128), nullable=True)
    guest_token_hash = Column(String(128), nullable=True)
    client_id = Column(String(64), nullable=True)
    joined_at = Column(DateTime, nullable=False)
    last_active_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("ux_dining_participant_token_hash", "guest_token_hash", unique=True),
        Index("ux_dining_participant_session_client", "session_id", "client_id", unique=True),
        Index("ux_dining_participant_session_customer", "session_id", "customer_id", unique=True),
        Index("idx_dining_participant_tenant_session", "tenant_id", "session_id"),
        Index("idx_dining_participant_tenant_customer", "tenant_id", "customer_id"),
    )
