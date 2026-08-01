"""Add checkout_requested_at to dining_sessions

Revision ID: 20260727_0001
Revises: 20260726_0001
Create Date: 2026-07-27
"""
from alembic import op
import sqlalchemy as sa


revision = "20260727_0001"
down_revision = "20260726_0001"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if not column_exists("dining_sessions", "checkout_requested_at"):
        op.add_column(
            "dining_sessions",
            sa.Column("checkout_requested_at", sa.DateTime(), nullable=True),
        )


def downgrade():
    if column_exists("dining_sessions", "checkout_requested_at"):
        op.drop_column("dining_sessions", "checkout_requested_at")
