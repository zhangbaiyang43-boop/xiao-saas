"""F1G-AF3 -- migration regression tests for 20260818_0001
(schema_convergence_missing_orm_columns).

Same two-layer convention as test_migration_bridge_missing_operational_tables.py
and test_plan_pricing_migration.py: structural checks on the migration
source, plus a real functional run of upgrade()/downgrade() against SQLite
via alembic's Operations bound to a sync connection.
"""

from __future__ import annotations

import importlib.util
import pathlib
import unittest

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "alembic" / "versions" / "20260818_0001_schema_convergence_missing_orm_columns.py"

ALL_13_COLUMNS = {
    "tenant": ["is_open", "wx_pay_enabled", "wx_mchid", "wx_api_key_v3", "wx_cert_serial",
               "wx_private_key", "feieyun_sn", "feieyun_key"],
    "customer": ["inviter_id", "inviter_parent_id"],
    "coupon_template": ["description"],
    "entrance_code": ["table_no"],
    "member_account": ["balance"],
}

# Deliberately NOT part of this migration -- see F1G-AF3's explicit scope decision.
DEFERRED_P2 = {
    "channel_entry": [],  # FK addition deferred, no column change here
    "customer_operation_log": [],  # index addition deferred, no column change here
}


def _load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PRE_MIGRATION_DDL = {
    "tenant": """CREATE TABLE tenant (
        id BIGINT PRIMARY KEY, tenant_id VARCHAR(32) NOT NULL, name VARCHAR(64) NOT NULL,
        password_hash VARCHAR(128) NOT NULL, status BOOLEAN, payment_mode VARCHAR(32) NOT NULL,
        created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
    )""",
    "customer": """CREATE TABLE customer (
        id BIGINT PRIMARY KEY, tenant_id VARCHAR(32) NOT NULL, openid VARCHAR(64) NOT NULL,
        inviter_type VARCHAR(16), status INTEGER NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
    )""",
    "coupon_template": """CREATE TABLE coupon_template (
        id BIGINT PRIMARY KEY, tenant_id VARCHAR(32) NOT NULL, name VARCHAR(64) NOT NULL,
        type VARCHAR(16) NOT NULL, value DECIMAL(10,2) NOT NULL,
        created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
    )""",
    "entrance_code": """CREATE TABLE entrance_code (
        id BIGINT PRIMARY KEY, tenant_id VARCHAR(32) NOT NULL, name VARCHAR(64) NOT NULL,
        scene VARCHAR(32) NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
    )""",
    "member_account": """CREATE TABLE member_account (
        id BIGINT PRIMARY KEY, tenant_id VARCHAR(32) NOT NULL, customer_id BIGINT NOT NULL,
        member_id VARCHAR(64) NOT NULL, level_code VARCHAR(16) NOT NULL, level_name VARCHAR(32) NOT NULL,
        total_consumption DECIMAL(10,2) NOT NULL, yearly_consumption DECIMAL(10,2) NOT NULL,
        points_balance INTEGER NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
    )""",
}


class ConvergenceStructureTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MIGRATION_PATH.exists())
        self.module = _load_module(MIGRATION_PATH, "f1gaf3_convergence_migration")
        self.source = MIGRATION_PATH.read_text(encoding="utf-8-sig")

    def test_revision_metadata_is_a_single_new_head(self):
        self.assertEqual(self.module.revision, "20260818_0001")
        self.assertEqual(self.module.down_revision, "20260817_0001")
        self.assertIsNone(self.module.branch_labels)
        self.assertIsNone(self.module.depends_on)

    def test_historical_migrations_are_untouched(self):
        bridge_path = ROOT / "alembic" / "versions" / "20260613_9000_bridge_missing_operational_tables.py"
        repointed_path = ROOT / "alembic" / "versions" / "20260614_0001_add_merchant_note_to_orders.py"
        bridge = _load_module(bridge_path, "f1gaf3_check_bridge")
        repointed = _load_module(repointed_path, "f1gaf3_check_repointed")
        self.assertEqual(bridge.down_revision, "20260524_0001")
        self.assertEqual(repointed.down_revision, "20260613_9000")

    def test_all_add_column_calls_are_guarded(self):
        upgrade_body = self.source.split("def upgrade")[1].split("def downgrade")[0]
        self.assertEqual(
            upgrade_body.count("op.add_column"),
            upgrade_body.count("if not column_exists("),
        )

    def test_all_13_columns_represented(self):
        upgrade_body = self.source.split("def upgrade")[1].split("def downgrade")[0]
        for table, columns in ALL_13_COLUMNS.items():
            for column in columns:
                self.assertIn(f'"{column}"', upgrade_body, f"{table}.{column} not found in upgrade()")

    def test_no_p2_deferred_changes_present(self):
        upgrade_body = self.source.split("def upgrade")[1].split("def downgrade")[0]
        self.assertNotIn("channel_entry", upgrade_body)
        self.assertNotIn("customer_operation_log", upgrade_body)
        self.assertNotIn("alter_column", upgrade_body)  # no nullability changes
        self.assertNotIn("store_listing", upgrade_body)

    def test_downgrade_is_non_destructive_no_op(self):
        downgrade_body = self.source.split("def downgrade")[1]
        self.assertNotIn("drop_column", downgrade_body)
        self.assertIn("pass", downgrade_body)


