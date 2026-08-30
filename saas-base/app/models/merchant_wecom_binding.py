from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String, UniqueConstraint

from app.models.base import BaseModel


class MerchantWecomBinding(BaseModel):
    __tablename__ = "merchant_wecom_bindings"
    __table_args__ = (
        UniqueConstraint("active_tenant_id_key", name="ux_merchant_wecom_active_tenant"),
        UniqueConstraint("active_external_userid_key", name="ux_merchant_wecom_active_external_userid"),
        Index("idx_merchant_wecom_tenant_status", "tenant_id", "status"),
        Index("idx_merchant_wecom_external_status", "external_userid", "status"),
    )

    external_userid = Column(String(128), nullable=False)
    wecom_user_id = Column(String(128), nullable=True)
    status = Column(String(16), nullable=False, default="ACTIVE")
    bound_by = Column(String(64), nullable=True)
    bound_at = Column(DateTime, nullable=False)
    unbound_at = Column(DateTime, nullable=True)
    active_tenant_id_key = Column(String(32), nullable=True)
    active_external_userid_key = Column(String(128), nullable=True)


class MerchantWecomBindingToken(BaseModel):
    __tablename__ = "merchant_wecom_binding_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="ux_merchant_wecom_token_hash"),
        Index("idx_merchant_wecom_token_source_event", "source_event_id"),
        Index("idx_merchant_wecom_token_external", "external_userid"),
        Index("idx_merchant_wecom_token_expires", "expires_at"),
    )

    token_hash = Column(String(64), nullable=False)
    external_userid = Column(String(128), nullable=False)
    wecom_user_id = Column(String(128), nullable=True)
    source_event_id = Column(BigInteger, nullable=True)
    status = Column(String(16), nullable=False, default="ACTIVE")
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    last_code_requested_at = Column(DateTime, nullable=True)
    code_request_count = Column(Integer, nullable=False, default=0)
