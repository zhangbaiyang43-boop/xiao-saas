"""Add order_items.item_remark; widen order_items.name to VARCHAR(255).

P0-02 snapshot closure: OrderItem.name becomes a pure server-canonical
dish+spec+addon description (see app/api/v1/orders.py
_validate_create_order_items_and_compute_total); per-item user free-text
remarks move into their own column instead of being folded into name.
spec/addon option names and counts are not length- or count-constrained
anywhere in the current schema/API (menu.py's spec_groups payload is an
unconstrained list), so a fixed bound on the combined canonical name could
not be proven from existing code -- widening avoids silently forcing the
new server-side name-composition logic to truncate a legitimate
dish+spec+addon description that no longer fits VARCHAR(64).

Purely additive: no backfill, no rewrite of historical order_items.name
values (widening a VARCHAR column does not alter stored data), no index on
item_remark, no change to any other table.

Revision ID: 20260813_0001
Revises: 20260811_0001
Create Date: 2026-08-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20260813_0001"
down_revision = "20260811_0001"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(col.get("name") == column_name for col in columns)


def upgrade():
    if not column_exists("order_items", "item_remark"):
        op.add_column(
            "order_items",
            sa.Column("item_remark", sa.String(length=255), nullable=True),
        )
    op.alter_column(
        "order_items",
        "name",
        type_=sa.String(length=255),
        existing_type=sa.String(length=64),
        nullable=False,
    )


def downgrade():
    op.alter_column(
        "order_items",
        "name",
        type_=sa.String(length=64),
        existing_type=sa.String(length=255),
        nullable=False,
    )
    if column_exists("order_items", "item_remark"):
        op.drop_column("order_items", "item_remark")
