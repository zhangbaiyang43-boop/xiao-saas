from sqlalchemy import BigInteger, Column, Index, JSON, String

from app.models.base import BaseModel


class WeworkEventLog(BaseModel):
    __tablename__ = "wework_event_log"

    external_userid = Column(String(128), nullable=True)
    userid = Column(String(128), nullable=True)
    event_type = Column(String(64), nullable=False)
    change_type = Column(String(64), nullable=True)
    state = Column(String(128), nullable=True)
    config_id = Column(String(128), nullable=True)
    raw_payload = Column(JSON, nullable=False)

    __table_args__ = (
        Index("idx_wework_event_tenant_created_at", "tenant_id", "created_at"),
        Index("idx_wework_event_tenant_external", "tenant_id", "external_userid"),
        Index("idx_wework_event_tenant_userid", "tenant_id", "userid"),
    )
