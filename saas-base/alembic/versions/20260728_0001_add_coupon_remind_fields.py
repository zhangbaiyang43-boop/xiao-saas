"""add remind_requested/remind_sent_at to coupon for expiry-reminder push

Revision ID: 20260728_0001
Revises: 20260727_0001
Create Date: 2026-07-28 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260728_0001"
down_revision = "20260727_0001"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if not column_exists("coupon", "remind_requested"):
        op.add_column(
            "coupon",
            sa.Column("remind_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if not column_exists("coupon", "remind_sent_at"):
        op.add_column("coupon", sa.Column("remind_sent_at", sa.DateTime(), nullable=True))


def downgrade():
    if column_exists("coupon", "remind_sent_at"):
        op.drop_column("coupon", "remind_sent_at")
    if column_exists("coupon", "remind_requested"):
        op.drop_column("coupon", "remind_requested")
