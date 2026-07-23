"""add original_price to menu_items

Revision ID: 20260614_0006
Revises: 20260614_0005
Create Date: 2026-06-14
"""
from alembic import op
import sqlalchemy as sa

revision = '20260614_0006'
down_revision = '20260614_0005'
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if not column_exists('menu_items', 'original_price'):
        op.add_column('menu_items', sa.Column('original_price', sa.Numeric(10, 2), nullable=True))


def downgrade():
    if column_exists('menu_items', 'original_price'):
        op.drop_column('menu_items', 'original_price')
