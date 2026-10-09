"""Versioned encryption contract for Tenant WeChat Pay secrets.

The keyring is an immutable process snapshot loaded from a local runtime secret
file.  This module never logs or returns key material, ciphertext, plaintext,
or secret fingerprints in an exception.
"""
from __future__ import annotations

import errno
import json
import os
import re
import stat
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import settings


ENVELOPE_VERSION = "v1"
KEY_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{0,31}")
FERNET_TOKEN_PATTERN = re.compile(r"gAAAA[A-Za-z0-9_-]*={0,2}")
KEYRING_ROOT_FIELDS = frozenset({"formatVersion", "activeKeyId", "keys"})
KEYRING_KEY_FIELDS = frozenset({"keyId", "algorithm", "usage", "key"})
KEY_USAGES = frozenset({"encrypt-decrypt", "decrypt-only"})
MAX_API_KEY_ENVELOPE_CHARS = 256
MAX_PRIVATE_KEY_ENVELOPE_CHARS = 65535
# Conservative maximum for a 32-character key id and Fernet overhead.
MAX_PRIVATE_KEY_PLAINTEXT_BYTES = 49055


class SecretField(str, Enum):
    API_V3_KEY = "wx_api_key_v3"
    PRIVATE_KEY = "wx_private_key"


class SecretFormat(str, Enum):
    EMPTY = "EMPTY"
    VERSIONED_ENVELOPE = "VERSIONED_ENVELOPE"
    LEGACY_RAW_FERNET = "LEGACY_RAW_FERNET"
    LEGACY_PLAINTEXT = "LEGACY_PLAINTEXT"
    INVALID_OR_UNKNOWN = "INVALID_OR_UNKNOWN"


class WxPaySecretError(RuntimeError):
    def __init__(self, reason_code: str):
        self.reason_code = reason_code
        super().__init__(reason_code)


class SecretEncryptionUnavailable(WxPaySecretError):
    """A new secret cannot be encrypted safely."""


class SecretDecryptionError(WxPaySecretError):
    """A stored secret cannot be authenticated and validated safely."""


@dataclass(frozen=True)
class KeyringKey:
    key_id: str
    usage: str
    fernet: Fernet


@dataclass(frozen=True)
class KeyringSnapshot:
    active_key_id: str
    keys: Mapping[str, KeyringKey]

    @property
    def active_key(self) -> KeyringKey:
        return self.keys[self.active_key_id]

    @property
    def legacy_raw_keys(self) -> tuple[KeyringKey, ...]:
        return tuple(key for key in self.keys.values() if key.usage == "decrypt-only")


def _configuration_error() -> SecretEncryptionUnavailable:
    return SecretEncryptionUnavailable("WXPAY_KEYRING_INVALID")


def _validate_key_id(value: object) -> str:
    if not isinstance(value, str) or not KEY_ID_PATTERN.fullmatch(value):
        raise _configuration_error()
    return value


@dataclass(frozen=True)
class KeyringSourcePolicy:
    """Which keyring files this process may trust.

    Source A (root-only): a regular file owned by uid 0, mode 0400/0600, whose
    whole directory chain is root-owned and not group/other writable.  A
    non-root service cannot open it, so it is never elevated into reading it.
    Source B (systemd LoadCredential): a service-owned 0400/0600 copy that sits
    directly in ``/run/credentials/<unit>`` and in the directory systemd
    announced through ``CREDENTIALS_DIRECTORY``.  Nothing else is trusted.
    ``extra_trusted_uids`` / ``verify_ancestors`` exist only so tests can use
    temp directories; production uses the default policy.
    """

    credentials_root: str = "/run/credentials"
    extra_trusted_uids: frozenset = frozenset()
    verify_ancestors: bool = True


KEYRING_SOURCE_POLICY = KeyringSourcePolicy()
MAX_KEYRING_BYTES = 65536
_READ_CHUNK = 16384


def _keyring_error(reason_code: str) -> SecretEncryptionUnavailable:
    return SecretEncryptionUnavailable(reason_code)


def _permission_denied() -> SecretEncryptionUnavailable:
    return _keyring_error("WXPAY_KEYRING_PERMISSION_DENIED")


def _open_error(exc: OSError) -> SecretEncryptionUnavailable:
    if exc.errno == errno.ENOENT:
        return _keyring_error("WXPAY_KEYRING_MISSING")
    # EACCES/EPERM, and ELOOP/ENOTDIR from O_NOFOLLOW/O_DIRECTORY (symlinks).
    return _permission_denied()


