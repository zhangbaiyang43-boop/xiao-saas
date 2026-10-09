#!/usr/bin/env python3
"""B4 isolated REHEARSAL of the PRODUCTION authorization mode (server-side, isolated MySQL 5.7 only).

Imports the B2 rehearsal driver for its helpers (isolated mysqld, throwaway Keyring, restore from the
verified backup). Exercises `--target production` end to end through the real CLI. Never connects to
the production database; secrets stay in memory; output is PASS/FAIL, reason codes and counts only.

Extra env: B4_PROD_DB_FINGERPRINT (sha256 fingerprint of the REAL production DB, used only to prove a
grant for the production database is refused here).
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
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wxpay_b2_rehearsal_driver as b2  # noqa: E402

mig, crypto, authority = b2.mig, b2.crypto, b2.mig.authority
spec = importlib.util.spec_from_file_location("wxpay_migration_grant", Path(__file__).resolve().parent / "wxpay_migration_grant.py")
grant_tool = importlib.util.module_from_spec(spec)
sys.modules["wxpay_migration_grant"] = grant_tool
spec.loader.exec_module(grant_tool)

RT = b2.RT
REPO, AUTH_DIR, LEDGER_DIR, BK_DIR = RT / "repo", RT / "authority", RT / "ledger", RT / "backup"
PUB, LEDGER, SVC, BKCOPY = AUTH_DIR / "authority.pub", LEDGER_DIR / "ledger.jsonl", RT / "work" / "service.env", BK_DIR / "copy.sql.gz"
PROD_FP = os.environ["B4_PROD_DB_FINGERPRINT"]
ALL_OUTPUT: list[str] = []
GRANT_COUNTER = [0]
PRIV: bytes = b""


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def setup_environment() -> None:
    global PRIV
    for directory, mode in ((AUTH_DIR, 0o755), (LEDGER_DIR, 0o700), (BK_DIR, 0o700)):
        directory.mkdir(mode=mode, exist_ok=True)
        os.chmod(directory, mode)
    PRIV, public_pem = authority.generate_keypair(None)  # throwaway rehearsal authority key
    PUB.write_bytes(public_pem)
    os.chmod(PUB, 0o644)
    shutil.copy(b2.BACKUP, BKCOPY)  # same bytes (sha256 identical) with a fresh mtime
    os.chmod(BKCOPY, 0o600)
    SVC.write_text("RESTAURANT_SERVICE=1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(REPO)], check=True)
    subprocess.run(["git", "-C", str(REPO), "-c", "user.name=rehearsal", "-c", "user.email=r@example.invalid", "commit", "-q", "--allow-empty", "-m", "rehearsal tree"], check=True)


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cli(*args, ack=False, env_extra=None):
    env = b2.base_env(**(env_extra or {}))
    result = subprocess.run([sys.executable, "-I", "-B", str(b2.EXECUTOR), *args], cwd=b2.WORK, env=env, capture_output=True, text=True, timeout=180)
    ALL_OUTPUT.extend([result.stdout, result.stderr])
    summary, refusal, plan = {}, None, None
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("event") == "summary":
            summary = event
        elif event.get("event") == "refused":
            refusal = event.get("reason")
        elif event.get("event") == "plan":
            plan = event
    return result.returncode, summary, refusal, plan


def prod_common():
    return ["--target", "production", "--authority-pubkey", str(PUB), "--ledger", str(LEDGER), "--repo-root", str(REPO), "--service-env-file", str(SVC)]


def get_plan(tenant: str, fields: list[str]) -> dict:
    args = ["--mode", "plan", "--tenant-id", tenant, *sum((["--field", f] for f in fields), []), *prod_common()]
    rc, _s, refusal, plan = cli(*args)
    assert rc == 0 and plan, f"plan failed: {refusal}"
    return plan


def make_grant(plan: dict, *, mutate=None, now=None, ttl=30, backup_path=None, backup_sha=None) -> Path:
    now = now or utcnow()
    grant = grant_tool.build_grant_from_plan(
        plan, backup_path=backup_path or str(BKCOPY), backup_sha256=backup_sha or sha_file(BKCOPY),
        recovery_attested_at=authority.iso(now - timedelta(days=1)), now=now, ttl_minutes=ttl,
    )
    grant.update(mutate or {})
    GRANT_COUNTER[0] += 1
    path = b2.WORK / f"grant-{GRANT_COUNTER[0]}.json"
    path.write_text(json.dumps(authority.sign_grant(PRIV, grant)), encoding="utf-8")
    return path


def apply_cmd(grant, tenants, fields=(), apply_flag=True, extra=()):
    args = ["--mode", "apply", *(["--apply"] if apply_flag else []), *prod_common(), *extra]
    if grant:
        args += ["--grant-file", str(grant)]
    for t in tenants:
        args += ["--tenant-id", t]
    for f in fields:
        args += ["--field", f]
    return cli(*args)


def ledger_text() -> str:
    return LEDGER.read_text() if LEDGER.exists() else ""


async def fresh():
    b2.reset_db(marker=False)
    b2.write_keyring([("rehearsal-a", "encrypt-decrypt")], "rehearsal-a")
    st = await b2.state()
    engine = mig.make_engine(b2.URL)
    async with engine.connect() as conn:
        enabled = {r[0]: bool(r[1]) for r in (await conn.execute(mig.text("SELECT tenant_id, wx_pay_enabled FROM tenant"))).all()}
    await engine.dispose()
    secret = b2.secret_tenants(st)
    batch1 = [t for t in secret if not enabled[t]][0]
    batch2 = [t for t in secret if enabled[t]][0]
    return st, batch1, batch2


async def expect_refused(label, reason, grant, tenants, fields=(), apply_flag=True, extra=(), env_extra=None):
    before, ledger_before = await b2.state(), ledger_text()
    if env_extra:
        rc, summary, refusal, _p = cli("--mode", "apply", *(["--apply"] if apply_flag else []), *prod_common(), *(["--grant-file", str(grant)] if grant else []),
                                      *sum((["--tenant-id", t] for t in tenants), []), *sum((["--field", f] for f in fields), []), *extra, env_extra=env_extra)
    else:
        rc, summary, refusal, _p = apply_cmd(grant, tenants, fields, apply_flag, extra)
    after = await b2.state()
    ok = rc == mig.EXIT_REFUSED and refusal == reason and after["secret_digest"] == before["secret_digest"] and ledger_text() == ledger_before
    b2.record(f"B4 refuse: {label}", ok, f"reason={refusal} rc={rc} db_unchanged={after['secret_digest'] == before['secret_digest']} grant_not_consumed={ledger_text() == ledger_before}")


async def scenarios() -> int:
    b2.WORK.mkdir(exist_ok=True)
    setup_environment()
    st0, t1, t2 = await fresh()
    plain_secrets = [v for tid in (t1, t2) for v in st0["raw"][tid] if v]
    fields_both = ["wx_api_key_v3", "wx_private_key"]
    b2.record("B4 setup: isolated production-mode environment (real trust policy, root-owned authority key/ledger)", len(plain_secrets) == 4, "batch1=payments-disabled tenant, batch2=payments-enabled tenant")

    plan1 = get_plan(t1, fields_both)
    b2.record("B4 plan mode is read-only and complete", plan1["rehearsal_marker_present"] is False and plan1["worktree_clean"] and plan1["service_write_flag"] == "ABSENT" and plan1["keyring_active_key_id"] == "rehearsal-a" and set(plan1["field_formats"].values()) == {"LEGACY_PLAINTEXT"} and (await b2.state())["secret_digest"] == st0["secret_digest"], f"alembic={plan1['alembic_revision']}")
    b2.record("B4 DB fingerprint of the rehearsal DB differs from the real production DB", plan1["db_fingerprint"] != PROD_FP)

    good = make_grant(plan1)
    # ---- refusal matrix (database and ledger must stay untouched every time)
    await expect_refused("no grant file given", "GRANT_MISSING", None, [t1])
    await expect_refused("no --apply", "APPLY_FLAG_MISSING", good, [t1], apply_flag=False)
    await expect_refused("grant file does not exist", "GRANT_MISSING", b2.WORK / "nope.json", [t1])
    await expect_refused("wrong database (grant is for the REAL production DB)", "DB_FINGERPRINT_MISMATCH", make_grant(plan1, mutate={"db_fingerprint": PROD_FP}), [t1])
    await expect_refused("wrong tenant", "TENANT_MISMATCH", good, [t2])
    await expect_refused("batch of tenants", "TENANT_SCOPE_NOT_SINGLE", good, [t1, t2])
    await expect_refused("no tenant", "TENANT_SCOPE_NOT_SINGLE", good, [])
    await expect_refused("wrong backend SHA", "BACKEND_SHA_MISMATCH", make_grant(plan1, mutate={"backend_sha": "b" * 40}), [t1])
    await expect_refused("wrong Alembic revision", "ALEMBIC_MISMATCH", make_grant(plan1, mutate={"alembic_revision": "20260101_0001"}), [t1])
    await expect_refused("wrong host", "HOST_MISMATCH", make_grant(plan1, mutate={"host": "some-other-host"}), [t1])
    await expect_refused("expired grant", "GRANT_EXPIRED", make_grant(plan1, now=utcnow() - timedelta(hours=2), ttl=30), [t1])
    await expect_refused("unauthorized field", "GRANT_FIELD_NOT_ALLOWED", make_grant(get_plan(t1, ["wx_api_key_v3"])), [t1], fields=["wx_private_key"])
    await expect_refused("non-whitelisted field in a signed grant", "GRANT_FIELD_NOT_ALLOWED", make_grant(plan1, mutate={"fields": ["name"]}), [t1])
    await expect_refused("batch/retry options", "OPTION_NOT_ALLOWED_IN_PRODUCTION", good, [t1], extra=["--continue-on-failure"])
    await expect_refused("backup missing", "BACKUP_UNAVAILABLE", make_grant(plan1, backup_path=str(BK_DIR / "missing.gz")), [t1])
    await expect_refused("backup hash differs", "BACKUP_HASH_MISMATCH", make_grant(plan1, backup_sha="e" * 64), [t1])
    os.utime(BKCOPY, (time.time() - 3 * 86400,) * 2)
    await expect_refused("backup older than 24h", "BACKUP_STALE", make_grant(plan1), [t1])
    os.utime(BKCOPY, None)
    await expect_refused("executor write flag off (this process only)", "EXECUTOR_WRITE_FLAG_OFF", good, [t1], env_extra={"WXPAY_ENVELOPE_WRITE_ENABLED": "false"})
    SVC.write_text("WXPAY_ENVELOPE_WRITE_ENABLED=true\n", encoding="utf-8")
    await expect_refused("SERVICE write flag on", "SERVICE_WRITE_FLAG_ON", good, [t1])
    SVC.write_text("RESTAURANT_SERVICE=1\n", encoding="utf-8")
    (REPO / "stray.txt").write_text("dirty")
    await expect_refused("dirty worktree", "WORKTREE_DIRTY", good, [t1])
    (REPO / "stray.txt").unlink()
    mysql_marker = f"CREATE TABLE {mig.MARKER_TABLE} (purpose VARCHAR(64))"
    b2.mysql_exec(mysql_marker, "saas_base")
    await expect_refused("rehearsal marker present in a production-mode DB", "REHEARSAL_MARKER_PRESENT_IN_PRODUCTION", good, [t1])
    b2.mysql_exec(f"DROP TABLE {mig.MARKER_TABLE}", "saas_base")
    b2.mysql_exec("UPDATE tenant SET wx_api_key_v3='%s' WHERE tenant_id='%s'" % ("Q" * 32, t1), "saas_base")
    await expect_refused("state drift after the plan was approved", "PLAN_DIGEST_MISMATCH", good, [t1])
    st0, t1, t2 = await fresh()
    plan1 = get_plan(t1, fields_both)
    good = make_grant(plan1)
    os.unlink(b2.KEYFILE)
    await expect_refused("Keyring unavailable", "KEYRING_UNAVAILABLE", good, [t1])
    b2.write_keyring([("rehearsal-a", "encrypt-decrypt")], "rehearsal-a")

    # ---- batch flow: tenant without payments first, payments-enabled tenant second
    before_t2 = (await b2.state())["raw"][t2]
    rc, summary, refusal, _p = apply_cmd(good, [t1])
    st1 = await b2.state()
    match, diff = b2.reader_matches({t1: st0["raw"][t1]}, st1["raw"])
    ok_batch1 = rc == 0 and summary.get("fields_updated") == 2 and summary.get("tenants_migrated") == 1 and st1["raw"][t2] == before_t2 and (match, diff) == (2, 0)
    b2.record("B4 batch 1 (payments disabled): one tenant, 2 fields, B1-reader MATCH, other tenant byte-identical", ok_batch1, f"updated={summary.get('fields_updated')} MATCH={match} DIFF={diff} other_unchanged={st1['raw'][t2] == before_t2}")
    b2.record("B4 non-secret columns unchanged (incl. updated_at)", st1["other_digest"] == st0["other_digest"])
    events = [json.loads(line) for line in ledger_text().splitlines()]
    b2.record("B4 ledger: consumed then finished OK, 0600, no secret", [e["event"] for e in events] == ["consumed", "finished"] and events[-1]["outcome"] == "OK" and oct(os.stat(LEDGER).st_mode & 0o777) == "0o600")
    await expect_refused("replay of a used grant", "GRANT_REUSED", good, [t1])
    rc, summary, _r, _p = apply_cmd(make_grant(get_plan(t1, fields_both)), [t1])
    again = await b2.state()
    b2.record("B4 completed tenant re-run with a fresh grant is an idempotent no-op", rc == 0 and summary.get("fields_updated") == 0 and again["secret_digest"] == st1["secret_digest"], f"fields_updated={summary.get('fields_updated')} bytes_identical={again['secret_digest'] == st1['secret_digest']}")
    plan2 = get_plan(t2, fields_both)
    rc, summary, _r, _p = apply_cmd(make_grant(plan2), [t2])
    st2 = await b2.state()
    match, diff = b2.reader_matches(st0["raw"], st2["raw"])
    b2.record("B4 batch 2 (payments enabled): migrated; all 4 fields now envelopes; MATCH=4", rc == 0 and st2["formats"]["PLAINTEXT"] == 0 and st2["formats"]["ENVELOPE"] == 4 and (match, diff) == (4, 0), f"MATCH={match} DIFF={diff} plaintext={st2['formats']['PLAINTEXT']} envelope={st2['formats']['ENVELOPE']}")

    # ---- CAS conflict stops the run and burns the grant (in-process, real MySQL 5.7)
    st0, t1, t2 = await fresh()
    plan1 = get_plan(t1, fields_both)
    grant = make_grant(plan1)
    original_api = st0["raw"][t1][0]
    swapped = original_api.swapcase() if original_api.swapcase() != original_api else original_api[::-1]

    async def concurrent(victim):
        engine = mig.make_engine(b2.URL)
        async with engine.begin() as conn:
            await conn.execute(mig.text("UPDATE tenant SET wx_api_key_v3=:v WHERE tenant_id=:t"), {"v": swapped, "t": victim})
        await engine.dispose()

    engine = mig.make_engine(b2.URL)
    report = await mig.run_production(engine, grant_path=str(grant), pubkey_path=str(PUB), ledger_path=str(LEDGER), tenant_ids=[t1],
                                      repo_root=str(REPO), service_env_path=str(SVC), env=mig.ProductionEnv(), hooks=mig.Hooks(before_update=concurrent))
    await engine.dispose()
    st = await b2.state()
    b2.record("B4 CAS conflict stops, other writer's value survives, exit 3", report.tenants_conflict == 1 and mig.exit_code(report) == mig.EXIT_CONFLICT and st["raw"][t1][0] == swapped and json.loads(ledger_text().splitlines()[-1])["outcome"] == "CONFLICT", f"conflicts={report.tenants_conflict}")
    await expect_refused("grant burned by the conflict", "GRANT_REUSED", grant, [t1])

    # ---- hard process death
    for label, point in (("before the first write", "before_update"), ("right after the commit", "after_commit")):
        st0, t1, t2 = await fresh()
        grant = make_grant(get_plan(t1, fields_both))
        crash = subprocess.run([sys.executable, "-I", "-B", str(Path(__file__).resolve()), "crash", point, str(grant), t1], cwd=b2.WORK,
                               env=b2.base_env(B2_RT=str(RT), B2_BACKUP_GZ=b2.BACKUP, B4_PROD_DB_FINGERPRINT=PROD_FP), capture_output=True, text=True)
        ALL_OUTPUT.extend([crash.stdout, crash.stderr])
        st = await b2.state()
        expected_env = 0 if point == "before_update" else 2
        entries = [json.loads(line) for line in ledger_text().splitlines()]
        b2.record(f"B4 process killed {label}: tenant is all-or-nothing, grant stays consumed", crash.returncode == 137 and st["formats"]["ENVELOPE"] == expected_env and entries[-1]["event"] == "consumed", f"exit={crash.returncode} envelopes={st['formats']['ENVELOPE']}")
        await expect_refused(f"replay after kill {label}", "GRANT_REUSED", grant, [t1])
        rc, summary, _r, _p = apply_cmd(make_grant(get_plan(t1, fields_both)), [t1])
        fin = await b2.state()
        b2.record(f"B4 recovery after kill {label}: new grant completes from database state", rc == 0 and fin["formats"]["ENVELOPE"] == 2 and (point == "before_update" or fin["raw"][t1] == st["raw"][t1]), f"fields_updated={summary.get('fields_updated')} committed_bytes_preserved={fin['raw'][t1] == st['raw'][t1]}")

    # ---- log / ledger / grant hygiene
    blob = "\n".join(ALL_OUTPUT) + ledger_text() + "".join(p.read_text() for p in b2.WORK.glob("grant-*.json"))
    leaked = [i for i, s in enumerate(plain_secrets) if s and (s in blob or (len(s) > 60 and s.splitlines()[1] in blob))]
    b2.record("B4 audit output sanitization: no secret in CLI output, ledger or grants", not leaked and len(blob) > 1000, f"leaked_values={len(leaked)} output_chars={len(blob)}")
    failed = [n for n, ok, _ in b2.RESULTS if not ok]
    print(f"B4_REHEARSAL_TOTAL={len(b2.RESULTS)} FAILED={len(failed)}")
    for n in failed:
        print("FAILED_CHECK:", n)
    return 0 if not failed else 1


async def crash_run(point: str, grant: str, tenant: str):
    async def die(_t):
        os._exit(137)

    engine = mig.make_engine(b2.URL)
    hooks = mig.Hooks(**{point: die})
    await mig.run_production(engine, grant_path=grant, pubkey_path=str(PUB), ledger_path=str(LEDGER), tenant_ids=[tenant],
                             repo_root=str(REPO), service_env_path=str(SVC), env=mig.ProductionEnv(), hooks=hooks)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "crash":
        asyncio.run(crash_run(sys.argv[2], sys.argv[3], sys.argv[4]))
    else:
        sys.exit(asyncio.run(scenarios()))
