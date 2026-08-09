"""Add channel revenue share foundation.

Revision ID: 20260809_0005
Revises: 20260809_0004
Create Date: 2026-08-09
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_0005"
down_revision = "20260809_0004"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    if not table_exists(table_name):
        return False
    return any(col["name"] == column_name for col in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade():
    if table_exists("billing_invoices"):
        if not column_exists("billing_invoices", "commission_eligible"):
            op.add_column(
                "billing_invoices",
                sa.Column("commission_eligible", sa.Boolean(), nullable=False, server_default=sa.false()),
            )
        if not column_exists("billing_invoices", "commission_policy_version"):
            op.add_column(
                "billing_invoices",
                sa.Column("commission_policy_version", sa.String(length=64), nullable=False, server_default="PRE_CHANNEL"),
            )

    if not table_exists("channel_partners"):
        op.create_table(
            "channel_partners",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("partner_code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("mobile", sa.String(length=32), nullable=False),
            sa.Column("partner_type", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("partner_code", name="ux_channel_partner_code"),
        )
        op.create_index("ix_channel_partners_id", "channel_partners", ["id"])
        op.create_index("idx_channel_partner_status", "channel_partners", ["status"])
        op.create_index("idx_channel_partner_mobile", "channel_partners", ["mobile"])

    if not table_exists("channel_lead_mobile_locks"):
        op.create_table(
            "channel_lead_mobile_locks",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("merchant_mobile_normalized", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("merchant_mobile_normalized", name="ux_channel_lead_mobile_lock"),
        )
        op.create_index("ix_channel_lead_mobile_locks_id", "channel_lead_mobile_locks", ["id"])

    if not table_exists("channel_leads"):
        op.create_table(
            "channel_leads",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("partner_id", sa.BigInteger(), nullable=False),
            sa.Column("merchant_name", sa.String(length=128), nullable=False),
            sa.Column("merchant_mobile", sa.String(length=32), nullable=False),
            sa.Column("merchant_mobile_normalized", sa.String(length=32), nullable=False),
            sa.Column("contact_name", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("protected_at", sa.DateTime(), nullable=False),
            sa.Column("protected_until", sa.DateTime(), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=True),
            sa.Column("converted_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["partner_id"], ["channel_partners.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_channel_leads_id", "channel_leads", ["id"])
        op.create_index("idx_channel_lead_partner_status", "channel_leads", ["partner_id", "status"])
        op.create_index("idx_channel_lead_mobile_status", "channel_leads", ["merchant_mobile_normalized", "status", "protected_until"])
        op.create_index("idx_channel_lead_tenant", "channel_leads", ["tenant_id"])

    if not table_exists("channel_partner_tenant_bindings"):
        op.create_table(
            "channel_partner_tenant_bindings",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("partner_id", sa.BigInteger(), nullable=False),
            sa.Column("source_lead_id", sa.BigInteger(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("commission_rate_bps", sa.Integer(), nullable=False),
            sa.Column("commission_term_months", sa.Integer(), nullable=False),
            sa.Column("commission_started_at", sa.DateTime(), nullable=True),
            sa.Column("commission_ends_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["partner_id"], ["channel_partners.id"]),
            sa.ForeignKeyConstraint(["source_lead_id"], ["channel_leads.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", name="ux_channel_binding_tenant"),
        )
        op.create_index("ix_channel_partner_tenant_bindings_id", "channel_partner_tenant_bindings", ["id"])
        op.create_index("idx_channel_binding_partner_status", "channel_partner_tenant_bindings", ["partner_id", "status"])
        op.create_index("idx_channel_binding_tenant_status", "channel_partner_tenant_bindings", ["tenant_id", "status"])

    if not table_exists("channel_commission_ledger"):
        op.create_table(
            "channel_commission_ledger",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("partner_id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("binding_id", sa.BigInteger(), nullable=False),
            sa.Column("billing_invoice_id", sa.BigInteger(), nullable=True),
            sa.Column("billing_payment_id", sa.BigInteger(), nullable=True),
            sa.Column("entry_type", sa.String(length=32), nullable=False),
            sa.Column("source_event_type", sa.String(length=64), nullable=False),
            sa.Column("source_event_id", sa.String(length=128), nullable=False),
            sa.Column("base_amount_cents", sa.Integer(), nullable=False),
            sa.Column("commission_rate_bps", sa.Integer(), nullable=False),
            sa.Column("commission_amount_cents", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("earned_at", sa.DateTime(), nullable=False),
            sa.Column("available_at", sa.DateTime(), nullable=False),
            sa.Column("source_ledger_id", sa.BigInteger(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["partner_id"], ["channel_partners.id"]),
            sa.ForeignKeyConstraint(["binding_id"], ["channel_partner_tenant_bindings.id"]),
            sa.ForeignKeyConstraint(["billing_invoice_id"], ["billing_invoices.id"]),
            sa.ForeignKeyConstraint(["billing_payment_id"], ["billing_payments.id"]),
            sa.ForeignKeyConstraint(["source_ledger_id"], ["channel_commission_ledger.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source_event_type", "source_event_id", name="ux_channel_ledger_source_event"),
        )
        op.create_index("ix_channel_commission_ledger_id", "channel_commission_ledger", ["id"])
        op.create_index("idx_channel_ledger_partner_status", "channel_commission_ledger", ["partner_id", "status"])
        op.create_index("idx_channel_ledger_tenant", "channel_commission_ledger", ["tenant_id"])
        op.create_index("idx_channel_ledger_binding", "channel_commission_ledger", ["binding_id"])
        op.create_index("idx_channel_ledger_payment", "channel_commission_ledger", ["billing_payment_id"])
        op.create_index("idx_channel_ledger_available", "channel_commission_ledger", ["status", "available_at"])

    if not table_exists("channel_commission_settlements"):
        op.create_table(
            "channel_commission_settlements",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("partner_id", sa.BigInteger(), nullable=False),
            sa.Column("settlement_no", sa.String(length=64), nullable=False),
            sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("period_start", sa.DateTime(), nullable=True),
            sa.Column("period_end", sa.DateTime(), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("settled_at", sa.DateTime(), nullable=True),
            sa.Column("operator", sa.String(length=64), nullable=False),
            sa.Column("transaction_reference", sa.String(length=128), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["partner_id"], ["channel_partners.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("settlement_no", name="ux_channel_settlement_no"),
        )
        op.create_index("ix_channel_commission_settlements_id", "channel_commission_settlements", ["id"])
        op.create_index("idx_channel_settlement_partner_status", "channel_commission_settlements", ["partner_id", "status"])

    if not table_exists("channel_commission_settlement_items"):
        op.create_table(
            "channel_commission_settlement_items",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("settlement_id", sa.BigInteger(), nullable=False),
            sa.Column("ledger_id", sa.BigInteger(), nullable=False),
            sa.Column("partner_id", sa.BigInteger(), nullable=False),
            sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["settlement_id"], ["channel_commission_settlements.id"]),
            sa.ForeignKeyConstraint(["ledger_id"], ["channel_commission_ledger.id"]),
            sa.ForeignKeyConstraint(["partner_id"], ["channel_partners.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("ledger_id", name="ux_channel_settlement_item_ledger"),
        )
        op.create_index("ix_channel_commission_settlement_items_id", "channel_commission_settlement_items", ["id"])
        op.create_index("idx_channel_settlement_item_settlement", "channel_commission_settlement_items", ["settlement_id"])
        op.create_index("idx_channel_settlement_item_partner", "channel_commission_settlement_items", ["partner_id"])


def downgrade():
    for table_name in [
        "channel_commission_settlement_items",
        "channel_commission_settlements",
        "channel_commission_ledger",
        "channel_partner_tenant_bindings",
        "channel_leads",
        "channel_lead_mobile_locks",
        "channel_partners",
    ]:
        if table_exists(table_name):
            op.drop_table(table_name)
    if table_exists("billing_invoices"):
        if column_exists("billing_invoices", "commission_policy_version"):
            op.drop_column("billing_invoices", "commission_policy_version")
        if column_exists("billing_invoices", "commission_eligible"):
            op.drop_column("billing_invoices", "commission_eligible")
