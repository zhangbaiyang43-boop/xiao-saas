"""Repair entrance_code missing fields and merge three heads

Revision ID: 20260711_0007
Revises: 20260430_0010, 20260505_0001_marketing_template, 20260711_0006
Create Date: 2026-07-11

This migration serves two purposes:
1. Merge three existing heads (20260430_0010, 20260505_0001_marketing_template, 20260711_0006)
   into a single head
2. Idempotently add missing entrance_code fields that were supposed to be added by 20260711_0006
   but were not actually applied to the database (version drift issue)

Downgrade risk: Since this migration is idempotent and cannot distinguish between
columns it added vs columns added by 20260711_0006, the downgrade may drop columns
that were originally added by 0006. Only safe during full environment teardown.
"""
from alembic import op
import sqlalchemy as sa


revision = "20260711_0007"
down_revision = ("20260430_0010", "20260505_0001_marketing_template", "20260711_0006")
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if not column_exists("entrance_code", "entry_type"):
        op.add_column("entrance_code", sa.Column("entry_type", sa.String(16), nullable=False, server_default="table"))

    if not column_exists("entrance_code", "order_mode"):
        op.add_column("entrance_code", sa.Column("order_mode", sa.String(16), nullable=False, server_default="dine_in"))

    if not column_exists("entrance_code", "table_id"):
        op.add_column("entrance_code", sa.Column("table_id", sa.BigInteger(), nullable=True))

    if not column_exists("entrance_code", "target_page"):
        op.add_column("entrance_code", sa.Column("target_page", sa.String(128), nullable=False, server_default="pages/order/index"))


def downgrade():
    if column_exists("entrance_code", "entry_type"):
        op.drop_column("entrance_code", "entry_type")

    if column_exists("entrance_code", "order_mode"):
        op.drop_column("entrance_code", "order_mode")

    if column_exists("entrance_code", "table_id"):
        op.drop_column("entrance_code", "table_id")

    if column_exists("entrance_code", "target_page"):
        op.drop_column("entrance_code", "target_page")
