from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text

from app.models.base import Base, BaseModel


class Order(BaseModel):
    __tablename__ = "orders"

    customer_id = Column(BigInteger, nullable=True)
    dining_session_id = Column(BigInteger, ForeignKey("dining_sessions.id"), nullable=True, index=True)
    participant_id = Column(BigInteger, ForeignKey("dining_participants.id"), nullable=True, index=True)
    order_type = Column(String(16), nullable=True)
    parent_order_id = Column(BigInteger, ForeignKey("orders.id"), nullable=True, index=True)
    table_no = Column(String(32), nullable=False, default="")
    phone = Column(String(20), nullable=True)
    total = Column(Numeric(10, 2), nullable=False, default=0)
    status = Column(String(16), nullable=False, default="pending")
    remark = Column(Text, nullable=True)
    merchant_note = Column(Text, nullable=True)
    coupon_id = Column(BigInteger, nullable=True)
    discount_amount = Column(Numeric(10, 2), nullable=True)
    payment_status = Column(String(16), nullable=False, default="unpaid")  # unpaid | paid
    payment_method = Column(String(16), nullable=True)   # mock | wxpay | balance
    payment_time = Column(String(32), nullable=True)     # ISO string，避免加列类型迁移
    print_status = Column(String(16), nullable=False, default="PENDING")  # PENDING | SUCCESS | FAILED
    printed_at = Column(DateTime, nullable=True)
    balance_deduct_requested = Column(Numeric(10, 2), nullable=True)  # 本单预定用于抵扣的余额，供微信回调核销
    refund_status = Column(String(16), nullable=True)  # None | processing | success | failed
    refund_amount = Column(Numeric(10, 2), nullable=True)
    refund_error = Column(Text, nullable=True)
    refunded_at = Column(DateTime, nullable=True)
    served_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    source = Column(String(16), nullable=False, default="miniprogram")   # miniprogram | h5

    __table_args__ = (
        Index("idx_orders_tenant_session", "tenant_id", "dining_session_id"),
        Index("idx_orders_tenant_participant", "tenant_id", "participant_id"),
        Index("idx_orders_tenant_session_status", "tenant_id", "dining_session_id", "status"),
        Index("idx_orders_parent_order", "parent_order_id"),
    )

class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger, ForeignKey("orders.id"), nullable=False, index=True)
    dish_id = Column(BigInteger, nullable=True)
    name = Column(String(64), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    qty = Column(Integer, nullable=False, default=1)



