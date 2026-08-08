"""Add pickup_no_assignments lease table for active desk tags.

Revision ID: 20260808_0002
Revises: 20260808_0001
Create Date: 2026-08-08
"""
from alembic import op
import sqlalchemy as sa


revision = "20260808_0002"
down_revision = "20260808_0001"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return table_name in sa.inspect(bind).get_table_names()


def upgrade():
    if table_exists("pickup_no_assignments"):
        return
    op.create_table(
        "pickup_no_assignments",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("pickup_no", sa.String(length=16), nullable=False),
        sa.Column("dining_session_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["dining_session_id"], ["dining_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "pickup_no", name="ux_pickup_no_assignment_tenant_no"),
        sa.UniqueConstraint("dining_session_id", name="ux_pickup_no_assignment_session"),
    )
    op.create_index(
        "idx_pickup_no_assignment_tenant",
        "pickup_no_assignments",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_pickup_no_assignments_dining_session_id",
        "pickup_no_assignments",
        ["dining_session_id"],
        unique=False,
    )
    op.create_index(
        "ix_pickup_no_assignments_id",
        "pickup_no_assignments",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_pickup_no_assignments_tenant_id",
        "pickup_no_assignments",
        ["tenant_id"],
        unique=False,
    )


def downgrade():
    if not table_exists("pickup_no_assignments"):
        return
    op.drop_index("ix_pickup_no_assignments_tenant_id", table_name="pickup_no_assignments")
    op.drop_index("ix_pickup_no_assignments_id", table_name="pickup_no_assignments")
    op.drop_index("ix_pickup_no_assignments_dining_session_id", table_name="pickup_no_assignments")
    op.drop_index("idx_pickup_no_assignment_tenant", table_name="pickup_no_assignments")
    op.drop_table("pickup_no_assignments")
