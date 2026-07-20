from sqlalchemy import Boolean, Column, Integer, Numeric, String, Text

from app.models.base import BaseModel


class MenuItem(BaseModel):
    __tablename__ = "menu_items"

    name = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Numeric(10, 2), nullable=False, default=0)
    category = Column(String(32), nullable=True, default="默认")
    emoji = Column(String(8), nullable=True, default="🍽️")
    available = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    image = Column(String(512), nullable=True)
    sales_count = Column(Integer, nullable=True, default=None)
    tags = Column(String(256), nullable=True, default=None)  # 逗号分隔，如 "本店特色,热卖"
    original_price = Column(Numeric(10, 2), nullable=True, default=None)  # 划线价，用于展示"省¥X"
    stock = Column(Integer, nullable=True, default=None)  # NULL=不限量, 0=售罄, >0=剩余数量
