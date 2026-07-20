from sqlalchemy import Column, Integer, String, DateTime, DECIMAL, Text, Index, BigInteger, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class MarketingTemplate(BaseModel):
    __tablename__ = 'marketing_template'
    
    template_code = Column(String(32), nullable=False, unique=True, comment="模编码")
    template_name = Column(String(64), nullable=False, comment="模名称")
    industry = Column(String(128), comment="适用行业")
    description = Column(Text, comment="模描述")
    target_customer_price_min = Column(DECIMAL(10, 2), default=0, comment="适合客单价下限")
    target_customer_price_max = Column(DECIMAL(10, 2), default=0, comment="适合客单价上限")
    status = Column(Integer, nullable=False, default=1, comment="状态：1启用 0停用")

    rules = relationship('MarketingTemplateRule', back_populates='template')
    merchant_templates = relationship('MerchantTemplate', back_populates='template')

    __table_args__ = (
        Index('idx_marketing_template_code', 'template_code'),
        Index('idx_marketing_template_status', 'status'),
    )


class MarketingTemplateRule(BaseModel):
    __tablename__ = 'marketing_template_rule'
    
    template_id = Column(BigInteger, ForeignKey('marketing_template.id'), nullable=False, comment="模")
    rule_code = Column(String(32), nullable=False, comment="则编码")
    rule_name = Column(String(64), nullable=False, comment="则名称")
    trigger_type = Column(String(32), nullable=False, comment="触发类型：first_scan/after_verify/no_verify_after_days")
    coupon_type = Column(String(32), nullable=False, comment="券类型：new_customer/after_consumption/recall")
    discount_type = Column(String(32), nullable=False, comment="优惠类型：no_threshold/amount_threshold")
    threshold_amount = Column(DECIMAL(10, 2), default=0, comment="门槛金额")
    discount_amount = Column(DECIMAL(10, 2), nullable=False, comment="优惠金额")
    valid_days = Column(Integer, nullable=False, default=1, comment="有效期天数")
    trigger_delay_days = Column(Integer, default=0, comment="触发延迟天数")
    sort_order = Column(Integer, default=0, comment="排序号")
    status = Column(Integer, nullable=False, default=1, comment="状态：1启用 0停用")

    template = relationship('MarketingTemplate', back_populates='rules')

    __table_args__ = (
        Index('idx_marketing_template_rule_template', 'template_id'),
        Index('idx_marketing_template_rule_status', 'status'),
    )


class MerchantTemplate(BaseModel):
    __tablename__ = 'merchant_template'
    
    template_id = Column(BigInteger, ForeignKey('marketing_template.id'), nullable=False, comment="模")
    status = Column(Integer, nullable=False, default=1, comment="状态：1启用 0停用")
    enabled_at = Column(DateTime, comment="启用时间")
    disabled_at = Column(DateTime, comment="停用时间")

    template = relationship('MarketingTemplate', back_populates='merchant_templates')
    rules = relationship('MerchantTemplateRule', back_populates='merchant_template')

    __table_args__ = (
        Index('idx_merchant_template_tenant', 'tenant_id'),
        Index('idx_merchant_template_template', 'template_id'),
        Index('idx_merchant_template_status', 'status'),
    )


class MerchantTemplateRule(BaseModel):
    __tablename__ = 'merchant_template_rule'
    
    merchant_template_id = Column(BigInteger, ForeignKey('merchant_template.id'), nullable=False, comment="商家模")
    source_template_rule_id = Column(BigInteger, ForeignKey('marketing_template_rule.id'), comment="源模则")
    rule_code = Column(String(32), nullable=False, comment="则编码")
    rule_name = Column(String(64), nullable=False, comment="则名称")
    trigger_type = Column(String(32), nullable=False, comment="触发类型")
    coupon_id = Column(BigInteger, ForeignKey('coupon.id'), comment="历史遗留字段，未使用")
    coupon_template_id = Column(BigInteger, ForeignKey('coupon_template.id'), comment="绑定的优惠券模板")
    trigger_delay_days = Column(Integer, default=0, comment="触发延迟天数")
    status = Column(Integer, nullable=False, default=1, comment="状态：1启用 0停用")

    merchant_template = relationship('MerchantTemplate', back_populates='rules')

    __table_args__ = (
        Index('idx_merchant_template_rule_merchant_template', 'merchant_template_id'),
        Index('idx_merchant_template_rule_status', 'status'),
        Index('idx_merchant_template_rule_trigger_type', 'trigger_type'),
    )