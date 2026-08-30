"""Add merchant WeCom binding tables.

Revision ID: 20260830_0001
Revises: 20260824_0001
Create Date: 2026-08-30
"""
from alembic import op
import sqlalchemy as sa


revision = "20260830_0001"
down_revision = "20260824_0001"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def upgrade():
    if not table_exists("merchant_wecom_bindings"):
        op.create_table(
            "merchant_wecom_bindings",
            sa.Column("external_userid", sa.String(length=128), nullable=False),
            sa.Column("wecom_user_id", sa.String(length=128), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("bound_by", sa.String(length=64), nullable=True),
            sa.Column("bound_at", sa.DateTime(), nullable=False),
            sa.Column("unbound_at", sa.DateTime(), nullable=True),
            sa.Column("active_tenant_id_key", sa.String(length=32), nullable=True),
            sa.Column("active_external_userid_key", sa.String(length=128), nullable=True),
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("active_tenant_id_key", name="ux_merchant_wecom_active_tenant"),
            sa.UniqueConstraint("active_external_userid_key", name="ux_merchant_wecom_active_external_userid"),
        )
        op.create_index("ix_merchant_wecom_bindings_id", "merchant_wecom_bindings", ["id"])
        op.create_index("ix_merchant_wecom_bindings_tenant_id", "merchant_wecom_bindings", ["tenant_id"])
        op.create_index("idx_merchant_wecom_tenant_status", "merchant_wecom_bindings", ["tenant_id", "status"])
        op.create_index("idx_merchant_wecom_external_status", "merchant_wecom_bindings", ["external_userid", "status"])

    if not table_exists("merchant_wecom_binding_tokens"):
        op.create_table(
            "merchant_wecom_binding_tokens",
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("external_userid", sa.String(length=128), nullable=False),
            sa.Column("wecom_user_id", sa.String(length=128), nullable=True),
            sa.Column("source_event_id", sa.BigInteger(), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("last_code_requested_at", sa.DateTime(), nullable=True),
            sa.Column("code_request_count", sa.Integer(), nullable=False),
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash", name="ux_merchant_wecom_token_hash"),
        )
        op.create_index("ix_merchant_wecom_binding_tokens_id", "merchant_wecom_binding_tokens", ["id"])
        op.create_index("ix_merchant_wecom_binding_tokens_tenant_id", "merchant_wecom_binding_tokens", ["tenant_id"])
        op.create_index("idx_merchant_wecom_token_source_event", "merchant_wecom_binding_tokens", ["source_event_id"])
        op.create_index("idx_merchant_wecom_token_external", "merchant_wecom_binding_tokens", ["external_userid"])
        op.create_index("idx_merchant_wecom_token_expires", "merchant_wecom_binding_tokens", ["expires_at"])


def downgrade():
    if table_exists("merchant_wecom_binding_tokens"):
        op.drop_table("merchant_wecom_binding_tokens")
    if table_exists("merchant_wecom_bindings"):
        op.drop_table("merchant_wecom_bindings")
