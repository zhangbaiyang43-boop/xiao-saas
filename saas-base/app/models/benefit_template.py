from sqlalchemy import Column, DateTime, DECIMAL, Index, Integer, JSON, String

from app.models.base import BaseModel


class BenefitTemplate(BaseModel):
    __tablename__ = "benefit_template"

    name = Column(String(64), nullable=False)
    level_code = Column(String(16), nullable=False)
    type = Column(String(32), nullable=False)
    value = Column(DECIMAL(10, 2), nullable=False, default=0)
    condition = Column(String(128))
    channel = Column(String(32), nullable=False, default="ALL")
    expire_at = Column(DateTime)
    cycle = Column(String(32))
    config = Column(JSON, nullable=False, default=dict)
    status = Column(Integer, nullable=False, default=1)

    __table_args__ = (
        Index("idx_benefit_template_tenant_level", "tenant_id", "level_code"),
        Index("idx_benefit_template_tenant_status", "tenant_id", "status"),
        Index("idx_benefit_template_tenant_channel", "tenant_id", "channel"),
    )
