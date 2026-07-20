from sqlalchemy import Column, Date, DateTime, Index, Integer, String, Text, UniqueConstraint

from app.models.base import BaseModel


class QueueTicket(BaseModel):
    __tablename__ = "queue_tickets"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "queue_date",
            "queue_type",
            "daily_sequence",
            name="uq_queue_ticket_daily_type_sequence",
        ),
        Index("idx_queue_ticket_tenant_status_created", "tenant_id", "status", "created_at"),
        Index("idx_queue_ticket_tenant_date_type", "tenant_id", "queue_date", "queue_type"),
        Index("idx_queue_ticket_query_token", "query_token", unique=True),
    )

    queue_no = Column(String(16), nullable=False, index=True)
    queue_type = Column(String(1), nullable=False)
    queue_date = Column(Date, nullable=False)
    daily_sequence = Column(Integer, nullable=False)
    query_token = Column(String(64), nullable=False)
    party_size = Column(Integer, nullable=False)
    phone = Column(String(20), nullable=True)
    note = Column(Text, nullable=True)
    status = Column(String(16), nullable=False, default="waiting")
    called_at = Column(DateTime, nullable=True)
    seated_at = Column(DateTime, nullable=True)
    skipped_at = Column(DateTime, nullable=True)
