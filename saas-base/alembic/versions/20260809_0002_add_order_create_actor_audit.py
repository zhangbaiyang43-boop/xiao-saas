"""Add order create actor audit fields (created_by_*).

Revision ID: 20260809_0002
Revises: 20260809_0001
Create Date: 2026-08-09

Phase R3: staff assisted add must record who created the order and
their role snapshot. No FK (matches served_by_account_id style).
Does not alter historical source/staff_note values.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_0002"
down_revision = "20260809_0001"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(col.get("name") == column_name for col in columns)


def upgrade():
    if not column_exists("orders", "created_by_account_id"):
        op.add_column(
            "orders",
            sa.Column("created_by_account_id", sa.BigInteger(), nullable=True),
        )
    if not column_exists("orders", "created_by_role"):
        op.add_column(
            "orders",
            sa.Column("created_by_role", sa.String(length=32), nullable=True),
        )


def downgrade():
    if column_exists("orders", "created_by_role"):
        op.drop_column("orders", "created_by_role")
    if column_exists("orders", "created_by_account_id"):
        op.drop_column("orders", "created_by_account_id")
