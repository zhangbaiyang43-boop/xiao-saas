"""add client_request_id to orders for create-order idempotency

Order creation had no request/idempotency key at all: a double-tap submit or a
client retry after a network timeout (the request actually succeeded server-side,
but the response was lost) would create two fully independent orders. For
postpay/table_account tenants this immediately prints two real kitchen tickets and
double-counts the table's running bill, with no payment step in between to catch it.

Revision ID: 20260730_0002
Revises: 20260730_0001
Create Date: 2026-07-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260730_0002"
down_revision = "20260730_0001"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    indexes = sa.inspect(bind).get_indexes(table_name)
    return any(item["name"] == index_name for item in indexes)


def upgrade():
    if not column_exists("orders", "client_request_id"):
        op.add_column("orders", sa.Column("client_request_id", sa.String(64), nullable=True))
    if not index_exists("orders", "ux_orders_tenant_client_request_id"):
        op.create_index(
            "ux_orders_tenant_client_request_id",
            "orders",
            ["tenant_id", "client_request_id"],
            unique=True,
        )


def downgrade():
    if index_exists("orders", "ux_orders_tenant_client_request_id"):
        op.drop_index("ux_orders_tenant_client_request_id", table_name="orders")
    if column_exists("orders", "client_request_id"):
        op.drop_column("orders", "client_request_id")