def _read_keyring_bytes(path: str, policy: KeyringSourcePolicy) -> bytes:
    """Open the keyring without following links and validate it by descriptor.

    Every path component is opened relative to its parent descriptor with
    O_NOFOLLOW, and type/owner/mode/size come from fstat() of the very
    descriptor that is then read, so there is no check-then-open gap.
    """
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None or not hasattr(os, "geteuid") or os.open not in os.supports_dir_fd:
        raise _permission_denied()
    if not path.startswith("/") or any(part in {".", ".."} for part in path.split("/")):
        raise _keyring_error("WXPAY_KEYRING_INVALID")
    names = [part for part in path.split("/") if part]
    if not names:
        raise _keyring_error("WXPAY_KEYRING_INVALID")
    euid = os.geteuid()
    cloexec = getattr(os, "O_CLOEXEC", 0)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | nofollow | cloexec
    file_flags = os.O_RDONLY | nofollow | cloexec | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOCTTY", 0)

    credentials_names = [part for part in policy.credentials_root.split("/") if part]
    in_credentials = (
        len(names) == len(credentials_names) + 2 and names[: len(credentials_names)] == credentials_names
    )
    if in_credentials and os.environ.get("CREDENTIALS_DIRECTORY") != "/" + "/".join(names[:-1]):
        in_credentials = False

    opened: list[int] = []
    try:
        try:
            current = os.open("/", directory_flags)
            opened.append(current)
            for index, name in enumerate(names[:-1]):
                current = os.open(name, directory_flags, dir_fd=current)
                opened.append(current)
                if not policy.verify_ancestors:
                    continue
                info = os.fstat(current)
                is_credentials_dir = in_credentials and index == len(names) - 2
                allowed = {0} | set(policy.extra_trusted_uids) | ({euid} if is_credentials_dir else set())
                if info.st_uid not in allowed or stat.S_IMODE(info.st_mode) & 0o022:
                    raise _permission_denied()
            fd = os.open(names[-1], file_flags, dir_fd=current)
            opened.append(fd)
        except OSError as exc:
            raise _open_error(exc) from exc

        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise _permission_denied()
        if stat.S_IMODE(info.st_mode) & ~0o600:
            raise _permission_denied()
        owner_ok = (
            info.st_uid == 0
            or info.st_uid in policy.extra_trusted_uids
            or (in_credentials and info.st_uid == euid)
        )
        if not owner_ok:
            raise _permission_denied()
        if info.st_size > MAX_KEYRING_BYTES:
            raise _keyring_error("WXPAY_KEYRING_INVALID")

        chunks: list[bytes] = []
        total = 0
        try:
            while True:
                chunk = os.read(fd, _READ_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_KEYRING_BYTES:
                    raise _keyring_error("WXPAY_KEYRING_INVALID")
                chunks.append(chunk)
            after = os.fstat(fd)
        except OSError as exc:
            raise _open_error(exc) from exc
        stable = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_uid, info.st_mode)
        if stable != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_uid, after.st_mode):
            raise _keyring_error("WXPAY_KEYRING_INVALID")
        return b"".join(chunks)
    finally:
        for descriptor in opened:
            try:
                os.close(descriptor)
            except OSError:
                pass


def load_keyring(path: str | Path, policy: KeyringSourcePolicy | None = None) -> KeyringSnapshot:
    raw = _read_keyring_bytes(str(path), policy or KEYRING_SOURCE_POLICY)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise _keyring_error("WXPAY_KEYRING_INVALID_JSON") from exc

    if not isinstance(payload, dict) or set(payload) != KEYRING_ROOT_FIELDS:
        raise _configuration_error()
    if payload.get("formatVersion") != 1 or not isinstance(payload.get("keys"), list):
        raise _configuration_error()
    active_key_id = _validate_key_id(payload.get("activeKeyId"))

    parsed: dict[str, KeyringKey] = {}
    active_usage_count = 0
    for item in payload["keys"]:
        if not isinstance(item, dict) or set(item) != KEYRING_KEY_FIELDS:
            raise _configuration_error()
        key_id = _validate_key_id(item.get("keyId"))
        if key_id in parsed or item.get("algorithm") != "fernet" or item.get("usage") not in KEY_USAGES:
            raise _configuration_error()
        try:
            raw_key = item.get("key")
            if not isinstance(raw_key, str):
                raise ValueError
            fernet = Fernet(raw_key.encode("ascii"))
        except (UnicodeError, TypeError, ValueError) as exc:
            raise _configuration_error() from exc
        usage = str(item["usage"])
        active_usage_count += int(usage == "encrypt-decrypt")
        parsed[key_id] = KeyringKey(key_id=key_id, usage=usage, fernet=fernet)

    if active_usage_count != 1 or active_key_id not in parsed or parsed[active_key_id].usage != "encrypt-decrypt":
        raise _keyring_error("WXPAY_KEYRING_ACTIVE_KEY_INVALID")
    return KeyringSnapshot(active_key_id=active_key_id, keys=MappingProxyType(parsed))


