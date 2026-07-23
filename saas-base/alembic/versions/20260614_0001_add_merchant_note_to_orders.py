"""add merchant_note to orders

Revision ID: 20260614_0001
Revises: 20260524_0001
Create Date: 2026-06-14
"""
from alembic import op
import sqlalchemy as sa

revision = '20260614_0001'
down_revision = '20260524_0001'
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if not column_exists('orders', 'merchant_note'):
        op.add_column('orders', sa.Column('merchant_note', sa.Text(), nullable=True))


def downgrade():
    if column_exists('orders', 'merchant_note'):
        op.drop_column('orders', 'merchant_note')
