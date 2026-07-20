"""Add refund tracking fields to orders

Revision ID: 20260720_0002
Revises: 20260720_0001
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa


revision = "20260720_0002"
down_revision = "20260720_0001"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if not column_exists("orders", "refund_status"):
        op.add_column("orders", sa.Column("refund_status", sa.String(length=16), nullable=True))
    if not column_exists("orders", "refund_amount"):
        op.add_column("orders", sa.Column("refund_amount", sa.Numeric(10, 2), nullable=True))
    if not column_exists("orders", "refund_error"):
        op.add_column("orders", sa.Column("refund_error", sa.Text(), nullable=True))
    if not column_exists("orders", "refunded_at"):
        op.add_column("orders", sa.Column("refunded_at", sa.DateTime(), nullable=True))


def downgrade():
    if column_exists("orders", "refunded_at"):
        op.drop_column("orders", "refunded_at")
    if column_exists("orders", "refund_error"):
        op.drop_column("orders", "refund_error")
    if column_exists("orders", "refund_amount"):
        op.drop_column("orders", "refund_amount")
    if column_exists("orders", "refund_status"):
        op.drop_column("orders", "refund_status")
