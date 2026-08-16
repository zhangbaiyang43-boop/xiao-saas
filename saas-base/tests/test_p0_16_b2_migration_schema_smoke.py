"""P0-16 Phase B2 -- B2-T12 (migration/schema smoke) and AUDIT-12 (legacy
NULL rows remain valid).

This project's existing convention (test_migration_contracts.py) does not
functionally exercise trivial additive migrations (e.g. 20260809_0001 /
20260809_0002, the served_by_*/created_by_* precedents this migration
follows) with a real alembic upgrade/downgrade in a unit test -- that's
covered by an actual `alembic upgrade head` / `downgrade -1` CLI smoke run
against a scratch SQLite DB as part of the gate sequence, not here. This
file verifies the migration's STRUCTURE (revision chain, additive-only
column set, no default/backfill/index/FK) plus the model-level legacy-row
contract.
"""

import importlib.util
import pathlib
import unittest

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.order import Order
from app.models.tenant import Tenant

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "alembic" / "versions" / "20260816_0001_add_order_lifecycle_audit_facts.py"

EXPECTED_NEW_COLUMNS = {
    "terminated_at",
    "terminated_actor_type",
    "terminated_actor_id",
    "terminated_actor_role",
    "termination_source",
    "settled_by_account_id",
    "settled_by_role",
}


class MigrationStructureTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MIGRATION_PATH.exists(), f"expected exactly one new migration at {MIGRATION_PATH}")
        spec = importlib.util.spec_from_file_location("p0_16_b2_migration", MIGRATION_PATH)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.source = MIGRATION_PATH.read_text(encoding="utf-8-sig")

    def test_revision_chains_onto_the_certified_b1_head(self):
        self.assertEqual(self.module.down_revision, "20260814_0002")

    def test_additive_only_no_default_no_backfill_no_index_no_fk(self):
        self.assertIn("op.add_column", self.source)
        self.assertNotIn("server_default", self.source)
        self.assertNotIn("op.create_index", self.source)
        self.assertNotIn("ForeignKey", self.source)
        self.assertNotIn("CheckConstraint", self.source)
        # no UPDATE/data-migration statements of any kind
        self.assertNotIn("op.execute", self.source)

    def test_exactly_seven_columns_added_to_orders(self):
        import re
        # column name is always the first add_column(...) argument after the
        # table name -- matches sa.Column("name", ...
        names = set(re.findall(r'add_column\(\s*"orders",\s*sa\.Column\(\s*"([a-z_]+)"', self.source))
        self.assertEqual(names, EXPECTED_NEW_COLUMNS)

    def test_all_new_columns_are_nullable(self):
        import re
        # every sa.Column(...) block for these columns must say nullable=True
        # -- matches up to the next nullable= kwarg rather than trying to
        # balance the nested parens inside sa.DateTime()/sa.String(length=32).
        for name in EXPECTED_NEW_COLUMNS:
            m = re.search(rf'sa\.Column\(\s*"{name}".*?nullable=(\w+)', self.source, re.DOTALL)
            self.assertIsNotNone(m, f"column {name} definition not found")
            self.assertEqual(m.group(1), "True")

    def test_downgrade_drops_exactly_the_same_seven_columns(self):
        import re
        names = set(re.findall(r'drop_column\(\s*"orders",\s*"([a-z_]+)"', self.source))
        self.assertEqual(names, EXPECTED_NEW_COLUMNS)

    def test_upgrade_and_downgrade_are_idempotent_via_column_exists_guard(self):
        self.assertIn("column_exists", self.source)
        # every add_column call must be guarded
        upgrade_body = self.source.split("def upgrade")[1].split("def downgrade")[0]
        self.assertEqual(upgrade_body.count("add_column"), upgrade_body.count("if not column_exists"))


class LegacyNullRowSerializationTest(unittest.IsolatedAsyncioTestCase):
    """AUDIT-12: a historical row created before this migration's runtime
    write paths existed must read back with all 7 new columns None, no
    exception -- NULL is a legitimate 'unknown legacy audit', not an
    invariant violation."""

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add(Tenant(
            tenant_id="tenant-legacy", name="Legacy Restaurant", password_hash="x",
            status=True, is_open=True, payment_mode="postpay",
        ))
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_legacy_cancelled_row_with_no_audit_facts_reads_back_safely(self):
        order = Order(
            tenant_id="tenant-legacy", table_no="A1", status="cancelled",
            payment_status="unpaid", payment_mode="postpay", total=28.0,
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)

        for field in EXPECTED_NEW_COLUMNS:
            self.assertIsNone(getattr(order, field))


if __name__ == "__main__":
    unittest.main()
