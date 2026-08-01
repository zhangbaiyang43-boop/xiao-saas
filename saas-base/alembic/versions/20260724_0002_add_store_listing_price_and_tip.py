"""Add avg_price and tip to store_listing

产品复盘发现列表页缺两样最直接的"值不值得去/好吃不好吃"判断信号：人均价格，
以及跟"一句话推荐"分开的"到店提醒"（避免运营把好话和真实提醒挤在一句话里，
读起来像广告文案）。

Revision ID: 20260724_0002
Revises: 20260724_0001
Create Date: 2026-07-24
"""
from alembic import op
import sqlalchemy as sa


revision = "20260724_0002"
down_revision = "20260724_0001"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if not column_exists("store_listing", "tip"):
        op.add_column("store_listing", sa.Column("tip", sa.Text(), nullable=True))
    if not column_exists("store_listing", "avg_price"):
        op.add_column("store_listing", sa.Column("avg_price", sa.Integer(), nullable=True))


def downgrade():
    if column_exists("store_listing", "avg_price"):
        op.drop_column("store_listing", "avg_price")
    if column_exists("store_listing", "tip"):
        op.drop_column("store_listing", "tip")
