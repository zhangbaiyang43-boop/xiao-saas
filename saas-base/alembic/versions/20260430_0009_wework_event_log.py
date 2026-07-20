"""add wework event log

Revision ID: 20260430_0009
Revises: 20260430_0008
Create Date: 2026-04-30 15:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260430_0009"
down_revision = "20260430_0008"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def upgrade():
    if table_exists("wework_event_log"):
        return

    op.create_table(
        "wework_event_log",
        sa.Column("external_userid", sa.String(length=128), nullable=True),
        sa.Column("userid", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("change_type", sa.String(length=64), nullable=True),
        sa.Column("state", sa.String(length=128), nullable=True),
        sa.Column("config_id", sa.String(length=128), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_wework_event_tenant_created_at", "wework_event_log", ["tenant_id", "created_at"])
    op.create_index("idx_wework_event_tenant_external", "wework_event_log", ["tenant_id", "external_userid"])
    op.create_index("idx_wework_event_tenant_userid", "wework_event_log", ["tenant_id", "userid"])


def downgrade():
    if table_exists("wework_event_log"):
        op.drop_table("wework_event_log")
