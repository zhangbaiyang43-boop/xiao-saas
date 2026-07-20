"""add coupon fields to orders, create order_reviews

Revision ID: 20260614_0002
Revises: 20260614_0001
Create Date: 2026-06-14
"""
from alembic import op
import sqlalchemy as sa

revision = '20260614_0002'
down_revision = '20260614_0001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orders', sa.Column('coupon_id', sa.BigInteger(), nullable=True))
    op.add_column('orders', sa.Column('discount_amount', sa.Numeric(10, 2), nullable=True))

    op.create_table(
        'order_reviews',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.String(32), nullable=False, index=True),
        sa.Column('order_id', sa.BigInteger(), sa.ForeignKey('orders.id'), nullable=False),
        sa.Column('customer_id', sa.BigInteger(), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('order_reviews')
    op.drop_column('orders', 'discount_amount')
    op.drop_column('orders', 'coupon_id')
