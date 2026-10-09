"""Versioned encryption contract for Tenant WeChat Pay secrets.

The keyring is an immutable process snapshot loaded from a local runtime secret
file.  This module never logs or returns key material, ciphertext, plaintext,
or secret fingerprints in an exception.
"""
from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
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


def _validate_file_security(path: Path) -> None:
    try:
        metadata = path.stat()
    except OSError as exc:
        raise SecretEncryptionUnavailable("WXPAY_KEYRING_MISSING") from exc
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        raise _configuration_error()
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise _configuration_error()
    if hasattr(os, "geteuid") and metadata.st_uid not in {0, os.geteuid()}:
        raise _configuration_error()


def load_keyring(path: str | Path) -> KeyringSnapshot:
    keyring_path = Path(path)
    _validate_file_security(keyring_path)
    try:
        if keyring_path.stat().st_size > 65536:
            raise _configuration_error()
        payload = json.loads(keyring_path.read_text(encoding="utf-8"))
    except SecretEncryptionUnavailable:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _configuration_error() from exc

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

    if active_usage_count != 1 or active_key_id not in parsed:
        raise _configuration_error()
    if parsed[active_key_id].usage != "encrypt-decrypt":
        raise _configuration_error()
    return KeyringSnapshot(active_key_id=active_key_id, keys=MappingProxyType(parsed))


@lru_cache(maxsize=1)
def get_keyring() -> KeyringSnapshot:
    path = str(getattr(settings, "WXPAY_SECRET_KEYRING_PATH", "") or "").strip()
    if not path:
        raise SecretEncryptionUnavailable("WXPAY_KEYRING_MISSING")
    return load_keyring(path)


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
