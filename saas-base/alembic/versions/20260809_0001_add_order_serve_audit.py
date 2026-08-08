"""Add order serve audit fields (served_by_*).

Revision ID: 20260809_0001
Revises: 20260808_0004
Create Date: 2026-08-09

Phase R2: Waiter serving is independent of kitchen done.
served_at already exists; add minimal audit columns without FK
(matches merchant_account_id style elsewhere).
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_0001"
down_revision = "20260808_0004"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(col.get("name") == column_name for col in columns)


def upgrade():
    if not column_exists("orders", "served_by_account_id"):
        op.add_column(
            "orders",
            sa.Column("served_by_account_id", sa.BigInteger(), nullable=True),
        )
    if not column_exists("orders", "served_by_role"):
        op.add_column(
            "orders",
            sa.Column("served_by_role", sa.String(length=32), nullable=True),
        )


def downgrade():
    if column_exists("orders", "served_by_role"):
        op.drop_column("orders", "served_by_role")
    if column_exists("orders", "served_by_account_id"):
        op.drop_column("orders", "served_by_account_id")
