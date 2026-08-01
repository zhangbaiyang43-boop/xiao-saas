"""Add dish_library_item table

平台级共享菜品库：商户在"加菜品"时勾选"分享到菜品库"，菜名和商户自己实拍的图片
会存进这张表（跨租户共享，不挂 tenant_id 外键约束，做法和 store_listing 表一致）。
同类目（川菜/烧烤/标准品）的其他商户可以从库里搜索并一键导入，直接复用已经上传
好的图片。

Revision ID: 20260730_0003
Revises: 20260730_0002
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa


revision = "20260730_0003"
down_revision = "20260730_0002"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return table_name in sa.inspect(bind).get_table_names()


def upgrade():
    if table_exists("dish_library_item"):
        return

    op.create_table(
        "dish_library_item",
        # id 由应用层 generate_snowflake_id 生成（跟 BaseModel 其它表一致），不用 MySQL
        # AUTO_INCREMENT——primary_key=True 在 MySQL 下会隐式加自增，跟雪花 id 冲突，
        # 所以这里显式用 PrimaryKeyConstraint，跟 dining_sessions 表的写法保持一致。
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("category", sa.String(32), nullable=True),
        sa.Column("cuisine_type", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="dish"),
        sa.Column("image", sa.String(512), nullable=True),
        sa.Column("reference_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("source_tenant_id", sa.String(32), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_dish_library_name", "dish_library_item", ["name"])
    op.create_index("idx_dish_library_cuisine_type", "dish_library_item", ["cuisine_type"])


def downgrade():
    if table_exists("dish_library_item"):
        op.drop_index("idx_dish_library_cuisine_type", table_name="dish_library_item")
        op.drop_index("idx_dish_library_name", table_name="dish_library_item")
        op.drop_table("dish_library_item")
