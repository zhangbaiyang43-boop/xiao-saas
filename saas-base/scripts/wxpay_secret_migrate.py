#!/usr/bin/env python3
"""WeChat Pay tenant-secret migration executor (B2 rehearsal + B4 production authorization).

Moves legacy plaintext ``tenant.wx_api_key_v3`` / ``tenant.wx_private_key`` values to the
B1 versioned envelope (``enc:v1:<key-id>:<fernet-token>``).

Two completely separate modes (``--target``):

* ``rehearsal`` (default): writes only a database carrying the rehearsal marker (see below).
* ``production``: writes only with a signed, short-lived, single-use, single-tenant grant bound to
  the host, Backend SHA, Alembic revision, database fingerprint, Keyring key id, a fresh backup and
  an immutable plan digest (see ``wxpay_migration_authority.py``). It is NOT enabled by any
  environment variable and is never started by the application. No production migration is
  authorized by this code: the owner must issue a grant in a separately authorized phase.

Safety properties enforced in code (rehearsal guard details):

* Modes: ``inventory`` / ``dry-run`` (default) / ``verify`` are read-only. ``apply`` writes only
  when ALL hold: ``--apply``; ``WXPAY_MIGRATION_ALLOW_ISOLATED_WRITE`` set to the exact
  acknowledgement string; the target database contains the rehearsal marker row; the target
  URL differs from the application's own ``DATABASE_URL``; the B1 write flag is on and a
  valid Keyring loads.  A production database has no marker, so it cannot be written.
* The target comes from ``WXPAY_MIGRATION_DATABASE_URL`` (never argv), so credentials cannot
  leak through the process list.
* Field whitelist: exactly the two WeChat Pay secret columns.
* Only ``LEGACY_PLAINTEXT`` values are encrypted.  Existing envelopes are never re-encrypted;
  empty values are left alone; raw-Fernet / unknown / malformed values REJECT the whole
  tenant (nothing about that tenant changes).
* One transaction per tenant, one UPDATE per tenant, byte-exact compare-and-swap on the old
  values (``BINARY`` on MySQL, because the column collation is case-insensitive), a rowcount
  check, and an in-transaction read-back verified through the B1 reader before COMMIT.
  A tenant failure never affects another tenant.  State is always re-read from the database,
  so a crashed run is resumed simply by running again.
* Output is structured JSON lines that contain only hashed tenant ids, format names and
  reason codes.  Exception text is never printed (driver errors can embed SQL parameters),
  the engine hides parameters, and no secret / Keyring byte is logged.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import socket
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine  # noqa: E402

from app.core import wxpay_secret_crypto as crypto  # noqa: E402
import wxpay_migration_authority as authority  # noqa: E402

ACK_ENV = "WXPAY_MIGRATION_ALLOW_ISOLATED_WRITE"
ACK_VALUE = "I_UNDERSTAND_THIS_WRITES_SECRETS_TO_AN_ISOLATED_DATABASE"
URL_ENV = "WXPAY_MIGRATION_DATABASE_URL"
MARKER_TABLE = "b2_rehearsal_marker"
MARKER_PURPOSE = "B2_ISOLATED_REHEARSAL"

# The ONLY columns this tool may read or write.
FIELDS: tuple[tuple[str, "crypto.SecretField"], ...] = (
    ("wx_api_key_v3", crypto.SecretField.API_V3_KEY),
    ("wx_private_key", crypto.SecretField.PRIVATE_KEY),
)

EXIT_OK, EXIT_FAILED, EXIT_CONFLICT, EXIT_REFUSED = 0, 2, 3, 4


class TenantFailure(Exception):
    """A per-tenant failure with a stable, secret-free reason code."""

    def __init__(self, reason_code: str):
        self.reason_code = reason_code
        super().__init__(reason_code)


class Refused(RuntimeError):
    """The run must not start (guard failure). Carries a stable reason code only."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass
class Hooks:
    """Test seams. Production/CLI use leaves every hook ``None``."""

    after_read: Optional[Callable[[str], Awaitable[None]]] = None
    before_update: Optional[Callable[[str], Awaitable[None]]] = None
    after_commit: Optional[Callable[[str], Awaitable[None]]] = None
    encrypt: Optional[Callable[[str, "crypto.SecretField"], str]] = None


