"""add wework contact way

Revision ID: 20260430_0010
Revises: 20260430_0009
Create Date: 2026-04-30 16:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260430_0010"
down_revision = "20260430_0009"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def upgrade():
    if table_exists("wework_contact_way"):
        return

    op.create_table(
        "wework_contact_way",
        sa.Column("config_id", sa.String(length=128), nullable=False),
        sa.Column("qr_code", sa.String(length=500), nullable=False),
        sa.Column("userid", sa.String(length=128), nullable=False),
        sa.Column("scene", sa.String(length=128), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("skip_verify", sa.Boolean(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("config_id"),
    )
    op.create_index("ix_wework_contact_way_config_id", "wework_contact_way", ["config_id"])
    op.create_index("ix_wework_contact_way_id", "wework_contact_way", ["id"])
    op.create_index("ix_wework_contact_way_tenant_id", "wework_contact_way", ["tenant_id"])
    op.create_index("idx_wework_contact_way_tenant_created_at", "wework_contact_way", ["tenant_id", "created_at"])
    op.create_index("idx_wework_contact_way_tenant_userid", "wework_contact_way", ["tenant_id", "userid"])


def downgrade():
    if table_exists("wework_contact_way"):
        op.drop_table("wework_contact_way")
