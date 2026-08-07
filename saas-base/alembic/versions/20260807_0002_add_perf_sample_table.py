"""Add perf_sample table for miniapp performance reporting

Revision ID: 20260807_0002
Revises: 20260807_0001
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa


revision = "20260807_0002"
down_revision = "20260807_0001"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def upgrade():
    if not table_exists("perf_sample"):
        op.create_table(
            "perf_sample",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("metric", sa.String(length=64), nullable=False),
            sa.Column("ms", sa.Integer(), nullable=False),
            sa.Column("meta", sa.Text(), nullable=True),
            sa.Column("client_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_perf_sample_metric", "perf_sample", ["metric"], unique=False)
        op.create_index("ix_perf_sample_tenant_id", "perf_sample", ["tenant_id"], unique=False)
        op.create_index(
            "idx_perf_sample_tenant_created_at",
            "perf_sample",
            ["tenant_id", "created_at"],
            unique=False,
        )


def downgrade():
    if table_exists("perf_sample"):
        op.drop_index("idx_perf_sample_tenant_created_at", table_name="perf_sample")
        op.drop_index("ix_perf_sample_tenant_id", table_name="perf_sample")
        op.drop_index("idx_perf_sample_metric", table_name="perf_sample")
        op.drop_table("perf_sample")