@dataclass(frozen=True)
class _KeyringOutcome:
    snapshot: KeyringSnapshot | None
    reason_code: str


_keyring_lock = threading.Lock()
_keyring_outcome: _KeyringOutcome | None = None


def _load_outcome() -> _KeyringOutcome:
    path = str(getattr(settings, "WXPAY_SECRET_KEYRING_PATH", "") or "").strip()
    if not path:
        return _KeyringOutcome(None, "WXPAY_KEYRING_MISSING")
    try:
        return _KeyringOutcome(load_keyring(path), "CONFIGURED")
    except SecretEncryptionUnavailable as exc:
        return _KeyringOutcome(None, exc.reason_code)
    except Exception:  # noqa: BLE001 - any unexpected failure is a sticky, sanitized failure
        return _KeyringOutcome(None, "WXPAY_KEYRING_INVALID")


def get_keyring() -> KeyringSnapshot:
    """Return this process's one-shot keyring outcome.

    The first call (serialized by a lock) loads the file exactly once.  Success
    and failure are both sticky: a failed process never re-reads the disk, so a
    replaced file cannot silently flip it to success.  Repair the file and
    restart the process.
    """
    global _keyring_outcome
    outcome = _keyring_outcome
    if outcome is None:
        with _keyring_lock:
            if _keyring_outcome is None:
                _keyring_outcome = _load_outcome()
            outcome = _keyring_outcome
    if outcome.snapshot is None:
        raise SecretEncryptionUnavailable(outcome.reason_code)
    return outcome.snapshot


def _reset_keyring_for_tests() -> None:
    global _keyring_outcome
    with _keyring_lock:
        _keyring_outcome = None


# Kept under the old lru_cache name so existing test fixtures keep working.
get_keyring.cache_clear = _reset_keyring_for_tests  # type: ignore[attr-defined]


def initialize_keyring() -> str:
    """Prime and validate the immutable process snapshot without blocking startup.

    A missing/invalid keyring is an expected compatibility state in B1: legacy
    plaintext reads remain available, while envelope reads and every secret
    write fail closed. Only the sanitized state code is returned.
    """
    try:
        get_keyring()
        return "CONFIGURED"
    except SecretEncryptionUnavailable as exc:
        return exc.reason_code


def _normalize_field(field: SecretField | str) -> SecretField:
    try:
        return field if isinstance(field, SecretField) else SecretField(field)
    except ValueError as exc:
        raise SecretDecryptionError("WXPAY_SECRET_FIELD_INVALID") from exc


def _valid_api_key(value: str) -> bool:
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError:
        return False
    return len(encoded) == 32 and all(0x21 <= byte <= 0x7E for byte in encoded)


def _valid_private_key(value: str) -> bool:
    try:
        encoded = value.replace("\\n", "\n").encode("utf-8")
        if len(encoded) > MAX_PRIVATE_KEY_PLAINTEXT_BYTES:
            return False
        key = serialization.load_pem_private_key(encoded, password=None)
        return isinstance(key, rsa.RSAPrivateKey) and 2048 <= key.key_size <= 8192
    except (TypeError, ValueError, UnicodeError):
        return False


def validate_plaintext(value: str, field: SecretField | str) -> bool:
    secret_field = _normalize_field(field)
    if not isinstance(value, str):
        return False
    if secret_field is SecretField.API_V3_KEY:
        return _valid_api_key(value)
    return _valid_private_key(value)


def _parse_envelope(value: str) -> tuple[str, str]:
    parts = value.split(":")
    if len(parts) != 4 or parts[0] != "enc" or parts[1] != ENVELOPE_VERSION:
        raise SecretDecryptionError("WXPAY_SECRET_FORMAT_UNSUPPORTED")
    key_id = parts[2]
    token = parts[3]
    if not KEY_ID_PATTERN.fullmatch(key_id) or not FERNET_TOKEN_PATTERN.fullmatch(token):
        raise SecretDecryptionError("WXPAY_SECRET_FORMAT_INVALID")
    return key_id, token


