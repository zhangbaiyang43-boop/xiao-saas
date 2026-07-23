"""Add store_member_no to customer

Adds a per-tenant sequential membership number (1, 2, 3... independent of
the snowflake-generated primary key) so the mini-program can show a real,
short, resume-worthy membership card number instead of the raw internal id.
Backfills existing customers ordered by (tenant_id, created_at, id) so
earlier joiners keep the smaller, more prestigious numbers.

Revision ID: 20260723_0001
Revises: 20260721_0001
Create Date: 2026-07-23
"""
from alembic import op
import sqlalchemy as sa


revision = "20260723_0001"
down_revision = "20260721_0001"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    indexes = sa.inspect(bind).get_indexes(table_name)
    return any(item["name"] == index_name for item in indexes)


def upgrade():
    if not column_exists("customer", "store_member_no"):
        op.add_column(
            "customer",
            sa.Column("store_member_no", sa.Integer(), nullable=True),
        )

    if not index_exists("customer", "idx_customer_tenant_member_no"):
        op.create_index(
            "idx_customer_tenant_member_no",
            "customer",
            ["tenant_id", "store_member_no"],
            unique=True,
        )

    # 存量数据回填：按租户内的真实加入顺序（created_at, id）从 1 开始编号，
    # 保证"号越小越是老会员"这个身份象征是真实的，不是随便分配的。
    bind = op.get_bind()
    customer_table = sa.table(
        "customer",
        sa.column("id", sa.BigInteger),
        sa.column("tenant_id", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("store_member_no", sa.Integer),
    )

    tenant_rows = bind.execute(
        sa.text("SELECT DISTINCT tenant_id FROM customer WHERE store_member_no IS NULL")
    ).fetchall()

    for (tenant_id,) in tenant_rows:
        customer_rows = bind.execute(
            sa.text(
                "SELECT id FROM customer WHERE tenant_id = :tenant_id AND store_member_no IS NULL "
                "ORDER BY created_at ASC, id ASC"
            ),
            {"tenant_id": tenant_id},
        ).fetchall()

        for seq, (customer_id,) in enumerate(customer_rows, start=1):
            bind.execute(
                customer_table.update()
                .where(customer_table.c.id == customer_id)
                .values(store_member_no=seq)
            )


def downgrade():
    if index_exists("customer", "idx_customer_tenant_member_no"):
        op.drop_index("idx_customer_tenant_member_no", table_name="customer")
    if column_exists("customer", "store_member_no"):
        op.drop_column("customer", "store_member_no")
