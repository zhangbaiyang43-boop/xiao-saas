from sqlalchemy import Column, Integer, String, DateTime, Index, Text
from app.models.base import BaseModel
from datetime import datetime

class TenantPlugin(BaseModel):
    __tablename__ = 'tenant_plugin'
    
    plugin_code = Column(String(64), nullable=False)
    status = Column(Integer, default=1)
    lifecycle_status = Column(String(32), default="ENABLED")
    version = Column(String(32))
    config_json = Column(Text, default="{}")
    last_error = Column(String(255))
    installed_at = Column(DateTime, nullable=False)
    enabled_at = Column(DateTime)
    disabled_at = Column(DateTime)
    
    __table_args__ = (
        Index('idx_tenant_plugin_unique', 'tenant_id', 'plugin_code', unique=True),
        Index('idx_tenant_plugin_status', 'tenant_id', 'status'),
        Index('idx_tenant_plugin_lifecycle', 'tenant_id', 'lifecycle_status'),
    )
