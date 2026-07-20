"""Add balance_deduct_requested to orders

Revision ID: 20260720_0001
Revises: 20260718_0001
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa


revision = "20260720_0001"
down_revision = "20260718_0001"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if not column_exists("orders", "balance_deduct_requested"):
        op.add_column(
            "orders",
            sa.Column("balance_deduct_requested", sa.Numeric(10, 2), nullable=True),
        )


def downgrade():
    if column_exists("orders", "balance_deduct_requested"):
        op.drop_column("orders", "balance_deduct_requested")
