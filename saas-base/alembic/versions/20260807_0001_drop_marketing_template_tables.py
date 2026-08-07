"""Drop deprecated marketing template tables

The MarketingTemplate/MerchantTemplate auto-coupon engine was disabled and its
admin UI removed; only CouponService rule_type issuance remains in production.

Revision ID: 20260807_0001
Revises: 20260803_0003
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa


revision = "20260807_0001"
down_revision = "20260803_0003"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def upgrade():
    if table_exists("merchant_template_rule"):
        op.drop_index("idx_merchant_template_rule_trigger_type", table_name="merchant_template_rule")
        op.drop_index("idx_merchant_template_rule_status", table_name="merchant_template_rule")
        op.drop_index("idx_merchant_template_rule_merchant_template", table_name="merchant_template_rule")
        op.drop_table("merchant_template_rule")

    if table_exists("merchant_template"):
        op.drop_index("idx_merchant_template_status", table_name="merchant_template")
        op.drop_index("idx_merchant_template_template", table_name="merchant_template")
        op.drop_index("idx_merchant_template_tenant", table_name="merchant_template")
        op.drop_table("merchant_template")

    if table_exists("marketing_template_rule"):
        op.drop_index("idx_marketing_template_rule_status", table_name="marketing_template_rule")
        op.drop_index("idx_marketing_template_rule_template", table_name="marketing_template_rule")
        op.drop_table("marketing_template_rule")

    if table_exists("marketing_template"):
        op.drop_index("idx_marketing_template_status", table_name="marketing_template")
        op.drop_index("idx_marketing_template_code", table_name="marketing_template")
        op.drop_table("marketing_template")


def downgrade():
    if not table_exists("marketing_template"):
        op.create_table(
            "marketing_template",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=True),
            sa.Column("template_code", sa.String(length=32), nullable=False),
            sa.Column("template_name", sa.String(length=64), nullable=False),
            sa.Column("industry", sa.String(length=128), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("target_customer_price_min", sa.DECIMAL(precision=10, scale=2), nullable=True),
            sa.Column("target_customer_price_max", sa.DECIMAL(precision=10, scale=2), nullable=True),
            sa.Column("status", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("template_code"),
        )
        op.create_index("idx_marketing_template_code", "marketing_template", ["template_code"], unique=False)
        op.create_index("idx_marketing_template_status", "marketing_template", ["status"], unique=False)

    if not table_exists("marketing_template_rule"):
        op.create_table(
            "marketing_template_rule",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=True),
            sa.Column("template_id", sa.BigInteger(), nullable=False),
            sa.Column("rule_code", sa.String(length=32), nullable=False),
            sa.Column("rule_name", sa.String(length=64), nullable=False),
            sa.Column("trigger_type", sa.String(length=32), nullable=False),
            sa.Column("coupon_type", sa.String(length=32), nullable=False),
            sa.Column("discount_type", sa.String(length=32), nullable=False),
            sa.Column("threshold_amount", sa.DECIMAL(precision=10, scale=2), nullable=True),
            sa.Column("discount_amount", sa.DECIMAL(precision=10, scale=2), nullable=False),
            sa.Column("valid_days", sa.Integer(), nullable=False),
            sa.Column("trigger_delay_days", sa.Integer(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=True),
            sa.Column("status", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["template_id"], ["marketing_template.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "idx_marketing_template_rule_template",
            "marketing_template_rule",
            ["template_id"],
            unique=False,
        )
        op.create_index(
            "idx_marketing_template_rule_status",
            "marketing_template_rule",
            ["status"],
            unique=False,
        )

    if not table_exists("merchant_template"):
        op.create_table(
            "merchant_template",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=True),
            sa.Column("template_id", sa.BigInteger(), nullable=False),
            sa.Column("status", sa.Integer(), nullable=False),
            sa.Column("enabled_at", sa.DateTime(), nullable=True),
            sa.Column("disabled_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["template_id"], ["marketing_template.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_merchant_template_tenant", "merchant_template", ["tenant_id"], unique=False)
        op.create_index("idx_merchant_template_template", "merchant_template", ["template_id"], unique=False)
        op.create_index("idx_merchant_template_status", "merchant_template", ["status"], unique=False)

    if not table_exists("merchant_template_rule"):
        op.create_table(
            "merchant_template_rule",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=True),
            sa.Column("merchant_template_id", sa.BigInteger(), nullable=False),
            sa.Column("source_template_rule_id", sa.BigInteger(), nullable=True),
            sa.Column("rule_code", sa.String(length=32), nullable=False),
            sa.Column("rule_name", sa.String(length=64), nullable=False),
            sa.Column("trigger_type", sa.String(length=32), nullable=False),
            sa.Column("coupon_id", sa.BigInteger(), nullable=True),
            sa.Column("coupon_template_id", sa.BigInteger(), nullable=True),
            sa.Column("trigger_delay_days", sa.Integer(), nullable=True),
            sa.Column("status", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["coupon_id"], ["coupon.id"]),
            sa.ForeignKeyConstraint(["coupon_template_id"], ["coupon_template.id"]),
            sa.ForeignKeyConstraint(["merchant_template_id"], ["merchant_template.id"]),
            sa.ForeignKeyConstraint(["source_template_rule_id"], ["marketing_template_rule.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "idx_merchant_template_rule_merchant_template",
            "merchant_template_rule",
            ["merchant_template_id"],
            unique=False,
        )
        op.create_index(
            "idx_merchant_template_rule_status",
            "merchant_template_rule",
            ["status"],
            unique=False,
        )
        op.create_index(
            "idx_merchant_template_rule_trigger_type",
            "merchant_template_rule",
            ["trigger_type"],
            unique=False,
        )
