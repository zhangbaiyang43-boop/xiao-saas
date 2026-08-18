"""Historical bootstrap repair: create orders, order_items, menu_items,
commission_record, customer_operation_log.

Revision ID: 20260613_9000
Revises: 20260524_0001
Create Date: 2026-08-19

F1G-AF0/AF1D forensic audit: a true, isolated MySQL 8 "empty DB -> alembic
upgrade head" replay (F1G-A) failed at 20260614_0001, because `orders`
(and, once the chain kept walking, order_items/menu_items/commission_record/
customer_operation_log) were never created by any migration -- every later
touch is an ALTER assuming the table already exists. That assumption was
always true against the one real deployment (which got these tables from a
pre-Alembic create_all/manual-SQL era, per MIGRATIONS.md's own documented
"already old database joining Alembic" path), so the gap was invisible
until a genuinely fresh bootstrap was tried against real MySQL.

This migration is inserted here, immediately after 20260524_0001 and
immediately before 20260614_0001 (which now points its down_revision at
this revision instead), because 20260614_0001 is the first migration that
assumes `orders` exists. `orders` and `order_items` are deliberately given
their historically-minimal, pre-20260614 column shape -- NOT the current
Base.metadata schema -- because several of the current Order columns
(dining_session_id, participant_id, parent_order_id, ...) are FKs to
dining_sessions/dining_participants, tables that don't exist until
20260715_0001. That migration already adds those columns AND their FK
constraints itself, guarded by the same column_exists()/foreign_key_exists()
pattern used throughout this file -- giving it the full current schema here
would make its own CREATE TABLE fail on real MySQL (FK to a nonexistent
target table), for no benefit, since the later migration already finishes
the job correctly. menu_items, commission_record, and customer_operation_log
have no FK columns and nothing downstream conflicts with them, so those
three are created with their full current schema directly.

table_exists() uses sa.inspect(bind).has_table(), the same safe check this
codebase already uses in 20260614_0002 -- NOT sa.inspect(bind).get_columns(),
which is what raised NoSuchTableError against real MySQL when a table
doesn't exist yet (the exact defect this migration exists to fix).
"""
from alembic import op
import sqlalchemy as sa

