"""initial core schema

Revision ID: 20260429_0001
Revises:
Create Date: 2026-04-29

"""
from alembic import op
import sqlalchemy as sa


revision = "20260429_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=128), nullable=False),
        sa.Column("corp_id", sa.String(length=64), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("logo_url", sa.String(length=500), nullable=True),
        sa.Column("status", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id"),
    )
    op.create_index(op.f("ix_tenant_id"), "tenant", ["id"], unique=False)
    op.create_index(op.f("ix_tenant_tenant_id"), "tenant", ["tenant_id"], unique=False)

    op.create_table(
        "customer",
        sa.Column("openid", sa.String(length=64), nullable=False),
        sa.Column("external_userid", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("last_consume_time", sa.DateTime(), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_customer_tenant_created_at", "customer", ["tenant_id", "created_at"], unique=False)
    op.create_index("idx_customer_tenant_openid", "customer", ["tenant_id", "openid"], unique=True)
    op.create_index("idx_customer_tenant_phone", "customer", ["tenant_id", "phone"], unique=False)
    op.create_index(op.f("ix_customer_id"), "customer", ["id"], unique=False)
    op.create_index(op.f("ix_customer_tenant_id"), "customer", ["tenant_id"], unique=False)

    op.create_table(
        "coupon_template",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("value", sa.DECIMAL(precision=10, scale=2), nullable=False),
        sa.Column("min_amount", sa.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column("total_stock", sa.Integer(), nullable=True),
        sa.Column("used_stock", sa.Integer(), nullable=True),
        sa.Column("start_time", sa.DateTime(), nullable=False),
        sa.Column("end_time", sa.DateTime(), nullable=False),
        sa.Column("status", sa.Integer(), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_coupon_template_tenant_created_at", "coupon_template", ["tenant_id", "created_at"], unique=False)
    op.create_index("idx_coupon_template_tenant_status", "coupon_template", ["tenant_id", "status"], unique=False)
    op.create_index(op.f("ix_coupon_template_id"), "coupon_template", ["id"], unique=False)
    op.create_index(op.f("ix_coupon_template_tenant_id"), "coupon_template", ["tenant_id"], unique=False)

    op.create_table(
        "tenant_config",
        sa.Column("member_rules", sa.JSON(), nullable=False),
        sa.Column("plugin_settings", sa.JSON(), nullable=False),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tenant_config_id"), "tenant_config", ["id"], unique=False)
    op.create_index(op.f("ix_tenant_config_tenant_id"), "tenant_config", ["tenant_id"], unique=False)

    op.create_table(
        "tenant_plugin",
        sa.Column("plugin_code", sa.String(length=64), nullable=False),
        sa.Column("status", sa.Integer(), nullable=True),
        sa.Column("installed_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_tenant_plugin_status", "tenant_plugin", ["tenant_id", "status"], unique=False)
    op.create_index("idx_tenant_plugin_unique", "tenant_plugin", ["tenant_id", "plugin_code"], unique=True)
    op.create_index(op.f("ix_tenant_plugin_id"), "tenant_plugin", ["id"], unique=False)
    op.create_index(op.f("ix_tenant_plugin_tenant_id"), "tenant_plugin", ["tenant_id"], unique=False)

    op.create_table(
        "consumption",
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("project", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.DECIMAL(precision=10, scale=2), nullable=False),
        sa.Column("consume_time", sa.DateTime(), nullable=False),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_consumption_customer_time", "consumption", ["customer_id", "consume_time"], unique=False)
    op.create_index("idx_consumption_tenant_created_at", "consumption", ["tenant_id", "created_at"], unique=False)
    op.create_index("idx_consumption_tenant_customer_time", "consumption", ["tenant_id", "customer_id", "consume_time"], unique=False)
    op.create_index(op.f("ix_consumption_id"), "consumption", ["id"], unique=False)
    op.create_index(op.f("ix_consumption_tenant_id"), "consumption", ["tenant_id"], unique=False)

    op.create_table(
        "coupon",
        sa.Column("template_id", sa.BigInteger(), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=True),
        sa.Column("use_time", sa.DateTime(), nullable=True),
        sa.Column("expire_time", sa.DateTime(), nullable=False),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["coupon_template.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("idx_coupon_code", "coupon", ["code"], unique=False)
    op.create_index("idx_coupon_customer", "coupon", ["customer_id"], unique=False)
    op.create_index("idx_coupon_tenant_created_at", "coupon", ["tenant_id", "created_at"], unique=False)
    op.create_index("idx_coupon_tenant_customer", "coupon", ["tenant_id", "customer_id"], unique=False)
    op.create_index("idx_coupon_tenant_status", "coupon", ["tenant_id", "status"], unique=False)
    op.create_index(op.f("ix_coupon_id"), "coupon", ["id"], unique=False)
    op.create_index(op.f("ix_coupon_tenant_id"), "coupon", ["tenant_id"], unique=False)

    op.create_table(
        "customer_identity",
        sa.Column("customer_id", sa.BigInteger(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("channel_user_id", sa.String(length=128), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("unionid", sa.String(length=128), nullable=True),
        sa.Column("bind_time", sa.DateTime(), nullable=False),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_customer_identity_channel", "customer_identity", ["tenant_id", "channel", "channel_user_id"], unique=True)
    op.create_index("idx_customer_identity_customer", "customer_identity", ["tenant_id", "customer_id"], unique=False)
    op.create_index("idx_customer_identity_phone", "customer_identity", ["tenant_id", "phone"], unique=False)
    op.create_index(op.f("ix_customer_identity_id"), "customer_identity", ["id"], unique=False)
    op.create_index(op.f("ix_customer_identity_tenant_id"), "customer_identity", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_table("customer_identity")
    op.drop_table("coupon")
    op.drop_table("consumption")
    op.drop_table("tenant_plugin")
    op.drop_table("tenant_config")
    op.drop_table("coupon_template")
    op.drop_table("customer")
    op.drop_table("tenant")
