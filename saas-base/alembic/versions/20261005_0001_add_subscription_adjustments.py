"""Add append-only subscription adjustment ledger.

Revision ID: 20261005_0001
Revises: 20260830_0001
Create Date: 2026-10-05
"""

from alembic import op
import sqlalchemy as sa


revision = "20261005_0001"
down_revision = "20260830_0001"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade():
    if table_exists("subscription_adjustments"):
        return

    op.create_table(
        "subscription_adjustments",
        sa.Column("subscription_id", sa.BigInteger(), nullable=False),
        sa.Column("plan_code", sa.String(length=32), nullable=False),
        sa.Column("target_field", sa.String(length=32), nullable=False),
        sa.Column("adjustment_type", sa.String(length=32), nullable=False),
        sa.Column("operation_type", sa.String(length=32), nullable=False),
        sa.Column("delta_days", sa.Integer(), nullable=True),
        sa.Column("before_expiry", sa.DateTime(), nullable=False),
        sa.Column("calculation_base_expiry", sa.DateTime(), nullable=False),
        sa.Column("after_expiry", sa.DateTime(), nullable=False),
        sa.Column("before_status", sa.String(length=32), nullable=False),
        sa.Column("after_status", sa.String(length=32), nullable=False),
        sa.Column("stored_subscription_status", sa.String(length=32), nullable=False),
        sa.Column("natural_expiry_recovery", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("operator_type", sa.String(length=32), nullable=False),
        sa.Column("operator_id", sa.String(length=128), nullable=True),
        sa.Column("operator_label", sa.String(length=64), nullable=False),
        sa.Column("operator_ip", sa.String(length=45), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=36), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["subscriptions.id"],
            name="fk_subscription_adjustment_subscription",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="ux_subscription_adjustment_tenant_idempotency",
        ),
    )
    op.create_index("ix_subscription_adjustments_id", "subscription_adjustments", ["id"])
    op.create_index("ix_subscription_adjustments_tenant_id", "subscription_adjustments", ["tenant_id"])
    op.create_index(
        "idx_subscription_adjustment_tenant_created",
        "subscription_adjustments",
        ["tenant_id", "created_at", "id"],
    )
    op.create_index(
        "idx_subscription_adjustment_subscription_created",
        "subscription_adjustments",
        ["subscription_id", "created_at", "id"],
    )


def downgrade():
    # Audit evidence is intentionally retained. Removing it requires a separate,
    # explicitly approved destructive-data migration.
    pass
