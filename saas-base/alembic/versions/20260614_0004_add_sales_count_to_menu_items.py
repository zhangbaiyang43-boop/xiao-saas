"""add sales_count to menu_items

Revision ID: 20260614_0004
Revises: 20260614_0003
Create Date: 2026-06-14
"""
from alembic import op
import sqlalchemy as sa

revision = '20260614_0004'
down_revision = '20260614_0003'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('menu_items', sa.Column('sales_count', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('menu_items', 'sales_count')