def classify_secret(value: str | None, field: SecretField | str) -> SecretFormat:
    _normalize_field(field)
    if value is None or value == "":
        return SecretFormat.EMPTY
    if not isinstance(value, str):
        return SecretFormat.INVALID_OR_UNKNOWN
    if value.startswith("enc:"):
        try:
            _parse_envelope(value)
            return SecretFormat.VERSIONED_ENVELOPE
        except SecretDecryptionError:
            return SecretFormat.INVALID_OR_UNKNOWN
    if value.startswith("gAAAA"):
        return SecretFormat.LEGACY_RAW_FERNET
    if validate_plaintext(value, field):
        return SecretFormat.LEGACY_PLAINTEXT
    return SecretFormat.INVALID_OR_UNKNOWN


def _authenticated_decrypt(fernet: Fernet, token: str, field: SecretField) -> str:
    try:
        plaintext = fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeError, TypeError, ValueError) as exc:
        raise SecretDecryptionError("WXPAY_SECRET_DECRYPT_FAILED") from exc
    if not validate_plaintext(plaintext, field):
        raise SecretDecryptionError("WXPAY_SECRET_PLAINTEXT_INVALID")
    return plaintext


def decrypt_secret(
    value: str | None,
    field: SecretField | str,
    *,
    allow_legacy_plaintext: bool | None = None,
) -> str | None:
    secret_field = _normalize_field(field)
    secret_format = classify_secret(value, secret_field)
    if secret_format is SecretFormat.EMPTY:
        return None
    if secret_format is SecretFormat.VERSIONED_ENVELOPE:
        key_id, token = _parse_envelope(str(value))
        try:
            key = get_keyring().keys.get(key_id)
        except SecretEncryptionUnavailable as exc:
            raise SecretDecryptionError(exc.reason_code) from exc
        if key is None:
            raise SecretDecryptionError("WXPAY_SECRET_KEY_UNKNOWN")
        return _authenticated_decrypt(key.fernet, token, secret_field)
    if secret_format is SecretFormat.LEGACY_RAW_FERNET:
        try:
            legacy_keys = get_keyring().legacy_raw_keys
        except SecretEncryptionUnavailable as exc:
            raise SecretDecryptionError(exc.reason_code) from exc
        for key in legacy_keys:
            try:
                return _authenticated_decrypt(key.fernet, str(value), secret_field)
            except SecretDecryptionError:
                continue
        raise SecretDecryptionError("WXPAY_SECRET_DECRYPT_FAILED")
    if secret_format is SecretFormat.LEGACY_PLAINTEXT:
        allowed = (
            bool(getattr(settings, "WXPAY_LEGACY_PLAINTEXT_READ_ENABLED", True))
            if allow_legacy_plaintext is None
            else allow_legacy_plaintext
        )
        if allowed:
            return str(value)
        raise SecretDecryptionError("WXPAY_LEGACY_PLAINTEXT_DISABLED")
    raise SecretDecryptionError("WXPAY_SECRET_FORMAT_INVALID")


def envelope_length_for_plaintext(plaintext_bytes: int, *, key_id_length: int = 32) -> int:
    if plaintext_bytes < 0 or not 1 <= key_id_length <= 32:
        raise ValueError("invalid envelope length input")
    padded = 16 * ((plaintext_bytes + 1 + 15) // 16)
    token_length = 4 * ((57 + padded + 2) // 3)
    return len("enc:v1:") + key_id_length + 1 + token_length


def encrypt_secret(value: str, field: SecretField | str) -> str:
    secret_field = _normalize_field(field)
    if not bool(getattr(settings, "WXPAY_ENVELOPE_WRITE_ENABLED", False)):
        raise SecretEncryptionUnavailable("WXPAY_ENVELOPE_WRITE_DISABLED")
    if not isinstance(value, str) or value.startswith("enc:") or value.startswith("gAAAA"):
        raise SecretEncryptionUnavailable("WXPAY_SECRET_INPUT_INVALID")
    if not validate_plaintext(value, secret_field):
        raise SecretEncryptionUnavailable("WXPAY_SECRET_INPUT_INVALID")
    try:
        keyring = get_keyring()
        token = keyring.active_key.fernet.encrypt(value.encode("utf-8")).decode("ascii")
    except SecretEncryptionUnavailable:
        raise
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SecretEncryptionUnavailable("WXPAY_SECRET_ENCRYPTION_FAILED") from exc
    envelope = f"enc:{ENVELOPE_VERSION}:{keyring.active_key_id}:{token}"
    limit = MAX_API_KEY_ENVELOPE_CHARS if secret_field is SecretField.API_V3_KEY else MAX_PRIVATE_KEY_ENVELOPE_CHARS
    if len(envelope) > limit:
        raise SecretEncryptionUnavailable("WXPAY_SECRET_TOO_LONG")
    return envelope
