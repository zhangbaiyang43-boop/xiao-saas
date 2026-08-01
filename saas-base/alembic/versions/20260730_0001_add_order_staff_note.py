"""add staff_note to orders so front-of-house staff can add a free-text note
(e.g. "front desk - Wang") when placing a staff-assisted order for a table,
without needing a per-employee account system

Revision ID: 20260730_0001
Revises: 20260729_0001
Create Date: 2026-07-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260730_0001"
down_revision = "20260729_0001"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if not column_exists("orders", "staff_note"):
        op.add_column("orders", sa.Column("staff_note", sa.String(64), nullable=True))


def downgrade():
    if column_exists("orders", "staff_note"):
        op.drop_column("orders", "staff_note")
