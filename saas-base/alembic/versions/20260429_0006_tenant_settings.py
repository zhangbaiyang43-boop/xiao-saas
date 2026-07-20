"""add tenant settings config fields

Revision ID: 20260429_0006
Revises: 20260429_0005
Create Date: 2026-04-29 12:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260429_0006"
down_revision = "20260429_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tenant_config", sa.Column("coupon_rules", sa.JSON(), nullable=True))
    op.add_column("tenant_config", sa.Column("business_info", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("tenant_config", "business_info")
    op.drop_column("tenant_config", "coupon_rules")
