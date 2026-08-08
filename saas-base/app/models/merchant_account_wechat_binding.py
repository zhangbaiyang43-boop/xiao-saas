from sqlalchemy import BigInteger, Column, DateTime, String

from app.models.base import BaseModel


class MerchantAccountWechatBinding(BaseModel):
    """WeChat identity bound to a merchant_account (Authentication only)."""

    __tablename__ = "merchant_account_wechat_bindings"

    merchant_account_id = Column(BigInteger, nullable=False, index=True)
    wechat_app_id = Column(String(64), nullable=False)
    openid = Column(String(128), nullable=False)
    unionid = Column(String(128), nullable=True)
    bound_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
