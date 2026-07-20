"""Add order print idempotency fields

Revision ID: 20260718_0001
Revises: 20260715_0001
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa


revision = "20260718_0001"
down_revision = "20260715_0001"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if not column_exists("orders", "print_status"):
        op.add_column(
            "orders",
            sa.Column("print_status", sa.String(length=16), nullable=False, server_default="PENDING"),
        )
    if not column_exists("orders", "printed_at"):
        op.add_column("orders", sa.Column("printed_at", sa.DateTime(), nullable=True))


def downgrade():
    if column_exists("orders", "printed_at"):
        op.drop_column("orders", "printed_at")
    if column_exists("orders", "print_status"):
        op.drop_column("orders", "print_status")
