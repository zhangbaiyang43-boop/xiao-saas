from sqlalchemy import Column, Index, Integer, String, Text

from app.models.base import BaseModel


class PerfSample(BaseModel):
    __tablename__ = "perf_sample"

    metric = Column(String(64), nullable=False, index=True)
    ms = Column(Integer, nullable=False)
    meta = Column(Text, nullable=True)
    client_id = Column(String(64), nullable=True)

    __table_args__ = (
        Index("idx_perf_sample_tenant_created_at", "tenant_id", "created_at"),
    )
