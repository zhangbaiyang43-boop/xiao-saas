"""membership core

Revision ID: 20260429_0003
Revises: 20260429_0002
Create Date: 2026-04-29

"""
from alembic import op
import sqlalchemy as sa


revision = "20260429_0003"
down_revision = "20260429_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "member_account",
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("member_id", sa.String(length=64), nullable=False),
        sa.Column("level_code", sa.String(length=16), nullable=False),
        sa.Column("level_name", sa.String(length=32), nullable=False),
        sa.Column("total_consumption", sa.DECIMAL(precision=10, scale=2), nullable=False),
        sa.Column("yearly_consumption", sa.DECIMAL(precision=10, scale=2), nullable=False),
        sa.Column("points_balance", sa.Integer(), nullable=False),
        sa.Column("last_consume_time", sa.DateTime(), nullable=True),
        sa.Column("level_checked_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_member_account_tenant_customer", "member_account", ["tenant_id", "customer_id"], unique=True)
    op.create_index("idx_member_account_tenant_level", "member_account", ["tenant_id", "level_code"], unique=False)
    op.create_index("idx_member_account_tenant_member", "member_account", ["tenant_id", "member_id"], unique=True)
    op.create_index(op.f("ix_member_account_id"), "member_account", ["id"], unique=False)
    op.create_index(op.f("ix_member_account_tenant_id"), "member_account", ["tenant_id"], unique=False)

    op.create_table(
        "point_ledger",
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("member_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("source_channel", sa.String(length=32), nullable=False),
        sa.Column("ref_id", sa.String(length=64), nullable=True),
        sa.Column("expire_at", sa.DateTime(), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_point_ledger_tenant_created_at", "point_ledger", ["tenant_id", "created_at"], unique=False)
    op.create_index("idx_point_ledger_tenant_customer", "point_ledger", ["tenant_id", "customer_id"], unique=False)
    op.create_index("idx_point_ledger_tenant_expire", "point_ledger", ["tenant_id", "expire_at"], unique=False)
    op.create_index("idx_point_ledger_tenant_member", "point_ledger", ["tenant_id", "member_id"], unique=False)
    op.create_index(op.f("ix_point_ledger_id"), "point_ledger", ["id"], unique=False)
    op.create_index(op.f("ix_point_ledger_tenant_id"), "point_ledger", ["tenant_id"], unique=False)

    op.create_table(
        "benefit_template",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("level_code", sa.String(length=16), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("value", sa.DECIMAL(precision=10, scale=2), nullable=False),
        sa.Column("condition", sa.String(length=128), nullable=True),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("expire_at", sa.DateTime(), nullable=True),
        sa.Column("cycle", sa.String(length=32), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_benefit_template_tenant_channel", "benefit_template", ["tenant_id", "channel"], unique=False)
    op.create_index("idx_benefit_template_tenant_level", "benefit_template", ["tenant_id", "level_code"], unique=False)
    op.create_index("idx_benefit_template_tenant_status", "benefit_template", ["tenant_id", "status"], unique=False)
    op.create_index(op.f("ix_benefit_template_id"), "benefit_template", ["id"], unique=False)
    op.create_index(op.f("ix_benefit_template_tenant_id"), "benefit_template", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_table("benefit_template")
    op.drop_table("point_ledger")
    op.drop_table("member_account")
