"""add plugin lifecycle fields

Revision ID: 20260429_0005
Revises: 20260429_0004
Create Date: 2026-04-29 11:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260429_0005"
down_revision = "20260429_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tenant_plugin", sa.Column("lifecycle_status", sa.String(length=32), nullable=True))
    op.add_column("tenant_plugin", sa.Column("version", sa.String(length=32), nullable=True))
    op.add_column("tenant_plugin", sa.Column("config_json", sa.Text(), nullable=True))
    op.add_column("tenant_plugin", sa.Column("last_error", sa.String(length=255), nullable=True))
    op.add_column("tenant_plugin", sa.Column("enabled_at", sa.DateTime(), nullable=True))
    op.add_column("tenant_plugin", sa.Column("disabled_at", sa.DateTime(), nullable=True))
    op.create_index("idx_tenant_plugin_lifecycle", "tenant_plugin", ["tenant_id", "lifecycle_status"], unique=False)
    op.execute("UPDATE tenant_plugin SET lifecycle_status = CASE WHEN status = 1 THEN 'ENABLED' ELSE 'INSTALLED_DISABLED' END")
    op.execute("UPDATE tenant_plugin SET config_json = '{}' WHERE config_json IS NULL")


def downgrade():
    op.drop_index("idx_tenant_plugin_lifecycle", table_name="tenant_plugin")
    op.drop_column("tenant_plugin", "disabled_at")
    op.drop_column("tenant_plugin", "enabled_at")
    op.drop_column("tenant_plugin", "last_error")
    op.drop_column("tenant_plugin", "config_json")
    op.drop_column("tenant_plugin", "version")
    op.drop_column("tenant_plugin", "lifecycle_status")
