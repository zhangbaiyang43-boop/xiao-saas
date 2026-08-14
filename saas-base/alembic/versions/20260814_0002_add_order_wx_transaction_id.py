"""Add the globally unique WeChat payment transaction identity.

Purely additive: nullable for legacy, mock, free and offline payments; no
historical backfill or rewrite.

Revision ID: 20260814_0002
Revises: 20260814_0001
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_0002"
down_revision = "20260814_0001"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    return any(
        column.get("name") == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def index_exists(table_name: str, index_name: str) -> bool:
    return any(
        index.get("name") == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def upgrade():
    if not column_exists("orders", "wx_transaction_id"):
        op.add_column(
            "orders",
            sa.Column("wx_transaction_id", sa.String(length=64), nullable=True),
        )
    if not index_exists("orders", "ux_orders_wx_transaction_id"):
        op.create_index(
            "ux_orders_wx_transaction_id",
            "orders",
            ["wx_transaction_id"],
            unique=True,
        )


def downgrade():
    if index_exists("orders", "ux_orders_wx_transaction_id"):
        op.drop_index("ux_orders_wx_transaction_id", table_name="orders")
    if column_exists("orders", "wx_transaction_id"):
        op.drop_column("orders", "wx_transaction_id")
