"""Add BillingPayment manual-review audit fields (F1G-CM Manual Verified
Subscription Payment V1).

Revision ID: 20260819_0001
Revises: 20260818_0001
Create Date: 2026-08-19

V1 SaaS subscription payment is manual-verified: the merchant scans an
official QR code and claims "I have paid"; a platform SuperAdmin then
confirms the funds actually arrived before any Subscription is extended.
`billing_payments.status` remains the one PENDING/PAID/FAILED/... funds
authority shared by every provider (FAKE/WXPAY/MANUAL) -- these five new
columns are purely "where is this in the human review workflow" bookkeeping
for provider="MANUAL" rows, kept separate so status's existing meaning for
every other provider is untouched. NULL manual_review_status means no
claim has been submitted yet (there is no separate "NONE" string).

Tip-appended (down_revision=20260818_0001, the current head): nothing
downstream assumes these columns already exist, and a clean replay already
reaches this revision's parent reliably.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260819_0001"
down_revision = "20260818_0001"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    if not table_exists(table_name):
        return False
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    if not table_exists(table_name):
        return False
    indexes = sa.inspect(bind).get_indexes(table_name)
    return any(item["name"] == index_name for item in indexes)


def upgrade():
    if not column_exists("billing_payments", "manual_review_status"):
        op.add_column("billing_payments", sa.Column("manual_review_status", sa.String(length=32), nullable=True))
    if not index_exists("billing_payments", "ix_billing_payments_manual_review_status"):
        op.create_index(
            "ix_billing_payments_manual_review_status", "billing_payments", ["manual_review_status"]
        )
    if not column_exists("billing_payments", "manual_claimed_at"):
        op.add_column("billing_payments", sa.Column("manual_claimed_at", sa.DateTime(), nullable=True))
    if not column_exists("billing_payments", "manual_reviewed_at"):
        op.add_column("billing_payments", sa.Column("manual_reviewed_at", sa.DateTime(), nullable=True))
    if not column_exists("billing_payments", "manual_reviewed_by"):
        op.add_column("billing_payments", sa.Column("manual_reviewed_by", sa.String(length=64), nullable=True))
    if not column_exists("billing_payments", "manual_review_note"):
        op.add_column("billing_payments", sa.Column("manual_review_note", sa.String(length=255), nullable=True))


def downgrade():
    # Non-destructive no-op, matching every prior convergence/bridge
    # migration's policy in this chain: this migration cannot distinguish
    # "added by this migration" from a hypothetical pre-existing value, and
    # these columns hold real audit-trail data (who reviewed a real
    # merchant's payment, when) that must never be silently dropped.
    pass
