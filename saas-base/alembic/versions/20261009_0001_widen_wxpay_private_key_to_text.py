"""Converge Tenant WeChat Pay private-key storage to TEXT.

Revision ID: 20261009_0001
Revises: 20260830_0001
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa


revision = "20261009_0001"
down_revision = "20260830_0001"
branch_labels = None
depends_on = None


def _mysql_data_type() -> str | None:
    bind = op.get_bind()
    if bind.dialect.name not in {"mysql", "mariadb"}:
        return None
    return bind.execute(
        sa.text(
            """
            SELECT DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'tenant'
              AND COLUMN_NAME = 'wx_private_key'
            """
        )
    ).scalar()


def upgrade():
    data_type = _mysql_data_type()
    if data_type is None or str(data_type).lower() in {"text", "mediumtext", "longtext"}:
        return
    op.alter_column(
        "tenant",
        "wx_private_key",
        existing_type=sa.String(length=4096),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade():
    data_type = _mysql_data_type()
    if data_type is None or str(data_type).lower() == "varchar":
        return
    bind = op.get_bind()
    longest = int(
        bind.execute(sa.text("SELECT COALESCE(MAX(CHAR_LENGTH(wx_private_key)), 0) FROM tenant")).scalar()
        or 0
    )
    if longest > 4096:
        raise RuntimeError("refusing to narrow tenant.wx_private_key: stored value exceeds 4096 characters")
    op.alter_column(
        "tenant",
        "wx_private_key",
        existing_type=sa.Text(),
        type_=sa.String(length=4096),
        existing_nullable=True,
    )
