"""Add pickup_no to orders

前台发给顾客的实体取餐牌号（如"07"），跟 table_no/DiningSession 的会话查重逻辑
无关，纯展示字段，详见 app/models/order.py 里 pickup_no 字段上的注释。

Revision ID: 20260803_0002
Revises: 20260803_0001
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa


revision = "20260803_0002"
down_revision = "20260803_0001"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if not column_exists("orders", "pickup_no"):
        op.add_column(
            "orders",
            sa.Column("pickup_no", sa.String(16), nullable=True),
        )


def downgrade():
    if column_exists("orders", "pickup_no"):
        op.drop_column("orders", "pickup_no")
