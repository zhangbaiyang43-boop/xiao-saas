"""increase user_agent field length

Revision ID: 20260501_0009
Revises: 20260430_0008
Create Date: 2026-05-01 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260501_0009"
down_revision = "20260430_0008"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "entrance_scan_log",
        "user_agent",
        type_=sa.String(length=1024),
        existing_type=sa.String(length=255),
        nullable=True,
    )


def downgrade():
    op.alter_column(
        "entrance_scan_log",
        "user_agent",
        type_=sa.String(length=255),
        existing_type=sa.String(length=1024),
        nullable=True,
    )