"""F1G-AF1 -- migration regression tests for 20260613_9000
(bridge_missing_operational_tables).

Two layers, matching this repo's established convention (see
test_plan_pricing_migration.py):

1. Structural checks on revision chain metadata and on which columns the
   bridge does/does not create for `orders` and `order_items`.
2. A real functional run of the bridge's upgrade()/downgrade() against a
   scratch SQLite DB, via alembic.operations.Operations bound to a plain
   sync connection -- so the actual op.create_table/create_index calls
   execute for real, not just a call-log.

Full historical `alembic upgrade head` MySQL replay is NOT exercised here
(this repo's existing convention explicitly scopes that to a real MySQL
instance -- see F1G-A/F1G-AF1's own required verification list); this file
only proves the bridge migration's own logic in isolation.
"""

from __future__ import annotations

import importlib.util
import pathlib
import unittest

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

ROOT = pathlib.Path(__file__).resolve().parents[1]
BRIDGE_PATH = ROOT / "alembic" / "versions" / "20260613_9000_bridge_missing_operational_tables.py"
REPOINTED_PATH = ROOT / "alembic" / "versions" / "20260614_0001_add_merchant_note_to_orders.py"

# Columns the current app/models/order.py Order model has that must NOT
# appear in the bridge's orders table -- they are added later by their own
# already-guarded migrations (see the bridge's own docstring for the full
# per-column mapping).
FUTURE_ORDERS_COLUMNS = {
    "merchant_note", "coupon_id", "discount_amount",
    "dining_session_id", "participant_id", "order_type", "parent_order_id",
    "served_at", "completed_at", "print_status", "printed_at",
    "balance_deduct_requested", "refund_status", "refund_amount",
    "refund_error", "refunded_at", "payment_mode", "reward_coupon_snapshot",
    "staff_note", "client_request_id", "pickup_no",
    "served_by_account_id", "served_by_role",
    "created_by_account_id", "created_by_role", "request_fingerprint",
    "wx_transaction_id", "terminated_at", "terminated_actor_type",
    "terminated_actor_id", "terminated_actor_role", "termination_source",
    "settled_by_account_id", "settled_by_role",
}

FUTURE_ORDER_ITEMS_COLUMNS = {"item_remark"}

BRIDGE_CREATED_TABLES = (
    "orders", "order_items", "menu_items", "commission_record", "customer_operation_log",
)


def _load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BridgeStructureTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(BRIDGE_PATH.exists())
        self.module = _load_module(BRIDGE_PATH, "f1gaf1_bridge_migration")

    def test_bridge_revision_metadata(self):
        self.assertEqual(self.module.revision, "20260613_9000")
        self.assertEqual(self.module.down_revision, "20260524_0001")
        self.assertIsNone(self.module.branch_labels)
        self.assertIsNone(self.module.depends_on)

    def test_20260614_0001_down_revision_repointed_to_bridge(self):
        repointed = _load_module(REPOINTED_PATH, "f1gaf1_repointed_migration")
        self.assertEqual(repointed.revision, "20260614_0001")
        self.assertEqual(repointed.down_revision, "20260613_9000")

    def test_all_create_table_calls_are_guarded_by_table_exists(self):
        source = BRIDGE_PATH.read_text(encoding="utf-8-sig")
        upgrade_body = source.split("def upgrade")[1].split("def downgrade")[0]
        self.assertEqual(
            upgrade_body.count("op.create_table"),
            upgrade_body.count("if not table_exists("),
            "every op.create_table must be preceded by a table_exists() guard",
        )

    def test_table_exists_uses_has_table_not_get_columns(self):
        source = BRIDGE_PATH.read_text(encoding="utf-8-sig")
        helper_body = source.split("def table_exists")[1].split("def upgrade")[0]
        self.assertIn("has_table", helper_body)
        self.assertNotIn("get_columns", helper_body)

    def test_orders_create_table_excludes_future_columns(self):
        source = BRIDGE_PATH.read_text(encoding="utf-8-sig")
        orders_block = source.split('"orders",')[1].split("op.create_index")[0]
        for column in FUTURE_ORDERS_COLUMNS:
            self.assertNotIn(
                f'"{column}"', orders_block,
                f"orders bridge create_table must not include future column {column!r}",
            )

    def test_order_items_create_table_excludes_future_columns(self):
        source = BRIDGE_PATH.read_text(encoding="utf-8-sig")
        order_items_block = source.split('"order_items",')[1].split("op.create_index")[0]
        for column in FUTURE_ORDER_ITEMS_COLUMNS:
            self.assertNotIn(f'"{column}"', order_items_block)

    def test_order_items_table_created_after_orders_in_source_order(self):
        source = BRIDGE_PATH.read_text(encoding="utf-8-sig")
        self.assertLess(source.index('"orders",'), source.index('"order_items",'))

    def test_downgrade_is_non_destructive_no_op(self):
        source = BRIDGE_PATH.read_text(encoding="utf-8-sig")
        downgrade_body = source.split("def downgrade")[1]
        self.assertNotIn("drop_table", downgrade_body)
        self.assertIn("pass", downgrade_body)


