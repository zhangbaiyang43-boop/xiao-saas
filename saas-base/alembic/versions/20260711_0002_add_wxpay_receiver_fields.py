"""add wxpay receiver verification fields

Revision ID: 20260711_0002
Revises: 20260614_0001
Create Date: 2026-07-11 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "20260711_0002"
down_revision = "20260711_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tenant", sa.Column("receiver_name", sa.String(length=128), nullable=True))
    op.add_column("tenant", sa.Column("receiver_type", sa.String(length=32), nullable=True))
    op.add_column("tenant", sa.Column("receiver_verified", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("tenant", sa.Column("payment_locked", sa.Boolean(), nullable=False, server_default=sa.text("1")))
    op.add_column("tenant", sa.Column("verified_time", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("tenant", "verified_time")
    op.drop_column("tenant", "payment_locked")
    op.drop_column("tenant", "receiver_verified")
    op.drop_column("tenant", "receiver_type")
    op.drop_column("tenant", "receiver_name")
