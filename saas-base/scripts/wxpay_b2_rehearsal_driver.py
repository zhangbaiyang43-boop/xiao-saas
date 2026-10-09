#!/usr/bin/env python3
"""B2 isolated migration REHEARSAL driver (server-side, isolated MySQL 5.7 only).

Runs every Gate 02-07 scenario against a throwaway socket-only mysqld that was restored
from the verified pre-deploy backup, using a throwaway test Keyring.  It never connects to
the production database.  Secrets live only in this process's memory; output is limited to
PASS/FAIL, counts and MATCH/DIFF.

Required env (set by the rehearsal orchestrator):
  B2_RT, B2_BACKUP_GZ, B2_OLD_CRYPTO_PY (optional, pre-B1 crypto.py for the rollback demo)
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path

RT = Path(os.environ["B2_RT"])
SOCK = str(RT / "mysql" / "mysql.sock")
BACKUP = os.environ["B2_BACKUP_GZ"]
OLD_CRYPTO = os.environ.get("B2_OLD_CRYPTO_PY", "")
EXECUTOR = RT / "tree" / "scripts" / "wxpay_secret_migrate.py"
KEYDIR = RT / "keyring"
KEYFILE = KEYDIR / "active.json"
URL = f"mysql+asyncmy://root@localhost/saas_base?unix_socket={SOCK}&charset=utf8mb4"
ROOT_URL = f"mysql+asyncmy://root@localhost/?unix_socket={SOCK}&charset=utf8mb4"
MYSQL = "/usr/bin/mysql"
MYSQLDUMP = "/usr/bin/mysqldump"
WORK = RT / "work"

spec = importlib.util.spec_from_file_location("wxpay_secret_migrate", EXECUTOR)
mig = importlib.util.module_from_spec(spec)
sys.modules["wxpay_secret_migrate"] = mig
spec.loader.exec_module(mig)
crypto = mig.crypto
from cryptography.fernet import Fernet  # noqa: E402
from sqlalchemy import text  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []
KEYS: dict[str, bytes] = {}


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""), flush=True)


def sh(args, **kwargs):
    return subprocess.run(args, capture_output=True, **kwargs)


def mysql_exec(sql: str, db: str = "") -> None:
    cmd = [MYSQL, "--no-defaults", "--protocol=socket", f"--socket={SOCK}", "-uroot"] + ([db] if db else []) + ["-e", sql]
    result = sh(cmd)
    if result.returncode != 0:
        raise RuntimeError("mysql_exec_failed")


def reset_db(marker: bool = True) -> None:
    mysql_exec("DROP DATABASE IF EXISTS saas_base")
    gz = subprocess.Popen(["zcat", BACKUP], stdout=subprocess.PIPE)
    restore = subprocess.run([MYSQL, "--no-defaults", "--protocol=socket", f"--socket={SOCK}", "-uroot", "--default-character-set=utf8mb4"], stdin=gz.stdout, capture_output=True)
    gz.stdout.close()
    gz.wait()
    if restore.returncode != 0:
        raise RuntimeError("restore_failed")
    if marker:
        mysql_exec(f"CREATE TABLE {mig.MARKER_TABLE} (purpose VARCHAR(64)); INSERT INTO {mig.MARKER_TABLE} VALUES ('{mig.MARKER_PURPOSE}')", "saas_base")


def write_keyring(keys, active, mode=0o600):
    entries = []
    for key_id, usage in keys:
        KEYS.setdefault(key_id, Fernet.generate_key())
        entries.append({"keyId": key_id, "algorithm": "fernet", "usage": usage, "key": KEYS[key_id].decode()})
    KEYDIR.mkdir(mode=0o700, exist_ok=True)
    os.chmod(KEYDIR, 0o700)
    KEYFILE.unlink(missing_ok=True)  # also removes a symlink instead of writing through it
    KEYFILE.write_text(json.dumps({"formatVersion": 1, "activeKeyId": active, "keys": entries}), encoding="utf-8")
    os.chmod(KEYFILE, mode)
    os.chown(KEYFILE, 0, 0)
    crypto.settings.WXPAY_SECRET_KEYRING_PATH = str(KEYFILE)
    crypto.get_keyring.cache_clear()


def base_env(**extra):
    env = {k: v for k, v in os.environ.items() if k.startswith(("B2_", "PATH", "HOME", "LANG", "LC_"))}
    env.update({
        "WXPAY_SECRET_KEYRING_PATH": str(KEYFILE), "WXPAY_ENVELOPE_WRITE_ENABLED": "true",
        "JWT_SECRET_KEY": "ci-only-dummy-signing-key-not-a-real-secret-0123456789abcdef", "REDIS_ENABLED": "false",
        "DATABASE_URL": "mysql+asyncmy://decoy@127.0.0.1:1/decoy", mig.URL_ENV: URL,
    })
    env.update(extra)
    return env


def cli_raw(*args, **env_extra):
    result = subprocess.run([sys.executable, "-I", "-B", str(EXECUTOR), *args], cwd=WORK, env=base_env(**env_extra), capture_output=True, text=True, timeout=180)
    return result.returncode, result.stdout


def secret_tenants(snapshot):
    # dict order == SQL "ORDER BY tenant_id" order, which is the order the executor processes tenants
    return [t for t, (api, pem) in snapshot["raw"].items() if api or pem]


def cli(*args, ack=True, **env_extra):
    env = base_env(**env_extra)
    if ack:
        env[mig.ACK_ENV] = mig.ACK_VALUE
    result = subprocess.run([sys.executable, "-I", "-B", str(EXECUTOR), *args], cwd=WORK, env=env, capture_output=True, text=True, timeout=180)
    summary, refusal = {}, None
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("event") == "summary":
            summary = event
        if event.get("event") == "refused":
            refusal = event.get("reason")
    return result.returncode, summary, refusal


async def engine_rows(url=URL):
    engine = mig.make_engine(url)
    try:
        async with engine.connect() as conn:
            rows = (await conn.execute(text("SELECT tenant_id, wx_api_key_v3, wx_private_key FROM tenant ORDER BY tenant_id"))).all()
            cols = [r[0] for r in (await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='saas_base' AND table_name='tenant' AND column_name NOT IN ('wx_api_key_v3','wx_private_key') ORDER BY ordinal_position"))).all()]
            other = (await conn.execute(text("SELECT " + ",".join(f"`{c}`" for c in cols) + " FROM tenant ORDER BY tenant_id"))).all()
    finally:
        await engine.dispose()
    return rows, other


def h(value):
    return hashlib.sha256((value or "").encode()).hexdigest()


async def state():
    rows, other = await engine_rows()
    secret_digest = hashlib.sha256(json.dumps([(r[0], h(r[1]), h(r[2])) for r in rows]).encode()).hexdigest()[:16]
    other_digest = hashlib.sha256(repr(other).encode()).hexdigest()[:16]
    formats = {"PLAINTEXT": 0, "ENVELOPE": 0, "EMPTY": 0, "OTHER": 0}
    for _tid, api, pem in rows:
        for value, field in ((api, crypto.SecretField.API_V3_KEY), (pem, crypto.SecretField.PRIVATE_KEY)):
            fmt = crypto.classify_secret(value, field)
            key = {"EMPTY": "EMPTY", "LEGACY_PLAINTEXT": "PLAINTEXT", "VERSIONED_ENVELOPE": "ENVELOPE"}.get(fmt.value, "OTHER")
            formats[key] += 1
    plain = {r[0]: (r[1], r[2]) for r in rows}
    return {"tenants": len(rows), "secret_digest": secret_digest, "other_digest": other_digest, "formats": formats, "raw": plain}


def reader_matches(before_plain, after_raw):
    match = diff = 0
    for tid, (api, pem) in before_plain.items():
        for original, now, field in ((api, after_raw[tid][0], crypto.SecretField.API_V3_KEY), (pem, after_raw[tid][1], crypto.SecretField.PRIVATE_KEY)):
            if not original:
                continue
            try:
                got = crypto.decrypt_secret(now, field)
            except crypto.WxPaySecretError:
                diff += 1
                continue
            match, diff = (match + 1, diff) if got == original else (match, diff + 1)
    return match, diff


async def killer(_tid):
    if killer.done:
        return
    killer.done = True
    ids = sh([MYSQL, "--no-defaults", "--protocol=socket", f"--socket={SOCK}", "-uroot", "-N", "-e", "SELECT id FROM information_schema.processlist WHERE db='saas_base' AND id <> CONNECTION_ID()"]).stdout.decode().split()
    for connection_id in ids:
        sh([MYSQL, "--no-defaults", "--protocol=socket", f"--socket={SOCK}", "-uroot", "-e", f"KILL CONNECTION {int(connection_id)}"])


killer.done = False


async def run_lib(mode="apply", **kwargs):
    engine = mig.make_engine(URL)
    try:
        os.environ[mig.ACK_ENV] = mig.ACK_VALUE
        return await mig.run(engine, mode, app_database_url="mysql+asyncmy://decoy@127.0.0.1:1/decoy", target_url=URL, **kwargs)
    finally:
        os.environ.pop(mig.ACK_ENV, None)
        await engine.dispose()


class Crash(BaseException):
    pass


async def scenarios():
    WORK.mkdir(exist_ok=True)
    reset_db(marker=False)
    pre = await state()
    expected_fields = pre["formats"]["PLAINTEXT"]
    record("GATE00 restored copy: 2 tenants with secrets, plaintext fields", expected_fields == 4, f"tenants={pre['tenants']} plaintext_fields={expected_fields} envelopes={pre['formats']['ENVELOPE']}")

    # ---- GATE 02: keyring behaviours under the REAL B1 trust policy (root-owned 0600, root-owned ancestors)
    write_keyring([("rehearsal-a", "encrypt-decrypt")], "rehearsal-a")
    try:
        snap = crypto.get_keyring()
        record("KEYRING_LOAD", True, "source=root-only")
        record("ACTIVE_KEY_VALID", snap.active_key_id == "rehearsal-a" and crypto.encrypt_secret("A" * 32, crypto.SecretField.API_V3_KEY).startswith("enc:v1:rehearsal-a:"))
    except crypto.WxPaySecretError as exc:
        record("KEYRING_LOAD", False, exc.reason_code)
    env_a = crypto.encrypt_secret("A" * 32, crypto.SecretField.API_V3_KEY)
    write_keyring([("rehearsal-b", "encrypt-decrypt"), ("rehearsal-a", "decrypt-only")], "rehearsal-b")
    ok = crypto.decrypt_secret(env_a, crypto.SecretField.API_V3_KEY) == "A" * 32 and crypto.encrypt_secret("B" * 32, crypto.SecretField.API_V3_KEY).startswith("enc:v1:rehearsal-b:")
    record("DECRYPT_ONLY_KEY_VALID", ok)
    for label, bad, code in (("UNKNOWN_KEY_ID", env_a.replace(":rehearsal-a:", ":rehearsal-zz:"), "WXPAY_SECRET_KEY_UNKNOWN"), ("CORRUPTED_TOKEN", env_a[:-6] + "AAAAAA", "WXPAY_SECRET_DECRYPT_FAILED")):
        try:
            crypto.decrypt_secret(bad, crypto.SecretField.API_V3_KEY)
            record(label, False, "decrypted")
        except crypto.WxPaySecretError as exc:
            record(label + "=FAIL_CLOSED", exc.reason_code == code, exc.reason_code)
    perm = []
    for label, mutate in (("mode_0644", lambda: os.chmod(KEYFILE, 0o644)), ("owner_nobody", lambda: os.chown(KEYFILE, 65534, 65534)), ("symlink", None)):
        write_keyring([("rehearsal-a", "encrypt-decrypt")], "rehearsal-a")
        if mutate:
            mutate()
        else:
            real = KEYDIR / "real.json"
            shutil.copy(KEYFILE, real)
            os.chmod(real, 0o600)
            KEYFILE.unlink()
            KEYFILE.symlink_to(real)
        crypto.get_keyring.cache_clear()
        try:
            crypto.get_keyring()
            perm.append(False)
        except crypto.SecretEncryptionUnavailable as exc:
            perm.append(exc.reason_code == "WXPAY_KEYRING_PERMISSION_DENIED")
        if not mutate:
            (KEYDIR / "real.json").unlink()
    record("PERMISSION_VIOLATION=FAIL_CLOSED", all(perm), f"cases={perm}")
    write_keyring([("rehearsal-a", "encrypt-decrypt")], "rehearsal-a")

    # ---- GATE 03/04: read-only modes and guards
    code, summary, _ = cli("--mode", "inventory")
    record("INVENTORY read-only", code == 0 and summary.get("format_counts", {}).get("LEGACY_PLAINTEXT") == 4, json.dumps(summary.get("format_counts")))
    code, summary, _ = cli()
    after = await state()
    record("DRY_RUN default: no writes", code == 0 and summary.get("mode") == "dry-run" and summary.get("fields_expected") == 4 and after["secret_digest"] == pre["secret_digest"], f"fields_expected={summary.get('fields_expected')}")
    guards = []
    guards.append(cli("--mode", "apply", ack=True)[2] == "APPLY_FLAG_MISSING")
    guards.append(cli("--mode", "apply", "--apply", ack=False)[2] == "ISOLATED_WRITE_ACK_MISSING")
    guards.append(cli("--mode", "apply", "--apply")[2] == "REHEARSAL_MARKER_MISSING")  # production-like: no marker
    guards.append(cli("--mode", "apply", "--apply", DATABASE_URL=URL)[2] in {"TARGET_EQUALS_APPLICATION_DATABASE"})
    mysql_exec(f"CREATE TABLE {mig.MARKER_TABLE} (purpose VARCHAR(64)); INSERT INTO {mig.MARKER_TABLE} VALUES ('{mig.MARKER_PURPOSE}')", "saas_base")
    guards.append(cli("--mode", "apply", "--apply", WXPAY_ENVELOPE_WRITE_ENABLED="false")[2] == "ENVELOPE_WRITE_FLAG_OFF")
    after = await state()
    record("APPLY guards refuse (flag/ack/marker/same-db/write-flag)", all(guards) and after["secret_digest"] == pre["secret_digest"], f"cases={guards}")

    # ---- GATE 04: the four-field migration
    snapshot_dump = RT / "pre-migration.sql.gz"
    dump = subprocess.run(f"{MYSQLDUMP} --no-defaults --protocol=socket --socket={SOCK} -uroot --single-transaction --routines --triggers --events --hex-blob --default-character-set=utf8mb4 --databases saas_base | gzip -c > {snapshot_dump}", shell=True, capture_output=True)
    record("GATE07A pre-migration snapshot taken", dump.returncode == 0 and snapshot_dump.stat().st_size > 1000, f"bytes={snapshot_dump.stat().st_size}")
    pre_mig = await state()
    code, summary, _ = cli("--mode", "apply", "--apply")
    post = await state()
    match, diff = reader_matches(pre_mig["raw"], post["raw"])
    record("MIGRATION 4 fields", code == 0 and summary.get("fields_updated") == 4 and post["formats"]["PLAINTEXT"] == 0 and post["formats"]["ENVELOPE"] == 4, f"expected=4 updated={summary.get('fields_updated')} plaintext_after={post['formats']['PLAINTEXT']} envelope_after={post['formats']['ENVELOPE']}")
    record("TENANT_COUNT_UNCHANGED", post["tenants"] == pre_mig["tenants"], f"{post['tenants']}")
    record("NON_SECRET_COLUMNS_UNCHANGED (incl. updated_at)", post["other_digest"] == pre_mig["other_digest"])
    record("DECRYPTION_MATCH via B1 reader", match == 4 and diff == 0, f"MATCH={match} DIFF={diff}")
    migrated_state = post
    code, summary, _ = cli("--mode", "apply", "--apply")
    again = await state()
    record("DUPLICATE_RUN_NOOP / idempotent", code == 0 and summary.get("fields_updated") == 0 and again["secret_digest"] == migrated_state["secret_digest"], f"fields_updated={summary.get('fields_updated')} bytes_identical={again['secret_digest'] == migrated_state['secret_digest']}")
    code, summary, _ = cli("--mode", "verify")
    record("VERIFY readable (envelopes)", code == 0 and summary.get("format_counts", {}).get("VERSIONED_ENVELOPE") == 4)

    # ---- GATE 05: fault injection (each starts from the restored pre-migration database)
    async def fresh():
        reset_db()
        write_keyring([("rehearsal-a", "encrypt-decrypt")], "rehearsal-a")
        return await state()

    # a. single-field encrypt failure / b. second field of a tenant fails
    for label, fail_at in (("a single-field encrypt failure", 1), ("b second field of a tenant fails", 2)):
        base = await fresh()
        calls = {"n": 0}

        def flaky(value, field, _fail_at=fail_at, _calls=calls):
            _calls["n"] += 1
            if _calls["n"] == _fail_at:
                raise crypto.SecretEncryptionUnavailable("WXPAY_SECRET_ENCRYPTION_FAILED")
            return crypto.encrypt_secret(value, field)

        report = await run_lib(hooks=mig.Hooks(encrypt=flaky), stop_on_failure=False)
        st = await state()
        first = secret_tenants(base)[0]
        atomic = st["raw"][first] == base["raw"][first]
        others_done = all((st["raw"][t][0] or "").startswith("enc:v1:") and (st["raw"][t][1] or "").startswith("enc:v1:") for t in secret_tenants(base) if t != first)
        record(f"GATE05{label}: tenant atomic + others migrated", report.tenants_failed == 1 and atomic and others_done, f"failed={report.tenants_failed} first_tenant_unchanged={atomic} migrated={report.tenants_migrated}")

    # c. database connection interruption
    base = await fresh()
    killer.done = False
    report = await run_lib(hooks=mig.Hooks(before_update=killer), stop_on_failure=False)
    st = await state()
    first = secret_tenants(base)[0]
    record("GATE05c DB connection killed mid-tenant", report.tenants_failed == 1 and st["raw"][first] == base["raw"][first] and report.tenants_migrated == 1, f"failed={report.tenants_failed} migrated={report.tenants_migrated} unchanged={st['raw'][first] == base['raw'][first]}")

    # d. CAS conflict (case-only concurrent change + normal change)
    base = await fresh()
    first = secret_tenants(base)[0]
    original_api = base["raw"][first][0]
    swapped = original_api.swapcase() if original_api.swapcase() != original_api else original_api[::-1]

    async def concurrent(victim):
        if concurrent.done:
            return
        concurrent.done = True
        engine = mig.make_engine(URL)
        async with engine.begin() as conn:
            await conn.execute(text("UPDATE tenant SET wx_api_key_v3=:v WHERE tenant_id=:t"), {"v": swapped, "t": victim})
        await engine.dispose()

    concurrent.done = False
    report = await run_lib(hooks=mig.Hooks(before_update=concurrent), stop_on_failure=False)
    st = await state()
    record("GATE05d CAS conflict detected, winner preserved", report.tenants_conflict == 1 and st["raw"][first][0] == swapped and st["raw"][first][1] == base["raw"][first][1], f"conflicts={report.tenants_conflict} exit={mig.exit_code(report)}")
    report = await run_lib()
    st = await state()
    record("GATE05d next run succeeds from fresh state", report.tenants_migrated >= 1 and st["formats"]["PLAINTEXT"] == 0)

    # e/f. keyring missing / active key invalid
    base = await fresh()
    os.unlink(KEYFILE)
    code, _s, reason = cli("--mode", "apply", "--apply")
    missing_ok = code == mig.EXIT_REFUSED and reason == "WXPAY_KEYRING_MISSING" and (await state())["secret_digest"] == base["secret_digest"]
    write_keyring([("rehearsal-a", "encrypt-decrypt")], "rehearsal-a")
    raw = json.loads(KEYFILE.read_text())
    raw["activeKeyId"] = "ghost"
    KEYFILE.write_text(json.dumps(raw))
    os.chmod(KEYFILE, 0o600)
    code, _s, reason2 = cli("--mode", "apply", "--apply")
    invalid_ok = code == mig.EXIT_REFUSED and reason2 == "WXPAY_KEYRING_ACTIVE_KEY_INVALID" and (await state())["secret_digest"] == base["secret_digest"]
    record("GATE05e keyring missing -> refused, no writes", missing_ok, str(reason))
    record("GATE05f active key invalid -> refused, no writes", invalid_ok, str(reason2))

    # g/h. unknown key id and corrupted token envelopes are never touched, and block their tenant
    base = await fresh()
    first = secret_tenants(base)[0]
    good = crypto.encrypt_secret(base["raw"][first][0], crypto.SecretField.API_V3_KEY)
    for label, bad in (("g unknown key id", good.replace(":rehearsal-a:", ":rehearsal-zz:")), ("h corrupted token", good[:-6] + "AAAAAA")):
        base = await fresh()
        mysql_exec("UPDATE tenant SET wx_api_key_v3=" + chr(39) + bad.replace(chr(39), "") + chr(39) + " WHERE tenant_id=" + chr(39) + first + chr(39), "saas_base")
        _rc, verify_out = cli_raw("--mode", "verify")
        flagged = "ERR:" in verify_out
        code2, summary2, _ = cli("--mode", "apply", "--apply", "--continue-on-failure")
        st2 = await state()
        untouched = st2["raw"][first][0] == bad and st2["raw"][first][1] == base["raw"][first][1]
        record(f"GATE05{label}: verify flags it, apply rejects tenant, nothing rewritten", flagged and untouched and summary2.get("rejected_tenant_count") == 1, f"flagged={flagged} rejected={summary2.get('rejected_tenant_count')} fields_updated_for_other_tenant={summary2.get('fields_updated')}")

    # i. process killed mid-run -> recover from DATABASE state
    base = await fresh()
    crash = subprocess.run([sys.executable, "-I", "-B", str(Path(__file__).resolve()), "crash"], cwd=WORK, env=base_env(B2_RT=str(RT), B2_BACKUP_GZ=BACKUP, **{mig.ACK_ENV: mig.ACK_VALUE}), capture_output=True, text=True)
    mid = await state()
    partial = mid["formats"]["ENVELOPE"] in (2,) and mid["formats"]["PLAINTEXT"] == 2
    tids = sorted(mid["raw"])
    done_tid = [t for t in tids if (mid["raw"][t][0] or "").startswith("enc:v1:")]
    code, summary, _ = cli("--mode", "apply", "--apply")
    fin = await state()
    keep = all(fin["raw"][t] == mid["raw"][t] for t in done_tid)
    record("GATE05i killed mid-run: partial state is whole-tenant", crash.returncode == 137 and partial, f"exit={crash.returncode} envelopes={mid['formats']['ENVELOPE']} plaintext={mid['formats']['PLAINTEXT']}")
    record("GATE05i restart recovery from DB state, no re-encryption", code == 0 and fin["formats"]["PLAINTEXT"] == 0 and fin["formats"]["ENVELOPE"] == 4 and keep and summary.get("tenants_noop") == 1, f"noop={summary.get('tenants_noop')} migrated={summary.get('tenants_migrated')} committed_tenant_bytes_identical={keep}")

    # ---- GATE 06: key rotation on the migrated data (envelopes written under key A)
    write_keyring([("rehearsal-b", "encrypt-decrypt"), ("rehearsal-a", "decrypt-only")], "rehearsal-b")
    crypto.get_keyring()  # this "process" loads its one-shot snapshot
    raw = json.loads(KEYFILE.read_text())
    raw["activeKeyId"] = "rehearsal-a"
    for entry in raw["keys"]:
        entry["usage"] = "encrypt-decrypt" if entry["keyId"] == "rehearsal-a" else "decrypt-only"
    KEYFILE.write_text(json.dumps(raw))
    os.chmod(KEYFILE, 0o600)
    unchanged_in_process = crypto.get_keyring().active_key_id == "rehearsal-b"
    write_keyring([("rehearsal-b", "encrypt-decrypt"), ("rehearsal-a", "decrypt-only")], "rehearsal-b")
    code, summary, _ = cli("--mode", "verify")
    record("GATE06 A-envelopes readable after B active + A decrypt-only", code == 0 and summary.get("format_counts", {}).get("VERSIONED_ENVELOPE") == 4)
    record("GATE06 new writes use B", crypto.encrypt_secret("C" * 32, crypto.SecretField.API_V3_KEY).startswith("enc:v1:rehearsal-b:"))
    record("GATE06 keyring change needs a restart (in-process snapshot immutable)", unchanged_in_process)
    write_keyring([("rehearsal-b", "encrypt-decrypt")], "rehearsal-b")  # A removed
    _rc, out = cli_raw("--mode", "verify")
    record("GATE06 A removed -> old envelopes fail closed (no guessing)", out.count("ERR:WXPAY_SECRET_KEY_UNKNOWN") == 4, f"fail_closed_fields={out.count('ERR:WXPAY_SECRET_KEY_UNKNOWN')}")
    write_keyring([("rehearsal-b", "encrypt-decrypt"), ("rehearsal-a", "decrypt-only")], "rehearsal-b")
    _rc, out = cli_raw("--mode", "verify")
    record("GATE06 restoring A (decrypt-only) recovers readability", out.count("/READABLE") == 4)

    # ---- GATE 07: rollback / restore / keyring loss / old-code risk
    write_keyring([("rehearsal-a", "encrypt-decrypt")], "rehearsal-a")
    reset_db()
    await run_lib()
    migrated = await state()
    # A. restore the pre-migration snapshot
    mysql_exec("DROP DATABASE saas_base")
    gz = subprocess.Popen(["zcat", str(snapshot_dump)], stdout=subprocess.PIPE)
    restore = subprocess.run([MYSQL, "--no-defaults", "--protocol=socket", f"--socket={SOCK}", "-uroot", "--default-character-set=utf8mb4"], stdin=gz.stdout, capture_output=True)
    gz.stdout.close()
    gz.wait()
    restored = await state()
    still_reads = all(crypto.decrypt_secret(v, f) is not None for t, (a, p) in restored["raw"].items() for v, f in ((a, crypto.SecretField.API_V3_KEY), (p, crypto.SecretField.PRIVATE_KEY)) if v)
    record("GATE07A pre-migration snapshot restore", restore.returncode == 0 and restored["secret_digest"] == pre_mig["secret_digest"] and restored["formats"]["PLAINTEXT"] == 4 and still_reads, f"secret_state_matches_pre_migration={restored['secret_digest'] == pre_mig['secret_digest']} plaintext={restored['formats']['PLAINTEXT']}")
    # B. executor failure then retry is covered by GATE05a/b/i; C. keyring lost
    reset_db()
    await run_lib()
    os.unlink(KEYFILE)
    crypto.get_keyring.cache_clear()
    _rc, out = cli_raw("--mode", "verify")
    lost = out.count("ERR:WXPAY_KEYRING_MISSING")
    record("GATE07C keyring lost -> all envelope fields fail closed", lost == 4, f"fail_closed_fields={lost}")
    write_keyring([("rehearsal-a", "encrypt-decrypt")], "rehearsal-a")  # same key bytes restored from the secure copy
    _rc, out = cli_raw("--mode", "verify")
    record("GATE07C restoring the keyring from its secure copy recovers readability", out.count("/READABLE") == 4)
    # D. old (pre-B1) code against an envelope
    if OLD_CRYPTO and Path(OLD_CRYPTO).exists():
        app_pkg, cfg = types.ModuleType("app"), types.ModuleType("app.config")
        cfg.settings = types.SimpleNamespace(SECRET_ENCRYPTION_KEY="")
        sys.modules["app"], sys.modules["app.config"] = app_pkg, cfg
        old_spec = importlib.util.spec_from_file_location("old_crypto", OLD_CRYPTO)
        old = importlib.util.module_from_spec(old_spec)
        sys.modules["old_crypto"] = old
        old_spec.loader.exec_module(old)
        env_value = crypto.encrypt_secret("D" * 32, crypto.SecretField.API_V3_KEY)
        returned = old.decrypt_secret(env_value)
        record("GATE07D pre-B1 code reads an envelope as the key itself (PRE_B1_CODE_ROLLBACK=FORBIDDEN)", returned == env_value and returned != "D" * 32, "old_reader_returns_envelope_as_plaintext=YES")
    # tenant isolation summary is evidenced by GATE05a/b/c/d (other tenants unaffected)

    iso = [ok for n, ok, _ in RESULTS if n.startswith(("GATE05a", "GATE05b", "GATE05c", "GATE05d"))]
    record("TENANT_ISOLATION: a tenant failure/conflict never touched another tenant", all(iso) and len(iso) >= 5)
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"REHEARSAL_TOTAL={len(RESULTS)} FAILED={len(failed)}")
    for n in failed:
        print("FAILED_CHECK:", n)
    return 0 if not failed else 1


async def crash_run():
    async def die(_tid):
        os._exit(137)

    await run_lib(hooks=mig.Hooks(after_commit=die))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "crash":
        asyncio.run(crash_run())
    else:
        sys.exit(asyncio.run(scenarios()))
