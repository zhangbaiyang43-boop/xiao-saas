"""B4: production authorization model of the WeChat Pay secret migration executor.

SQLite + throwaway Ed25519 keys + synthetic data.  Real-MySQL behaviour (CAS conflicts, server
fingerprint) is covered by test_wxpay_secret_migration_production_mode_schema_mysql.py.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text

from app.config import settings
from app.core import wxpay_secret_crypto as crypto

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(SCRIPTS))
authority = _load("wxpay_migration_authority", "wxpay_migration_authority.py")
mig = _load("wxpay_secret_migrate_b4", "wxpay_secret_migrate.py")
grant_tool = _load("wxpay_migration_grant", "wxpay_migration_grant.py")

POSIX = hasattr(os, "geteuid") and hasattr(os, "O_NOFOLLOW")
EUID = os.geteuid() if POSIX else 0
TEST_POLICY = crypto.KeyringSourcePolicy(extra_trusted_uids=frozenset({EUID}), verify_ancestors=False)
NOW = datetime(2026, 10, 10, 3, 0, 0, tzinfo=timezone.utc)
API = ["A" * 32, "B1" * 16, "Zz9!" * 8]


def _pem() -> str:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


PEMS = [_pem(), _pem()]


class Crash(BaseException):
    """Simulated process death."""


@unittest.skipUnless(POSIX, "POSIX trust model")
class ProductionBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.saved = (settings.WXPAY_SECRET_KEYRING_PATH, settings.WXPAY_ENVELOPE_WRITE_ENABLED,
                      settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED, crypto.KEYRING_SOURCE_POLICY)
        crypto.KEYRING_SOURCE_POLICY = TEST_POLICY
        settings.WXPAY_ENVELOPE_WRITE_ENABLED = True  # the EXECUTOR process; the service flag is a separate file
        settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED = True
        self.dir = Path(os.path.realpath(tempfile.mkdtemp(prefix="wxpay-b4-")))
        self.keyring = self.dir / "keyring.json"
        self.keys = {}
        self.write_keyring("wxpay-2026-10")
        self.private_pem, public_pem = authority.generate_keypair()
        self.pubkey = self.dir / "authority.pub"
        self.pubkey.write_bytes(public_pem)
        os.chmod(self.pubkey, 0o644)
        self.backup = self.dir / "backup.sql.gz"
        self.backup.write_bytes(b"synthetic backup bytes " * 50)
        self.touch_backup(NOW - timedelta(hours=2))
        self.svc_env = self.dir / "service.env"
        self.svc_env.write_text("SOME_OTHER=1\n", encoding="utf-8")
        self.ledger = self.dir / "ledger.jsonl"
        self.env = mig.ProductionEnv(
            now_fn=lambda: NOW, host_fn=lambda: "prod-host-1", git_fn=lambda _root: ("a" * 40, True),
            trusted_uids=frozenset({EUID}),
        )
        self.url = f"sqlite+aiosqlite:///{self.dir / 'prod.db'}"
        self.engine = mig.make_engine(self.url)
        async with self.engine.begin() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text(
                "CREATE TABLE tenant (tenant_id VARCHAR(64) PRIMARY KEY, name VARCHAR(100), "
                "wx_api_key_v3 VARCHAR(256), wx_private_key TEXT, updated_at VARCHAR(32))"))
            await conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            await conn.execute(text("INSERT INTO alembic_version VALUES ('20261009_0001')"))
            for tid, api, pem in (("t1", API[0], PEMS[0]), ("t2", API[1], PEMS[1])):
                await conn.execute(text("INSERT INTO tenant VALUES (:t, :n, :a, :p, '2026-01-01 00:00:00')"),
                                   {"t": tid, "n": f"n-{tid}", "a": api, "p": pem})
        crypto.get_keyring.cache_clear()

    async def asyncTearDown(self):
        await self.engine.dispose()
        (settings.WXPAY_SECRET_KEYRING_PATH, settings.WXPAY_ENVELOPE_WRITE_ENABLED,
         settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED, crypto.KEYRING_SOURCE_POLICY) = self.saved
        crypto.get_keyring.cache_clear()
        shutil.rmtree(self.dir, ignore_errors=True)

    # ---- helpers
    def write_keyring(self, key_id: str):
        self.keys.setdefault(key_id, Fernet.generate_key())
        self.keyring.write_text(json.dumps({"formatVersion": 1, "activeKeyId": key_id, "keys": [
            {"keyId": key_id, "algorithm": "fernet", "usage": "encrypt-decrypt", "key": self.keys[key_id].decode()}]}), encoding="utf-8")
        os.chmod(self.keyring, 0o600)
        settings.WXPAY_SECRET_KEYRING_PATH = str(self.keyring)
        crypto.get_keyring.cache_clear()

    def touch_backup(self, moment: datetime):
        os.utime(self.backup, (moment.timestamp(), moment.timestamp()))

    async def table(self):
        async with self.engine.connect() as conn:
            return {r[0]: tuple(r[1:]) for r in (await conn.execute(text("SELECT tenant_id, name, wx_api_key_v3, wx_private_key, updated_at FROM tenant ORDER BY tenant_id"))).all()}

    async def issue(self, *, tenant="t1", fields=("wx_api_key_v3", "wx_private_key"), mutate=None, private_pem=None,
                    issued=NOW, ttl=30, name="grant.json") -> Path:
        facts, _ = await mig.compute_plan(self.engine, tenant, list(fields), self.env, "repo", str(self.backup), str(self.svc_env))
        grant = authority.new_grant(
            host="prod-host-1", tenant_id=tenant, fields=list(fields), backend_sha=facts.backend_sha,
            alembic_revision=facts.alembic_revision, db_fingerprint=facts.db_fingerprint, plan_digest=facts.plan_digest,
            keyring_active_key_id=facts.keyring_active_key_id, backup_path=str(self.backup), backup_sha256=facts.backup.sha256,
            recovery_attested_at=authority.iso(NOW - timedelta(days=5)), now=issued, ttl_minutes=ttl,
        )
        grant.update(mutate or {})
        path = self.dir / name
        path.write_text(json.dumps(authority.sign_grant(private_pem or self.private_pem, grant)), encoding="utf-8")
        return path

    async def prod(self, grant, tenants=("t1",), cli_fields=None, hooks=None, env=None):
        return await mig.run_production(
            self.engine, grant_path=str(grant), pubkey_path=str(self.pubkey), ledger_path=str(self.ledger),
            tenant_ids=list(tenants), cli_fields=cli_fields, repo_root="repo", service_env_path=str(self.svc_env),
            env=env or self.env, hooks=hooks,
        )

    async def assert_refused(self, reason, grant, **kwargs):
        before = await self.table()
        ledger_before = self.ledger.read_text() if self.ledger.exists() else ""
        with self.assertRaises(authority.AuthorityRefused) as caught:
            await self.prod(grant, **kwargs)
        self.assertEqual(caught.exception.reason, reason)
        self.assertEqual(await self.table(), before, f"{reason}: database must be untouched")
        ledger_after = self.ledger.read_text() if self.ledger.exists() else ""
        self.assertEqual(ledger_after, ledger_before, f"{reason}: a refused run must not consume the grant")


class GrantValidationTest(ProductionBase):
    async def test_missing_grant_file_and_missing_or_untrusted_authority_key(self):
        await self.assert_refused("GRANT_MISSING", self.dir / "absent.json")
        grant = await self.issue()
        self.pubkey.unlink()
        await self.assert_refused("AUTHORITY_KEY_MISSING", grant)
        self.pubkey.write_bytes(authority.generate_keypair()[1])
        os.chmod(self.pubkey, 0o666)
        await self.assert_refused("AUTHORITY_KEY_UNTRUSTED", grant)
        os.chmod(self.pubkey, 0o644)
        wrong_owner = mig.ProductionEnv(now_fn=self.env.now_fn, host_fn=self.env.host_fn, git_fn=self.env.git_fn, trusted_uids=frozenset({EUID + 1}))
        await self.assert_refused("AUTHORITY_KEY_UNTRUSTED", grant, env=wrong_owner)

    async def test_bad_signature_tampering_and_foreign_key_are_rejected(self):
        grant = await self.issue()
        document = json.loads(grant.read_text())
        document["grant"]["tenant_id"] = "t2"  # edited after signing
        tampered = self.dir / "tampered.json"
        tampered.write_text(json.dumps(document))
        await self.assert_refused("GRANT_SIGNATURE_INVALID", tampered, tenants=("t2",))
        foreign_private, _ = authority.generate_keypair()
        await self.assert_refused("GRANT_SIGNATURE_INVALID", await self.issue(private_pem=foreign_private, name="foreign.json"))
        malformed = self.dir / "malformed.json"
        malformed.write_text("{not json")
        await self.assert_refused("GRANT_MALFORMED", malformed)
        extra = json.loads(grant.read_text())
        extra["grant"]["bonus"] = 1
        (self.dir / "extra.json").write_text(json.dumps(extra))
        await self.assert_refused("GRANT_MALFORMED", self.dir / "extra.json")

    async def test_expired_not_yet_valid_and_overlong_grants_are_rejected(self):
        grant = await self.issue(ttl=30)
        later = mig.ProductionEnv(now_fn=lambda: NOW + timedelta(minutes=31), host_fn=self.env.host_fn, git_fn=self.env.git_fn, trusted_uids=self.env.trusted_uids)
        await self.assert_refused("GRANT_EXPIRED", grant, env=later)
        earlier = mig.ProductionEnv(now_fn=lambda: NOW - timedelta(minutes=10), host_fn=self.env.host_fn, git_fn=self.env.git_fn, trusted_uids=self.env.trusted_uids)
        await self.assert_refused("GRANT_NOT_YET_VALID", grant, env=earlier)
        overlong = await self.issue(mutate={"expires_at": authority.iso(NOW + timedelta(hours=2))}, name="long.json")
        await self.assert_refused("GRANT_LIFETIME_INVALID", overlong)

    async def test_grant_naming_a_non_whitelisted_field_or_wildcard_tenant_is_rejected(self):
        await self.assert_refused("GRANT_FIELD_NOT_ALLOWED", await self.issue(mutate={"fields": ["name"]}, name="f1.json"))
        await self.assert_refused("GRANT_FIELD_NOT_ALLOWED", await self.issue(mutate={"fields": ["wx_api_key_v3", "updated_at"]}, name="f2.json"))
        await self.assert_refused("GRANT_FIELD_NOT_ALLOWED", await self.issue(mutate={"fields": []}, name="f3.json"))
        await self.assert_refused("GRANT_TENANT_INVALID", await self.issue(mutate={"tenant_id": "*"}, name="w1.json"), tenants=("*",))
        await self.assert_refused("GRANT_TENANT_INVALID", await self.issue(mutate={"tenant_id": "t1,t2"}, name="w2.json"), tenants=("t1,t2",))


class ScopeAndBindingTest(ProductionBase):
    async def test_batch_and_wrong_tenant_and_unauthorized_field_are_rejected_before_any_database_access(self):
        grant = await self.issue()
        await self.assert_refused("TENANT_SCOPE_NOT_SINGLE", grant, tenants=("t1", "t2"))
        await self.assert_refused("TENANT_SCOPE_NOT_SINGLE", grant, tenants=())
        await self.assert_refused("TENANT_MISMATCH", grant, tenants=("t2",))
        partial = await self.issue(fields=("wx_api_key_v3",), name="partial.json")
        await self.assert_refused("GRANT_FIELD_NOT_ALLOWED", partial, cli_fields=["wx_private_key"])
        await self.assert_refused("FIELD_NOT_WHITELISTED", grant, cli_fields=["name"])

    async def test_every_binding_mismatch_is_refused_with_its_own_stable_code(self):
        cases = [
            ("HOST_MISMATCH", {"host": "other-host"}),
            ("DB_FINGERPRINT_MISMATCH", {"db_fingerprint": "0" * 64}),
            ("BACKEND_SHA_MISMATCH", {"backend_sha": "b" * 40}),
            ("ALEMBIC_MISMATCH", {"alembic_revision": "20260101_0001"}),
            ("KEYRING_KEY_ID_MISMATCH", {"keyring_active_key_id": "wxpay-1999-01"}),
            ("BACKUP_HASH_MISMATCH", {"backup_sha256": "c" * 64}),
            ("BACKUP_UNAVAILABLE", {"backup_path": str(self.dir / "no-such-backup")}),
            ("RECOVERY_ATTESTATION_STALE", {"recovery_attested_at": authority.iso(NOW - timedelta(days=200))}),
            ("PLAN_DIGEST_MISMATCH", {"plan_digest": "d" * 64}),
        ]
        for index, (reason, mutate) in enumerate(cases):
            with self.subTest(reason):
                await self.assert_refused(reason, await self.issue(mutate=mutate, name=f"b{index}.json"))

    async def test_dirty_worktree_and_stale_backup_and_keyring_and_service_flag(self):
        grant = await self.issue()
        dirty = mig.ProductionEnv(now_fn=self.env.now_fn, host_fn=self.env.host_fn, git_fn=lambda _r: ("a" * 40, False), trusted_uids=self.env.trusted_uids)
        await self.assert_refused("WORKTREE_DIRTY", grant, env=dirty)

        self.touch_backup(NOW - timedelta(days=3))
        await self.assert_refused("BACKUP_STALE", grant)
        self.touch_backup(NOW - timedelta(hours=2))

        self.svc_env.write_text("WXPAY_ENVELOPE_WRITE_ENABLED=true\n", encoding="utf-8")
        await self.assert_refused("SERVICE_WRITE_FLAG_ON", grant)
        self.svc_env.write_text("SOME_OTHER=1\n", encoding="utf-8")

        settings.WXPAY_ENVELOPE_WRITE_ENABLED = False
        await self.assert_refused("EXECUTOR_WRITE_FLAG_OFF", grant)
        settings.WXPAY_ENVELOPE_WRITE_ENABLED = True

        self.keyring.unlink()
        crypto.get_keyring.cache_clear()
        await self.assert_refused("KEYRING_UNAVAILABLE", grant)

    async def test_production_database_must_not_carry_the_rehearsal_marker(self):
        grant = await self.issue()
        async with self.engine.begin() as conn:
            await conn.execute(text(f"CREATE TABLE {mig.MARKER_TABLE} (purpose VARCHAR(64))"))
        await self.assert_refused("REHEARSAL_MARKER_PRESENT_IN_PRODUCTION", grant)

    async def test_state_drift_after_issuance_invalidates_the_plan_digest(self):
        grant = await self.issue()
        async with self.engine.begin() as conn:  # a merchant edited their key after the owner approved the plan
            await conn.execute(text("UPDATE tenant SET wx_api_key_v3 = :v WHERE tenant_id = 't1'"), {"v": "Q" * 32})
        await self.assert_refused("PLAN_DIGEST_MISMATCH", grant)


class ExecutionTest(ProductionBase):
    async def test_authorized_run_migrates_exactly_the_one_tenant_and_burns_the_grant(self):
        grant = await self.issue()
        before = await self.table()
        report = await self.prod(grant)
        after = await self.table()
        self.assertEqual((report.tenants_migrated, report.fields_updated, report.decrypt_match_count, report.tenants_failed), (1, 2, 2, 0))
        self.assertTrue(after["t1"][1].startswith("enc:v1:wxpay-2026-10:") and after["t1"][2].startswith("enc:v1:wxpay-2026-10:"))
        self.assertEqual(after["t2"], before["t2"])  # the other tenant is untouched
        self.assertEqual((after["t1"][0], after["t1"][3]), (before["t1"][0], before["t1"][3]))  # non-secret columns
        events = [json.loads(line) for line in self.ledger.read_text().splitlines()]
        self.assertEqual([e["event"] for e in events], ["consumed", "finished"])
        self.assertEqual(events[1]["outcome"], "OK")
        self.assertEqual(oct(os.stat(self.ledger).st_mode & 0o777), "0o600")
        blob = json.dumps(report.events) + json.dumps(report.summary()) + self.ledger.read_text()
        for secret in API + PEMS + [PEMS[0].splitlines()[1]]:
            self.assertNotIn(secret, blob)

    async def test_grant_is_single_use_and_reuse_is_reported_first(self):
        grant = await self.issue()
        await self.prod(grant)
        ledger_text = self.ledger.read_text()
        with self.assertRaises(authority.AuthorityRefused) as caught:
            await self.prod(grant)
        self.assertEqual(caught.exception.reason, "GRANT_REUSED")  # even though the state also drifted
        self.assertEqual(self.ledger.read_text(), ledger_text)

    async def test_completed_tenant_rerun_with_a_fresh_grant_is_an_idempotent_noop(self):
        await self.prod(await self.issue(name="first.json"))
        done = await self.table()
        report = await self.prod(await self.issue(name="second.json"))
        self.assertEqual((report.fields_updated, report.tenants_migrated, report.tenants_noop), (0, 0, 1))
        self.assertEqual(await self.table(), done)  # byte-identical: nothing re-encrypted

    async def test_partial_field_grant_leaves_the_other_field_exactly_as_it_was(self):
        grant = await self.issue(fields=("wx_api_key_v3",), name="partial.json")
        before = await self.table()
        report = await self.prod(grant, cli_fields=["wx_api_key_v3"])
        after = await self.table()
        self.assertEqual(report.fields_updated, 1)
        self.assertTrue(after["t1"][1].startswith("enc:v1:"))
        self.assertEqual(after["t1"][2], before["t1"][2])  # private key stayed plaintext

    async def test_crash_before_the_first_write_burns_the_grant_and_a_new_grant_completes(self):
        grant = await self.issue(name="crash.json")
        before = await self.table()

        async def die(_tid):
            raise Crash()

        with self.assertRaises(Crash):
            await self.prod(grant, hooks=mig.Hooks(before_update=die))
        self.assertEqual(await self.table(), before)  # atomic: nothing half-migrated
        entries = [json.loads(line) for line in self.ledger.read_text().splitlines()]
        self.assertEqual(entries[-1]["outcome"], "CRASHED_OR_INTERRUPTED")
        with self.assertRaises(authority.AuthorityRefused) as caught:
            await self.prod(grant)  # the burned grant cannot be replayed
        self.assertEqual(caught.exception.reason, "GRANT_REUSED")
        report = await self.prod(await self.issue(name="recovery.json"))  # a newly issued grant recovers
        self.assertEqual(report.tenants_migrated, 1)

    async def test_hard_kill_leaves_only_a_consumed_entry_and_still_blocks_replay(self):
        grant = await self.issue(name="killed.json")
        loaded = json.loads(grant.read_text())["grant"]
        ledger = authority.Ledger(str(self.ledger), frozenset({EUID}))
        ledger.consume(loaded["grant_id"], "hash", NOW)  # the process dies right here: no finish()
        os.close(ledger.fd)  # (lock released by process death)
        with self.assertRaises(authority.AuthorityRefused) as caught:
            await self.prod(grant)
        self.assertEqual(caught.exception.reason, "GRANT_REUSED")

    async def test_encrypt_failure_in_production_mode_rolls_back_and_stops(self):
        grant = await self.issue(name="fail.json")
        before = await self.table()

        def flaky(value, field):
            raise crypto.SecretEncryptionUnavailable("WXPAY_SECRET_ENCRYPTION_FAILED")

        report = await self.prod(grant, hooks=mig.Hooks(encrypt=flaky))
        self.assertEqual((report.tenants_failed, report.fields_updated), (1, 0))
        self.assertEqual(await self.table(), before)
        self.assertEqual(json.loads(self.ledger.read_text().splitlines()[-1])["outcome"], "FAILED")
        self.assertEqual(mig.exit_code(report), mig.EXIT_FAILED)


class LedgerAndGuardsTest(ProductionBase):
    async def test_ledger_lock_blocks_a_second_concurrent_run_and_untrusted_ledger_is_refused(self):
        first = authority.Ledger(str(self.ledger), frozenset({EUID}))
        first.consume("g-1", "h", NOW)
        second = authority.Ledger(str(self.ledger), frozenset({EUID}))
        with self.assertRaises(authority.AuthorityRefused) as caught:
            second.consume("g-2", "h", NOW)
        self.assertEqual(caught.exception.reason, "LEDGER_LOCKED")
        first.finish("OK", NOW)
        loose = self.dir / "loose-ledger.jsonl"
        loose.write_text("")
        os.chmod(loose, 0o644)
        with self.assertRaises(authority.AuthorityRefused) as caught:
            authority.Ledger(str(loose), frozenset({EUID})).consume("g-3", "h", NOW)
        self.assertEqual(caught.exception.reason, "LEDGER_UNTRUSTED")

    async def test_cli_refuses_production_without_apply_grant_or_with_batch_options(self):
        out = io.StringIO()
        env = {mig.URL_ENV: self.url}
        with contextlib.redirect_stdout(out), patch.dict(os.environ, env):
            self.assertEqual(mig.main(["--mode", "apply", "--target", "production"]), mig.EXIT_REFUSED)
            self.assertEqual(mig.main(["--mode", "apply", "--apply", "--target", "production", "--tenant-id", "t1"]), mig.EXIT_REFUSED)
            self.assertEqual(mig.main(["--mode", "apply", "--apply", "--target", "production", "--continue-on-failure", "--grant-file", "x"]), mig.EXIT_REFUSED)
            self.assertEqual(mig.main(["--mode", "apply", "--apply", "--target", "production", "--retry-conflicts", "1", "--grant-file", "x"]), mig.EXIT_REFUSED)
            self.assertEqual(mig.main(["--mode", "plan", "--tenant-id", "t1"]), mig.EXIT_REFUSED)
        reasons = [json.loads(line)["reason"] for line in out.getvalue().splitlines()]
        self.assertEqual(reasons, ["APPLY_FLAG_MISSING", "GRANT_MISSING", "OPTION_NOT_ALLOWED_IN_PRODUCTION",
                                   "OPTION_NOT_ALLOWED_IN_PRODUCTION", "PLAN_NEEDS_ONE_TENANT_AND_FIELDS"])

    async def test_rehearsal_mode_still_works_only_on_a_marked_database_and_never_bypasses_production_checks(self):
        before = await self.table()
        with patch.dict(os.environ, {mig.ACK_ENV: mig.ACK_VALUE}):
            with self.assertRaises(mig.Refused) as caught:  # unmarked == production-like: rehearsal cannot write
                await mig.run(self.engine, "apply", app_database_url="sqlite+aiosqlite:///other", target_url=self.url)
        self.assertEqual(caught.exception.reason, "REHEARSAL_MARKER_MISSING")
        self.assertEqual(await self.table(), before)
        async with self.engine.begin() as conn:
            await conn.execute(text(f"CREATE TABLE {mig.MARKER_TABLE} (purpose VARCHAR(64))"))
            await conn.execute(text(f"INSERT INTO {mig.MARKER_TABLE} VALUES (:p)"), {"p": mig.MARKER_PURPOSE})
        with patch.dict(os.environ, {mig.ACK_ENV: mig.ACK_VALUE}):
            report = await mig.run(self.engine, "apply", app_database_url="sqlite+aiosqlite:///other", target_url=self.url)
        self.assertEqual(report.fields_updated, 4)  # REHEARSAL on a marked database works, as in B2
        # ...and that same marked database is refused in PRODUCTION mode even with a perfectly valid grant
        self.assertTrue(await mig.marker_present(self.engine))

    async def test_plan_mode_is_read_only_and_exposes_no_secret(self):
        before = await self.table()
        facts, formats = await mig.compute_plan(self.engine, "t1", ["wx_api_key_v3", "wx_private_key"], self.env, "repo", str(self.backup), str(self.svc_env))
        self.assertEqual(formats, {"wx_api_key_v3": "LEGACY_PLAINTEXT", "wx_private_key": "LEGACY_PLAINTEXT"})
        self.assertEqual(len(facts.plan_digest), 64)
        self.assertEqual(await self.table(), before)
        self.assertNotIn(API[0], json.dumps({"digest": facts.plan_digest, "formats": formats, "fp": facts.db_fingerprint}))

    def test_nothing_in_the_application_can_trigger_a_migration(self):
        app_dir = Path(__file__).resolve().parents[1] / "app"
        offenders = [str(p) for p in app_dir.rglob("*.py")
                     if "wxpay_secret_migrate" in p.read_text(encoding="utf-8", errors="replace")
                     or "wxpay_migration_authority" in p.read_text(encoding="utf-8", errors="replace")]
        self.assertEqual(offenders, [])


class AuthorityLibraryTest(unittest.TestCase):
    def test_sign_verify_roundtrip_with_a_passphrase_protected_key(self):
        private_pem, public_pem = authority.generate_keypair(passphrase=b"test-pass")
        public = serialization.load_pem_public_key(public_pem)
        grant = authority.new_grant(
            host="h", tenant_id="t", fields=["wx_api_key_v3"], backend_sha="a" * 40, alembic_revision="r",
            db_fingerprint="b" * 64, plan_digest="c" * 64, keyring_active_key_id="k", backup_path="/b", backup_sha256="d" * 64,
            recovery_attested_at=authority.iso(NOW), now=NOW, ttl_minutes=999,
        )
        self.assertLessEqual(datetime.strptime(grant["expires_at"], "%Y-%m-%dT%H:%M:%SZ") - datetime.strptime(grant["issued_at"], "%Y-%m-%dT%H:%M:%SZ"), timedelta(hours=1))
        document = authority.sign_grant(private_pem, grant, passphrase=b"test-pass")
        self.assertEqual(authority.verify_grant_document(document, public, NOW)["tenant_id"], "t")
        with self.assertRaises(Exception):
            authority.sign_grant(private_pem, grant, passphrase=b"wrong")

    def test_plan_digest_changes_with_every_bound_input(self):
        base = dict(host="h", backend_sha="a" * 40, alembic_revision="r", db_fingerprint="f" * 64, keyring_active_key_id="k",
                    tenant_id="t", fields=["wx_api_key_v3"], field_formats={"wx_api_key_v3": "LEGACY_PLAINTEXT"},
                    old_value_hashes={"wx_api_key_v3": authority.hash_value("one")})
        digest = authority.plan_digest(**base)
        self.assertEqual(digest, authority.plan_digest(**base))
        for key, value in (("host", "h2"), ("backend_sha", "b" * 40), ("alembic_revision", "r2"), ("db_fingerprint", "e" * 64),
                           ("keyring_active_key_id", "k2"), ("tenant_id", "t2"), ("fields", ["wx_private_key"]),
                           ("field_formats", {"wx_api_key_v3": "VERSIONED_ENVELOPE"}),
                           ("old_value_hashes", {"wx_api_key_v3": authority.hash_value("two")})):
            self.assertNotEqual(digest, authority.plan_digest(**{**base, key: value}), key)


class GrantToolTest(unittest.TestCase):
    PLAN = {
        "event": "plan", "host": "prod-host-1", "backend_sha": "a" * 40, "worktree_clean": True,
        "alembic_revision": "20261009_0001", "db_fingerprint": "f" * 64, "keyring_active_key_id": "wxpay-2026-10",
        "service_write_flag": "ABSENT", "tenant_id": "t1", "fields": ["wx_api_key_v3"], "field_formats": {},
        "plan_digest": "c" * 64, "rehearsal_marker_present": False,
    }

    def build(self, **overrides):
        plan = {**self.PLAN, **overrides}
        return grant_tool.build_grant_from_plan(
            plan, backup_path="/root/backups/x.sql.gz", backup_sha256="d" * 64,
            recovery_attested_at=authority.iso(NOW), now=NOW,
        )

    def test_a_clean_plan_becomes_a_narrow_grant_that_verifies(self):
        private_pem, public_pem = authority.generate_keypair()
        grant = self.build()
        self.assertEqual((grant["tenant_id"], grant["fields"], grant["plan_digest"]), ("t1", ["wx_api_key_v3"], "c" * 64))
        document = authority.sign_grant(private_pem, grant)
        public = serialization.load_pem_public_key(public_pem)
        self.assertEqual(authority.verify_grant_document(document, public, NOW)["grant_id"], grant["grant_id"])
        self.assertFalse([v for v in grant.values() if isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_-]{43}=", v)])  # no Fernet-key-shaped value

    def test_a_grant_is_never_built_from_an_unsafe_or_foreign_plan(self):
        for overrides in ({"worktree_clean": False}, {"rehearsal_marker_present": True}, {"service_write_flag": "TRUE"},
                          {"keyring_active_key_id": None}, {"event": "refused"}):
            with self.subTest(overrides), self.assertRaises(ValueError):
                self.build(**overrides)
        with self.assertRaises(ValueError):
            grant_tool.build_grant_from_plan({"event": "plan"}, backup_path="/b", backup_sha256="d" * 64,
                                             recovery_attested_at=authority.iso(NOW), now=NOW)


if __name__ == "__main__":
    unittest.main()
