"""add short_invite_code to customer for human-readable invite links

Revision ID: 20260524_0001
Revises: 20260523_0001
Create Date: 2026-05-24 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260524_0001"
down_revision = "20260523_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("customer", sa.Column("short_invite_code", sa.String(length=8), nullable=True))
    op.create_index(
        "idx_customer_tenant_short_invite_code",
        "customer",
        ["tenant_id", "short_invite_code"],
    )


def downgrade():
    op.drop_index("idx_customer_tenant_short_invite_code", table_name="customer")
    op.drop_column("customer", "short_invite_code")
