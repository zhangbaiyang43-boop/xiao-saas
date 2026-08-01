"""Add zone_type to entrance_code

桌码分区：给"桌贴码"标记简餐区(quick)/正餐区(full)，下单时按这张桌码的分区
自动决定 payment_mode（先付款/桌台账单），不用整店只能配一种收款模式。
留空 = 跟随店铺整体的 payment_mode，完全向后兼容老商户/老桌码。

Revision ID: 20260801_0001
Revises: 20260730_0003
Create Date: 2026-08-01
"""
from alembic import op
import sqlalchemy as sa


revision = "20260801_0001"
down_revision = "20260730_0003"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if not column_exists("entrance_code", "zone_type"):
        op.add_column(
            "entrance_code",
            sa.Column("zone_type", sa.String(length=16), nullable=True),
        )


def downgrade():
    if column_exists("entrance_code", "zone_type"):
        op.drop_column("entrance_code", "zone_type")
