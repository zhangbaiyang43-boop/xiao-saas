"""Add (tenant_id, created_at) index for merchant historical order queries.

Revision ID: 20260824_0001
Revises: 20260820_0001
Create Date: 2026-08-24
"""
from alembic import op
import sqlalchemy as sa


revision = "20260824_0001"
down_revision = "20260820_0001"
branch_labels = None
depends_on = None


def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    indexes = sa.inspect(bind).get_indexes(table_name)
    return any(item["name"] == index_name for item in indexes)


def upgrade():
    if not index_exists("orders", "idx_orders_tenant_created_at"):
        op.create_index("idx_orders_tenant_created_at", "orders", ["tenant_id", "created_at"])


def downgrade():
    if index_exists("orders", "idx_orders_tenant_created_at"):
        op.drop_index("idx_orders_tenant_created_at", table_name="orders")
