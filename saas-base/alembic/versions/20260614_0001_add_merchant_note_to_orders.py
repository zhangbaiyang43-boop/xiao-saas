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


def upgrade():
    op.add_column('orders', sa.Column('merchant_note', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('orders', 'merchant_note')