revision = "20260613_9000"
down_revision = "20260524_0001"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def upgrade():
    # orders -- historically-minimal shape. merchant_note/coupon_id/
    # discount_amount/dining_session_id/participant_id/order_type/
    # parent_order_id/served_at/completed_at/print_status/printed_at/
    # balance_deduct_requested/refund_status/refund_amount/refund_error/
    # refunded_at/payment_mode/reward_coupon_snapshot/staff_note/
    # client_request_id/pickup_no/served_by_account_id/served_by_role/
    # created_by_account_id/created_by_role/request_fingerprint/
    # wx_transaction_id/terminated_*/termination_source/settled_by_* are all
    # added later by their own already-guarded migrations -- adding them
    # here would be redundant at best and, for the FK columns, DDL-unsafe.
    if not table_exists("orders"):
        op.create_table(
            "orders",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("customer_id", sa.BigInteger(), nullable=True),
            sa.Column("table_no", sa.String(length=32), nullable=False),
            sa.Column("phone", sa.String(length=20), nullable=True),
            sa.Column("total", sa.Numeric(10, 2), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("remark", sa.Text(), nullable=True),
            sa.Column("payment_status", sa.String(length=16), nullable=False),
            sa.Column("payment_method", sa.String(length=16), nullable=True),
            sa.Column("payment_time", sa.String(length=32), nullable=True),
            sa.Column("source", sa.String(length=16), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_orders_id"), "orders", ["id"], unique=False)
        op.create_index(op.f("ix_orders_tenant_id"), "orders", ["tenant_id"], unique=False)

    # order_items -- depends on orders, so it must be created after it.
    # Historically-minimal shape: item_remark is added later by the
    # already-guarded 20260813_0001, which also (unconditionally, but
    # harmlessly) widens `name` to VARCHAR(255) regardless of the width
    # created here.
    if not table_exists("order_items"):
        op.create_table(
            "order_items",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("order_id", sa.BigInteger(), sa.ForeignKey("orders.id"), nullable=False),
            sa.Column("dish_id", sa.BigInteger(), nullable=True),
            sa.Column("name", sa.String(length=64), nullable=False),
            sa.Column("price", sa.Numeric(10, 2), nullable=False),
            sa.Column("qty", sa.Integer(), nullable=False),
        )
        op.create_index(op.f("ix_order_items_order_id"), "order_items", ["order_id"], unique=False)

    # menu_items -- no FK, no downstream conflict: full current schema is safe.
    if not table_exists("menu_items"):
        op.create_table(
            "menu_items",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("name", sa.String(length=64), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("price", sa.Numeric(10, 2), nullable=False),
            sa.Column("category", sa.String(length=32), nullable=True),
            sa.Column("emoji", sa.String(length=8), nullable=True),
            sa.Column("available", sa.Boolean(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("image", sa.String(length=512), nullable=True),
            sa.Column("sales_count", sa.Integer(), nullable=True),
            sa.Column("tags", sa.String(length=256), nullable=True),
            sa.Column("original_price", sa.Numeric(10, 2), nullable=True),
            sa.Column("stock", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_menu_items_id"), "menu_items", ["id"], unique=False)
        op.create_index(op.f("ix_menu_items_tenant_id"), "menu_items", ["tenant_id"], unique=False)

    # commission_record -- no real FK constraint anywhere on this table
    # (user_id/receiver_id/order_id/source_coupon_id are plain columns,
    # matching this codebase's established "no FK, project style"
    # convention) -- full current schema is safe.
    if not table_exists("commission_record"):
        op.create_table(
            "commission_record",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("order_id", sa.String(length=64), nullable=True),
            sa.Column("amount", sa.DECIMAL(precision=10, scale=2), nullable=False),
            sa.Column("level", sa.Integer(), nullable=False),
            sa.Column("receiver_id", sa.BigInteger(), nullable=False),
            sa.Column("receiver_type", sa.String(length=16), nullable=True),
            sa.Column("commission_amount", sa.DECIMAL(precision=10, scale=2), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("source_type", sa.String(length=32), nullable=False),
            sa.Column("source_coupon_id", sa.BigInteger(), nullable=True),
            sa.Column("settled_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "source_coupon_id", "level", name="uq_commission_coupon_level"),
        )
        op.create_index(op.f("ix_commission_record_id"), "commission_record", ["id"], unique=False)
        op.create_index(op.f("ix_commission_record_tenant_id"), "commission_record", ["tenant_id"], unique=False)
        op.create_index("idx_commission_tenant_receiver", "commission_record", ["tenant_id", "receiver_id"], unique=False)
        op.create_index("idx_commission_tenant_user", "commission_record", ["tenant_id", "user_id"], unique=False)
        op.create_index("idx_commission_tenant_status", "commission_record", ["tenant_id", "status"], unique=False)
        op.create_index("idx_commission_tenant_created_at", "commission_record", ["tenant_id", "created_at"], unique=False)

    # customer_operation_log -- never referenced by any other migration at
    # all, so unlike the other four tables there is no later ALTER to rely
    # on; the full current, final application schema must be created here.
    if not table_exists("customer_operation_log"):
        op.create_table(
            "customer_operation_log",
            sa.Column("id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("customer_id", sa.BigInteger(), nullable=True),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("actor_type", sa.String(length=32), nullable=False),
            sa.Column("actor_id", sa.String(length=64), nullable=True),
            sa.Column("actor_name", sa.String(length=64), nullable=True),
            sa.Column("phone", sa.String(length=20), nullable=True),
            sa.Column("openid", sa.String(length=64), nullable=True),
            sa.Column("detail", sa.JSON(), nullable=True),
            sa.Column("ip", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_customer_operation_log_id"), "customer_operation_log", ["id"], unique=False)
        op.create_index(op.f("ix_customer_operation_log_tenant_id"), "customer_operation_log", ["tenant_id"], unique=False)
        op.create_index("idx_customer_log_tenant_customer", "customer_operation_log", ["tenant_id", "customer_id"], unique=False)
        op.create_index("idx_customer_log_tenant_action", "customer_operation_log", ["tenant_id", "action"], unique=False)
        op.create_index("idx_customer_log_tenant_created", "customer_operation_log", ["tenant_id", "created_at"], unique=False)


def downgrade():
    # This historical bootstrap repair intentionally has a non-destructive
    # downgrade because existing deployments may have these tables from the
    # pre-Alembic create_all era. The upgrade() side only ever no-ops via
    # table_exists() against a database that already has these tables, so
    # there is no reliable way to distinguish "created by this migration"
    # from "pre-existed before Alembic" -- a destructive drop here could
    # delete real orders/menu/commission data on any database that reaches
    # this point in a downgrade. Nothing to undo.
    pass