@dataclass
class Report:
    mode: str
    tenants_considered: int = 0
    tenants_migrated: int = 0
    tenants_noop: int = 0
    tenants_conflict: int = 0
    tenants_failed: int = 0
    tenants_rejected: int = 0
    fields_expected: int = 0
    fields_updated: int = 0
    decrypt_match_count: int = 0
    decrypt_diff_count: int = 0
    stopped_early: bool = False
    format_counts: dict[str, int] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    counted_fields: set = field(default_factory=set, repr=False)

    def summary(self) -> dict[str, Any]:
        return {
            "event": "summary", "mode": self.mode,
            "tenants_considered": self.tenants_considered, "tenants_migrated": self.tenants_migrated,
            "tenants_noop": self.tenants_noop, "cas_conflict_count": self.tenants_conflict,
            "failed_tenant_count": self.tenants_failed, "rejected_tenant_count": self.tenants_rejected,
            "fields_expected": self.fields_expected, "fields_updated": self.fields_updated,
            "decrypt_match_count": self.decrypt_match_count, "decrypt_diff_count": self.decrypt_diff_count,
            "stopped_early": self.stopped_early, "format_counts": dict(sorted(self.format_counts.items())),
        }


def hash_tenant(tenant_id: Any) -> str:
    return hashlib.sha256(("b2|" + str(tenant_id)).encode()).hexdigest()[:10]


def _emit(report: Report, **event: Any) -> None:
    report.events.append(event)


def _is_mysql(engine: AsyncEngine) -> bool:
    return engine.dialect.name in {"mysql", "mariadb"}


def _cas_clause(engine: AsyncEngine, column: str, param: str) -> str:
    # MySQL columns are utf8mb4_general_ci: plain '=' would treat 'a' and 'A' as equal and
    # could "win" a CAS against a value that really changed. BINARY forces a byte compare.
    return f"BINARY {column} <=> BINARY :{param}" if _is_mysql(engine) else f"{column} IS :{param}"


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, hide_parameters=True, echo=False, pool_pre_ping=False)


async def assert_apply_allowed(engine: AsyncEngine, *, app_database_url: str, target_url: str) -> None:
    if os.environ.get(ACK_ENV) != ACK_VALUE:
        raise Refused("ISOLATED_WRITE_ACK_MISSING")
    if app_database_url and app_database_url == target_url:
        raise Refused("TARGET_EQUALS_APPLICATION_DATABASE")
    async with engine.connect() as conn:
        try:
            rows = (await conn.execute(text(f"SELECT purpose FROM {MARKER_TABLE}"))).all()
        except Exception:  # no marker table -> not a rehearsal database
            raise Refused("REHEARSAL_MARKER_MISSING") from None
    if len(rows) != 1 or rows[0][0] != MARKER_PURPOSE:
        raise Refused("REHEARSAL_MARKER_INVALID")
    if not bool(getattr(crypto.settings, "WXPAY_ENVELOPE_WRITE_ENABLED", False)):
        raise Refused("ENVELOPE_WRITE_FLAG_OFF")
    try:
        crypto.get_keyring()
    except crypto.SecretEncryptionUnavailable as exc:
        raise Refused(exc.reason_code) from None


def _plan(row: Any) -> tuple[dict[str, dict[str, Any]], str]:
    """Classify both fields. Returns (per-field info, tenant verdict).

    Verdicts: EMPTY_OR_DONE (nothing to do), MIGRATE, REJECT.
    """
    info: dict[str, dict[str, Any]] = {}
    migrate, reject = False, False
    for index, (column, secret_field) in enumerate(FIELDS, start=1):
        value = row[index]
        fmt = crypto.classify_secret(value, secret_field)
        info[column] = {"format": fmt.value, "value": value, "secret_field": secret_field, "unreadable": None}
        if fmt is crypto.SecretFormat.LEGACY_PLAINTEXT:
            migrate = True
        elif fmt in {crypto.SecretFormat.LEGACY_RAW_FERNET, crypto.SecretFormat.INVALID_OR_UNKNOWN}:
            reject = True
        elif fmt is crypto.SecretFormat.VERSIONED_ENVELOPE:
            # An envelope the current Keyring cannot read (unknown key id, corrupted token,
            # missing Keyring) must not be masked by migrating the tenant's other field.
            try:
                crypto.decrypt_secret(value, secret_field, allow_legacy_plaintext=False)
            except crypto.WxPaySecretError as exc:
                info[column]["unreadable"] = exc.reason_code
                reject = True
    return info, ("REJECT" if reject else "MIGRATE" if migrate else "EMPTY_OR_DONE")


