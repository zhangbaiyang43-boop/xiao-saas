from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import validates

from app.models.base import Base, BaseModel
from app.utils.id_generator import generate_snowflake_id


class Plan(Base):
    """SaaS 套餐目录（FREE / STANDARD / PRO ...）。与 Tenant 同级的全局主数据，不属于任何租户，
    所以跟 Tenant 一样直接挂在 Base 下、不继承 BaseModel（BaseModel 强制要求 tenant_id）。

    price_month_cents / price_year_cents 是唯一价格权威（Phase F1A，见
    docs/saas-subscription-audit.md）：整数分，后端专有，禁止客户端传入金额、禁止浮点数、
    禁止 ×12×折扣 之类的运行时推导——年付折扣仅用于前端展示文案。"""

    __tablename__ = "plans"

    id = Column(BigInteger, primary_key=True, index=True, default=generate_snowflake_id)
    code = Column(String(32), nullable=False)
    name = Column(String(64), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    price_month_cents = Column(Integer, nullable=False, default=0)
    price_year_cents = Column(Integer, nullable=False, default=0)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("code", name="ux_plan_code"),
    )

    @validates("price_month_cents", "price_year_cents")
    def _validate_price_non_negative(self, key, value):
        if value is not None and value < 0:
            raise ValueError(f"{key} must be >= 0, got {value}")
        return value


class Subscription(BaseModel):
    """某个 Tenant 与某个 Plan 之间的商业关系快照（Phase 02 数据骨架）。
    没有任何业务代码读取这张表来做权限判断——见 docs/saas-subscription-audit.md §16/§27。
    一个 tenant 允许有多行历史记录，"当前"由 SubscriptionService 按 created_at 取最新一行。"""

    __tablename__ = "subscriptions"

    plan_id = Column(BigInteger, ForeignKey("plans.id"), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="TRIAL")
    trial_started_at = Column(DateTime, nullable=True)
    trial_ends_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    ends_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_subscription_tenant_status", "tenant_id", "status"),
        Index("idx_subscription_tenant_created", "tenant_id", "created_at"),
    )
