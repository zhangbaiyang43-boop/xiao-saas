"""add coupon verify operation fields

Revision ID: 20260429_0004
Revises: 20260429_0003
Create Date: 2026-04-29 10:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260429_0004"
down_revision = "20260429_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("coupon", sa.Column("revoke_time", sa.DateTime(), nullable=True))
    op.add_column("coupon", sa.Column("revoke_reason", sa.String(length=255), nullable=True))
    op.add_column("coupon", sa.Column("abnormal_reason", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("coupon", "abnormal_reason")
    op.drop_column("coupon", "revoke_reason")
    op.drop_column("coupon", "revoke_time")