async def _list_tenants(engine: AsyncEngine, only: Optional[list[str]]) -> list[str]:
    sql = (
        "SELECT tenant_id FROM tenant WHERE "
        "(wx_api_key_v3 IS NOT NULL AND wx_api_key_v3 <> '') OR (wx_private_key IS NOT NULL AND wx_private_key <> '') "
        "ORDER BY tenant_id"
    )
    async with engine.connect() as conn:
        ids = [str(r[0]) for r in (await conn.execute(text(sql))).all()]
    return [t for t in ids if t in set(only)] if only else ids


_SELECT = "SELECT tenant_id, wx_api_key_v3, wx_private_key FROM tenant WHERE tenant_id = :tid"


async def _read_only_pass(engine: AsyncEngine, report: Report, tenants: list[str], mode: str) -> None:
    for tid in tenants:
        async with engine.connect() as conn:
            row = (await conn.execute(text(_SELECT), {"tid": tid})).first()
        if row is None:
            continue
        info, verdict = _plan(row)
        report.tenants_considered += 1
        event: dict[str, Any] = {"event": "tenant", "tid": hash_tenant(tid), "verdict": verdict, "fields": {}}
        for column, details in info.items():
            fmt = details["format"]
            report.format_counts[fmt] = report.format_counts.get(fmt, 0) + 1
            if fmt == "LEGACY_PLAINTEXT":
                report.fields_expected += 1
            status = fmt
            if mode == "verify" and fmt not in {"EMPTY"}:
                try:
                    crypto.decrypt_secret(details["value"], details["secret_field"])
                    status = fmt + "/READABLE"
                except crypto.WxPaySecretError as exc:
                    status = fmt + "/ERR:" + exc.reason_code
            event["fields"][column] = status
        if mode == "dry-run":
            event["would_migrate"] = verdict == "MIGRATE"
        if verdict == "REJECT":
            report.tenants_rejected += 1
        elif verdict == "EMPTY_OR_DONE":
            report.tenants_noop += 1
        _emit(report, **event)


