"""Phase F1A -- migration regression tests for 20260817_0001
(add_plan_pricing_and_seed_catalog).

Two layers, matching this repo's existing convention split
(test_migration_contracts.py / test_p0_16_b2_migration_schema_smoke.py):

1. Structural checks on the migration source (revision chain, idempotency
   guards, UPDATE-in-place for existing rows, no CHECK constraint).
2. A real functional run of this migration's upgrade() against a scratch
   SQLite DB pre-loaded with the PRE-migration schema/data -- using
   alembic.operations.Operations bound to a plain sync connection, so the
   actual add_column/INSERT/UPDATE statements execute for real (not just a
   fake-op call-log). Full historical `alembic upgrade head` replay from the
   very first revision is NOT exercised here: several earlier, unrelated
   migrations in this chain use MySQL-only DDL (e.g. `ALTER TABLE ...
   ALTER COLUMN ... DROP DEFAULT`) that SQLite's ALTER TABLE dialect cannot
   parse, so a base->head replay is a MySQL-only smoke check
   (scripts/db-upgrade.ps1), not something this suite can run without a
   MySQL instance.
"""

from __future__ import annotations

import importlib.util
import pathlib
import unittest

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "alembic" / "versions" / "20260817_0001_add_plan_pricing_and_seed_catalog.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("f1a_plan_pricing_migration", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PRE_MIGRATION_PLANS_DDL = """
CREATE TABLE plans (
    id BIGINT PRIMARY KEY,
    code VARCHAR(32) NOT NULL UNIQUE,
    name VARCHAR(64) NOT NULL,
    is_active BOOLEAN NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
)
"""

PRE_MIGRATION_SUBSCRIPTIONS_DDL = """
CREATE TABLE subscriptions (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(32) NOT NULL,
    plan_id BIGINT NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
)
"""

PRE_MIGRATION_BILLING_INVOICES_DDL = """
CREATE TABLE billing_invoices (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(32) NOT NULL,
    invoice_no VARCHAR(64) NOT NULL UNIQUE,
    charge_type VARCHAR(32) NOT NULL,
    description VARCHAR(255) NOT NULL,
    amount_cents INTEGER NOT NULL,
    currency VARCHAR(8) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
)
"""

EXISTING_PRO_ID = 700000000000000123


class MigrationStructureTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MIGRATION_PATH.exists())
        self.module = _load_migration()
        self.source = MIGRATION_PATH.read_text(encoding="utf-8-sig")

    def test_revision_chains_onto_certified_head(self):
        self.assertEqual(self.module.down_revision, "20260816_0001")
        self.assertIsNone(self.module.branch_labels)
        self.assertIsNone(self.module.depends_on)

    def test_upgrade_column_adds_are_guarded_by_column_exists(self):
        upgrade_body = self.source.split("def upgrade")[1].split("def downgrade")[0]
        self.assertEqual(upgrade_body.count("add_column"), upgrade_body.count("if not column_exists"))

    def test_existing_row_path_uses_update_never_delete(self):
        upgrade_body = self.source.split("def upgrade")[1].split("def downgrade")[0]
        self.assertIn("UPDATE plans", upgrade_body)
        self.assertNotIn("DELETE FROM plans", upgrade_body)
        self.assertNotIn("DELETE FROM plans".lower(), upgrade_body.lower())

    def test_no_db_check_constraint_added(self):
        # PRICE_DB_CHECK_CONSTRAINT=DEFER -- see the migration's own docstring
        # for why (can't read-only prove MySQL >= 8.0.16 from inside it).
        self.assertNotIn("CheckConstraint", self.source)
        self.assertNotIn("CHECK (", self.source)

    def test_plan_seed_matches_frozen_commercial_contract(self):
        self.assertEqual(
            self.module.PLAN_SEED,
            (
                ("FREE", "免费版", 0, 0, 0),
                ("STANDARD", "普通版", 5900, 60900, 1),
                ("PRO", "专业版", 9900, 102200, 2),
            ),
        )


class MigrationFunctionalUpgradeTest(unittest.TestCase):
    """Runs the real upgrade() against SQLite, pre-loaded with the
    pre-migration schema, via alembic's Operations bound to a sync
    connection -- so `from alembic import op` inside the migration module
    resolves to a real, working op for the duration of the `with` block."""

    def setUp(self):
        self.module = _load_migration()
        self.engine = sa.create_engine("sqlite:///:memory:")

    def tearDown(self):
        self.engine.dispose()

    def _run_upgrade(self, connection):
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            self.module.upgrade()

    def _plans_rows(self, connection):
        rows = connection.execute(
            sa.text(
                "SELECT code, name, price_month_cents, price_year_cents, sort_order, is_active "
                "FROM plans ORDER BY sort_order"
            )
        ).fetchall()
        return {row[0]: tuple(row) for row in rows}

    # ---- A/C: fresh-like DB -> FREE/STANDARD/PRO all created ---------------

    def test_fresh_database_seeds_all_three_plans_with_exact_values(self):
        with self.engine.begin() as connection:
            connection.execute(sa.text(PRE_MIGRATION_PLANS_DDL))
            connection.execute(sa.text(PRE_MIGRATION_BILLING_INVOICES_DDL))
            self._run_upgrade(connection)

            rows = self._plans_rows(connection)
            self.assertEqual(
                rows["FREE"],
                ("FREE", "免费版", 0, 0, 0, 1),
            )
            self.assertEqual(
                rows["STANDARD"],
                ("STANDARD", "普通版", 5900, 60900, 1, 1),
            )
            self.assertEqual(
                rows["PRO"],
                ("PRO", "专业版", 9900, 102200, 2, 1),
            )

    # ---- B: existing-like DB -> PRO id preserved, Subscription.plan_id intact --

    def test_existing_pro_row_is_updated_in_place_id_preserved(self):
        with self.engine.begin() as connection:
            connection.execute(sa.text(PRE_MIGRATION_PLANS_DDL))
            connection.execute(sa.text(PRE_MIGRATION_SUBSCRIPTIONS_DDL))
            connection.execute(sa.text(PRE_MIGRATION_BILLING_INVOICES_DDL))
            connection.execute(
                sa.text(
                    "INSERT INTO plans (id, code, name, is_active, created_at, updated_at) "
                    "VALUES (:id, 'PRO', '专业版', 1, '2026-02-01 00:00:00', '2026-02-01 00:00:00')"
                ),
                {"id": EXISTING_PRO_ID},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO subscriptions (id, tenant_id, plan_id, status, created_at, updated_at) "
                    "VALUES (1, 'tenant-a', :plan_id, 'ACTIVE', '2026-02-01 00:00:00', '2026-02-01 00:00:00')"
                ),
                {"plan_id": EXISTING_PRO_ID},
            )

            self._run_upgrade(connection)

            pro_id = connection.execute(sa.text("SELECT id FROM plans WHERE code = 'PRO'")).scalar()
            self.assertEqual(pro_id, EXISTING_PRO_ID)

            row = self._plans_rows(connection)["PRO"]
            self.assertEqual(row, ("PRO", "专业版", 9900, 102200, 2, 1))

            sub_plan_id = connection.execute(sa.text("SELECT plan_id FROM subscriptions WHERE id = 1")).scalar()
            self.assertEqual(sub_plan_id, EXISTING_PRO_ID)

            plan_count = connection.execute(sa.text("SELECT COUNT(*) FROM plans WHERE code = 'PRO'")).scalar()
            self.assertEqual(plan_count, 1)

    # ---- D: re-running the seed is idempotent -------------------------------

    def test_rerunning_upgrade_is_idempotent_no_duplicates(self):
        with self.engine.begin() as connection:
            connection.execute(sa.text(PRE_MIGRATION_PLANS_DDL))
            connection.execute(sa.text(PRE_MIGRATION_BILLING_INVOICES_DDL))
            self._run_upgrade(connection)
            self._run_upgrade(connection)

            for code in ("FREE", "STANDARD", "PRO"):
                count = connection.execute(
                    sa.text("SELECT COUNT(*) FROM plans WHERE code = :code"), {"code": code}
                ).scalar()
                self.assertEqual(count, 1, f"duplicate {code} row after re-running upgrade()")

            rows = self._plans_rows(connection)
            self.assertEqual(rows["PRO"], ("PRO", "专业版", 9900, 102200, 2, 1))

    # ---- E: pre-existing BillingInvoice rows with NULL plan_code/billing_period --

    def test_legacy_billing_invoice_row_survives_with_null_plan_columns(self):
        with self.engine.begin() as connection:
            connection.execute(sa.text(PRE_MIGRATION_PLANS_DDL))
            connection.execute(sa.text(PRE_MIGRATION_BILLING_INVOICES_DDL))
            connection.execute(
                sa.text(
                    "INSERT INTO billing_invoices "
                    "(id, tenant_id, invoice_no, charge_type, description, amount_cents, currency, "
                    "status, created_at, updated_at) "
                    "VALUES (1, 'tenant-a', 'INV-LEGACY-1', 'AD_HOC', 'legacy charge', 1000, 'CNY', "
                    "'PAID', '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
                )
            )

            self._run_upgrade(connection)

            row = connection.execute(
                sa.text(
                    "SELECT invoice_no, amount_cents, plan_code, billing_period "
                    "FROM billing_invoices WHERE id = 1"
                )
            ).fetchone()
            self.assertEqual(row[0], "INV-LEGACY-1")
            self.assertEqual(row[1], 1000)
            self.assertIsNone(row[2])
            self.assertIsNone(row[3])


if __name__ == "__main__":
    unittest.main()
