"""Add merchant and order payment mode fields

Revision ID: 20260726_0001
Revises: 20260724_0002
Create Date: 2026-07-26
"""
from alembic import op
import sqlalchemy as sa


revision = "20260726_0001"
down_revision = "20260724_0002"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if not column_exists("tenant", "payment_mode"):
        op.add_column(
            "tenant",
            sa.Column("payment_mode", sa.String(length=32), nullable=False, server_default="prepay"),
        )
    if not column_exists("orders", "payment_mode"):
        op.add_column(
            "orders",
            sa.Column("payment_mode", sa.String(length=32), nullable=False, server_default="prepay"),
        )


def downgrade():
    if column_exists("orders", "payment_mode"):
        op.drop_column("orders", "payment_mode")
    if column_exists("tenant", "payment_mode"):
        op.drop_column("tenant", "payment_mode")