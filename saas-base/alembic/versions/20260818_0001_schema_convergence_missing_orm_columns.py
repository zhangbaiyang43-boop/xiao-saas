"""Schema convergence: add 13 runtime-required ORM columns that were never
added by any migration (F1G-AF2 forensic audit).

Revision ID: 20260818_0001
Revises: 20260817_0001
Create Date: 2026-08-19

F1G-AF2 audited all 45 ORM tables against a real, fully-migrated MySQL 8
database and found 13 columns the current models declare that no
migration -- not even a failed/partial one -- ever references:

  tenant: is_open, wx_pay_enabled, wx_mchid, wx_api_key_v3, wx_cert_serial,
    wx_private_key, feieyun_sn, feieyun_key
  customer: inviter_id, inviter_parent_id
  coupon_template: description
  entrance_code: table_no
  member_account: balance

Same root cause as the orders/order_items/menu_items/commission_record/
customer_operation_log gap 20260613_9000 already fixed: these columns
already existed on the one real deployment (via its pre-Alembic
create_all/manual-SQL era), so no migration author ever needed to write
one. Confirmed via clean MySQL 8 replay that a fresh Tenant/Customer/
CouponTemplate/EntranceCode/MemberAccount ORM insert or select fails
outright with "Unknown column" against a database built purely by
`alembic upgrade head` -- this is the exact failure F1G-B hit trying to
create a test Tenant.

Unlike that earlier gap, no downstream migration assumes any of these 13
columns already exists (grepped alembic/versions/ for every column name:
zero hits anywhere), and a clean `alembic upgrade head` already reaches
this revision's parent (20260817_0001) reliably -- so this is appended at
the current tip rather than inserted as a historical bridge. See F1G-AF2's
audit report for the full methodology and the option analysis that ruled
out a bridge here.

customer.inviter_id also needs the idx_customer_tenant_inviter composite
index the Customer model declares in __table_args__ -- it could never have
been created before since it references the also-missing inviter_id
column.

Deliberately NOT included (see F1G-AF2's DEFERRED_SCHEMA_P2 and F1G-AF3's
explicit scope decision): channel_entry's missing coupon_template_id FK
constraint, customer_operation_log's two missing standalone indexes on
action/customer_id, and the pre-existing tenant/tenant_config nullability
mismatches. None of those block a real ORM INSERT/SELECT the way a
missing column does; bundling them here would blur this migration's single
purpose and its own regression-test story.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260818_0001"
down_revision = "20260817_0001"
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
    # tenant -- all 8 are nullable in the ORM (no server_default needed;
    # MySQL allows adding a nullable column to a non-empty table with no
    # default, existing rows simply read back NULL).
    if not column_exists("tenant", "is_open"):
        op.add_column("tenant", sa.Column("is_open", sa.Boolean(), nullable=True))
    if not column_exists("tenant", "wx_pay_enabled"):
        op.add_column("tenant", sa.Column("wx_pay_enabled", sa.Boolean(), nullable=True))
    if not column_exists("tenant", "wx_mchid"):
        op.add_column("tenant", sa.Column("wx_mchid", sa.String(length=64), nullable=True))
    if not column_exists("tenant", "wx_api_key_v3"):
        op.add_column("tenant", sa.Column("wx_api_key_v3", sa.String(length=256), nullable=True))
    if not column_exists("tenant", "wx_cert_serial"):
        op.add_column("tenant", sa.Column("wx_cert_serial", sa.String(length=128), nullable=True))
    if not column_exists("tenant", "wx_private_key"):
        op.add_column("tenant", sa.Column("wx_private_key", sa.String(length=4096), nullable=True))
    if not column_exists("tenant", "feieyun_sn"):
        op.add_column("tenant", sa.Column("feieyun_sn", sa.String(length=64), nullable=True))
    if not column_exists("tenant", "feieyun_key"):
        op.add_column("tenant", sa.Column("feieyun_key", sa.String(length=64), nullable=True))

    # customer
    if not column_exists("customer", "inviter_id"):
        op.add_column("customer", sa.Column("inviter_id", sa.BigInteger(), nullable=True))
    if not column_exists("customer", "inviter_parent_id"):
        op.add_column("customer", sa.Column("inviter_parent_id", sa.BigInteger(), nullable=True))
    if not index_exists("customer", "idx_customer_tenant_inviter"):
        op.create_index("idx_customer_tenant_inviter", "customer", ["tenant_id", "inviter_id"])

    # coupon_template
    if not column_exists("coupon_template", "description"):
        op.add_column("coupon_template", sa.Column("description", sa.Text(), nullable=True))

    # entrance_code
    if not column_exists("entrance_code", "table_no"):
        op.add_column("entrance_code", sa.Column("table_no", sa.String(length=32), nullable=True))

    # member_account.balance -- the ORM declares this NOT NULL with a
    # Python-side default=0. A NOT NULL column added to a table that may
    # already have rows needs a server_default to backfill them (MySQL
    # rejects ADD COLUMN ... NOT NULL with no default against a non-empty
    # table) -- the same reasoning already applied to print_status/
    # payment_mode elsewhere in this migration chain.
    if not column_exists("member_account", "balance"):
        op.add_column(
            "member_account",
            sa.Column("balance", sa.DECIMAL(precision=10, scale=2), nullable=False, server_default="0"),
        )


def downgrade():
    # Non-destructive no-op, matching 20260613_9000's bridge policy: this
    # migration cannot reliably tell "column was added by this revision"
    # apart from "column pre-existed before Alembic convergence" (the one
    # real deployment already has all 13 from its pre-Alembic create_all
    # era) -- a destructive drop here could delete real tenant WeChat Pay /
    # printer credentials or customer inviter data on any database that
    # reaches this point in a downgrade. Nothing to undo.
    pass
