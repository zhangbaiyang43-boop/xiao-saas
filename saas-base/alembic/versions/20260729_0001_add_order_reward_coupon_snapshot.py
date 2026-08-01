"""add reward_coupon_snapshot to orders so the async wxpay reward (first/second-order
coupon) can be handed back to the client on the next status poll instead of only
existing inside the wxpay webhook that the miniapp never sees

Revision ID: 20260729_0001
Revises: 20260728_0001
Create Date: 2026-07-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_0001"
down_revision = "20260728_0001"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if not column_exists("orders", "reward_coupon_snapshot"):
        op.add_column("orders", sa.Column("reward_coupon_snapshot", sa.Text(), nullable=True))


def downgrade():
    if column_exists("orders", "reward_coupon_snapshot"):
        op.drop_column("orders", "reward_coupon_snapshot")
