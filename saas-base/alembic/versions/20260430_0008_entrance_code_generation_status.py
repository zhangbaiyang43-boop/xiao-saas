"""add entrance code generation status

Revision ID: 20260430_0008
Revises: 20260429_0007
Create Date: 2026-04-30 09:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260430_0008"
down_revision = "20260429_0007"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if not column_exists("entrance_code", "generation_status"):
        op.add_column(
            "entrance_code",
            sa.Column("generation_status", sa.String(length=16), nullable=False, server_default="SUCCESS"),
        )
    if not column_exists("entrance_code", "generation_error"):
        op.add_column(
            "entrance_code",
            sa.Column("generation_error", sa.String(length=512), nullable=True),
        )


def downgrade():
    if column_exists("entrance_code", "generation_error"):
        op.drop_column("entrance_code", "generation_error")
    if column_exists("entrance_code", "generation_status"):
        op.drop_column("entrance_code", "generation_status")
