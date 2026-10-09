"""B4 production mode on a REAL MySQL 5.7 (CI "MySQL 5.7 schema convergence" job). Synthetic data only."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.core import wxpay_secret_crypto as crypto

MYSQL_URL = os.getenv("WXPAY_SCHEMA_TEST_DATABASE_URL", "")
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


authority = sys.modules.get("wxpay_migration_authority") or _load("wxpay_migration_authority", "wxpay_migration_authority.py")
mig = _load("wxpay_secret_migrate_b4_mysql", "wxpay_secret_migrate.py")

POSIX = hasattr(os, "geteuid") and hasattr(os, "O_NOFOLLOW")
EUID = os.geteuid() if POSIX else 0
DB_A, DB_B = "wxpay_prod_gate_a", "wxpay_prod_gate_b"
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _pem() -> str:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


@unittest.skipUnless(MYSQL_URL.startswith("mysql+asyncmy://") and POSIX, "isolated MySQL gate only")
class ProductionModeOnMySqlTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.saved = (settings.WXPAY_SECRET_KEYRING_PATH, settings.WXPAY_ENVELOPE_WRITE_ENABLED,
                      settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED, crypto.KEYRING_SOURCE_POLICY)
        crypto.KEYRING_SOURCE_POLICY = crypto.KeyringSourcePolicy(extra_trusted_uids=frozenset({EUID}), verify_ancestors=False)
        settings.WXPAY_ENVELOPE_WRITE_ENABLED = True
        settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED = True
        self.dir = Path(os.path.realpath(tempfile.mkdtemp(prefix="wxpay-b4-mysql-")))
        keyring = self.dir / "keyring.json"
        keyring.write_text(json.dumps({"formatVersion": 1, "activeKeyId": "gate-b4", "keys": [
            {"keyId": "gate-b4", "algorithm": "fernet", "usage": "encrypt-decrypt", "key": Fernet.generate_key().decode()}]}), encoding="utf-8")
        os.chmod(keyring, 0o600)
        settings.WXPAY_SECRET_KEYRING_PATH = str(keyring)
        crypto.get_keyring.cache_clear()
        self.private_pem, public_pem = authority.generate_keypair()
        self.pubkey = self.dir / "authority.pub"
        self.pubkey.write_bytes(public_pem)
        self.backup = self.dir / "backup.sql.gz"
        self.backup.write_bytes(b"synthetic backup " * 100)
        self.svc_env = self.dir / "service.env"
        self.svc_env.write_text("X=1\n", encoding="utf-8")
        self.ledger = self.dir / "ledger.jsonl"
        self.env = mig.ProductionEnv(now_fn=lambda: datetime.now(timezone.utc), host_fn=lambda: "gate-host",
                                     git_fn=lambda _r: ("a" * 40, True), trusted_uids=frozenset({EUID}))
        admin = create_async_engine(MYSQL_URL)
        async with admin.begin() as conn:
            for name in (DB_A, DB_B):
                await conn.execute(text(f"DROP DATABASE IF EXISTS {name}"))
                await conn.execute(text(f"CREATE DATABASE {name} CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"))
        await admin.dispose()
        self.url_a = MYSQL_URL.rsplit("/", 1)[0] + f"/{DB_A}?charset=utf8mb4"
        self.url_b = MYSQL_URL.rsplit("/", 1)[0] + f"/{DB_B}?charset=utf8mb4"
        self.engine = mig.make_engine(self.url_a)
        self.engine_b = mig.make_engine(self.url_b)
        for engine in (self.engine, self.engine_b):
            async with engine.begin() as conn:
                await conn.execute(text(
                    "CREATE TABLE tenant (id BIGINT PRIMARY KEY AUTO_INCREMENT, tenant_id VARCHAR(64) NOT NULL UNIQUE, "
                    "name VARCHAR(100), wx_api_key_v3 VARCHAR(256) NULL, wx_private_key TEXT NULL, "
                    "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP) "
                    "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci"))
                await conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
                await conn.execute(text("INSERT INTO alembic_version VALUES ('20261009_0001')"))
        self.pems = {"t1": _pem(), "t2": _pem()}
        async with self.engine.begin() as conn:
            for tid, api in (("t1", "AbCdEfGhIjKlMnOpQrStUvWxYz123456"), ("t2", "C" * 32)):
                await conn.execute(text("INSERT INTO tenant (tenant_id, name, wx_api_key_v3, wx_private_key, updated_at) VALUES (:t,:n,:a,:p,'2026-01-01 00:00:00')"),
                                   {"t": tid, "n": f"n-{tid}", "a": api, "p": self.pems[tid]})

    async def asyncTearDown(self):
        await self.engine.dispose()
        await self.engine_b.dispose()
        admin = create_async_engine(MYSQL_URL)
        async with admin.begin() as conn:
            for name in (DB_A, DB_B):
                await conn.execute(text(f"DROP DATABASE IF EXISTS {name}"))
        await admin.dispose()
        (settings.WXPAY_SECRET_KEYRING_PATH, settings.WXPAY_ENVELOPE_WRITE_ENABLED,
         settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED, crypto.KEYRING_SOURCE_POLICY) = self.saved
        crypto.get_keyring.cache_clear()
        shutil.rmtree(self.dir, ignore_errors=True)

    async def row(self, tid="t1"):
        async with self.engine.connect() as conn:
            return tuple((await conn.execute(text("SELECT name, wx_api_key_v3, wx_private_key, updated_at FROM tenant WHERE tenant_id=:t"), {"t": tid})).one())

    async def issue(self, engine=None, name="grant.json", mutate=None) -> Path:
        facts, _ = await mig.compute_plan(engine or self.engine, "t1", ["wx_api_key_v3", "wx_private_key"], self.env, "repo", str(self.backup), str(self.svc_env))
        grant = authority.new_grant(
            host="gate-host", tenant_id="t1", fields=["wx_api_key_v3", "wx_private_key"], backend_sha=facts.backend_sha,
            alembic_revision=facts.alembic_revision, db_fingerprint=facts.db_fingerprint, plan_digest=facts.plan_digest,
            keyring_active_key_id=facts.keyring_active_key_id, backup_path=str(self.backup), backup_sha256=facts.backup.sha256,
            recovery_attested_at=authority.iso(datetime.now(timezone.utc) - timedelta(days=1)), now=datetime.now(timezone.utc),
        )
        grant.update(mutate or {})
        path = self.dir / name
        path.write_text(json.dumps(authority.sign_grant(self.private_pem, grant)), encoding="utf-8")
        return path

    async def prod(self, grant, hooks=None, engine=None):
        return await mig.run_production(
            engine or self.engine, grant_path=str(grant), pubkey_path=str(self.pubkey), ledger_path=str(self.ledger),
            tenant_ids=["t1"], repo_root="repo", service_env_path=str(self.svc_env), env=self.env, hooks=hooks)

    async def test_fingerprint_comes_from_the_live_server_and_distinguishes_databases(self):
        fp_a = await mig.db_fingerprint(self.engine)
        fp_b = await mig.db_fingerprint(self.engine_b)
        self.assertEqual(len(fp_a), 64)
        self.assertNotEqual(fp_a, fp_b)  # same server, different schema => different fingerprint
        async with self.engine.connect() as conn:
            self.assertTrue((await conn.execute(text("SELECT @@server_uuid"))).scalar())

    async def test_grant_for_one_database_is_refused_on_another(self):
        grant = await self.issue(engine=self.engine)
        with self.assertRaises(authority.AuthorityRefused) as caught:
            await self.prod(grant, engine=self.engine_b)
        self.assertEqual(caught.exception.reason, "DB_FINGERPRINT_MISMATCH")

    async def test_authorized_run_on_mysql_keeps_updated_at_and_other_tenants(self):
        grant = await self.issue()
        t2_before = await self.row("t2")
        before = await self.row("t1")
        report = await self.prod(grant)
        after = await self.row("t1")
        self.assertEqual((report.tenants_migrated, report.fields_updated, report.decrypt_match_count), (1, 2, 2))
        self.assertEqual((after[0], after[3]), (before[0], before[3]))  # ON UPDATE CURRENT_TIMESTAMP did not fire
        self.assertEqual(await self.row("t2"), t2_before)
        self.assertEqual(crypto.decrypt_secret(after[2], crypto.SecretField.PRIVATE_KEY, allow_legacy_plaintext=False), self.pems["t1"])

    async def test_cas_conflict_stops_burns_the_grant_and_preserves_the_other_writer(self):
        grant = await self.issue()
        api = (await self.row("t1"))[1]

        async def concurrent_case_only_edit(_tid):
            other = mig.make_engine(self.url_a)
            async with other.begin() as conn:
                await conn.execute(text("UPDATE tenant SET wx_api_key_v3=:v WHERE tenant_id='t1'"), {"v": api.swapcase()})
            await other.dispose()

        report = await self.prod(grant, hooks=mig.Hooks(before_update=concurrent_case_only_edit))
        self.assertEqual((report.tenants_conflict, report.fields_updated, report.tenants_migrated), (1, 0, 0))
        self.assertEqual(mig.exit_code(report), mig.EXIT_CONFLICT)
        row = await self.row("t1")
        self.assertEqual(row[1], api.swapcase())
        self.assertEqual(row[2], self.pems["t1"])
        self.assertEqual(json.loads(self.ledger.read_text().splitlines()[-1])["outcome"], "CONFLICT")
        with self.assertRaises(authority.AuthorityRefused) as caught:
            await self.prod(grant)
        self.assertEqual(caught.exception.reason, "GRANT_REUSED")

    async def test_killed_connection_rolls_back_and_the_grant_is_burned(self):
        grant = await self.issue()
        before = await self.row("t1")

        async def kill_executor_connections(_tid):
            admin = create_async_engine(MYSQL_URL)
            async with admin.begin() as conn:
                ids = [r[0] for r in (await conn.execute(text(f"SELECT id FROM information_schema.processlist WHERE db = '{DB_A}' AND id <> CONNECTION_ID()"))).all()]
                for connection_id in ids:
                    await conn.execute(text(f"KILL CONNECTION {int(connection_id)}"))
            await admin.dispose()

        report = await self.prod(grant, hooks=mig.Hooks(before_update=kill_executor_connections))
        self.assertEqual((report.tenants_failed, report.fields_updated), (1, 0))
        await self.engine.dispose()  # drop pooled connections the test itself just killed
        self.assertEqual(await self.row("t1"), before)
        self.assertNotIn(self.pems["t1"][:40], json.dumps(report.events))
        self.assertEqual(json.loads(self.ledger.read_text().splitlines()[-1])["outcome"], "FAILED")


if __name__ == "__main__":
    unittest.main()
