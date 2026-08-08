"""Staff WeChat bindings + trusted devices; nullable staff password.

Revision ID: 20260808_0004
Revises: 20260808_0003
Create Date: 2026-08-08

Authentication V2: WeChat bind + trusted device refresh.
Authorization still merchant_account → role → permission.
"""
from alembic import op
import sqlalchemy as sa


revision = "20260808_0004"
down_revision = "20260808_0003"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return table_name in sa.inspect(bind).get_table_names()


def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    indexes = sa.inspect(bind).get_indexes(table_name)
    return any(idx.get("name") == index_name for idx in indexes)


def column_nullable(table_name: str, column_name: str) -> bool | None:
    bind = op.get_bind()
    for col in sa.inspect(bind).get_columns(table_name):
        if col["name"] == column_name:
            return bool(col.get("nullable"))
    return None


def upgrade():
    if table_exists("merchant_accounts"):
        if column_nullable("merchant_accounts", "username") is False:
            op.alter_column(
                "merchant_accounts",
                "username",
                existing_type=sa.String(length=64),
                nullable=True,
            )
        if column_nullable("merchant_accounts", "password_hash") is False:
            op.alter_column(
                "merchant_accounts",
                "password_hash",
                existing_type=sa.String(length=128),
                nullable=True,
            )

    if not table_exists("merchant_account_wechat_bindings"):
        op.create_table(
            "merchant_account_wechat_bindings",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("merchant_account_id", sa.BigInteger(), nullable=False),
            sa.Column("wechat_app_id", sa.String(length=64), nullable=False),
            sa.Column("openid", sa.String(length=128), nullable=False),
            sa.Column("unionid", sa.String(length=128), nullable=True),
            sa.Column("bound_at", sa.DateTime(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_ma_wx_bind_tenant_id",
            "merchant_account_wechat_bindings",
            ["tenant_id"],
        )
        op.create_index(
            "ix_ma_wx_bind_account_id",
            "merchant_account_wechat_bindings",
            ["merchant_account_id"],
        )
        op.create_index(
            "ix_ma_wx_bind_app_openid",
            "merchant_account_wechat_bindings",
            ["wechat_app_id", "openid"],
        )
        # One active binding per (account, app). Enforced in service;
        # composite unique on active rows is approximated by app-level revoke.

    if not table_exists("merchant_account_trusted_devices"):
        op.create_table(
            "merchant_account_trusted_devices",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("merchant_account_id", sa.BigInteger(), nullable=False),
            sa.Column("device_id", sa.String(length=64), nullable=False),
            sa.Column("device_secret_hash", sa.String(length=128), nullable=False),
            sa.Column("device_name", sa.String(length=64), nullable=True),
            sa.Column("user_agent_summary", sa.String(length=128), nullable=True),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("device_id", name="ux_ma_trusted_device_id"),
        )
        op.create_index(
            "ix_ma_trusted_device_tenant_id",
            "merchant_account_trusted_devices",
            ["tenant_id"],
        )
        op.create_index(
            "ix_ma_trusted_device_account_id",
            "merchant_account_trusted_devices",
            ["merchant_account_id"],
        )


def downgrade():
    if table_exists("merchant_account_trusted_devices"):
        op.drop_table("merchant_account_trusted_devices")
    if table_exists("merchant_account_wechat_bindings"):
        op.drop_table("merchant_account_wechat_bindings")
    if table_exists("merchant_accounts"):
        # Do not force NOT NULL if existing NULL rows exist.
        pass
