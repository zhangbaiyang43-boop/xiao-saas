"""Add staff_id to entrance_code

员工分享码：一张 entry_type='staff_share' 的入口码，挂在具体某位员工身上，
扫码后跳到员工专属的分享页（subpkg-member/pages/staff-share），而不是点餐页。

Revision ID: 20260803_0001
Revises: 20260802_0001
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa


revision = "20260803_0001"
down_revision = "20260802_0001"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if not column_exists("entrance_code", "staff_id"):
        op.add_column(
            "entrance_code",
            sa.Column("staff_id", sa.BigInteger, nullable=True),
        )


def downgrade():
    if column_exists("entrance_code", "staff_id"):
        op.drop_column("entrance_code", "staff_id")
