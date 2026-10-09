#!/usr/bin/env python3
"""Owner-side (OFFLINE) tool for the WeChat Pay secret migration authorization model.

Run on the owner's own machine, never on the production host:

  keygen   create the Ed25519 authority key pair (private key is passphrase-protected)
  issue    sign a short-lived, single-tenant grant from the executor's read-only `plan` output
  verify   check a grant's signature and validity window against a public key

The private key never leaves the owner's machine; only the PUBLIC key is installed on the server
(root-owned, /etc/saas-base/migration-authority.pub). Passphrases are read with getpass and are
never accepted as arguments. This tool never talks to the database or the production host.
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import wxpay_migration_authority as authority  # noqa: E402

PLAN_KEYS = ("host", "backend_sha", "alembic_revision", "db_fingerprint", "keyring_active_key_id", "tenant_id", "fields", "plan_digest")


def build_grant_from_plan(plan: dict, *, backup_path: str, backup_sha256: str, recovery_attested_at: str,
                          now: datetime, ttl_minutes: int = 30) -> dict:
    """Pure function: executor `plan` output + owner attestations -> unsigned grant."""
    if plan.get("event") != "plan" or any(key not in plan for key in PLAN_KEYS):
        raise ValueError("not an executor plan document")
    if not plan.get("worktree_clean"):
        raise ValueError("plan was taken from a dirty worktree")
    if plan.get("rehearsal_marker_present"):
        raise ValueError("plan was taken from a rehearsal database")
    if plan.get("service_write_flag") == "TRUE":
        raise ValueError("service envelope write flag is on")
    if plan["keyring_active_key_id"] in (None, ""):
        raise ValueError("keyring was unavailable when the plan was taken")
    return authority.new_grant(
        host=plan["host"], tenant_id=plan["tenant_id"], fields=plan["fields"], backend_sha=plan["backend_sha"],
        alembic_revision=plan["alembic_revision"], db_fingerprint=plan["db_fingerprint"], plan_digest=plan["plan_digest"],
        keyring_active_key_id=plan["keyring_active_key_id"], backup_path=backup_path, backup_sha256=backup_sha256,
        recovery_attested_at=recovery_attested_at, now=now, ttl_minutes=ttl_minutes,
    )


def _passphrase(confirm: bool) -> bytes:
    first = getpass.getpass("Authority key passphrase: ")
    if confirm and getpass.getpass("Repeat passphrase: ") != first:
        raise SystemExit("passphrases differ")
    return first.encode("utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    keygen = sub.add_parser("keygen")
    keygen.add_argument("--private-out", required=True)
    keygen.add_argument("--public-out", required=True)
    issue = sub.add_parser("issue")
    issue.add_argument("--plan-file", required=True)
    issue.add_argument("--backup-path", required=True, help="path of the fresh DB backup ON THE SERVER")
    issue.add_argument("--backup-sha256", required=True)
    issue.add_argument("--recovery-attested-at", required=True, help="UTC, e.g. 2026-10-09T09:30:00Z (when Keyring recovery was last verified)")
    issue.add_argument("--private-key", required=True)
    issue.add_argument("--ttl-minutes", type=int, default=30)
    issue.add_argument("--out", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--grant", required=True)
    verify.add_argument("--public-key", required=True)
    args = parser.parse_args(argv)

    if args.command == "keygen":
        private_pem, public_pem = authority.generate_keypair(_passphrase(confirm=True))
        for path, data, mode in ((args.private_out, private_pem, 0o600), (args.public_out, public_pem, 0o644)):
            target = Path(path)
            if target.exists():
                raise SystemExit(f"refusing to overwrite {path}")
            target.write_bytes(data)
            target.chmod(mode)
        print(json.dumps({"event": "keygen", "private_key": args.private_out, "public_key": args.public_out}))
        return 0
    if args.command == "issue":
        plan = json.loads(Path(args.plan_file).read_text(encoding="utf-8").strip().splitlines()[-1])
        grant = build_grant_from_plan(
            plan, backup_path=args.backup_path, backup_sha256=args.backup_sha256,
            recovery_attested_at=args.recovery_attested_at, now=datetime.now(timezone.utc), ttl_minutes=args.ttl_minutes,
        )
        document = authority.sign_grant(Path(args.private_key).read_bytes(), grant, _passphrase(confirm=False))
        target = Path(args.out)
        if target.exists():
            raise SystemExit(f"refusing to overwrite {args.out}")
        target.write_text(json.dumps(document, indent=1), encoding="utf-8")
        print(json.dumps({"event": "issued", "grant_id": grant["grant_id"], "tenant_id": grant["tenant_id"],
                          "fields": grant["fields"], "expires_at": grant["expires_at"]}))
        return 0
    document = json.loads(Path(args.grant).read_text(encoding="utf-8"))
    public = authority.load_public_key(args.public_key, trusted_uids=frozenset({Path(args.public_key).stat().st_uid}))
    grant = authority.verify_grant_document(document, public, datetime.now(timezone.utc))
    print(json.dumps({"event": "grant_valid", "grant_id": grant["grant_id"], "tenant_id": grant["tenant_id"], "expires_at": grant["expires_at"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
