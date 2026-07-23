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


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def upgrade():
    if not column_exists('orders', 'coupon_id'):
        op.add_column('orders', sa.Column('coupon_id', sa.BigInteger(), nullable=True))
    if not column_exists('orders', 'discount_amount'):
        op.add_column('orders', sa.Column('discount_amount', sa.Numeric(10, 2), nullable=True))

    if not table_exists('order_reviews'):
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
    if table_exists('order_reviews'):
        op.drop_table('order_reviews')
    if column_exists('orders', 'discount_amount'):
        op.drop_column('orders', 'discount_amount')
    if column_exists('orders', 'coupon_id'):
        op.drop_column('orders', 'coupon_id')
