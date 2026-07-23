"""channel_entry table

Revision ID: 20260502_0001
Revises: 20260501_0009
Create Date: 2026-05-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260502_0001"
down_revision = "20260501_0009"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def upgrade():
    if not table_exists("channel_entry"):
        op.create_table(
            "channel_entry",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("name", sa.String(length=64), nullable=False),
            sa.Column("channel_code", sa.String(length=32), nullable=False),
            sa.Column("landing_title", sa.String(length=128), nullable=True),
            sa.Column("landing_subtitle", sa.String(length=256), nullable=True),
            sa.Column("cover_image", sa.String(length=512), nullable=True),
            sa.Column("coupon_template_id", sa.BigInteger(), nullable=True),
            sa.Column("mini_program_qrcode_url", sa.String(length=512), nullable=True),
            sa.Column("h5_url", sa.String(length=512), nullable=True),
            sa.Column("qrcode_url", sa.String(length=512), nullable=True),
            sa.Column("status", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("visit_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("scan_count", sa.Integer(), nullable=False, server_default="0"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("h5_url"),
        )
        op.create_index("idx_channel_entry_tenant_status", "channel_entry", ["tenant_id", "status"])
        op.create_index("idx_channel_entry_tenant_channel", "channel_entry", ["tenant_id", "channel_code"])
        op.create_index("idx_channel_entry_tenant_created", "channel_entry", ["tenant_id", "created_at"])
        op.create_index("idx_channel_entry_h5_url", "channel_entry", ["h5_url"], unique=True)

    if not table_exists("channel_entry_visit_log"):
        op.create_table(
            "channel_entry_visit_log",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("entry_id", sa.BigInteger(), nullable=False),
            sa.Column("channel_code", sa.String(length=32), nullable=False),
            sa.Column("user_agent", sa.String(length=1024), nullable=True),
            sa.Column("referer", sa.String(length=2048), nullable=True),
            sa.Column("ip", sa.String(length=64), nullable=True),
            sa.Column("query_params", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["entry_id"], ["channel_entry.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_channel_visit_tenant_entry", "channel_entry_visit_log", ["tenant_id", "entry_id"])
        op.create_index("idx_channel_visit_tenant_created", "channel_entry_visit_log", ["tenant_id", "created_at"])


def downgrade():
    op.drop_table("channel_entry_visit_log")
    op.drop_table("channel_entry")