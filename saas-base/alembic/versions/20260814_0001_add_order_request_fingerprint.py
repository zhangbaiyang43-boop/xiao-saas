"""Add orders.request_fingerprint (P0-04 idempotency conflict detection).

Audited: OrderItem has no structured specifications/extras columns -- only
dish_id, name (display snapshot), price, qty, item_remark (see P0-02).
Reconstructing original request semantics by reversing OrderItem.name is
explicitly forbidden (it's a display snapshot, not a structured request
envelope; P0-02 already established this). Existing persisted fields cannot
losslessly express whether a client_request_id retry carries the same
business intent as the original submission, so a dedicated column is
required.

request_fingerprint is a SHA-256 hex digest of the *canonical, normalized*
submission semantics (table/session/coupon/order-remark + per-item dish_id/
qty/specifications/extras/item_remark, with specifications and extras sorted
so click/submission order never affects the digest -- see
_compute_request_fingerprint in app/api/v1/orders.py), computed once from the
raw request body at creation time and stored alongside the order. It is NOT
the idempotency identity itself -- (tenant_id, client_request_id) remains the
sole unique-constrained primary identity (unchanged, not touched by this
migration). request_fingerprint only detects when the *same* client_request_id
is reused with a genuinely different business intent, to fail closed instead
of silently replaying stale content.

Purely additive: nullable, no backfill, no rewrite of historical rows (a NULL
fingerprint on a pre-migration order means "legacy replay compatibility" --
existing replay behavior continues unchanged for it, per explicit design),
not part of the existing unique index, no other table touched.

Revision ID: 20260814_0001
Revises: 20260813_0001
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_0001"
down_revision = "20260813_0001"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(col.get("name") == column_name for col in columns)


def upgrade():
    if not column_exists("orders", "request_fingerprint"):
        op.add_column(
            "orders",
            sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
        )


def downgrade():
    if column_exists("orders", "request_fingerprint"):
        op.drop_column("orders", "request_fingerprint")
