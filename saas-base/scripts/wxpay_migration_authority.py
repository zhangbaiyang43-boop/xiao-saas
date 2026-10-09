#!/usr/bin/env python3
"""Production authorization model for the WeChat Pay secret migration executor (B4).

A production migration may only run with a *grant*: a small JSON document signed (Ed25519) by
the owner's offline authority key and verified on the production host against a root-owned
public key that is NOT part of the repository.  A grant is deliberately narrow:

* one tenant, a named subset of the two whitelisted columns;
* bound to the production host, the exact Backend git SHA, the Alembic revision, the target
  database fingerprint, the Keyring active key id, a fresh database backup (sha256) and an
  owner attestation that Keyring recovery was verified;
* bound to an immutable *plan digest* that covers the tenant's current secret formats and the
  hash of the exact old values the compare-and-swap will pin, so any drift invalidates it;
* short lived (<= 1 hour) and single use (consumed in a locked, fsync'ed ledger before the
  first write, so a crash burns the grant instead of leaving it replayable).

The grant is an authorization record, not a cryptographic secret: it contains no key material
and is never used as an encryption key.  Nothing here is imported by the application.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

try:  # POSIX only; the executor is a server-side tool
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

GRANT_VERSION = "b4-grant-v1"
GRANT_PURPOSE = "WXPAY_SECRET_MIGRATION"
SIGNATURE_DOMAIN = b"wxpay-b4-grant-v1\n"
MAX_GRANT_LIFETIME = timedelta(hours=1)
CLOCK_SKEW = timedelta(seconds=60)
BACKUP_MAX_AGE = timedelta(hours=24)
RECOVERY_ATTESTATION_MAX_AGE = timedelta(days=90)
ALLOWED_FIELDS = ("wx_api_key_v3", "wx_private_key")
DEFAULT_PUBKEY_PATH = "/etc/saas-base/migration-authority.pub"
DEFAULT_LEDGER_PATH = "/var/lib/saas-base/wxpay-migration-ledger.jsonl"

GRANT_KEYS = frozenset({
    "version", "purpose", "grant_id", "host", "tenant_id", "fields", "backend_sha", "alembic_revision",
    "db_fingerprint", "plan_digest", "keyring_active_key_id", "backup_path", "backup_sha256",
    "recovery_attested_at", "issued_at", "expires_at",
})
_HEX40 = frozenset("0123456789abcdef")


class AuthorityRefused(RuntimeError):
    """A production precondition failed. Carries a stable, secret-free reason code only."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def canonical(document: Any) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _utc(value: str, reason: str) -> datetime:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        raise AuthorityRefused(reason) from None
    return parsed


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hex(value: Any, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and set(value) <= _HEX40


# ---------------------------------------------------------------------------------------- keys
def generate_keypair(passphrase: Optional[bytes] = None) -> tuple[bytes, bytes]:
    """Owner-side only. Returns (private_pem, public_pem)."""
    key = Ed25519PrivateKey.generate()
    encryption = serialization.BestAvailableEncryption(passphrase) if passphrase else serialization.NoEncryption()
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, encryption)
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return private, public


