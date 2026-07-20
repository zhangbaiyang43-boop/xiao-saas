"""add member entrance codes

Revision ID: 20260429_0007
Revises: 20260429_0006
Create Date: 2026-04-29 16:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260429_0007"
down_revision = "20260429_0006"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    indexes = sa.inspect(bind).get_indexes(table_name)
    return any(item["name"] == index_name for item in indexes)


def create_index_if_missing(index_name: str, table_name: str, columns: list[str], unique: bool = False):
    if table_exists(table_name) and not index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def drop_index_if_exists(index_name: str, table_name: str):
    if table_exists(table_name) and index_exists(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade():
    if not table_exists("entrance_code"):
        op.create_table(
            "entrance_code",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("name", sa.String(length=64), nullable=False),
            sa.Column("channel", sa.String(length=32), nullable=False, server_default="STORE"),
            sa.Column("scene", sa.String(length=32), nullable=False),
            sa.Column("page", sa.String(length=128), nullable=False, server_default="pages/entry/index"),
            sa.Column("coupon_template_id", sa.BigInteger(), nullable=True),
            sa.Column("image_url", sa.String(length=255), nullable=True),
            sa.Column("env_version", sa.String(length=16), nullable=False, server_default="trial"),
            sa.Column("code_type", sa.String(length=16), nullable=False, server_default="TEST"),
            sa.Column("status", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("scan_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_scan_time", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["coupon_template_id"], ["coupon_template.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    create_index_if_missing("idx_entrance_code_tenant_scene", "entrance_code", ["tenant_id", "scene"], unique=True)
    create_index_if_missing("idx_entrance_code_tenant_status", "entrance_code", ["tenant_id", "status"])
    create_index_if_missing("idx_entrance_code_tenant_channel", "entrance_code", ["tenant_id", "channel"])
    create_index_if_missing("idx_entrance_code_tenant_created_at", "entrance_code", ["tenant_id", "created_at"])

    if not table_exists("entrance_scan_log"):
        op.create_table(
            "entrance_scan_log",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("entrance_code_id", sa.BigInteger(), nullable=False),
            sa.Column("customer_id", sa.BigInteger(), nullable=True),
            sa.Column("openid", sa.String(length=128), nullable=True),
            sa.Column("scene", sa.String(length=32), nullable=False),
            sa.Column("channel", sa.String(length=32), nullable=False),
            sa.Column("event_type", sa.String(length=32), nullable=False, server_default="SCAN"),
            sa.Column("ip", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
            sa.ForeignKeyConstraint(["entrance_code_id"], ["entrance_code.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    create_index_if_missing("idx_entrance_scan_tenant_code", "entrance_scan_log", ["tenant_id", "entrance_code_id"])
    create_index_if_missing("idx_entrance_scan_tenant_customer", "entrance_scan_log", ["tenant_id", "customer_id"])
    create_index_if_missing("idx_entrance_scan_tenant_created_at", "entrance_scan_log", ["tenant_id", "created_at"])


def downgrade():
    drop_index_if_exists("idx_entrance_scan_tenant_created_at", "entrance_scan_log")
    drop_index_if_exists("idx_entrance_scan_tenant_customer", "entrance_scan_log")
    drop_index_if_exists("idx_entrance_scan_tenant_code", "entrance_scan_log")
    if table_exists("entrance_scan_log"):
        op.drop_table("entrance_scan_log")

    drop_index_if_exists("idx_entrance_code_tenant_created_at", "entrance_code")
    drop_index_if_exists("idx_entrance_code_tenant_channel", "entrance_code")
    drop_index_if_exists("idx_entrance_code_tenant_status", "entrance_code")
    drop_index_if_exists("idx_entrance_code_tenant_scene", "entrance_code")
    if table_exists("entrance_code"):
        op.drop_table("entrance_code")
