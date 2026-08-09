"""Add unique normalized mobile for channel partners.

Revision ID: 20260809_0006
Revises: 20260809_0005
Create Date: 2026-08-09
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_0006"
down_revision = "20260809_0005"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    if not table_exists(table_name):
        return False
    return any(col["name"] == column_name for col in sa.inspect(op.get_bind()).get_columns(table_name))


def index_exists(table_name: str, index_name: str) -> bool:
    if not table_exists(table_name):
        return False
    indexes = sa.inspect(op.get_bind()).get_indexes(table_name)
    uniques = sa.inspect(op.get_bind()).get_unique_constraints(table_name)
    return any(item["name"] == index_name for item in indexes + uniques)


def upgrade():
    if not table_exists("channel_partners"):
        return

    bind = op.get_bind()
    dialect = bind.dialect.name
    if not column_exists("channel_partners", "mobile_normalized"):
        op.add_column("channel_partners", sa.Column("mobile_normalized", sa.String(length=32), nullable=True))

    if dialect == "mysql":
        bind.execute(
            sa.text(
                """
                UPDATE channel_partners
                SET mobile_normalized = REGEXP_REPLACE(COALESCE(mobile, ''), '[^0-9]', '')
                WHERE mobile_normalized IS NULL OR mobile_normalized = ''
                """
            )
        )
    else:
        bind.execute(
            sa.text(
                """
                UPDATE channel_partners
                SET mobile_normalized = COALESCE(mobile, '')
                WHERE mobile_normalized IS NULL OR mobile_normalized = ''
                """
            )
        )

    duplicates = bind.execute(
        sa.text(
            """
            SELECT mobile_normalized, COUNT(*) AS cnt
            FROM channel_partners
            GROUP BY mobile_normalized
            HAVING mobile_normalized <> '' AND COUNT(*) > 1
            """
        )
    ).fetchall()
    if duplicates:
        sample = ", ".join(str(row[0]) for row in duplicates[:5])
        raise RuntimeError(f"duplicate channel partner mobile_normalized found: {sample}")

    if dialect == "mysql":
        op.alter_column("channel_partners", "mobile_normalized", existing_type=sa.String(length=32), nullable=False)
    if not index_exists("channel_partners", "ux_channel_partner_mobile_normalized"):
        op.create_unique_constraint(
            "ux_channel_partner_mobile_normalized",
            "channel_partners",
            ["mobile_normalized"],
        )


def downgrade():
    if not table_exists("channel_partners"):
        return
    if index_exists("channel_partners", "ux_channel_partner_mobile_normalized"):
        op.drop_constraint("ux_channel_partner_mobile_normalized", "channel_partners", type_="unique")
    if column_exists("channel_partners", "mobile_normalized"):
        op.drop_column("channel_partners", "mobile_normalized")
