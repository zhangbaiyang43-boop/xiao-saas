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


def upgrade():
    op.add_column('menu_items', sa.Column('original_price', sa.Numeric(10, 2), nullable=True))


def downgrade():
    op.drop_column('menu_items', 'original_price')
