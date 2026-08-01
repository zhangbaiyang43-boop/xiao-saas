"""Add store_listing table

本地探店指南（找店/免费商家入驻）用到的门店条目表。跟 tenant 表是弱关联——
多数条目一开始是运营录入或商家自助提交的免费展示信息，claimed_tenant_id 在
商家真正开通开心点单后才回填，因此这里不加外键约束，跟项目里 tenant_id 字段
的一贯处理方式保持一致。

Revision ID: 20260724_0001
Revises: 20260723_0001
Create Date: 2026-07-24
"""
from alembic import op
import sqlalchemy as sa


revision = "20260724_0001"
down_revision = "20260723_0001"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return table_name in sa.inspect(bind).get_table_names()


def upgrade():
    if table_exists("store_listing"):
        return

    op.create_table(
        "store_listing",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("city", sa.String(32), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("category", sa.String(32), nullable=True),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("business_hours", sa.String(64), nullable=True),
        sa.Column("cover_image", sa.String(512), nullable=True),
        sa.Column("intro", sa.Text(), nullable=True),
        sa.Column("dishes", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("source", sa.String(24), nullable=False, server_default="operator_added"),
        sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claimed_tenant_id", sa.String(32), nullable=True),
        sa.Column("contact_name", sa.String(32), nullable=True),
        sa.Column("contact_phone", sa.String(20), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("verified_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("idx_store_listing_city_status", "store_listing", ["city", "status"])
    op.create_index("idx_store_listing_claimed_tenant", "store_listing", ["claimed_tenant_id"])


def downgrade():
    if table_exists("store_listing"):
        op.drop_index("idx_store_listing_claimed_tenant", table_name="store_listing")
        op.drop_index("idx_store_listing_city_status", table_name="store_listing")
        op.drop_table("store_listing")
