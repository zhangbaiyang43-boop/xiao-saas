#!/usr/bin/env python3
"""WeChat Pay tenant-secret migration executor -- B2 ISOLATED-REHEARSAL PROTOTYPE.

Moves legacy plaintext ``tenant.wx_api_key_v3`` / ``tenant.wx_private_key`` values to the
B1 versioned envelope (``enc:v1:<key-id>:<fernet-token>``).

NOT authorized for production. Safety properties enforced in code:

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
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine  # noqa: E402

from app.core import wxpay_secret_crypto as crypto  # noqa: E402

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


async def _migrate_one(engine: AsyncEngine, tid: str, report: Report, hooks: Hooks) -> str:
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
                        if (tid, column) not in report.counted_fields:
                            report.counted_fields.add((tid, column))
                            report.fields_expected += 1
                        new_values[column] = encrypt(details["value"], details["secret_field"])
                        if not str(new_values[column]).startswith("enc:v1:"):
                            raise TenantFailure("ENCRYPT_NON_ENVELOPE")

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
) -> Report:
    hooks = hooks or Hooks()
    report = Report(mode=mode)
    if mode == "apply":
        await assert_apply_allowed(engine, app_database_url=app_database_url, target_url=target_url)
    tenants = await _list_tenants(engine, only_tenants)
    if mode != "apply":
        await _read_only_pass(engine, report, tenants, mode)
        return report

    for tid in tenants:
        report.tenants_considered += 1
        outcome = await _migrate_one(engine, tid, report, hooks)
        attempts = 0
        while outcome == "CONFLICT" and attempts < retry_conflicts:
            attempts += 1
            outcome = await _migrate_one(engine, tid, report, hooks)
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
    parser.add_argument("--mode", choices=["inventory", "dry-run", "verify", "apply"], default="dry-run")
    parser.add_argument("--apply", action="store_true", help="required together with --mode apply")
    parser.add_argument("--tenant-id", action="append", default=None, help="restrict to these tenant ids")
    parser.add_argument("--continue-on-failure", action="store_true")
    parser.add_argument("--retry-conflicts", type=int, default=0)
    args = parser.parse_args(argv)

    mode = args.mode
    if mode == "apply" and not args.apply:
        print(json.dumps({"event": "refused", "reason": "APPLY_FLAG_MISSING"}))
        return EXIT_REFUSED
    target_url = os.environ.get(URL_ENV, "")
    if not target_url:
        print(json.dumps({"event": "refused", "reason": "TARGET_URL_ENV_MISSING"}))
        return EXIT_REFUSED
    engine = make_engine(target_url)

    async def _go() -> int:
        try:
            report = await run(
                engine, mode, only_tenants=args.tenant_id, stop_on_failure=not args.continue_on_failure,
                retry_conflicts=max(0, args.retry_conflicts),
                app_database_url=os.environ.get("DATABASE_URL", ""), target_url=target_url,
            )
        except Refused as exc:
            print(json.dumps({"event": "refused", "reason": exc.reason}))
            return EXIT_REFUSED
        finally:
            await engine.dispose()
        _print_report(report)
        return exit_code(report)

    return asyncio.run(_go())


if __name__ == "__main__":
    sys.exit(main())
