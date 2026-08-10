"""Add Plan/Subscription data skeleton (Phase 02 — additive only, no enforcement).

No existing table is altered. No row is inserted into any table. Legacy tenants
end up with zero subscription rows, which is intentional (see
docs/saas-subscription-audit.md Phase 02 §8/§27).

Revision ID: 20260811_0001
Revises: 20260809_0006
Create Date: 2026-08-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260811_0001"
down_revision = "20260809_0006"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return table_name in sa.inspect(bind).get_table_names()


def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    return any(index["name"] == index_name for index in sa.inspect(bind).get_indexes(table_name))


def upgrade():
    if not table_exists("plans"):
        op.create_table(
            "plans",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("code", sa.String(length=32), nullable=False),
            sa.Column("name", sa.String(length=64), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code", name="ux_plan_code"),
        )
        op.create_index("ix_plans_id", "plans", ["id"], unique=False)

    if not table_exists("subscriptions"):
        op.create_table(
            "subscriptions",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("plan_id", sa.BigInteger(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("trial_started_at", sa.DateTime(), nullable=True),
            sa.Column("trial_ends_at", sa.DateTime(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("ends_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["plan_id"], ["plans.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_subscriptions_id", "subscriptions", ["id"], unique=False)
        op.create_index("ix_subscriptions_tenant_id", "subscriptions", ["tenant_id"], unique=False)
        op.create_index("ix_subscriptions_plan_id", "subscriptions", ["plan_id"], unique=False)
        op.create_index("idx_subscription_tenant_status", "subscriptions", ["tenant_id", "status"], unique=False)
        op.create_index("idx_subscription_tenant_created", "subscriptions", ["tenant_id", "created_at"], unique=False)


def downgrade():
    if table_exists("subscriptions"):
        for idx_name in (
            "idx_subscription_tenant_created",
            "idx_subscription_tenant_status",
            "ix_subscriptions_plan_id",
            "ix_subscriptions_tenant_id",
            "ix_subscriptions_id",
        ):
            if index_exists("subscriptions", idx_name):
                op.drop_index(idx_name, table_name="subscriptions")
        op.drop_table("subscriptions")

    if table_exists("plans"):
        if index_exists("plans", "ix_plans_id"):
            op.drop_index("ix_plans_id", table_name="plans")
        op.drop_table("plans")
