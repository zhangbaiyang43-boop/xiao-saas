from sqlalchemy import Column, BigInteger, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from app.utils.id_generator import generate_snowflake_id

from app.models.base import Base

class Tenant(Base):
    __tablename__ = 'tenant'
    
    id = Column(BigInteger, primary_key=True, index=True, default=generate_snowflake_id)
    tenant_id = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(64), nullable=False)
    password_hash = Column(String(128), nullable=False)
    corp_id = Column(String(64))
    phone = Column(String(20))
    address = Column(String(500))
    logo_url = Column(String(500))
    status = Column(Boolean, default=True)
    is_open = Column(Boolean, default=True)              # 营业开关
    payment_mode = Column(String(32), nullable=False, default="prepay")  # prepay | postpay | table_account
    wx_pay_enabled = Column(Boolean, default=False)      # 是否已开通微信支付
    wx_mchid = Column(String(64), nullable=True)         # 商家自己的微信支付商户号
    wx_api_key_v3 = Column(String(256), nullable=True)   # 商家 APIv3 密钥
    wx_cert_serial = Column(String(128), nullable=True)  # 商家证书序列号
    wx_private_key = Column(String(4096), nullable=True) # 商家私钥 PEM
    wx_public_key_id = Column(String(128), nullable=True) # 微信支付公钥ID
    wx_public_key = Column(String(4096), nullable=True)   # 微信支付公钥（加密存储）
    wx_verify_mode = Column(String(32), default="public_key") # public_key | platform_certificate
    receiver_name = Column(String(128), nullable=True)   # 收款主体
    receiver_type = Column(String(32), nullable=True)    # enterprise | individual
    receiver_verified = Column(Boolean, default=False)   # 收款信息是否已验证
    payment_locked = Column(Boolean, default=True)       # 收款账户是否锁定
    verified_time = Column(DateTime, nullable=True)      # 最后验证时间
    feieyun_sn = Column(String(64), nullable=True)       # 飞鹅云打印机编号
    feieyun_key = Column(String(64), nullable=True)      # 飞鹅云打印机识别码
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
