"""Make tenant.phone a database-enforced unique identity (Merchant Provisioning
Foundation Phase 01, P0-01).

Prior to this migration, phone uniqueness was enforced only by an
application-level SELECT-then-INSERT pre-check in TenantService/login.py/
super_admin.py -- a classic TOCTOU race: two concurrent requests for the same
phone could both pass the pre-check and both insert, since no DB constraint
backed it up. Login (get_tenant_by_phone -> scalar_one_or_none()) would then
raise MultipleResultsFound for that phone.

Revision ID: 20260820_0001
Revises: 20260819_0002
Create Date: 2026-08-20

SAFETY: this migration refuses to run if it finds any existing duplicate,
non-null phone values -- it will not silently create a broken/unenforceable
index, and it will never delete or merge rows on its own. If it aborts with
DuplicatePhoneDataError, a human must inspect and resolve the conflicting
rows (merge, deactivate, or clear the stale one's phone) before re-running
`alembic upgrade head`.
"""
from alembic import op
import sqlalchemy as sa


revision = "20260820_0001"
down_revision = "20260819_0002"
branch_labels = None
depends_on = None


class DuplicatePhoneDataError(RuntimeError):
    """Raised when pre-migration scanning finds tenant rows that already
    share a phone number -- upgrade() stops here on purpose; this is a data
    conflict for a human to resolve, not something a migration should guess
    at fixing (merging/deleting rows automatically could destroy real
    business data)."""


def index_exists(table_name: str, index_name: str) -> bool:
    return any(
        index.get("name") == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def _find_duplicate_phones(bind) -> list[tuple[str, int]]:
    rows = bind.execute(
        sa.text(
            "SELECT phone, COUNT(*) AS c FROM tenant "
            "WHERE phone IS NOT NULL AND phone != '' "
            "GROUP BY phone HAVING COUNT(*) > 1"
        )
    ).fetchall()
    return [(row[0], row[1]) for row in rows]


def upgrade():
    bind = op.get_bind()

    duplicates = _find_duplicate_phones(bind)
    if duplicates:
        preview = ", ".join(f"{phone!r} x{count}" for phone, count in duplicates[:10])
        more = "" if len(duplicates) <= 10 else f" (+{len(duplicates) - 10} more)"
        raise DuplicatePhoneDataError(
            "Cannot add ux_tenant_phone: tenant.phone already has "
            f"{len(duplicates)} duplicate value(s) in the database: {preview}{more}. "
            "Resolve these rows by hand (merge the duplicate tenants, or clear "
            "the phone on whichever row is stale/wrong) and re-run "
            "`alembic upgrade head` -- this migration will not merge or delete "
            "data on its own."
        )

    if not index_exists("tenant", "ux_tenant_phone"):
        op.create_index("ux_tenant_phone", "tenant", ["phone"], unique=True)


def downgrade():
    if index_exists("tenant", "ux_tenant_phone"):
        op.drop_index("ux_tenant_phone", table_name="tenant")
