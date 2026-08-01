"""Add staff referral commission support

员工推荐佣金：新建 staff 表（极简，员工不需要登录，只挂一个专属推荐码），
customer 表加 inviter_type 区分"邀请人是顾客还是员工"，commission_record
表加 receiver_type 区分"这笔账要发券给顾客，还是记一笔待发放的现金给员工"。
老数据两个新字段都是 NULL，代码里按 NULL/'customer' 当成"顾客"处理，
完全向后兼容。

Revision ID: 20260802_0001
Revises: 20260801_0001
Create Date: 2026-08-02
"""
from alembic import op
import sqlalchemy as sa


revision = "20260802_0001"
down_revision = "20260801_0001"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if not table_exists("staff"):
        op.create_table(
            "staff",
            sa.Column("id", sa.BigInteger, primary_key=True),
            sa.Column("tenant_id", sa.String(length=32), nullable=False, index=True),
            sa.Column("name", sa.String(length=64), nullable=False),
            sa.Column("invite_code", sa.String(length=8), nullable=True),
            sa.Column("status", sa.Integer, nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime, nullable=False),
            sa.Column("updated_at", sa.DateTime, nullable=False),
        )
        op.create_index("idx_staff_tenant_status", "staff", ["tenant_id", "status"])
        op.create_index("idx_staff_tenant_invite_code", "staff", ["tenant_id", "invite_code"])

    if not column_exists("customer", "inviter_type"):
        op.add_column(
            "customer",
            sa.Column("inviter_type", sa.String(length=16), nullable=True),
        )

    if not column_exists("commission_record", "receiver_type"):
        op.add_column(
            "commission_record",
            sa.Column("receiver_type", sa.String(length=16), nullable=True),
        )


def downgrade():
    if column_exists("commission_record", "receiver_type"):
        op.drop_column("commission_record", "receiver_type")
    if column_exists("customer", "inviter_type"):
        op.drop_column("customer", "inviter_type")
    if table_exists("staff"):
        op.drop_index("idx_staff_tenant_invite_code", table_name="staff")
        op.drop_index("idx_staff_tenant_status", table_name="staff")
        op.drop_table("staff")
