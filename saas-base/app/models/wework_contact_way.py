from sqlalchemy import Boolean, Column, Index, JSON, String

from app.models.base import BaseModel


class WeworkContactWay(BaseModel):
    __tablename__ = "wework_contact_way"

    config_id = Column(String(128), nullable=False, unique=True, index=True)
    qr_code = Column(String(500), nullable=False)
    userid = Column(String(128), nullable=False)
    scene = Column(String(128), nullable=True)
    remark = Column(String(255), nullable=True)
    skip_verify = Column(Boolean, default=True, nullable=False)
    raw_payload = Column(JSON, nullable=True)

    __table_args__ = (
        Index("idx_wework_contact_way_tenant_created_at", "tenant_id", "created_at"),
        Index("idx_wework_contact_way_tenant_userid", "tenant_id", "userid"),
    )