class ConvergenceFunctionalTest(unittest.TestCase):
    """Runs the real upgrade()/downgrade() against SQLite via alembic's
    Operations bound to a sync connection."""

    def setUp(self):
        self.module = _load_module(MIGRATION_PATH, "f1gaf3_convergence_functional")
        self.engine = sa.create_engine("sqlite:///:memory:")

    def tearDown(self):
        self.engine.dispose()

    def _run(self, connection, fn):
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            fn()

    def _create_pre_migration_tables(self, connection):
        for ddl in PRE_MIGRATION_DDL.values():
            connection.execute(sa.text(ddl))

    def test_missing_column_added_once(self):
        with self.engine.begin() as connection:
            self._create_pre_migration_tables(connection)
            self._run(connection, self.module.upgrade)
            inspector = sa.inspect(connection)
            for table, columns in ALL_13_COLUMNS.items():
                real_columns = {c["name"] for c in inspector.get_columns(table)}
                for column in columns:
                    self.assertIn(column, real_columns, f"{table}.{column} was not added")

    def test_customer_inviter_index_created(self):
        with self.engine.begin() as connection:
            self._create_pre_migration_tables(connection)
            self._run(connection, self.module.upgrade)
            index_names = {idx["name"] for idx in sa.inspect(connection).get_indexes("customer")}
            self.assertIn("idx_customer_tenant_inviter", index_names)

    def test_existing_column_is_a_true_no_op(self):
        with self.engine.begin() as connection:
            self._create_pre_migration_tables(connection)
            # Simulate a production-like DB where tenant.is_open already exists.
            connection.execute(sa.text("ALTER TABLE tenant ADD COLUMN is_open BOOLEAN"))
            connection.execute(sa.text("INSERT INTO tenant (id, tenant_id, name, password_hash, payment_mode, is_open, created_at, updated_at) "
                                        "VALUES (1, 'sentinel', 'Sentinel Shop', 'x', 'prepay', 1, '2026-01-01', '2026-01-01')"))
            self._run(connection, self.module.upgrade)
            row = connection.execute(sa.text("SELECT tenant_id, is_open FROM tenant WHERE id = 1")).fetchone()
            self.assertEqual(tuple(row), ("sentinel", 1))
            # The other 7 tenant columns and every other table's missing
            # column must still have been added.
            tenant_columns = {c["name"] for c in sa.inspect(connection).get_columns("tenant")}
            self.assertIn("wx_mchid", tenant_columns)
            self.assertIn("feieyun_sn", tenant_columns)

    def test_member_account_balance_not_null_with_server_default_backfills_existing_rows(self):
        with self.engine.begin() as connection:
            self._create_pre_migration_tables(connection)
            connection.execute(sa.text(
                "INSERT INTO member_account (id, tenant_id, customer_id, member_id, level_code, level_name, "
                "total_consumption, yearly_consumption, points_balance, created_at, updated_at) "
                "VALUES (1, 'sentinel', 1, 'M001', 'LV1', 'Normal', 0, 0, 0, '2026-01-01', '2026-01-01')"
            ))
            self._run(connection, self.module.upgrade)
            balance = connection.execute(sa.text("SELECT balance FROM member_account WHERE id = 1")).scalar()
            self.assertEqual(float(balance), 0.0, "existing row must backfill via server_default, not fail or stay NULL")

    def test_rerunning_upgrade_is_idempotent(self):
        with self.engine.begin() as connection:
            self._create_pre_migration_tables(connection)
            self._run(connection, self.module.upgrade)
            self._run(connection, self.module.upgrade)
            tenant_columns = {c["name"] for c in sa.inspect(connection).get_columns("tenant")}
            for column in ALL_13_COLUMNS["tenant"]:
                self.assertIn(column, tenant_columns)

    def test_downgrade_never_drops_any_column(self):
        with self.engine.begin() as connection:
            self._create_pre_migration_tables(connection)
            self._run(connection, self.module.upgrade)
            self._run(connection, self.module.downgrade)
            tenant_columns = {c["name"] for c in sa.inspect(connection).get_columns("tenant")}
            for column in ALL_13_COLUMNS["tenant"]:
                self.assertIn(column, tenant_columns, f"downgrade must not have dropped tenant.{column}")


if __name__ == "__main__":
    unittest.main()
