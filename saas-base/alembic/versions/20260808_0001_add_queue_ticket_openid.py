"""Add openid/customer_id to queue_tickets for subscribe messages

Revision ID: 20260808_0001
Revises: 20260807_0002
Create Date: 2026-08-08
"""
from alembic import op
import sqlalchemy as sa


revision = "20260808_0001"
down_revision = "20260807_0002"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    return column_name in {c["name"] for c in sa.inspect(bind).get_columns(table_name)}


def upgrade():
    if not sa.inspect(op.get_bind()).has_table("queue_tickets"):
        return
    if not _column_exists("queue_tickets", "openid"):
        op.add_column("queue_tickets", sa.Column("openid", sa.String(length=64), nullable=True))
    if not _column_exists("queue_tickets", "customer_id"):
        op.add_column("queue_tickets", sa.Column("customer_id", sa.BigInteger(), nullable=True))


def downgrade():
    if not sa.inspect(op.get_bind()).has_table("queue_tickets"):
        return
    if _column_exists("queue_tickets", "customer_id"):
        op.drop_column("queue_tickets", "customer_id")
    if _column_exists("queue_tickets", "openid"):
        op.drop_column("queue_tickets", "openid")
