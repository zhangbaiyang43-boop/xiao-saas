from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String

from app.models.base import BaseModel


class EntranceCode(BaseModel):
    __tablename__ = "entrance_code"

    id = Column(BigInteger, primary_key=True, index=True)
    name = Column(String(64), nullable=False)
    channel = Column(String(32), nullable=False, default="STORE")
    scene = Column(String(32), nullable=False)
    page = Column(String(128), nullable=False, default="pages/order/index")
    coupon_template_id = Column(BigInteger, ForeignKey("coupon_template.id"), nullable=True)
    image_url = Column(String(255), nullable=True)
    env_version = Column(String(16), nullable=False, default="release")
    code_type = Column(String(16), nullable=False, default="WECHAT")
    generation_status = Column(String(16), nullable=False, default="SUCCESS")
    generation_error = Column(String(512), nullable=True)
    status = Column(Integer, nullable=False, default=1)
    scan_count = Column(Integer, nullable=False, default=0)
    member_count = Column(Integer, nullable=False, default=0)
    last_scan_time = Column(DateTime, nullable=True)
    table_no = Column(String(32), nullable=True)
    
    entry_type = Column(String(16), nullable=False, default="table")
    order_mode = Column(String(16), nullable=False, default="dine_in")
    table_id = Column(BigInteger, nullable=True)
    target_page = Column(String(128), nullable=False, default="pages/order/index")

    __table_args__ = (
        Index("idx_entrance_code_tenant_scene", "tenant_id", "scene", unique=True),
        Index("idx_entrance_code_tenant_status", "tenant_id", "status"),
        Index("idx_entrance_code_tenant_channel", "tenant_id", "channel"),
        Index("idx_entrance_code_tenant_created_at", "tenant_id", "created_at"),
    )


class EntranceScanLog(BaseModel):
    __tablename__ = "entrance_scan_log"

    id = Column(BigInteger, primary_key=True, index=True)
    entrance_code_id = Column(BigInteger, ForeignKey("entrance_code.id"), nullable=False)
    customer_id = Column(BigInteger, ForeignKey("customer.id"), nullable=True)
    openid = Column(String(128), nullable=True)
    scene = Column(String(32), nullable=False)
    channel = Column(String(32), nullable=False)
    event_type = Column(String(32), nullable=False, default="SCAN")
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(1024), nullable=True)

    __table_args__ = (
        Index("idx_entrance_scan_tenant_code", "tenant_id", "entrance_code_id"),
        Index("idx_entrance_scan_tenant_customer", "tenant_id", "customer_id"),
        Index("idx_entrance_scan_tenant_created_at", "tenant_id", "created_at"),
    )
