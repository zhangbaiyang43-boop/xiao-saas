"""Add coupon_template_id to merchant_template_rule

The existing coupon_id column is FK'd to coupon.id (an individual issued
coupon instance, which always requires a customer_id), but the code that
uses it actually needs to reference a CouponTemplate (the reusable
template a rule issues copies of). Adding a separate, correctly-targeted
column instead of repurposing coupon_id, to avoid breaking its existing
FK constraint / any stored data.

Revision ID: 20260721_0001
Revises: 20260720_0002
Create Date: 2026-07-21
"""
from alembic import op
import sqlalchemy as sa


revision = "20260721_0001"
down_revision = "20260720_0002"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if not column_exists("merchant_template_rule", "coupon_template_id"):
        op.add_column(
            "merchant_template_rule",
            sa.Column("coupon_template_id", sa.BigInteger(), nullable=True),
        )
        op.create_foreign_key(
            "fk_merchant_template_rule_coupon_template",
            "merchant_template_rule",
            "coupon_template",
            ["coupon_template_id"],
            ["id"],
        )


def downgrade():
    if column_exists("merchant_template_rule", "coupon_template_id"):
        op.drop_constraint(
            "fk_merchant_template_rule_coupon_template",
            "merchant_template_rule",
            type_="foreignkey",
        )
        op.drop_column("merchant_template_rule", "coupon_template_id")
