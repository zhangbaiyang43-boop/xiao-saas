"""Logic tests for the B2 isolated-rehearsal migration executor (SQLite; no MySQL needed).

Real-MySQL semantics (byte-exact CAS, InnoDB rollback, killed connections) live in
test_wxpay_secret_migration_schema_mysql.py.  Everything here is synthetic.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
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

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "wxpay_secret_migrate.py"
_spec = importlib.util.spec_from_file_location("wxpay_secret_migrate", SCRIPT)
mig = importlib.util.module_from_spec(_spec)
sys.modules["wxpay_secret_migrate"] = mig
_spec.loader.exec_module(mig)

POSIX = hasattr(os, "geteuid") and hasattr(os, "O_NOFOLLOW")
EUID = os.geteuid() if POSIX else 0
TEST_POLICY = crypto.KeyringSourcePolicy(extra_trusted_uids=frozenset({EUID}), verify_ancestors=False)
ACK = {mig.ACK_ENV: mig.ACK_VALUE}


def _pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


PEMS = [_pem(), _pem(), _pem()]
APIS = ["A" * 32, "B1" * 16, "Zz9!" * 8]


class Crash(BaseException):
    """Simulates the migration process dying (not an Exception on purpose)."""


@unittest.skipUnless(POSIX, "keyring trust policy is POSIX-only")
class ExecutorBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.saved = (
            settings.WXPAY_SECRET_KEYRING_PATH, settings.WXPAY_ENVELOPE_WRITE_ENABLED,
            settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED, crypto.KEYRING_SOURCE_POLICY,
        )
        crypto.KEYRING_SOURCE_POLICY = TEST_POLICY
        settings.WXPAY_ENVELOPE_WRITE_ENABLED = True
        settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED = True
        self.dir = Path(os.path.realpath(tempfile.mkdtemp(prefix="wxpay-mig-")))
        self.keyring_path = self.dir / "keyring.json"
        self.write_keyring([("key-a", "encrypt-decrypt")], active="key-a")
        self.db_path = self.dir / "gate.db"
        self.url = f"sqlite+aiosqlite:///{self.db_path}"
        self.engine = mig.make_engine(self.url)
        async with self.engine.begin() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text(
                "CREATE TABLE tenant (tenant_id VARCHAR(64) PRIMARY KEY, name VARCHAR(100), "
                "wx_api_key_v3 VARCHAR(256), wx_private_key TEXT, updated_at VARCHAR(32))"
            ))
            await conn.execute(text(f"CREATE TABLE {mig.MARKER_TABLE} (purpose VARCHAR(64))"))
            await conn.execute(text(f"INSERT INTO {mig.MARKER_TABLE} VALUES (:p)"), {"p": mig.MARKER_PURPOSE})
        crypto.get_keyring.cache_clear()

    async def asyncTearDown(self):
        await self.engine.dispose()
        settings.WXPAY_SECRET_KEYRING_PATH, settings.WXPAY_ENVELOPE_WRITE_ENABLED, settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED, crypto.KEYRING_SOURCE_POLICY = self.saved
        crypto.get_keyring.cache_clear()
        shutil.rmtree(self.dir, ignore_errors=True)

    # -- helpers -----------------------------------------------------------------
    def write_keyring(self, keys, active: str, mode: int = 0o600):
        self.keys = getattr(self, "keys", {})
        entries = []
        for key_id, usage in keys:
            self.keys.setdefault(key_id, Fernet.generate_key())
            entries.append({"keyId": key_id, "algorithm": "fernet", "usage": usage, "key": self.keys[key_id].decode()})
        self.keyring_path.write_text(json.dumps({"formatVersion": 1, "activeKeyId": active, "keys": entries}), encoding="utf-8")
        os.chmod(self.keyring_path, mode)
        settings.WXPAY_SECRET_KEYRING_PATH = str(self.keyring_path)

    async def seed(self, rows):
        async with self.engine.begin() as conn:
            for tid, api, pem in rows:
                await conn.execute(
                    text("INSERT INTO tenant VALUES (:t, :n, :a, :p, '2026-01-01 00:00:00')"),
                    {"t": tid, "n": f"name-{tid}", "a": api, "p": pem},
                )

    async def table(self):
        async with self.engine.connect() as conn:
            return {r[0]: tuple(r[1:]) for r in (await conn.execute(text("SELECT tenant_id, name, wx_api_key_v3, wx_private_key, updated_at FROM tenant ORDER BY tenant_id"))).all()}

    async def run_mig(self, mode="apply", **kwargs):
        with patch.dict(os.environ, ACK):
            return await mig.run(self.engine, mode, app_database_url="sqlite+aiosqlite:///other", target_url=self.url, **kwargs)

    def no_secret_in(self, report):
        blob = json.dumps(report.events) + json.dumps(report.summary())
        for secret in APIS + PEMS:
            self.assertNotIn(secret, blob)
            self.assertNotIn(secret.strip().splitlines()[1] if "\n" in secret else secret, blob)
        self.assertNotIn(self.keys["key-a"].decode(), blob)


class SafetyGuardTest(ExecutorBase):
    async def test_dry_run_is_the_default_and_never_writes_or_prints_secrets(self):
        await self.seed([("t1", APIS[0], PEMS[0]), ("t2", APIS[1], PEMS[1])])
        before = await self.table()
        report = await mig.run(self.engine)
        self.assertEqual(report.mode, "dry-run")
        self.assertEqual(report.fields_expected, 4)
        self.assertEqual(report.fields_updated, 0)
        self.assertEqual(await self.table(), before)
        self.no_secret_in(report)

    async def test_apply_requires_every_guard_and_leaves_the_database_untouched_when_refused(self):
        await self.seed([("t1", APIS[0], PEMS[0])])
        before = await self.table()
        kw = dict(app_database_url="sqlite+aiosqlite:///other", target_url=self.url)

        with self.assertRaises(mig.Refused) as caught:  # no acknowledgement
            await mig.run(self.engine, "apply", **kw)
        self.assertEqual(caught.exception.reason, "ISOLATED_WRITE_ACK_MISSING")

        with patch.dict(os.environ, ACK):
            with self.assertRaises(mig.Refused) as caught:  # target == application database
                await mig.run(self.engine, "apply", app_database_url=self.url, target_url=self.url)
            self.assertEqual(caught.exception.reason, "TARGET_EQUALS_APPLICATION_DATABASE")

            async with self.engine.begin() as conn:
                await conn.execute(text(f"DELETE FROM {mig.MARKER_TABLE}"))
            with self.assertRaises(mig.Refused) as caught:  # marker row missing
                await mig.run(self.engine, "apply", **kw)
            self.assertEqual(caught.exception.reason, "REHEARSAL_MARKER_INVALID")
            async with self.engine.begin() as conn:
                await conn.execute(text(f"DROP TABLE {mig.MARKER_TABLE}"))
            with self.assertRaises(mig.Refused) as caught:  # production-like: no marker table at all
                await mig.run(self.engine, "apply", **kw)
            self.assertEqual(caught.exception.reason, "REHEARSAL_MARKER_MISSING")
        self.assertEqual(await self.table(), before)

    async def test_write_flag_off_and_keyring_problems_refuse_before_any_write(self):
        await self.seed([("t1", APIS[0], PEMS[0])])
        before = await self.table()
        settings.WXPAY_ENVELOPE_WRITE_ENABLED = False
        with self.assertRaises(mig.Refused) as caught:
            await self.run_mig()
        self.assertEqual(caught.exception.reason, "ENVELOPE_WRITE_FLAG_OFF")
        settings.WXPAY_ENVELOPE_WRITE_ENABLED = True

        for label, prepare, expected in (
            ("missing", lambda: self.keyring_path.unlink(), "WXPAY_KEYRING_MISSING"),
            ("permission", lambda: (self.write_keyring([("key-a", "encrypt-decrypt")], "key-a"), os.chmod(self.keyring_path, 0o644)), "WXPAY_KEYRING_PERMISSION_DENIED"),
            ("active_key_invalid", lambda: (self.write_keyring([("key-a", "encrypt-decrypt")], "key-a"), self.keyring_path.write_text(json.dumps({"formatVersion": 1, "activeKeyId": "ghost", "keys": [{"keyId": "key-a", "algorithm": "fernet", "usage": "encrypt-decrypt", "key": self.keys["key-a"].decode()}]})), os.chmod(self.keyring_path, 0o600)), "WXPAY_KEYRING_ACTIVE_KEY_INVALID"),
        ):
            with self.subTest(label):
                crypto.get_keyring.cache_clear()
                prepare()
                with self.assertRaises(mig.Refused) as caught:
                    await self.run_mig()
                self.assertEqual(caught.exception.reason, expected)
                self.assertEqual(await self.table(), before)

    def test_cli_refuses_without_apply_flag_or_target_env(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch.dict(os.environ, {}, clear=False):
            os.environ.pop(mig.URL_ENV, None)
            self.assertEqual(mig.main(["--mode", "apply"]), mig.EXIT_REFUSED)
            self.assertEqual(mig.main(["--mode", "dry-run"]), mig.EXIT_REFUSED)
        self.assertIn("APPLY_FLAG_MISSING", out.getvalue())
        self.assertIn("TARGET_URL_ENV_MISSING", out.getvalue())

    def test_only_the_two_secret_columns_are_whitelisted(self):
        self.assertEqual([c for c, _ in mig.FIELDS], ["wx_api_key_v3", "wx_private_key"])

    def test_mysql_cas_is_byte_exact_not_collation_equal(self):
        mysql_engine = create_async_engine("mysql+asyncmy://u@localhost/db")
        self.assertIn("BINARY wx_private_key", mig._cas_clause(mysql_engine, "wx_private_key", "old_1"))
        self.assertIn("<=>", mig._cas_clause(mysql_engine, "wx_private_key", "old_1"))
        self.assertNotIn("BINARY", mig._cas_clause(self.engine, "wx_private_key", "old_1"))


class MigrationBehaviourTest(ExecutorBase):
    async def test_migrates_four_fields_and_reader_returns_the_original_secrets(self):
        await self.seed([("t1", APIS[0], PEMS[0]), ("t2", APIS[1], PEMS[1])])
        before = await self.table()
        report = await self.run_mig()
        after = await self.table()
        self.assertEqual((report.tenants_migrated, report.fields_expected, report.fields_updated, report.decrypt_match_count), (2, 4, 4, 4))
        self.assertEqual((report.tenants_failed, report.tenants_conflict, report.tenants_rejected), (0, 0, 0))
        for tid, (name, api, pem, updated) in after.items():
            self.assertEqual((name, updated), (before[tid][0], before[tid][3]))  # non-secret columns untouched
            self.assertTrue(api.startswith("enc:v1:key-a:") and pem.startswith("enc:v1:key-a:"))
            self.assertEqual(crypto.decrypt_secret(api, crypto.SecretField.API_V3_KEY, allow_legacy_plaintext=False), before[tid][1])
            self.assertEqual(crypto.decrypt_secret(pem, crypto.SecretField.PRIVATE_KEY, allow_legacy_plaintext=False), before[tid][2])
        self.no_secret_in(report)

    async def test_second_run_is_a_noop_and_never_reencrypts(self):
        await self.seed([("t1", APIS[0], PEMS[0])])
        await self.run_mig()
        first = await self.table()
        report = await self.run_mig()
        self.assertEqual((report.fields_updated, report.tenants_migrated, report.tenants_noop), (0, 0, 1))
        self.assertEqual(await self.table(), first)  # byte-identical: tokens were not regenerated

    async def test_existing_envelope_field_is_kept_and_only_plaintext_field_migrates(self):
        done = crypto.encrypt_secret(APIS[0], crypto.SecretField.API_V3_KEY)
        await self.seed([("t1", done, PEMS[0])])
        await self.run_mig()
        _, api, pem, _ = (await self.table())["t1"]
        self.assertEqual(api, done)
        self.assertTrue(pem.startswith("enc:v1:"))

    async def test_empty_fields_are_left_alone(self):
        await self.seed([("t1", None, PEMS[0]), ("t2", "", "")])
        report = await self.run_mig()
        table = await self.table()
        self.assertIsNone(table["t1"][1])
        self.assertEqual(table["t2"][1:3], ("", ""))
        self.assertEqual(report.fields_updated, 1)

    async def test_unknown_or_raw_fernet_rejects_the_whole_tenant_and_nothing_changes(self):
        raw = Fernet(Fernet.generate_key()).encrypt(APIS[0].encode()).decode()
        await self.seed([("t1", APIS[0], PEMS[0]), ("t2", raw, PEMS[1]), ("t3", APIS[2], "not-a-pem")])
        before = await self.table()
        report = await self.run_mig(stop_on_failure=False)
        after = await self.table()
        self.assertEqual((report.tenants_migrated, report.tenants_rejected), (1, 2))
        self.assertEqual(after["t2"], before["t2"])  # valid pem of a rejected tenant is NOT migrated either
        self.assertEqual(after["t3"], before["t3"])
        self.assertTrue(after["t1"][1].startswith("enc:v1:"))

    async def test_failure_stops_the_run_by_default_and_never_skips_silently(self):
        await self.seed([("t1", APIS[0], "not-a-pem"), ("t2", APIS[1], PEMS[1])])
        report = await self.run_mig()
        self.assertTrue(report.stopped_early)
        self.assertEqual(mig.exit_code(report), mig.EXIT_FAILED)
        self.assertEqual((await self.table())["t2"][1], APIS[1])  # stopped before t2


class AtomicityAndRecoveryTest(ExecutorBase):
    async def test_second_field_encrypt_failure_rolls_back_the_whole_tenant_only(self):
        await self.seed([("t1", APIS[0], PEMS[0]), ("t2", APIS[1], PEMS[1])])
        before = await self.table()
        calls = {"n": 0}

        def flaky(value, field):
            calls["n"] += 1
            if calls["n"] == 2:  # t1's second field
                raise crypto.SecretEncryptionUnavailable("WXPAY_SECRET_ENCRYPTION_FAILED")
            return crypto.encrypt_secret(value, field)

        report = await self.run_mig(hooks=mig.Hooks(encrypt=flaky), stop_on_failure=False)
        after = await self.table()
        self.assertEqual(after["t1"], before["t1"])  # NOT half-migrated
        self.assertTrue(after["t2"][1].startswith("enc:v1:") and after["t2"][2].startswith("enc:v1:"))
        self.assertEqual((report.tenants_failed, report.tenants_migrated), (1, 1))
        failed = [e for e in report.events if e.get("outcome") == "FAILED"]
        self.assertEqual(failed[0]["reason"], "WXPAY_SECRET_ENCRYPTION_FAILED")

    async def test_readback_mismatch_rolls_back(self):
        await self.seed([("t1", APIS[0], PEMS[0])])
        before = await self.table()
        wrong = crypto.encrypt_secret(APIS[2], crypto.SecretField.API_V3_KEY)  # valid envelope, different secret
        report = await self.run_mig(hooks=mig.Hooks(encrypt=lambda v, f: wrong if f is crypto.SecretField.API_V3_KEY else crypto.encrypt_secret(v, f)))
        self.assertEqual(await self.table(), before)
        self.assertEqual((report.tenants_failed, report.decrypt_diff_count), (1, 1))

    async def test_process_crash_between_tenants_resumes_from_database_state(self):
        await self.seed([("t1", APIS[0], PEMS[0]), ("t2", APIS[1], PEMS[1]), ("t3", APIS[2], PEMS[2])])

        async def die(_tid):
            raise Crash()

        with self.assertRaises(Crash):
            await self.run_mig(hooks=mig.Hooks(after_commit=die))
        partial = await self.table()
        self.assertTrue(partial["t1"][1].startswith("enc:v1:"))  # t1 committed before the crash
        self.assertEqual(partial["t2"][1], APIS[1])  # t2/t3 untouched

        report = await self.run_mig()  # a brand-new run, no memory of the crash
        self.assertEqual((report.tenants_noop, report.tenants_migrated, report.fields_updated), (1, 2, 4))
        final = await self.table()
        self.assertEqual(final["t1"], partial["t1"])  # t1 not re-encrypted
        self.assertTrue(all(v[1].startswith("enc:v1:") and v[2].startswith("enc:v1:") for v in final.values()))

    async def test_driver_style_exception_text_never_reaches_the_output(self):
        await self.seed([("t1", APIS[0], PEMS[0])])

        async def leak(_tid):
            raise RuntimeError(f"SQL failed [parameters: ({APIS[0]!r}, {PEMS[0][:60]!r})]")

        report = await self.run_mig(hooks=mig.Hooks(before_update=leak))
        self.assertEqual(report.tenants_failed, 1)
        self.assertEqual(report.events[0]["reason"], "RuntimeError")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            mig._print_report(report)
        for secret in (APIS[0], PEMS[0][:60]):
            self.assertNotIn(secret, out.getvalue())
        self.assertEqual((await self.table())["t1"][1], APIS[0])


class VerifyAndRotationTest(ExecutorBase):
    async def migrated(self):
        await self.seed([("t1", APIS[0], PEMS[0])])
        await self.run_mig()

    async def verify_fields(self):
        report = await mig.run(self.engine, "verify")
        return report.events[0]["fields"]

    async def test_rotation_keeps_old_envelopes_readable_and_new_writes_use_the_new_key(self):
        await self.migrated()
        self.assertIn(":key-a:", (await self.table())["t1"][1])

        self.write_keyring([("key-b", "encrypt-decrypt"), ("key-a", "decrypt-only")], active="key-b")
        # same process: the failed/old snapshot is immutable until restart
        self.assertEqual(crypto.get_keyring().active_key_id, "key-a")
        crypto.get_keyring.cache_clear()  # == process restart
        self.assertEqual(crypto.get_keyring().active_key_id, "key-b")
        self.assertTrue(all(v.endswith("/READABLE") for v in (await self.verify_fields()).values()))
        self.assertIn(":key-b:", crypto.encrypt_secret(APIS[1], crypto.SecretField.API_V3_KEY))

        self.write_keyring([("key-b", "encrypt-decrypt")], active="key-b")  # A removed
        crypto.get_keyring.cache_clear()
        fields = await self.verify_fields()
        self.assertTrue(all(v.endswith("ERR:WXPAY_SECRET_KEY_UNKNOWN") for v in fields.values()), fields)

    async def test_corrupted_token_and_unknown_key_id_fail_closed(self):
        good = crypto.encrypt_secret(APIS[0], crypto.SecretField.API_V3_KEY)
        corrupted = good[:-6] + ("AAAAAA" if not good.endswith("AAAAAA") else "BBBBBB")
        unknown = good.replace(":key-a:", ":key-zz:")
        await self.seed([("t1", corrupted, unknown)])
        fields = await self.verify_fields()
        self.assertIn("ERR:WXPAY_SECRET_DECRYPT_FAILED", fields["wx_api_key_v3"])
        self.assertIn("ERR:WXPAY_SECRET_KEY_UNKNOWN", fields["wx_private_key"])
        report = await self.run_mig()  # apply must never touch envelopes it cannot classify as legacy plaintext
        self.assertEqual(report.fields_updated, 0)
        self.assertEqual((await self.table())["t1"][1:3], (corrupted, unknown))


    async def test_unreadable_envelope_blocks_the_tenants_other_field_from_being_migrated(self):
        good = crypto.encrypt_secret(APIS[0], crypto.SecretField.API_V3_KEY)
        unknown = good.replace(":key-a:", ":key-zz:")
        await self.seed([("t1", unknown, PEMS[0]), ("t2", APIS[1], PEMS[1])])
        before = await self.table()
        report = await self.run_mig(stop_on_failure=False)
        after = await self.table()
        self.assertEqual(after["t1"], before["t1"])  # plaintext pem NOT migrated: the broken envelope stays visible
        rejected = [e for e in report.events if e.get("outcome") == "REJECTED"][0]
        self.assertEqual(rejected["unreadable_envelope"], {"wx_api_key_v3": "WXPAY_SECRET_KEY_UNKNOWN"})
        self.assertTrue(after["t2"][1].startswith("enc:v1:"))  # other tenants unaffected
        self.assertEqual((report.tenants_rejected, report.tenants_migrated), (1, 1))


if __name__ == "__main__":
    unittest.main()
