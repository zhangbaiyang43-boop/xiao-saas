"""Add pickup_no to dining_sessions

牌子发一次管整桌，不是每单一个，详见 app/models/dining.py 里 pickup_no 字段上的注释。

Revision ID: 20260803_0003
Revises: 20260803_0002
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa


revision = "20260803_0003"
down_revision = "20260803_0002"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if not column_exists("dining_sessions", "pickup_no"):
        op.add_column(
            "dining_sessions",
            sa.Column("pickup_no", sa.String(16), nullable=True),
        )


def downgrade():
    if column_exists("dining_sessions", "pickup_no"):
        op.drop_column("dining_sessions", "pickup_no")
