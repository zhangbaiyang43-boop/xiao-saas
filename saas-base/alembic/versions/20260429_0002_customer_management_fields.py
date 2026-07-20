"""customer management fields

Revision ID: 20260429_0002
Revises: 20260429_0001
Create Date: 2026-04-29

"""
from alembic import op
import sqlalchemy as sa


revision = "20260429_0002"
down_revision = "20260429_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customer", sa.Column("status", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("customer", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index("idx_customer_tenant_status", "customer", ["tenant_id", "status"], unique=False)
    op.alter_column("customer", "status", server_default=None)


def downgrade() -> None:
    op.drop_index("idx_customer_tenant_status", table_name="customer")
    op.drop_column("customer", "deleted_at")
    op.drop_column("customer", "status")
