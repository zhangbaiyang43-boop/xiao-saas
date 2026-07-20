"""add verify_code to coupon for short-code display

Revision ID: 20260523_0001
Revises: 20260502_0001
Create Date: 2026-05-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260523_0001"
down_revision = "20260502_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("coupon", sa.Column("verify_code", sa.String(length=8), nullable=True))
    op.create_index("idx_coupon_tenant_verify_code", "coupon", ["tenant_id", "verify_code"])


def downgrade():
    op.drop_index("idx_coupon_tenant_verify_code", table_name="coupon")
    op.drop_column("coupon", "verify_code")
