"""Add missing wxpay public key fields to tenant table (idempotent)

Revision ID: 20260711_0004
Revises: 20260430_0008
Create Date: 2026-07-11

"""
from alembic import op
import sqlalchemy as sa


revision = "20260711_0004"
down_revision = "20260430_0008"
branch_labels = None
depends_on = None


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    columns = sa.inspect(bind).get_columns(table_name)
    return any(item["name"] == column_name for item in columns)


def upgrade():
    if not column_exists("tenant", "wx_public_key_id"):
        op.add_column("tenant", sa.Column("wx_public_key_id", sa.String(128), nullable=True))
    
    if not column_exists("tenant", "wx_public_key"):
        op.add_column("tenant", sa.Column("wx_public_key", sa.String(4096), nullable=True))
    
    if not column_exists("tenant", "wx_verify_mode"):
        op.add_column("tenant", sa.Column("wx_verify_mode", sa.String(32), nullable=False, server_default="public_key"))


def downgrade():
    if column_exists("tenant", "wx_public_key_id"):
        op.drop_column("tenant", "wx_public_key_id")
    
    if column_exists("tenant", "wx_public_key"):
        op.drop_column("tenant", "wx_public_key")
    
    if column_exists("tenant", "wx_verify_mode"):
        op.drop_column("tenant", "wx_verify_mode")
