from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, Text

from app.models.base import BaseModel


class ChannelEntry(BaseModel):
    __tablename__ = "channel_entry"

    name = Column(String(64), nullable=False, comment="渠道名称")
    channel_code = Column(String(32), nullable=False, comment="渠道编码：douyin/kuaishou/meituan/eleme/moments/offline/custom")
    landing_title = Column(String(128), nullable=True, comment="落地页标题")
    landing_subtitle = Column(String(256), nullable=True, comment="落地页副标题")
    cover_image = Column(String(512), nullable=True, comment="落地页封面图")
    coupon_template_id = Column(BigInteger, ForeignKey("coupon_template.id"), nullable=True, comment="绑定的优惠券模")
    mini_program_qrcode_url = Column(String(512), nullable=True, comment="小程序二维码地址")
    h5_url = Column(String(512), nullable=True, unique=True, comment="H5落地页链接")
    qrcode_url = Column(String(512), nullable=True, comment="H5链接二维码图片地址")
    status = Column(Integer, nullable=False, default=1, comment="状态：1启用 0停用")
    visit_count = Column(Integer, nullable=False, default=0, comment="访问次数")
    scan_count = Column(Integer, nullable=False, default=0, comment="扫码次数")

    __table_args__ = (
        Index("idx_channel_entry_tenant_status", "tenant_id", "status"),
        Index("idx_channel_entry_tenant_channel", "tenant_id", "channel_code"),
        Index("idx_channel_entry_tenant_created", "tenant_id", "created_at"),
        Index("idx_channel_entry_h5_url", "h5_url", unique=True),
    )


class ChannelEntryVisitLog(BaseModel):
    __tablename__ = "channel_entry_visit_log"

    entry_id = Column(BigInteger, ForeignKey("channel_entry.id"), nullable=False, comment="渠道入口")
    channel_code = Column(String(32), nullable=False, comment="渠道编码")
    user_agent = Column(String(1024), nullable=True, comment="用户代理")
    referer = Column(String(2048), nullable=True, comment="来源页面")
    ip = Column(String(64), nullable=True, comment="IP地址")
    query_params = Column(Text, nullable=True, comment="URL查询参数JSON")

    __table_args__ = (
        Index("idx_channel_visit_tenant_entry", "tenant_id", "entry_id"),
        Index("idx_channel_visit_tenant_created", "tenant_id", "created_at"),
    )