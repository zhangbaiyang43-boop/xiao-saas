import inspect
import unittest
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.config import settings
from app.main import startup
from app.models import Base


class MigrationContractsTest(unittest.TestCase):
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