async def _migrate_one(engine: AsyncEngine, tid: str, report: Report, hooks: Hooks, allowed_fields: Optional[set[str]] = None) -> str:
    """Returns MIGRATED / NOOP / REJECTED / CONFLICT / FAILED. Never raises for tenant-level errors."""
    encrypt = hooks.encrypt or crypto.encrypt_secret
    event: dict[str, Any] = {"event": "tenant", "tid": hash_tenant(tid), "fields": {}}
    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                row = (await conn.execute(text(_SELECT), {"tid": tid})).first()
                if row is None:
                    await trans.rollback()
                    event["outcome"] = "NOOP_TENANT_GONE"
                    _emit(report, **event)
                    return "NOOP"
                info, verdict = _plan(row)
                for column, details in info.items():
                    event["fields"][column] = details["format"]
                if verdict == "EMPTY_OR_DONE":
                    await trans.rollback()
                    event["outcome"] = "NOOP"
                    _emit(report, **event)
                    return "NOOP"
                if verdict == "REJECT":
                    await trans.rollback()
                    event["outcome"] = "REJECTED"
                    unreadable = {c: d["unreadable"] for c, d in info.items() if d["unreadable"]}
                    if unreadable:
                        event["unreadable_envelope"] = unreadable
                    _emit(report, **event)
                    return "REJECTED"
                if hooks.after_read:
                    await hooks.after_read(tid)

                new_values: dict[str, str] = {}
                originals: dict[str, Optional[str]] = {}
                for column, details in info.items():
                    originals[column] = details["value"]
                    if details["format"] == "LEGACY_PLAINTEXT":
                        if allowed_fields is not None and column not in allowed_fields:
                            continue  # not authorized for this run: left exactly as it is
                        if (tid, column) not in report.counted_fields:
                            report.counted_fields.add((tid, column))
                            report.fields_expected += 1
                        new_values[column] = encrypt(details["value"], details["secret_field"])
                        if not str(new_values[column]).startswith("enc:v1:"):
                            raise TenantFailure("ENCRYPT_NON_ENVELOPE")

                if not new_values:
                    await trans.rollback()
                    event["outcome"] = "NOOP_NO_AUTHORIZED_FIELD"
                    _emit(report, **event)
                    return "NOOP"
                if hooks.before_update:
                    await hooks.before_update(tid)

                sets = ", ".join(f"{col} = :new_{i}" for i, col in enumerate(FIELDS_BY_NAME_ORDER(new_values)))
                params: dict[str, Any] = {"tid": tid}
                where = ["tenant_id = :tid"]
                for i, (column, _sf) in enumerate(FIELDS):
                    # compare EVERY target column of the row to what this transaction read
                    params[f"old_{i}"] = originals[column]
                    where.append(_cas_clause(engine, column, f"old_{i}"))
                for i, col in enumerate(FIELDS_BY_NAME_ORDER(new_values)):
                    params[f"new_{i}"] = new_values[col]
                # updated_at = updated_at pins the non-secret audit timestamp on MySQL (ON UPDATE CURRENT_TIMESTAMP)
                result = await conn.execute(
                    text(f"UPDATE tenant SET {sets}, updated_at = updated_at WHERE {' AND '.join(where)}"), params
                )
                if result.rowcount != 1:
                    await trans.rollback()
                    event["outcome"] = "CONFLICT"
                    _emit(report, **event)
                    return "CONFLICT"

                # read back inside the same transaction and prove the B1 reader returns the original secret
                back = (await conn.execute(text(_SELECT), {"tid": tid})).first()
                matches = 0
                for index, (column, secret_field) in enumerate(FIELDS, start=1):
                    if column in new_values:
                        got = crypto.decrypt_secret(back[index], secret_field, allow_legacy_plaintext=False)
                        if got != originals[column] or not str(back[index]).startswith("enc:v1:"):
                            raise TenantFailure("VERIFY_MISMATCH")
                        matches += 1
                    elif back[index] != originals[column]:
                        raise TenantFailure("UNRELATED_FIELD_CHANGED")
                await trans.commit()
            except BaseException:
                if trans.is_active:
                    await trans.rollback()
                raise
        report.fields_updated += len(new_values)
        report.decrypt_match_count += matches
        event["outcome"] = "MIGRATED"
        event["fields_updated"] = sorted(new_values)
        _emit(report, **event)
        if hooks.after_commit:
            await hooks.after_commit(tid)
        return "MIGRATED"
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        raise
    except Exception as exc:
        # Never print str(exc): driver errors may embed SQL parameters (i.e. secrets).
        event["outcome"] = "FAILED"
        event["reason"] = getattr(exc, "reason_code", type(exc).__name__)
        report.decrypt_diff_count += 1 if event["reason"] == "VERIFY_MISMATCH" else 0
        _emit(report, **event)
        return "FAILED"


def FIELDS_BY_NAME_ORDER(new_values: dict[str, str]) -> list[str]:
    return [column for column, _sf in FIELDS if column in new_values]


