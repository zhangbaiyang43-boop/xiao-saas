from sqlalchemy import Column, BigInteger, String, Numeric, DateTime, Integer
from datetime import datetime

from app.utils.id_generator import generate_snowflake_id
from app.models.base import Base


class DishLibraryItem(Base):
    """跨商户共享的菜品库：商户上传菜品图片后可选择"分享到菜品库"，图片是商户自己
    实拍的，不涉及外部版权采购。之后同类目（川菜/烧烤/标准品）的其他商户可以搜索
    并一键导入同名菜品，直接复用这张图，不用重新想菜名、重新拍照。跨租户共享，
    不挂 tenant_id 外键约束，做法和 store_listing 表一致。"""

    __tablename__ = "dish_library_item"

    id = Column(BigInteger, primary_key=True, index=True, default=generate_snowflake_id)
    name = Column(String(64), nullable=False, index=True)
    category = Column(String(32), nullable=True)
    cuisine_type = Column(String(16), nullable=False, index=True)  # sichuan | bbq | universal
    kind = Column(String(16), nullable=False, default="dish")  # dish=现做菜品 | standard=标准品(瓶装/包装)
    image = Column(String(512), nullable=True)
    reference_price = Column(Numeric(10, 2), nullable=True)
    source_tenant_id = Column(String(32), nullable=True)  # 贡献者，仅用于追溯/后续治理，不做权限判断
    use_count = Column(Integer, nullable=False, default=0)  # 被导入次数，用于按热门排序
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
