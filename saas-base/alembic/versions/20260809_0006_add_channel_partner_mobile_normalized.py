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


def _ops(op_impl=None):
    return op_impl or op


def table_exists(table_name: str, op_impl=None) -> bool:
    operations = _ops(op_impl)
    if hasattr(operations, "table_exists"):
        return operations.table_exists(table_name)
    return table_name in sa.inspect(operations.get_bind()).get_table_names()


def column_exists(table_name: str, column_name: str, op_impl=None) -> bool:
    operations = _ops(op_impl)
    if hasattr(operations, "column_exists"):
        return operations.column_exists(table_name, column_name)
    if not table_exists(table_name, operations):
        return False
    return any(col["name"] == column_name for col in sa.inspect(operations.get_bind()).get_columns(table_name))


def index_exists(table_name: str, index_name: str, op_impl=None) -> bool:
    operations = _ops(op_impl)
    if hasattr(operations, "index_exists"):
        return operations.index_exists(table_name, index_name)
    if not table_exists(table_name, operations):
        return False
    indexes = sa.inspect(operations.get_bind()).get_indexes(table_name)
    uniques = sa.inspect(operations.get_bind()).get_unique_constraints(table_name)
    return any(item["name"] == index_name for item in indexes + uniques)


def normalize_mobile_for_migration(mobile) -> str:
    return "".join(ch for ch in (mobile or "") if ch in "0123456789")


def _row_value(row, key):
    if isinstance(row, dict):
        return row.get(key)
    if hasattr(row, "_mapping"):
        return row._mapping.get(key)
    return getattr(row, key)


def prepare_mobile_normalized_updates(rows):
    updates = []
    owners = {}

    for row in rows:
        row_id = _row_value(row, "id")
        current = _row_value(row, "mobile_normalized")
        normalized = current or normalize_mobile_for_migration(_row_value(row, "mobile"))
        if not normalized:
            raise RuntimeError(f"empty channel partner mobile_normalized found for row id={row_id}")
        if normalized in owners:
            raise RuntimeError(
                "duplicate channel partner mobile_normalized found: "
                f"{normalized} (row ids {owners[normalized]}, {row_id})"
            )
        owners[normalized] = row_id
        if not current:
            updates.append((row_id, normalized))

    return updates


def upgrade(op_impl=None):
    operations = _ops(op_impl)
    if not table_exists("channel_partners", operations):
        return

    bind = operations.get_bind()
    dialect = bind.dialect.name
    if not column_exists("channel_partners", "mobile_normalized", operations):
        operations.add_column("channel_partners", sa.Column("mobile_normalized", sa.String(length=32), nullable=True))

    rows = bind.execute(
        sa.text(
            """
            SELECT id, mobile, mobile_normalized
            FROM channel_partners
            """
        )
    ).fetchall()
    updates = prepare_mobile_normalized_updates(rows)
    for row_id, normalized in updates:
        bind.execute(
            sa.text(
                """
                UPDATE channel_partners
                SET mobile_normalized = :mobile_normalized
                WHERE id = :id
                """
            ),
            {"id": row_id, "mobile_normalized": normalized},
        )

    empty_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(*) AS cnt
            FROM channel_partners
            WHERE mobile_normalized IS NULL OR mobile_normalized = ''
            """
        )
    ).scalar()
    if empty_count:
        raise RuntimeError(f"empty channel partner mobile_normalized rows found: {empty_count}")

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
        operations.alter_column("channel_partners", "mobile_normalized", existing_type=sa.String(length=32), nullable=False)
    if not index_exists("channel_partners", "ux_channel_partner_mobile_normalized", operations):
        operations.create_unique_constraint(
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
