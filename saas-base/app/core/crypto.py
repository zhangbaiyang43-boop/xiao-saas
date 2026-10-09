"""Compatibility exports for the WeChat Pay secret crypto contract.

New code must use :mod:`app.core.wxpay_secret_crypto` with an explicit field.
The former permissive/raw-Fernet writer is intentionally disabled so an old
``SECRET_ENCRYPTION_KEY`` can never bypass the B1 envelope gate.
"""
from __future__ import annotations

from app.core.wxpay_secret_crypto import (
    SecretDecryptionError,
    SecretEncryptionUnavailable,
    SecretField,
    decrypt_secret as _decrypt_secret,
    encrypt_secret as _encrypt_secret,
)


def encrypt_secret(value: str | None, field: SecretField | str | None = None) -> str | None:
    if not value:
        return value
    if field is None:
        raise SecretEncryptionUnavailable("WXPAY_SECRET_FIELD_REQUIRED")
    return _encrypt_secret(value, field)


def encrypt_secret_strict(value: str, field: SecretField | str | None = None) -> str:
    if field is None:
        raise SecretEncryptionUnavailable("WXPAY_SECRET_FIELD_REQUIRED")
    return _encrypt_secret(value, field)


def decrypt_secret(
    value: str | None,
    field: SecretField | str | None = None,
    *,
    allow_legacy_plaintext: bool | None = None,
) -> str | None:
    if not value:
        return value
    if field is None:
        raise SecretDecryptionError("WXPAY_SECRET_FIELD_REQUIRED")
    return _decrypt_secret(value, field, allow_legacy_plaintext=allow_legacy_plaintext)