class BridgeFunctionalTest(unittest.TestCase):
    """Runs the real upgrade()/downgrade() against SQLite via alembic's
    Operations bound to a sync connection, matching the existing
    test_plan_pricing_migration.py convention."""

    def setUp(self):
        self.module = _load_module(BRIDGE_PATH, "f1gaf1_bridge_functional")
        self.engine = sa.create_engine("sqlite:///:memory:")

    def tearDown(self):
        self.engine.dispose()

    def _run(self, connection, fn):
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            fn()

    def test_empty_database_creates_all_five_tables(self):
        with self.engine.begin() as connection:
            self._run(connection, self.module.upgrade)
            inspector = sa.inspect(connection)
            for table in BRIDGE_CREATED_TABLES:
                self.assertTrue(inspector.has_table(table), f"{table} was not created")

    def test_orders_table_has_only_historical_minimum_columns(self):
        with self.engine.begin() as connection:
            self._run(connection, self.module.upgrade)
            columns = {c["name"] for c in sa.inspect(connection).get_columns("orders")}
            self.assertTrue(FUTURE_ORDERS_COLUMNS.isdisjoint(columns))
            self.assertEqual(
                columns,
                {
                    "id", "tenant_id", "customer_id", "table_no", "phone", "total",
                    "status", "remark", "payment_status", "payment_method",
                    "payment_time", "source", "created_at", "updated_at",
                },
            )

    def test_order_items_fk_to_orders_is_valid_because_orders_created_first(self):
        with self.engine.begin() as connection:
            # No exception here is itself the proof: SQLite (like MySQL) would
            # reject a FOREIGN KEY referencing a table that doesn't exist yet
            # if creation order were wrong.
            self._run(connection, self.module.upgrade)
            columns = {c["name"] for c in sa.inspect(connection).get_columns("order_items")}
            self.assertEqual(columns, {"id", "order_id", "dish_id", "name", "price", "qty"})

    def test_table_already_exists_is_a_true_no_op_preserves_preexisting_shape(self):
        """Simulates a production-like DB where these tables already exist
        (pre-Alembic create_all era) with a shape that may differ from the
        bridge's own historical reconstruction -- the bridge must not touch
        it at all, proving the table_exists() guard is a real skip, not a
        drop-and-recreate."""
        with self.engine.begin() as connection:
            connection.execute(sa.text(
                "CREATE TABLE orders (id BIGINT PRIMARY KEY, tenant_id VARCHAR(32) NOT NULL, "
                "a_column_the_bridge_does_not_know_about VARCHAR(8) NOT NULL DEFAULT 'sentinel')"
            ))
            connection.execute(sa.text(
                "INSERT INTO orders (id, tenant_id, a_column_the_bridge_does_not_know_about) "
                "VALUES (1, 'tenant-a', 'sentinel')"
            ))
            self._run(connection, self.module.upgrade)

            columns = {c["name"] for c in sa.inspect(connection).get_columns("orders")}
            self.assertIn("a_column_the_bridge_does_not_know_about", columns)
            self.assertNotIn("table_no", columns, "bridge must not have touched a pre-existing orders table")
            row = connection.execute(sa.text("SELECT id, tenant_id FROM orders WHERE id = 1")).fetchone()
            self.assertEqual(tuple(row), (1, "tenant-a"))

            # The other four tables are still genuinely missing and must
            # still be created by the same upgrade() call.
            inspector = sa.inspect(connection)
            for table in ("order_items", "menu_items", "commission_record", "customer_operation_log"):
                self.assertTrue(inspector.has_table(table), f"{table} should still be created")

    def test_rerunning_upgrade_is_idempotent(self):
        with self.engine.begin() as connection:
            self._run(connection, self.module.upgrade)
            self._run(connection, self.module.upgrade)
            inspector = sa.inspect(connection)
            for table in BRIDGE_CREATED_TABLES:
                self.assertTrue(inspector.has_table(table))

    def test_downgrade_never_drops_any_business_table(self):
        with self.engine.begin() as connection:
            self._run(connection, self.module.upgrade)
            self._run(connection, self.module.downgrade)
            inspector = sa.inspect(connection)
            for table in BRIDGE_CREATED_TABLES:
                self.assertTrue(inspector.has_table(table), f"downgrade must not have dropped {table}")


if __name__ == "__main__":
    unittest.main()
