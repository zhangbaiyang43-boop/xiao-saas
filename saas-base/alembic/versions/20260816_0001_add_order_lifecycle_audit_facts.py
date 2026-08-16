"""Add order lifecycle audit facts (terminated_*, settled_by_*).

Revision ID: 20260816_0001
Revises: 20260814_0002
Create Date: 2026-08-16

P0-16 Phase B2: durable WHO/WHEN/HOW facts for order termination
(cancelled/rejected) and settlement, distinct from Order.status (current
business state). Additive only, no FK, no index, no default, no backfill --
matches merchant_account_id style elsewhere (see
20260809_0001_add_order_serve_audit.py / 20260809_0002_add_order_create_actor_audit.py).
Historical rows keep these columns NULL ("unknown legacy audit"), which is a
legitimate, permanent state -- not something this migration backfills.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0001"
down_revision = "20260814_0002"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(col.get("name") == column_name for col in columns)


def upgrade():
    if not column_exists("orders", "terminated_at"):
        op.add_column(
            "orders",
            sa.Column("terminated_at", sa.DateTime(), nullable=True),
        )
    if not column_exists("orders", "terminated_actor_type"):
        op.add_column(
            "orders",
            sa.Column("terminated_actor_type", sa.String(length=32), nullable=True),
        )
    if not column_exists("orders", "terminated_actor_id"):
        op.add_column(
            "orders",
            sa.Column("terminated_actor_id", sa.BigInteger(), nullable=True),
        )
    if not column_exists("orders", "terminated_actor_role"):
        op.add_column(
            "orders",
            sa.Column("terminated_actor_role", sa.String(length=32), nullable=True),
        )
    if not column_exists("orders", "termination_source"):
        op.add_column(
            "orders",
            sa.Column("termination_source", sa.String(length=32), nullable=True),
        )
    if not column_exists("orders", "settled_by_account_id"):
        op.add_column(
            "orders",
            sa.Column("settled_by_account_id", sa.BigInteger(), nullable=True),
        )
    if not column_exists("orders", "settled_by_role"):
        op.add_column(
            "orders",
            sa.Column("settled_by_role", sa.String(length=32), nullable=True),
        )


def downgrade():
    if column_exists("orders", "settled_by_role"):
        op.drop_column("orders", "settled_by_role")
    if column_exists("orders", "settled_by_account_id"):
        op.drop_column("orders", "settled_by_account_id")
    if column_exists("orders", "termination_source"):
        op.drop_column("orders", "termination_source")
    if column_exists("orders", "terminated_actor_role"):
        op.drop_column("orders", "terminated_actor_role")
    if column_exists("orders", "terminated_actor_id"):
        op.drop_column("orders", "terminated_actor_id")
    if column_exists("orders", "terminated_actor_type"):
        op.drop_column("orders", "terminated_actor_type")
    if column_exists("orders", "terminated_at"):
        op.drop_column("orders", "terminated_at")
