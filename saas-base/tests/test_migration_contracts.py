import inspect
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.config import settings
from app.main import startup
from app.models import Base


class MigrationContractsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = Path(__file__).resolve().parents[1]
        migration_path = root / "alembic" / "versions" / "20260809_0006_add_channel_partner_mobile_normalized.py"
        spec = importlib.util.spec_from_file_location("migration_20260809_0006", migration_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.mobile_migration = module
        cls.mobile_migration_source = migration_path.read_text(encoding="utf-8")

    def test_alembic_has_versioned_migrations(self):
        root = Path(__file__).resolve().parents[1]
        config = Config(str(root / "alembic.ini"))
        script = ScriptDirectory.from_config(config)
        revisions = list(script.walk_revisions())

        self.assertGreaterEqual(len(revisions), 1)
        self.assertTrue((root / "alembic" / "versions").is_dir())

    def test_alembic_metadata_covers_all_current_models(self):
        expected_tables = {
            "tenant",
            "tenant_config",
            "tenant_plugin",
            "customer",
            "customer_identity",
            "consumption",
            "coupon_template",
            "coupon",
        }

        self.assertTrue(expected_tables.issubset(set(Base.metadata.tables.keys())))

    def test_runtime_auto_create_tables_is_disabled_by_default(self):
        self.assertFalse(settings.AUTO_CREATE_TABLES)
        source = inspect.getsource(startup)

        self.assertIn("settings.AUTO_CREATE_TABLES", source)
        self.assertIn("Base.metadata.create_all", source)

    def test_channel_partner_mobile_normalization_uses_digits_only(self):
        normalize = self.mobile_migration.normalize_mobile_for_migration

        self.assertEqual(normalize("13812345678"), "13812345678")
        self.assertEqual(normalize("138-1234-5678"), "13812345678")
        self.assertEqual(normalize("+86 138 1234 5678"), "8613812345678")
        self.assertEqual(normalize("１３８-1234-５６７８"), "1234")

    def test_channel_partner_mobile_migration_source_avoids_mysql8_regexp_replace(self):
        self.assertNotIn("REGEXP_REPLACE", self.mobile_migration_source)

    def test_channel_partner_mobile_migration_blocks_duplicate_normalized_values(self):
        rows = [
            {"id": 1, "mobile": "138-1234-5678", "mobile_normalized": None},
            {"id": 2, "mobile": "13812345678", "mobile_normalized": ""},
        ]

        with self.assertRaisesRegex(RuntimeError, "duplicate channel partner mobile_normalized"):
            self.mobile_migration.prepare_mobile_normalized_updates(rows)

    def test_channel_partner_mobile_migration_blocks_empty_normalized_value(self):
        rows = [{"id": 1, "mobile": "---", "mobile_normalized": None}]

        with self.assertRaisesRegex(RuntimeError, "empty channel partner mobile_normalized"):
            self.mobile_migration.prepare_mobile_normalized_updates(rows)

    def test_channel_partner_mobile_migration_can_rerun_after_column_exists(self):
        rows = [
            {"id": 1, "mobile": "138-1234-5678", "mobile_normalized": None},
            {"id": 2, "mobile": "13912345678", "mobile_normalized": "13912345678"},
        ]

        updates = self.mobile_migration.prepare_mobile_normalized_updates(rows)

        self.assertEqual(updates, [(1, "13812345678")])

    def test_channel_partner_mobile_migration_empty_table_succeeds(self):
        fake_op = _FakeMobileMigrationOp(rows=[])

        self.mobile_migration.upgrade(op_impl=fake_op)

        self.assertFalse(fake_op.updates)
        self.assertIn(("add_column", "channel_partners", "mobile_normalized"), fake_op.calls)
        self.assertIn(("create_unique_constraint", "ux_channel_partner_mobile_normalized"), fake_op.calls)

    def test_channel_partner_mobile_migration_creates_unique_constraint_after_success(self):
        fake_op = _FakeMobileMigrationOp(rows=[{"id": 1, "mobile": "138-1234-5678", "mobile_normalized": None}])

        self.mobile_migration.upgrade(op_impl=fake_op)

        self.assertEqual(fake_op.updates, [(1, "13812345678")])
        self.assertIn(("alter_column", "channel_partners", "mobile_normalized", False), fake_op.calls)
        self.assertIn(("create_unique_constraint", "ux_channel_partner_mobile_normalized"), fake_op.calls)


class _FakeResult:
    def __init__(self, rows=None, scalar_value=None):
        self._rows = rows or []
        self._scalar_value = scalar_value

    def fetchall(self):
        return self._rows

    def scalar(self):
        return self._scalar_value


class _FakeBind:
    dialect = SimpleNamespace(name="mysql")

    def __init__(self, rows):
        self.rows = rows
        self.updates = []

    def execute(self, statement, params=None):
        sql = str(statement)
        if "SELECT id, mobile, mobile_normalized" in sql:
            return _FakeResult(rows=self.rows)
        if "COUNT(*)" in sql:
            return _FakeResult(scalar_value=0)
        if "UPDATE channel_partners" in sql:
            self.updates.append((params["id"], params["mobile_normalized"]))
            return _FakeResult()
        return _FakeResult()


class _FakeMobileMigrationOp:
    def __init__(self, rows, column_exists=False, index_exists=False):
        self.bind = _FakeBind(rows)
        self._column_exists = column_exists
        self._index_exists = index_exists
        self.calls = []
        self.updates = self.bind.updates

    def get_bind(self):
        return self.bind

    def table_exists(self, table_name):
        return table_name == "channel_partners"

    def column_exists(self, table_name, column_name):
        return table_name == "channel_partners" and column_name == "mobile_normalized" and self._column_exists

    def index_exists(self, table_name, index_name):
        return (
            table_name == "channel_partners"
            and index_name == "ux_channel_partner_mobile_normalized"
            and self._index_exists
        )

    def add_column(self, table_name, column):
        self.calls.append(("add_column", table_name, column.name))
        self._column_exists = True

    def alter_column(self, table_name, column_name, **kwargs):
        self.calls.append(("alter_column", table_name, column_name, kwargs.get("nullable")))

    def create_unique_constraint(self, name, table_name, columns):
        self.calls.append(("create_unique_constraint", name))
        self._index_exists = True
