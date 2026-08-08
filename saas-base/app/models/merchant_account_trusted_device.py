from sqlalchemy import BigInteger, Column, DateTime, String, UniqueConstraint

from app.models.base import BaseModel


class MerchantAccountTrustedDevice(BaseModel):
    """Long-lived opaque device credential (secret stored hashed only)."""

    __tablename__ = "merchant_account_trusted_devices"
    __table_args__ = (UniqueConstraint("device_id", name="ux_ma_trusted_device_id"),)

    merchant_account_id = Column(BigInteger, nullable=False, index=True)
    device_id = Column(String(64), nullable=False)
    device_secret_hash = Column(String(128), nullable=False)
    device_name = Column(String(64), nullable=True)
    user_agent_summary = Column(String(128), nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
