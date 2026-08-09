"""Add independent SaaS billing invoice and payment tables.

Revision ID: 20260809_0004
Revises: 20260809_0003
Create Date: 2026-08-09
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_0004"
down_revision = "20260809_0003"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return table_name in sa.inspect(bind).get_table_names()


def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    return any(index["name"] == index_name for index in sa.inspect(bind).get_indexes(table_name))


def upgrade():
    if not table_exists("billing_invoices"):
        op.create_table(
            "billing_invoices",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("invoice_no", sa.String(length=64), nullable=False),
            sa.Column("charge_type", sa.String(length=32), nullable=False),
            sa.Column("description", sa.String(length=255), nullable=False),
            sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(length=8), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column("paid_at", sa.DateTime(), nullable=True),
            sa.Column("expired_at", sa.DateTime(), nullable=True),
            sa.Column("success_processed_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("invoice_no", name="ux_billing_invoice_no"),
        )
        op.create_index("ix_billing_invoices_id", "billing_invoices", ["id"], unique=False)
        op.create_index("ix_billing_invoices_tenant_id", "billing_invoices", ["tenant_id"], unique=False)
        op.create_index("idx_billing_invoice_tenant_status", "billing_invoices", ["tenant_id", "status"], unique=False)
        op.create_index("idx_billing_invoice_tenant_created", "billing_invoices", ["tenant_id", "created_at"], unique=False)

    if not table_exists("billing_payments"):
        op.create_table(
            "billing_payments",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("invoice_id", sa.BigInteger(), nullable=False),
            sa.Column("payment_no", sa.String(length=64), nullable=False),
            sa.Column("out_trade_no", sa.String(length=64), nullable=False),
            sa.Column("provider", sa.String(length=32), nullable=False),
            sa.Column("provider_mchid", sa.String(length=64), nullable=True),
            sa.Column("provider_appid", sa.String(length=64), nullable=True),
            sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(length=8), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("transaction_id", sa.String(length=128), nullable=True),
            sa.Column("paid_at", sa.DateTime(), nullable=True),
            sa.Column("anomaly_reason", sa.String(length=64), nullable=True),
            sa.Column("provider_metadata", sa.JSON(), nullable=True),
            sa.Column("failure_reason", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["invoice_id"], ["billing_invoices.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("payment_no", name="ux_billing_payment_no"),
            sa.UniqueConstraint("out_trade_no", name="ux_billing_payment_out_trade_no"),
            sa.UniqueConstraint("transaction_id", name="ux_billing_payment_transaction_id"),
        )
        op.create_index("ix_billing_payments_id", "billing_payments", ["id"], unique=False)
        op.create_index("ix_billing_payments_tenant_id", "billing_payments", ["tenant_id"], unique=False)
        op.create_index("ix_billing_payments_invoice_id", "billing_payments", ["invoice_id"], unique=False)
        op.create_index("idx_billing_payment_tenant_status", "billing_payments", ["tenant_id", "status"], unique=False)
        op.create_index("idx_billing_payment_tenant_invoice", "billing_payments", ["tenant_id", "invoice_id"], unique=False)


def downgrade():
    if table_exists("billing_payments"):
        if index_exists("billing_payments", "idx_billing_payment_tenant_invoice"):
            op.drop_index("idx_billing_payment_tenant_invoice", table_name="billing_payments")
        if index_exists("billing_payments", "idx_billing_payment_tenant_status"):
            op.drop_index("idx_billing_payment_tenant_status", table_name="billing_payments")
        op.drop_table("billing_payments")
    if table_exists("billing_invoices"):
        if index_exists("billing_invoices", "idx_billing_invoice_tenant_created"):
            op.drop_index("idx_billing_invoice_tenant_created", table_name="billing_invoices")
        if index_exists("billing_invoices", "idx_billing_invoice_tenant_status"):
            op.drop_index("idx_billing_invoice_tenant_status", table_name="billing_invoices")
        op.drop_table("billing_invoices")