async def run(
    engine: AsyncEngine,
    mode: str = "dry-run",
    *,
    only_tenants: Optional[list[str]] = None,
    hooks: Optional[Hooks] = None,
    stop_on_failure: bool = True,
    retry_conflicts: int = 0,
    app_database_url: str = "",
    target_url: str = "",
    allowed_fields: Optional[set[str]] = None,
    _skip_rehearsal_guard: bool = False,
) -> Report:
    hooks = hooks or Hooks()
    report = Report(mode=mode)
    if mode == "apply" and not _skip_rehearsal_guard:
        await assert_apply_allowed(engine, app_database_url=app_database_url, target_url=target_url)
    tenants = await _list_tenants(engine, only_tenants)
    if mode != "apply":
        await _read_only_pass(engine, report, tenants, mode)
        return report

    for tid in tenants:
        report.tenants_considered += 1
        outcome = await _migrate_one(engine, tid, report, hooks, allowed_fields)
        attempts = 0
        while outcome == "CONFLICT" and attempts < retry_conflicts:
            attempts += 1
            outcome = await _migrate_one(engine, tid, report, hooks, allowed_fields)
        if outcome == "MIGRATED":
            report.tenants_migrated += 1
        elif outcome == "NOOP":
            report.tenants_noop += 1
        elif outcome == "CONFLICT":
            report.tenants_conflict += 1
        elif outcome == "REJECTED":
            report.tenants_rejected += 1
        else:
            report.tenants_failed += 1
        if stop_on_failure and outcome in {"FAILED", "REJECTED"}:
            report.stopped_early = True
            break
    return report


# --------------------------------------------------------------------------------------------
# B4 production mode: nothing below runs unless a signed, single-use, single-tenant grant passes
# every check in wxpay_migration_authority.check_preconditions.
# --------------------------------------------------------------------------------------------
@dataclass
class ProductionEnv:
    """Injection points for the facts the executor reads from the host (real by default)."""

    now_fn: Callable[[], Any] = field(default=lambda: datetime.now(timezone.utc))
    host_fn: Callable[[], str] = field(default=lambda: socket.gethostname())
    git_fn: Optional[Callable[[str], tuple[str, bool]]] = None
    trusted_uids: frozenset = frozenset({0})