def _check_trusted_file(path: str, trusted_uids: frozenset[int], *, forbid_group_other_write: bool = True) -> int:
    """Open without following links; require a regular file owned by a trusted uid."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        raise AuthorityRefused("AUTHORITY_KEY_MISSING") from None
    except OSError:
        raise AuthorityRefused("AUTHORITY_KEY_UNTRUSTED") from None
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid not in trusted_uids or (
        forbid_group_other_write and stat.S_IMODE(info.st_mode) & 0o022
    ):
        os.close(fd)
        raise AuthorityRefused("AUTHORITY_KEY_UNTRUSTED")
    return fd


def load_public_key(path: str = DEFAULT_PUBKEY_PATH, trusted_uids: frozenset[int] = frozenset({0})) -> Ed25519PublicKey:
    fd = _check_trusted_file(path, trusted_uids)
    try:
        data = os.read(fd, 8192)
    finally:
        os.close(fd)
    try:
        key = serialization.load_pem_public_key(data)
    except ValueError:
        raise AuthorityRefused("AUTHORITY_KEY_INVALID") from None
    if not isinstance(key, Ed25519PublicKey):
        raise AuthorityRefused("AUTHORITY_KEY_INVALID")
    return key


# --------------------------------------------------------------------------------------- grants
def sign_grant(private_pem: bytes, grant: dict[str, Any], passphrase: Optional[bytes] = None) -> dict[str, Any]:
    """Owner-side only (offline). The executor never signs."""
    key = serialization.load_pem_private_key(private_pem, password=passphrase)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("authority key must be Ed25519")
    signature = key.sign(SIGNATURE_DOMAIN + canonical(grant))
    return {"grant": grant, "signature": base64.b64encode(signature).decode("ascii")}


def new_grant(*, host: str, tenant_id: str, fields: list[str], backend_sha: str, alembic_revision: str,
              db_fingerprint: str, plan_digest: str, keyring_active_key_id: str, backup_path: str,
              backup_sha256: str, recovery_attested_at: str, now: datetime, ttl_minutes: int = 30) -> dict[str, Any]:
    ttl = min(timedelta(minutes=ttl_minutes), MAX_GRANT_LIFETIME)
    return {
        "version": GRANT_VERSION, "purpose": GRANT_PURPOSE, "grant_id": uuid.uuid4().hex, "host": host,
        "tenant_id": tenant_id, "fields": list(fields), "backend_sha": backend_sha,
        "alembic_revision": alembic_revision, "db_fingerprint": db_fingerprint, "plan_digest": plan_digest,
        "keyring_active_key_id": keyring_active_key_id, "backup_path": backup_path, "backup_sha256": backup_sha256,
        "recovery_attested_at": recovery_attested_at, "issued_at": iso(now), "expires_at": iso(now + ttl),
    }


def verify_grant_document(document: Any, public_key: Ed25519PublicKey, now: datetime) -> dict[str, Any]:
    """Structure, signature, validity window and field whitelist. Raises AuthorityRefused."""
    if not isinstance(document, dict) or set(document) != {"grant", "signature"} or not isinstance(document["grant"], dict):
        raise AuthorityRefused("GRANT_MALFORMED")
    grant = document["grant"]
    if set(grant) != GRANT_KEYS:
        raise AuthorityRefused("GRANT_MALFORMED")
    try:
        signature = base64.b64decode(document["signature"], validate=True)
        public_key.verify(signature, SIGNATURE_DOMAIN + canonical(grant))
    except (InvalidSignature, ValueError, TypeError):
        raise AuthorityRefused("GRANT_SIGNATURE_INVALID") from None
    if grant["version"] != GRANT_VERSION or grant["purpose"] != GRANT_PURPOSE:
        raise AuthorityRefused("GRANT_MALFORMED")
    fields = grant["fields"]
    if not isinstance(fields, list) or not fields or len(set(fields)) != len(fields) or any(f not in ALLOWED_FIELDS for f in fields):
        raise AuthorityRefused("GRANT_FIELD_NOT_ALLOWED")
    tenant = grant["tenant_id"]
    if not isinstance(tenant, str) or not tenant or any(ch in tenant for ch in "*%,;\n\r ") :
        raise AuthorityRefused("GRANT_TENANT_INVALID")
    for name, length in (("backend_sha", 40), ("plan_digest", 64), ("db_fingerprint", 64), ("backup_sha256", 64)):
        if not _hex(grant[name], length):
            raise AuthorityRefused("GRANT_MALFORMED")
    for name in ("grant_id", "host", "alembic_revision", "keyring_active_key_id", "backup_path"):
        if not isinstance(grant[name], str) or not grant[name]:
            raise AuthorityRefused("GRANT_MALFORMED")
    issued = _utc(grant["issued_at"], "GRANT_MALFORMED")
    expires = _utc(grant["expires_at"], "GRANT_MALFORMED")
    if expires - issued > MAX_GRANT_LIFETIME or expires <= issued:
        raise AuthorityRefused("GRANT_LIFETIME_INVALID")
    if now + CLOCK_SKEW < issued:
        raise AuthorityRefused("GRANT_NOT_YET_VALID")
    if now > expires:
        raise AuthorityRefused("GRANT_EXPIRED")
    return grant


# --------------------------------------------------------------------------------------- facts
@dataclass(frozen=True)
class BackupFacts:
    exists: bool
    sha256: str = ""
    mtime: Optional[datetime] = None


@dataclass(frozen=True)
class Facts:
    """Everything the executor learned about the live world (injected in tests)."""

    now: datetime
    host: str
    backend_sha: str
    worktree_clean: bool
    alembic_revision: str
    db_fingerprint: str
    rehearsal_marker_present: bool
    keyring_active_key_id: Optional[str]  # None => Keyring unavailable
    service_write_flag: str  # ABSENT | FALSE | TRUE
    backup: BackupFacts
    plan_digest: str


def inspect_backup(path: str) -> BackupFacts:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return BackupFacts(False)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            return BackupFacts(False)
        digest = hashlib.sha256()
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                break
            digest.update(chunk)
        return BackupFacts(True, digest.hexdigest(), datetime.fromtimestamp(info.st_mtime, tz=timezone.utc))
    finally:
        os.close(fd)


def plan_digest(*, host: str, backend_sha: str, alembic_revision: str, db_fingerprint: str, keyring_active_key_id: str,
                tenant_id: str, fields: list[str], field_formats: dict[str, str], old_value_hashes: dict[str, str]) -> str:
    return hashlib.sha256(canonical({
        "v": "b4-plan-v1", "host": host, "backend_sha": backend_sha, "alembic_revision": alembic_revision,
        "db_fingerprint": db_fingerprint, "keyring_active_key_id": keyring_active_key_id, "tenant_id": tenant_id,
        "fields": sorted(fields), "field_formats": field_formats, "old_value_hashes": old_value_hashes,
    })).hexdigest()


def hash_value(value: Optional[str]) -> str:
    return hashlib.sha256(("b4|" + (value or "")).encode("utf-8")).hexdigest()


def check_scope(grant: dict[str, Any], *, cli_tenant_ids: list[str], cli_fields: list[str]) -> None:
    """Scope checks that need no database or host access (run first, so a bad request touches nothing)."""
    if len(cli_tenant_ids) != 1:
        raise AuthorityRefused("TENANT_SCOPE_NOT_SINGLE")
    if cli_tenant_ids[0] != grant["tenant_id"]:
        raise AuthorityRefused("TENANT_MISMATCH")
    if cli_fields and not set(cli_fields) <= set(ALLOWED_FIELDS):
        raise AuthorityRefused("FIELD_NOT_WHITELISTED")
    if cli_fields and not set(cli_fields) <= set(grant["fields"]):
        raise AuthorityRefused("GRANT_FIELD_NOT_ALLOWED")


def check_preconditions(grant: dict[str, Any], facts: Facts, *, cli_tenant_ids: list[str], cli_fields: list[str]) -> None:
    """Every production precondition, in a fixed order. Raises AuthorityRefused(reason)."""
    check_scope(grant, cli_tenant_ids=cli_tenant_ids, cli_fields=cli_fields)
    if facts.rehearsal_marker_present:
        raise AuthorityRefused("REHEARSAL_MARKER_PRESENT_IN_PRODUCTION")
    if facts.host != grant["host"]:
        raise AuthorityRefused("HOST_MISMATCH")
    if facts.db_fingerprint != grant["db_fingerprint"]:
        raise AuthorityRefused("DB_FINGERPRINT_MISMATCH")
    if facts.backend_sha != grant["backend_sha"]:
        raise AuthorityRefused("BACKEND_SHA_MISMATCH")
    if not facts.worktree_clean:
        raise AuthorityRefused("WORKTREE_DIRTY")
    if facts.alembic_revision != grant["alembic_revision"]:
        raise AuthorityRefused("ALEMBIC_MISMATCH")
    if facts.keyring_active_key_id is None:
        raise AuthorityRefused("KEYRING_UNAVAILABLE")
    if facts.keyring_active_key_id != grant["keyring_active_key_id"]:
        raise AuthorityRefused("KEYRING_KEY_ID_MISMATCH")
    if facts.service_write_flag == "TRUE":
        raise AuthorityRefused("SERVICE_WRITE_FLAG_ON")
    if not facts.backup.exists:
        raise AuthorityRefused("BACKUP_UNAVAILABLE")
    if facts.backup.sha256 != grant["backup_sha256"]:
        raise AuthorityRefused("BACKUP_HASH_MISMATCH")
    if facts.backup.mtime is None or facts.now - facts.backup.mtime > BACKUP_MAX_AGE:
        raise AuthorityRefused("BACKUP_STALE")
    attested = _utc(grant["recovery_attested_at"], "RECOVERY_ATTESTATION_INVALID")
    if facts.now - attested > RECOVERY_ATTESTATION_MAX_AGE or attested > facts.now + CLOCK_SKEW:
        raise AuthorityRefused("RECOVERY_ATTESTATION_STALE")
    if facts.plan_digest != grant["plan_digest"]:
        raise AuthorityRefused("PLAN_DIGEST_MISMATCH")


# --------------------------------------------------------------------------------------- ledger
class Ledger:
    """Append-only, flock-guarded record of consumed grants (single use + one run at a time)."""

    def __init__(self, path: str, trusted_uids: frozenset[int] = frozenset({0})):
        self.path = path
        self.trusted_uids = trusted_uids
        self.fd: Optional[int] = None
        self.grant_id: Optional[str] = None

    def already_used(self, grant_id: str) -> bool:
        """Read-only early check (no lock, no file creation). consume() re-checks under the lock."""
        try:
            with open(self.path, encoding="utf-8") as handle:
                return any(json.loads(line).get("grant_id") == grant_id for line in handle if line.strip())
        except FileNotFoundError:
            return False
        except (OSError, ValueError):
            raise AuthorityRefused("LEDGER_CORRUPT") from None

    def consume(self, grant_id: str, tenant_hash: str, now: datetime) -> None:
        if fcntl is None:  # pragma: no cover
            raise AuthorityRefused("LEDGER_UNAVAILABLE")
        flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(self.path, flags, 0o600)
        except OSError:
            raise AuthorityRefused("LEDGER_UNAVAILABLE") from None
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid not in self.trusted_uids or stat.S_IMODE(info.st_mode) & 0o077:
            os.close(fd)
            raise AuthorityRefused("LEDGER_UNTRUSTED")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise AuthorityRefused("LEDGER_LOCKED") from None
        os.lseek(fd, 0, os.SEEK_SET)
        content = b""
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                break
            content += chunk
        for line in content.decode("utf-8", "replace").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                os.close(fd)
                raise AuthorityRefused("LEDGER_CORRUPT") from None
            if entry.get("grant_id") == grant_id:
                os.close(fd)
                raise AuthorityRefused("GRANT_REUSED")
        self.fd, self.grant_id = fd, grant_id
        self._append({"event": "consumed", "grant_id": grant_id, "tenant": tenant_hash, "at": iso(now)})

    def _append(self, entry: dict[str, Any]) -> None:
        assert self.fd is not None
        os.write(self.fd, (json.dumps(entry, sort_keys=True) + "\n").encode("ascii"))
        os.fsync(self.fd)

    def finish(self, outcome: str, now: datetime) -> None:
        if self.fd is None:
            return
        try:
            self._append({"event": "finished", "grant_id": self.grant_id, "outcome": outcome, "at": iso(now)})
        finally:
            os.close(self.fd)  # releases the flock
            self.fd = None
