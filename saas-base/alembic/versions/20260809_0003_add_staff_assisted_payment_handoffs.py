"""Add staff assisted payment handoff table.

Revision ID: 20260809_0003
Revises: 20260809_0002
Create Date: 2026-08-09
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_0003"
down_revision = "20260809_0002"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return table_name in sa.inspect(bind).get_table_names()


def upgrade():
    if table_exists("staff_assisted_payment_handoffs"):
        return
    op.create_table(
        "staff_assisted_payment_handoffs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by_account_id", sa.BigInteger(), nullable=True),
        sa.Column("created_by_role", sa.String(length=32), nullable=True),
        sa.Column("claimed_customer_id", sa.BigInteger(), nullable=True),
        sa.Column("claimed_openid", sa.String(length=128), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_staff_assisted_payment_handoffs_id", "staff_assisted_payment_handoffs", ["id"], unique=False)
    op.create_index("ix_staff_assisted_payment_handoffs_tenant_id", "staff_assisted_payment_handoffs", ["tenant_id"], unique=False)
    op.create_index("ix_staff_assisted_payment_handoffs_order_id", "staff_assisted_payment_handoffs", ["order_id"], unique=False)
    op.create_index("ix_staff_assisted_payment_handoffs_token_hash", "staff_assisted_payment_handoffs", ["token_hash"], unique=True)
    op.create_index("idx_saph_tenant_order", "staff_assisted_payment_handoffs", ["tenant_id", "order_id"], unique=False)
    op.create_index("idx_saph_tenant_status", "staff_assisted_payment_handoffs", ["tenant_id", "status"], unique=False)


def downgrade():
    if table_exists("staff_assisted_payment_handoffs"):
        op.drop_table("staff_assisted_payment_handoffs")
