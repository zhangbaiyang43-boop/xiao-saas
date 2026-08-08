from sqlalchemy import Column, String, UniqueConstraint

from app.models.base import BaseModel


class MerchantAccount(BaseModel):
    """Login-capable merchant staff account (not referral Staff).

    Owner continues to authenticate as Tenant via SMS; staff use username+password
    scoped to tenant_id (shop phone identifies the tenant at login).
    """

    __tablename__ = "merchant_accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "username", name="ux_merchant_account_tenant_username"),
    )

    name = Column(String(64), nullable=False)
    username = Column(String(64), nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    role = Column(String(32), nullable=False, default="waiter")  # waiter | kitchen (owner is Tenant)
    status = Column(String(16), nullable=False, default="active")  # active | disabled