def git_state(repo_root: str) -> tuple[str, bool]:
    """(HEAD sha, worktree clean). Read-only git calls; an unreadable repo is 'not clean'."""
    import subprocess

    try:
        sha = subprocess.run(["git", "-C", repo_root, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30).stdout.strip()
        dirty = subprocess.run(["git", "-C", repo_root, "--no-optional-locks", "status", "--porcelain"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "", False
    return sha, (len(sha) == 40 and dirty == "")


def service_write_flag(env_path: str) -> str:
    """ABSENT | FALSE | TRUE for WXPAY_ENVELOPE_WRITE_ENABLED in the SERVICE's env file (only that key is read)."""
    try:
        with open(env_path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if line.startswith("WXPAY_ENVELOPE_WRITE_ENABLED="):
                    value = line.split("=", 1)[1].strip().strip("\"'").lower()
                    return "TRUE" if value in {"1", "true", "yes", "on"} else "FALSE"
    except OSError:
        return "TRUE"  # unreadable => fail closed
    return "ABSENT"


async def db_fingerprint(engine: AsyncEngine) -> str:
    async with engine.connect() as conn:
        if _is_mysql(engine):
            name, uuid_ = (await conn.execute(text("SELECT DATABASE(), @@server_uuid"))).one()
            basis = f"mysql|{name}|{uuid_}"
        else:
            basis = f"{engine.dialect.name}|{engine.url.database}"
    return hashlib.sha256(basis.encode()).hexdigest()


async def read_alembic_revision(engine: AsyncEngine) -> str:
    try:
        async with engine.connect() as conn:
            rows = (await conn.execute(text("SELECT version_num FROM alembic_version"))).all()
    except Exception:
        return "UNREADABLE"
    return str(rows[0][0]) if len(rows) == 1 else "AMBIGUOUS"


async def marker_present(engine: AsyncEngine) -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text(f"SELECT 1 FROM {MARKER_TABLE} LIMIT 1"))
        return True
    except Exception:
        return False


async def compute_plan(engine: AsyncEngine, tenant_id: str, fields: list[str], env: "ProductionEnv", repo_root: str,
                       backup_path: str = "", service_env_path: str = "") -> tuple["authority.Facts", dict[str, str]]:
    """Read-only. Everything the grant is bound to, plus the plan digest of the tenant's current state."""
    async with engine.connect() as conn:
        row = (await conn.execute(text(_SELECT), {"tid": tenant_id})).first()
    if row is None:
        raise authority.AuthorityRefused("TENANT_NOT_FOUND")
    info, _verdict = _plan(row)
    sha, clean = (env.git_fn or git_state)(repo_root)
    try:
        keyring_id: Optional[str] = crypto.get_keyring().active_key_id
    except crypto.SecretEncryptionUnavailable:
        keyring_id = None
    host, revision, fingerprint = env.host_fn(), await read_alembic_revision(engine), await db_fingerprint(engine)
    formats = {column: details["format"] for column, details in info.items()}
    hashes = {column: authority.hash_value(info[column]["value"]) for column in fields if column in info}
    digest = authority.plan_digest(
        host=host, backend_sha=sha, alembic_revision=revision, db_fingerprint=fingerprint,
        keyring_active_key_id=keyring_id or "UNAVAILABLE", tenant_id=tenant_id, fields=fields,
        field_formats=formats, old_value_hashes=hashes,
    )
    facts = authority.Facts(
        now=env.now_fn(), host=host, backend_sha=sha, worktree_clean=clean, alembic_revision=revision,
        db_fingerprint=fingerprint, rehearsal_marker_present=await marker_present(engine),
        keyring_active_key_id=keyring_id, service_write_flag=service_write_flag(service_env_path) if service_env_path else "ABSENT",
        backup=authority.inspect_backup(backup_path) if backup_path else authority.BackupFacts(False), plan_digest=digest,
    )
    return facts, formats


async def run_production(
    engine: AsyncEngine,
    *,
    grant_path: str,
    pubkey_path: str = authority.DEFAULT_PUBKEY_PATH,
    ledger_path: str = authority.DEFAULT_LEDGER_PATH,
    tenant_ids: list[str],
    cli_fields: Optional[list[str]] = None,
    repo_root: str,
    service_env_path: str,
    env: Optional[ProductionEnv] = None,
    hooks: Optional[Hooks] = None,
) -> Report:
    """The ONLY production write path. One tenant, one grant, one run."""
    env = env or ProductionEnv()
    cli_fields = cli_fields or []
    public_key = authority.load_public_key(pubkey_path, env.trusted_uids)
    try:
        with open(grant_path, encoding="utf-8") as handle:
            document = json.load(handle)
    except FileNotFoundError:
        raise authority.AuthorityRefused("GRANT_MISSING") from None
    except (OSError, ValueError):
        raise authority.AuthorityRefused("GRANT_MALFORMED") from None
    grant = authority.verify_grant_document(document, public_key, env.now_fn())

    if authority.Ledger(ledger_path, env.trusted_uids).already_used(grant["grant_id"]):
        raise authority.AuthorityRefused("GRANT_REUSED")  # report reuse before any state-dependent check
    authority.check_scope(grant, cli_tenant_ids=tenant_ids, cli_fields=cli_fields)  # no DB / host access yet
    # A grant pointed at the wrong database must be reported as exactly that, before any tenant lookup.
    if await db_fingerprint(engine) != grant["db_fingerprint"]:
        raise authority.AuthorityRefused("DB_FINGERPRINT_MISMATCH")
    facts, _formats = await compute_plan(
        engine, grant["tenant_id"], grant["fields"], env, repo_root, grant["backup_path"], service_env_path,
    )
    authority.check_preconditions(grant, facts, cli_tenant_ids=tenant_ids, cli_fields=cli_fields)
    if not bool(getattr(crypto.settings, "WXPAY_ENVELOPE_WRITE_ENABLED", False)):
        raise authority.AuthorityRefused("EXECUTOR_WRITE_FLAG_OFF")  # this process only; the service flag stays off

    ledger = authority.Ledger(ledger_path, env.trusted_uids)
    ledger.consume(grant["grant_id"], hash_tenant(grant["tenant_id"]), env.now_fn())
    outcome = "CRASHED_OR_INTERRUPTED"
    try:
        report = await run(
            engine, "apply", only_tenants=[grant["tenant_id"]], hooks=hooks, stop_on_failure=True, retry_conflicts=0,
            allowed_fields=set(grant["fields"]), _skip_rehearsal_guard=True,
        )
        outcome = "OK" if exit_code(report) == EXIT_OK else ("CONFLICT" if report.tenants_conflict else "FAILED")
        return report
    finally:
        ledger.finish(outcome, env.now_fn())


def exit_code(report: Report) -> int:
    if report.tenants_failed or report.tenants_rejected:
        return EXIT_FAILED
    if report.tenants_conflict:
        return EXIT_CONFLICT
    return EXIT_OK


def _print_report(report: Report) -> None:
    for event in report.events:
        print(json.dumps(event, sort_keys=True))
    print(json.dumps(report.summary(), sort_keys=True))


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=["inventory", "dry-run", "verify", "plan", "apply"], default="dry-run")
    parser.add_argument("--target", choices=["rehearsal", "production"], default="rehearsal")
    parser.add_argument("--apply", action="store_true", help="required together with --mode apply")
    parser.add_argument("--tenant-id", action="append", default=None, help="restrict to these tenant ids")
    parser.add_argument("--field", action="append", default=None, help="column(s) to migrate (production: must be inside the grant)")
    parser.add_argument("--continue-on-failure", action="store_true")
    parser.add_argument("--retry-conflicts", type=int, default=0)
    parser.add_argument("--grant-file", default="")
    parser.add_argument("--authority-pubkey", default=authority.DEFAULT_PUBKEY_PATH)
    parser.add_argument("--ledger", default=authority.DEFAULT_LEDGER_PATH)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--service-env-file", default="/www/wwwroot/xiao/saas-base/.env")
    args = parser.parse_args(argv)

    def refuse(reason: str) -> int:
        print(json.dumps({"event": "refused", "reason": reason}))
        return EXIT_REFUSED

    mode = args.mode
    if mode == "apply" and not args.apply:
        return refuse("APPLY_FLAG_MISSING")
    target_url = os.environ.get(URL_ENV, "")
    if not target_url:
        return refuse("TARGET_URL_ENV_MISSING")
    production = args.target == "production"
    if production and mode == "apply" and (args.continue_on_failure or args.retry_conflicts):
        return refuse("OPTION_NOT_ALLOWED_IN_PRODUCTION")
    if production and mode == "apply" and not args.grant_file:
        return refuse("GRANT_MISSING")
    if mode == "plan" and (not args.tenant_id or len(args.tenant_id) != 1 or not args.field):
        return refuse("PLAN_NEEDS_ONE_TENANT_AND_FIELDS")
    engine = make_engine(target_url)

    async def _go() -> int:
        try:
            if mode == "plan":
                facts, formats = await compute_plan(
                    engine, args.tenant_id[0], args.field, ProductionEnv(), args.repo_root, "", args.service_env_file
                )
                print(json.dumps({
                    "event": "plan", "host": facts.host, "backend_sha": facts.backend_sha, "worktree_clean": facts.worktree_clean,
                    "alembic_revision": facts.alembic_revision, "db_fingerprint": facts.db_fingerprint,
                    "keyring_active_key_id": facts.keyring_active_key_id, "service_write_flag": facts.service_write_flag,
                    "tenant_id": args.tenant_id[0], "fields": args.field, "field_formats": formats,
                    "plan_digest": facts.plan_digest, "rehearsal_marker_present": facts.rehearsal_marker_present,
                }, sort_keys=True))
                return EXIT_OK
            if production and mode == "apply":
                report = await run_production(
                    engine, grant_path=args.grant_file, pubkey_path=args.authority_pubkey, ledger_path=args.ledger,
                    tenant_ids=args.tenant_id or [], cli_fields=args.field, repo_root=args.repo_root,
                    service_env_path=args.service_env_file,
                )
            else:
                report = await run(
                    engine, mode, only_tenants=args.tenant_id, stop_on_failure=not args.continue_on_failure,
                    retry_conflicts=max(0, args.retry_conflicts),
                    app_database_url=os.environ.get("DATABASE_URL", ""), target_url=target_url,
                )
        except (Refused, authority.AuthorityRefused) as exc:
            return refuse(exc.reason)
        finally:
            await engine.dispose()
        _print_report(report)
        return exit_code(report)

    return asyncio.run(_go())


if __name__ == "__main__":
    sys.exit(main())
