"""B2 migration executor on a REAL MySQL 5.7 (CI "MySQL 5.7 schema convergence" job).

The tenant fixture mirrors the production DDL shape (utf8mb4_general_ci, varchar(256) +
text, an auto-updating updated_at).  All data is synthetic.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.core import wxpay_secret_crypto as crypto

MYSQL_URL = os.getenv("WXPAY_SCHEMA_TEST_DATABASE_URL", "")
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "wxpay_secret_migrate.py"
_spec = importlib.util.spec_from_file_location("wxpay_secret_migrate_mysql", SCRIPT)
mig = importlib.util.module_from_spec(_spec)
sys.modules["wxpay_secret_migrate_mysql"] = mig
_spec.loader.exec_module(mig)

POSIX = hasattr(os, "geteuid") and hasattr(os, "O_NOFOLLOW")
EUID = os.geteuid() if POSIX else 0
DB = "wxpay_migration_gate"
ACK = {mig.ACK_ENV: mig.ACK_VALUE}


def _pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


@unittest.skipUnless(MYSQL_URL.startswith("mysql+asyncmy://") and POSIX, "isolated MySQL gate only")
class MigrationOnMySqlTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.saved = (
            settings.WXPAY_SECRET_KEYRING_PATH, settings.WXPAY_ENVELOPE_WRITE_ENABLED,
            settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED, crypto.KEYRING_SOURCE_POLICY,
        )
        crypto.KEYRING_SOURCE_POLICY = crypto.KeyringSourcePolicy(extra_trusted_uids=frozenset({EUID}), verify_ancestors=False)
        settings.WXPAY_ENVELOPE_WRITE_ENABLED = True
        settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED = True
        self.dir = Path(os.path.realpath(tempfile.mkdtemp(prefix="wxpay-mig-mysql-")))
        keyring = self.dir / "keyring.json"
        keyring.write_text(json.dumps({"formatVersion": 1, "activeKeyId": "gate-a", "keys": [
            {"keyId": "gate-a", "algorithm": "fernet", "usage": "encrypt-decrypt", "key": Fernet.generate_key().decode()}]}), encoding="utf-8")
        os.chmod(keyring, 0o600)
        settings.WXPAY_SECRET_KEYRING_PATH = str(keyring)
        crypto.get_keyring.cache_clear()

        admin = create_async_engine(MYSQL_URL)
        async with admin.begin() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {DB}"))
            await conn.execute(text(f"CREATE DATABASE {DB} CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"))
        await admin.dispose()
        self.url = MYSQL_URL.rsplit("/", 1)[0] + f"/{DB}?charset=utf8mb4"
        self.engine = mig.make_engine(self.url)
        async with self.engine.begin() as conn:
            await conn.execute(text(
                "CREATE TABLE tenant (id BIGINT PRIMARY KEY AUTO_INCREMENT, tenant_id VARCHAR(64) NOT NULL UNIQUE, "
                "name VARCHAR(100), wx_api_key_v3 VARCHAR(256) NULL, wx_private_key TEXT NULL, "
                "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP) "
                "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci"
            ))
            await conn.execute(text(f"CREATE TABLE {mig.MARKER_TABLE} (purpose VARCHAR(64))"))
            await conn.execute(text(f"INSERT INTO {mig.MARKER_TABLE} VALUES (:p)"), {"p": mig.MARKER_PURPOSE})

    async def asyncTearDown(self):
        await self.engine.dispose()
        admin = create_async_engine(MYSQL_URL)
        async with admin.begin() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {DB}"))
        await admin.dispose()
        settings.WXPAY_SECRET_KEYRING_PATH, settings.WXPAY_ENVELOPE_WRITE_ENABLED, settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED, crypto.KEYRING_SOURCE_POLICY = self.saved
        crypto.get_keyring.cache_clear()
        shutil.rmtree(self.dir, ignore_errors=True)

    async def seed(self, tid, api, pem):
        async with self.engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO tenant (tenant_id, name, wx_api_key_v3, wx_private_key, updated_at) VALUES (:t, :n, :a, :p, '2026-01-01 00:00:00')"),
                {"t": tid, "n": f"name-{tid}", "a": api, "p": pem},
            )

    async def row(self, tid):
        async with self.engine.connect() as conn:
            return tuple((await conn.execute(text("SELECT name, wx_api_key_v3, wx_private_key, updated_at FROM tenant WHERE tenant_id=:t"), {"t": tid})).one())

    async def migrate(self, **kwargs):
        with patch.dict(os.environ, ACK):
            return await mig.run(self.engine, "apply", app_database_url="mysql+asyncmy://other/x", target_url=self.url, **kwargs)

    async def test_migration_keeps_non_secret_columns_and_updated_at_pinned(self):
        api, pem = "A" * 32, _pem()
        await self.seed("t1", api, pem)
        before = await self.row("t1")
        report = await self.migrate()
        after = await self.row("t1")
        self.assertEqual((report.fields_updated, report.decrypt_match_count, report.tenants_failed), (2, 2, 0))
        self.assertEqual((after[0], after[3]), (before[0], before[3]))  # ON UPDATE CURRENT_TIMESTAMP did not fire
        self.assertEqual(crypto.decrypt_secret(after[1], crypto.SecretField.API_V3_KEY, allow_legacy_plaintext=False), api)
        self.assertEqual(crypto.decrypt_secret(after[2], crypto.SecretField.PRIVATE_KEY, allow_legacy_plaintext=False), pem)
        again = await self.migrate()
        self.assertEqual((again.fields_updated, again.tenants_noop), (0, 1))
        self.assertEqual(await self.row("t1"), after)

    async def test_cas_conflict_is_detected_even_when_the_change_is_only_letter_case(self):
        """utf8mb4_general_ci says 'abc' = 'ABC'; the CAS must still see a different value."""
        api, pem = "AbCdEfGhIjKlMnOpQrStUvWxYz123456", _pem()
        await self.seed("t1", api, pem)

        async def concurrent_edit(_tid):
            other = mig.make_engine(self.url)
            async with other.begin() as conn:
                await conn.execute(text("UPDATE tenant SET wx_api_key_v3 = :v WHERE tenant_id = 't1'"), {"v": api.swapcase()})
            await other.dispose()

        report = await self.migrate(hooks=mig.Hooks(before_update=concurrent_edit))
        self.assertEqual((report.tenants_conflict, report.fields_updated, report.tenants_migrated), (1, 0, 0))
        self.assertEqual(mig.exit_code(report), mig.EXIT_CONFLICT)
        row = await self.row("t1")
        self.assertEqual(row[1], api.swapcase())  # the concurrent writer's value survived
        self.assertEqual(row[2], pem)  # nothing of ours was applied

        retried = await self.migrate()  # next run re-reads fresh state and succeeds
        self.assertEqual(retried.tenants_migrated, 1)

    async def test_conflict_retry_option_reads_fresh_state_and_succeeds(self):
        await self.seed("t1", "A" * 32, _pem())
        fired = {"done": False}

        async def edit_once(_tid):
            if fired["done"]:
                return
            fired["done"] = True
            other = mig.make_engine(self.url)
            async with other.begin() as conn:
                await conn.execute(text("UPDATE tenant SET wx_api_key_v3 = :v WHERE tenant_id = 't1'"), {"v": "B" * 32})
            await other.dispose()

        report = await self.migrate(hooks=mig.Hooks(before_update=edit_once), retry_conflicts=1)
        self.assertEqual((report.tenants_conflict, report.tenants_migrated), (0, 1))
        self.assertEqual(crypto.decrypt_secret((await self.row("t1"))[1], crypto.SecretField.API_V3_KEY, allow_legacy_plaintext=False), "B" * 32)

    async def test_innodb_rollback_leaves_no_half_migrated_tenant(self):
        api, pem = "A" * 32, _pem()
        await self.seed("t1", api, pem)
        await self.seed("t2", "C" * 32, _pem())
        before = await self.row("t1")
        calls = {"n": 0}

        def second_field_fails(value, field):
            calls["n"] += 1
            if calls["n"] == 2:
                raise crypto.SecretEncryptionUnavailable("WXPAY_SECRET_ENCRYPTION_FAILED")
            return crypto.encrypt_secret(value, field)

        report = await self.migrate(hooks=mig.Hooks(encrypt=second_field_fails), stop_on_failure=False)
        self.assertEqual(await self.row("t1"), before)
        self.assertEqual((report.tenants_failed, report.tenants_migrated), (1, 1))
        t2 = await self.row("t2")
        self.assertTrue(t2[1].startswith("enc:v1:") and t2[2].startswith("enc:v1:"))

    async def test_database_connection_killed_mid_tenant_fails_that_tenant_only(self):
        await self.seed("t1", "A" * 32, _pem())
        await self.seed("t2", "C" * 32, _pem())
        before = await self.row("t1")
        killed = {"done": False}

        async def kill_executor_connections(_tid):
            if killed["done"]:
                return
            killed["done"] = True
            admin = create_async_engine(MYSQL_URL)
            async with admin.begin() as conn:
                ids = [r[0] for r in (await conn.execute(text(
                    f"SELECT id FROM information_schema.processlist WHERE db = '{DB}' AND id <> CONNECTION_ID()"))).all()]
                for connection_id in ids:
                    await conn.execute(text(f"KILL CONNECTION {int(connection_id)}"))
            await admin.dispose()

        report = await self.migrate(hooks=mig.Hooks(before_update=kill_executor_connections), stop_on_failure=False)
        self.assertEqual(await self.row("t1"), before)  # rolled back by the server
        self.assertEqual((report.tenants_failed, report.tenants_migrated), (1, 1))
        failed = [e for e in report.events if e.get("outcome") == "FAILED"][0]
        self.assertNotIn("A" * 32, json.dumps(report.events))
        self.assertTrue(failed["reason"])  # a stable class name, never driver text

    async def test_marker_missing_means_the_database_cannot_be_written(self):
        await self.seed("t1", "A" * 32, _pem())
        before = await self.row("t1")
        async with self.engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE {mig.MARKER_TABLE}"))
        with self.assertRaises(mig.Refused):
            await self.migrate()
        self.assertEqual(await self.row("t1"), before)


if __name__ == "__main__":
    unittest.main()
