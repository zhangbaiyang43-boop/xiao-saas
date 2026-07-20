"""Add dining session and participant tables

Revision ID: 20260715_0001
Revises: 20260711_0007
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa


revision = "20260715_0001"
down_revision = "20260711_0007"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return table_name in sa.inspect(bind).get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    indexes = sa.inspect(bind).get_indexes(table_name)
    return any(item["name"] == index_name for item in indexes)


def foreign_key_exists(table_name: str, fk_name: str) -> bool:
    bind = op.get_bind()
    foreign_keys = sa.inspect(bind).get_foreign_keys(table_name)
    return any(item["name"] == fk_name for item in foreign_keys)


def upgrade():
    if not table_exists("dining_sessions"):
        op.create_table(
            "dining_sessions",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("table_no", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="OPEN"),
            sa.Column("active_key", sa.String(length=96), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("last_activity_at", sa.DateTime(), nullable=False),
            sa.Column("closed_at", sa.DateTime(), nullable=True),
            sa.Column("closed_by", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not index_exists("dining_sessions", "ix_dining_sessions_id"):
        op.create_index("ix_dining_sessions_id", "dining_sessions", ["id"])
    if not index_exists("dining_sessions", "ix_dining_sessions_tenant_id"):
        op.create_index("ix_dining_sessions_tenant_id", "dining_sessions", ["tenant_id"])
    if not index_exists("dining_sessions", "ux_dining_session_active_key"):
        op.create_index("ux_dining_session_active_key", "dining_sessions", ["active_key"], unique=True)
    if not index_exists("dining_sessions", "idx_dining_session_tenant_table_status"):
        op.create_index("idx_dining_session_tenant_table_status", "dining_sessions", ["tenant_id", "table_no", "status"])
    if not index_exists("dining_sessions", "idx_dining_session_tenant_table_created"):
        op.create_index("idx_dining_session_tenant_table_created", "dining_sessions", ["tenant_id", "table_no", "created_at"])

    if not table_exists("dining_participants"):
        op.create_table(
            "dining_participants",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("session_id", sa.BigInteger(), nullable=False),
            sa.Column("customer_id", sa.BigInteger(), nullable=True),
            sa.Column("openid", sa.String(length=128), nullable=True),
            sa.Column("guest_token_hash", sa.String(length=128), nullable=True),
            sa.Column("client_id", sa.String(length=64), nullable=True),
            sa.Column("joined_at", sa.DateTime(), nullable=False),
            sa.Column("last_active_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
            sa.ForeignKeyConstraint(["session_id"], ["dining_sessions.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    if not index_exists("dining_participants", "ix_dining_participants_id"):
        op.create_index("ix_dining_participants_id", "dining_participants", ["id"])
    if not index_exists("dining_participants", "ix_dining_participants_tenant_id"):
        op.create_index("ix_dining_participants_tenant_id", "dining_participants", ["tenant_id"])
    if not index_exists("dining_participants", "ix_dining_participants_session_id"):
        op.create_index("ix_dining_participants_session_id", "dining_participants", ["session_id"])
    if not index_exists("dining_participants", "ux_dining_participant_token_hash"):
        op.create_index("ux_dining_participant_token_hash", "dining_participants", ["guest_token_hash"], unique=True)
    if not index_exists("dining_participants", "ux_dining_participant_session_client"):
        op.create_index("ux_dining_participant_session_client", "dining_participants", ["session_id", "client_id"], unique=True)
    if not index_exists("dining_participants", "ux_dining_participant_session_customer"):
        op.create_index("ux_dining_participant_session_customer", "dining_participants", ["session_id", "customer_id"], unique=True)
    if not index_exists("dining_participants", "idx_dining_participant_tenant_session"):
        op.create_index("idx_dining_participant_tenant_session", "dining_participants", ["tenant_id", "session_id"])
    if not index_exists("dining_participants", "idx_dining_participant_tenant_customer"):
        op.create_index("idx_dining_participant_tenant_customer", "dining_participants", ["tenant_id", "customer_id"])

    order_columns = {
        "dining_session_id": sa.Column("dining_session_id", sa.BigInteger(), nullable=True),
        "participant_id": sa.Column("participant_id", sa.BigInteger(), nullable=True),
        "order_type": sa.Column("order_type", sa.String(length=16), nullable=True),
        "parent_order_id": sa.Column("parent_order_id", sa.BigInteger(), nullable=True),
        "served_at": sa.Column("served_at", sa.DateTime(), nullable=True),
        "completed_at": sa.Column("completed_at", sa.DateTime(), nullable=True),
    }
    for name, column in order_columns.items():
        if not column_exists("orders", name):
            op.add_column("orders", column)

    if not foreign_key_exists("orders", "fk_orders_dining_session"):
        op.create_foreign_key("fk_orders_dining_session", "orders", "dining_sessions", ["dining_session_id"], ["id"])
    if not foreign_key_exists("orders", "fk_orders_participant"):
        op.create_foreign_key("fk_orders_participant", "orders", "dining_participants", ["participant_id"], ["id"])
    if not foreign_key_exists("orders", "fk_orders_parent_order"):
        op.create_foreign_key("fk_orders_parent_order", "orders", "orders", ["parent_order_id"], ["id"])
    if not index_exists("orders", "ix_orders_dining_session_id"):
        op.create_index("ix_orders_dining_session_id", "orders", ["dining_session_id"])
    if not index_exists("orders", "ix_orders_participant_id"):
        op.create_index("ix_orders_participant_id", "orders", ["participant_id"])
    if not index_exists("orders", "ix_orders_parent_order_id"):
        op.create_index("ix_orders_parent_order_id", "orders", ["parent_order_id"])
    if not index_exists("orders", "idx_orders_tenant_session"):
        op.create_index("idx_orders_tenant_session", "orders", ["tenant_id", "dining_session_id"])
    if not index_exists("orders", "idx_orders_tenant_participant"):
        op.create_index("idx_orders_tenant_participant", "orders", ["tenant_id", "participant_id"])
    if not index_exists("orders", "idx_orders_tenant_session_status"):
        op.create_index("idx_orders_tenant_session_status", "orders", ["tenant_id", "dining_session_id", "status"])
    if not index_exists("orders", "idx_orders_parent_order"):
        op.create_index("idx_orders_parent_order", "orders", ["parent_order_id"])


def downgrade():
    for fk_name in ("fk_orders_parent_order", "fk_orders_participant", "fk_orders_dining_session"):
        if foreign_key_exists("orders", fk_name):
            op.drop_constraint(fk_name, "orders", type_="foreignkey")
    for index_name in (
        "idx_orders_parent_order",
        "idx_orders_tenant_session_status",
        "idx_orders_tenant_participant",
        "idx_orders_tenant_session",
        "ix_orders_parent_order_id",
        "ix_orders_participant_id",
        "ix_orders_dining_session_id",
    ):
        if index_exists("orders", index_name):
            op.drop_index(index_name, table_name="orders")

    for column_name in ("completed_at", "served_at", "parent_order_id", "order_type", "participant_id", "dining_session_id"):
        if column_exists("orders", column_name):
            op.drop_column("orders", column_name)

    if table_exists("dining_participants"):
        op.drop_table("dining_participants")
    if table_exists("dining_sessions"):
        op.drop_table("dining_sessions")

