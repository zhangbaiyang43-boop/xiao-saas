"""Add merchant_accounts for staff login roles.

Revision ID: 20260808_0003
Revises: 20260808_0002
Create Date: 2026-08-08

Owner accounts remain Tenant SMS login (role=owner in JWT).
Staff accounts live in merchant_accounts with per-tenant unique username.
"""
from alembic import op
import sqlalchemy as sa


revision = "20260808_0003"
down_revision = "20260808_0002"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return table_name in sa.inspect(bind).get_table_names()


def upgrade():
    if table_exists("merchant_accounts"):
        return
    op.create_table(
        "merchant_accounts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "username", name="ux_merchant_account_tenant_username"),
    )
    op.create_index("ix_merchant_accounts_tenant_id", "merchant_accounts", ["tenant_id"])
    op.create_index("ix_merchant_accounts_username", "merchant_accounts", ["username"])
    op.create_index("ix_merchant_accounts_id", "merchant_accounts", ["id"])


def downgrade():
    if not table_exists("merchant_accounts"):
        return
    op.drop_index("ix_merchant_accounts_id", table_name="merchant_accounts")
    op.drop_index("ix_merchant_accounts_username", table_name="merchant_accounts")
    op.drop_index("ix_merchant_accounts_tenant_id", table_name="merchant_accounts")
    op.drop_table("merchant_accounts")
