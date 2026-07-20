from datetime import datetime
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text

from app.models.base import Base, BaseModel


class OrderReview(Base):
    __tablename__ = "order_reviews"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(String(32), nullable=False, index=True)
    order_id = Column(BigInteger, ForeignKey("orders.id"), nullable=False)
    customer_id = Column(BigInteger, nullable=True)
    rating = Column(Integer, nullable=False)
    content = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=True, default=datetime.utcnow)
