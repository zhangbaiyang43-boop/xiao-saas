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
    payment_mode = Column(String(32), nullable=False, default="prepay")  # prepay | postpay | table_account
    payment_method = Column(String(16), nullable=True)   # mock | wxpay | balance
    payment_time = Column(String(32), nullable=True)     # ISO string，避免加列类型迁移
    print_status = Column(String(16), nullable=False, default="PENDING")  # PENDING | SUCCESS | FAILED | UNKNOWN
    printed_at = Column(DateTime, nullable=True)
    balance_deduct_requested = Column(Numeric(10, 2), nullable=True)  # 本单预定用于抵扣的余额，供微信回调核销
    refund_status = Column(String(16), nullable=True)  # None | processing | success | failed
    refund_amount = Column(Numeric(10, 2), nullable=True)
    refund_error = Column(Text, nullable=True)
    refunded_at = Column(DateTime, nullable=True)
    # Waiter serving (Phase R2): independent of order.status done.
    # Kitchen complete → status=done + served_at NULL → Waiter queue.
    served_at = Column(DateTime, nullable=True)
    served_by_account_id = Column(BigInteger, nullable=True)  # merchant_accounts.id; no FK (project style)
    served_by_role = Column(String(32), nullable=True)  # waiter | owner
    completed_at = Column(DateTime, nullable=True)
    source = Column(String(16), nullable=False, default="miniprogram")   # miniprogram | h5 | staff
    staff_note = Column(String(64), nullable=True)  # 服务员代客加单时的可选备注（如"前台-老王"），不关联账号，仅展示
    # 前台发给顾客的实体取餐牌号（如"07"）。跟 table_no 不是一回事——牌子是跟着顾客走的
    # 临时凭证，不代表固定桌位，不能塞进 table_no/DiningSession（那边靠 table_no 做
    # 会话查重，牌子号在一天内会被反复重复使用，会把不相关的顾客错误合并进同一桌账）。
    # 这里只是一个展示用的自由文本字段，牌子池子的实际调度仍由前台人工管理。
    pickup_no = Column(String(16), nullable=True)
    # 支付成功后实际发放的首单/复购/第二单奖励券快照（JSON 字符串），供客户端在
    # 微信支付异步回调落库后，通过轮询 /orders/my 把这个奖励拿回来展示——微信支付的
    # 真实发券发生在 wxpay_notify 这个服务器对服务器回调里，回调结果不会回到小程序端。
    reward_coupon_snapshot = Column(Text, nullable=True)
    # 客户端为这一次"提交订单"生成的幂等键（比如双击提交、弱网超时后自动重试）。
    # NULL 不受这个唯一约束限制（MySQL/SQLite 的唯一索引都把 NULL 视为互不相同），
    # 老订单和没传这个字段的调用方完全不受影响。
    client_request_id = Column(String(64), nullable=True)

    __table_args__ = (
        Index("idx_orders_tenant_session", "tenant_id", "dining_session_id"),
        Index("idx_orders_tenant_participant", "tenant_id", "participant_id"),
        Index("idx_orders_tenant_session_status", "tenant_id", "dining_session_id", "status"),
        Index("idx_orders_parent_order", "parent_order_id"),
        Index("ux_orders_tenant_client_request_id", "tenant_id", "client_request_id", unique=True),
    )

class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger, ForeignKey("orders.id"), nullable=False, index=True)
    dish_id = Column(BigInteger, nullable=True)
    name = Column(String(64), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    qty = Column(Integer, nullable=False, default=1)



