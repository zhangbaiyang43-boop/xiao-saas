from sqlalchemy import JSON, Column

from app.models.base import BaseModel


class TenantConfig(BaseModel):
    __tablename__ = "tenant_config"

    member_rules = Column(JSON, nullable=False, default=dict)
    coupon_rules = Column(JSON, nullable=False, default=dict)
    business_info = Column(JSON, nullable=False, default=dict)
    plugin_settings = Column(JSON, nullable=False, default=dict)
