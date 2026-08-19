"""Add Plan pricing/sort_order fields, BillingInvoice plan-purchase snapshot
columns, and idempotently seed/backfill the three canonical commercial plans
(FREE / STANDARD / PRO).

Price authority is this table: price_month_cents / price_year_cents are
integer-cents, backend-only, fixed final prices (see
docs/saas-subscription-audit.md Phase F1A). No CHECK constraint is added here
-- PRICE_DB_CHECK_CONSTRAINT=DEFER, since this migration cannot read-only
prove the target MySQL is >= 8.0.16 from inside the migration itself.
Non-negative price validation lives at the application layer instead
(Plan._validate_price_non_negative in app/models/subscription.py).

The pre-existing PRO row (Phase 02, docs/saas-subscription-audit.md) is
UPDATEd in place, never DELETEd+INSERTed: existing Subscription rows may
already reference its id via Subscription.plan_id.

Revision ID: 20260817_0001
Revises: 20260816_0001
Create Date: 2026-08-17
"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa

from app.utils.id_generator import generate_snowflake_id


revision = "20260817_0001"
down_revision = "20260816_0001"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return table_name in sa.inspect(bind).get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    return any(col["name"] == column_name for col in sa.inspect(bind).get_columns(table_name))


# code, name, price_month_cents, price_year_cents, sort_order -- frozen commercial
# contract (Phase F1A). The 14% annual discount implied by price_year_cents is
# display/marketing only; it is never derived at runtime.
PLAN_SEED = (
    ("FREE", "免费版", 0, 0, 0),
    ("STANDARD", "普通版", 5900, 60900, 1),
    ("PRO", "专业版", 9900, 102200, 2),
)


def upgrade():
    if not column_exists("plans", "price_month_cents"):
        op.add_column("plans", sa.Column("price_month_cents", sa.Integer(), nullable=False, server_default="0"))
    if not column_exists("plans", "price_year_cents"):
        op.add_column("plans", sa.Column("price_year_cents", sa.Integer(), nullable=False, server_default="0"))
    if not column_exists("plans", "sort_order"):
        op.add_column("plans", sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))

    if not column_exists("billing_invoices", "plan_code"):
        op.add_column("billing_invoices", sa.Column("plan_code", sa.String(length=32), nullable=True))
    if not column_exists("billing_invoices", "billing_period"):
        op.add_column("billing_invoices", sa.Column("billing_period", sa.String(length=8), nullable=True))

    bind = op.get_bind()
    now = datetime.utcnow()
    for code, name, price_month_cents, price_year_cents, sort_order in PLAN_SEED:
        existing = bind.execute(
            sa.text("SELECT id FROM plans WHERE code = :code"),
            {"code": code},
        ).fetchone()
        params = {
            "code": code,
            "name": name,
            "price_month_cents": price_month_cents,
            "price_year_cents": price_year_cents,
            "sort_order": sort_order,
            "now": now,
        }
        if existing is None:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO plans
                        (id, code, name, is_active, price_month_cents, price_year_cents, sort_order, created_at, updated_at)
                    VALUES
                        (:id, :code, :name, 1, :price_month_cents, :price_year_cents, :sort_order, :now, :now)
                    """
                ),
                {**params, "id": generate_snowflake_id()},
            )
        else:
            bind.execute(
                sa.text(
                    """
                    UPDATE plans
                    SET name = :name,
                        is_active = 1,
                        price_month_cents = :price_month_cents,
                        price_year_cents = :price_year_cents,
                        sort_order = :sort_order,
                        updated_at = :now
                    WHERE code = :code
                    """
                ),
                params,
            )


def downgrade():
    if table_exists("billing_invoices"):
        if column_exists("billing_invoices", "billing_period"):
            op.drop_column("billing_invoices", "billing_period")
        if column_exists("billing_invoices", "plan_code"):
            op.drop_column("billing_invoices", "plan_code")

    if table_exists("plans"):
        if column_exists("plans", "sort_order"):
            op.drop_column("plans", "sort_order")
        if column_exists("plans", "price_year_cents"):
            op.drop_column("plans", "price_year_cents")
        if column_exists("plans", "price_month_cents"):
            op.drop_column("plans", "price_month_cents")
