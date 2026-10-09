from __future__ import annotations

import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import settings
from app.core.wxpay_secret_crypto import (
    MAX_PRIVATE_KEY_PLAINTEXT_BYTES,
    SecretDecryptionError,
    SecretEncryptionUnavailable,
    SecretField,
    SecretFormat,
    classify_secret,
    decrypt_secret,
    encrypt_secret,
    envelope_length_for_plaintext,
    get_keyring,
    initialize_keyring,
    load_keyring,
)
from app.services.wxpay_service import WxPayService


API_KEY = "a" * 32


def private_key_pem(key_size: int = 2048) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


PRIVATE_KEY = private_key_pem()


class SyntheticKeyring:
    def __init__(
        self,
        *,
        active_key: bytes | None = None,
        active_id: str = "wxpay-2026-01",
        legacy_key: bytes | None = None,
        legacy_id: str = "wxpay-2025-01",
    ):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "wxpay-keyring.json"
        self.active_key = active_key or Fernet.generate_key()
        keys = [
            {
                "keyId": active_id,
                "algorithm": "fernet",
                "usage": "encrypt-decrypt",
                "key": self.active_key.decode(),
            }
        ]
        if legacy_key:
            keys.append(
                {
                    "keyId": legacy_id,
                    "algorithm": "fernet",
                    "usage": "decrypt-only",
                    "key": legacy_key.decode(),
                }
            )
        self.write({"formatVersion": 1, "activeKeyId": active_id, "keys": keys})

    def write(self, payload: dict) -> None:
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        os.chmod(self.path, 0o600)

    def close(self) -> None:
        self.directory.cleanup()


class EnvelopeContractTest(unittest.TestCase):
    def setUp(self):
        self.original_path = settings.WXPAY_SECRET_KEYRING_PATH
        self.original_write = settings.WXPAY_ENVELOPE_WRITE_ENABLED
        self.original_legacy = settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED
        self.keyring = SyntheticKeyring()
        settings.WXPAY_SECRET_KEYRING_PATH = str(self.keyring.path)
        settings.WXPAY_ENVELOPE_WRITE_ENABLED = True
        settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED = True
        get_keyring.cache_clear()

    def tearDown(self):
        settings.WXPAY_SECRET_KEYRING_PATH = self.original_path
        settings.WXPAY_ENVELOPE_WRITE_ENABLED = self.original_write
        settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED = self.original_legacy
        get_keyring.cache_clear()
        self.keyring.close()

    def test_api_key_and_pem_envelopes_round_trip(self):
        for field, value in (
            (SecretField.API_V3_KEY, API_KEY),
            (SecretField.PRIVATE_KEY, PRIVATE_KEY),
        ):
            with self.subTest(field=field):
                encrypted = encrypt_secret(value, field)
                self.assertTrue(encrypted.startswith("enc:v1:wxpay-2026-01:gAAAA"))
                self.assertEqual(decrypt_secret(encrypted, field), value)

    def test_same_secret_has_isolated_randomized_ciphertexts(self):
        tenant_a = encrypt_secret(API_KEY, SecretField.API_V3_KEY)
        tenant_b = encrypt_secret(API_KEY, SecretField.API_V3_KEY)
        self.assertNotEqual(tenant_a, tenant_b)
        self.assertEqual(decrypt_secret(tenant_a, SecretField.API_V3_KEY), API_KEY)
        self.assertEqual(decrypt_secret(tenant_b, SecretField.API_V3_KEY), API_KEY)

    def test_payment_runtime_decrypts_before_sdk_and_rejects_corruption(self):
        tenant = SimpleNamespace(
            tenant_id="tenant-a",
            wx_pay_enabled=True,
            wx_mchid="1234567890",
            wx_api_key_v3=encrypt_secret(API_KEY, SecretField.API_V3_KEY),
            wx_cert_serial="A" * 40,
            wx_private_key=encrypt_secret(PRIVATE_KEY, SecretField.PRIVATE_KEY),
            wx_public_key_id=None,
            wx_public_key=None,
        )
        client = object()
        with patch("app.services.wxpay_service._build_client", return_value=client) as build:
            service = WxPayService(tenant)
        self.assertTrue(service.enabled)
        self.assertEqual(build.call_args.kwargs["api_key_v3"], API_KEY)
        self.assertEqual(build.call_args.kwargs["private_key_pem"], PRIVATE_KEY)

        tenant.wx_api_key_v3 = tenant.wx_api_key_v3[:-1] + (
            "A" if tenant.wx_api_key_v3[-1] != "A" else "B"
        )
        with patch("app.services.wxpay_service._build_client") as build:
            service = WxPayService(tenant)
        self.assertFalse(service.enabled)
        build.assert_not_called()

    def test_envelope_parser_rejects_unknown_version_invalid_id_and_extra_fields(self):
        invalid_values = (
            "enc:v2:wxpay-2026-01:gAAAAA",
            "enc:v1:UPPER:gAAAAA",
            "enc:v1:-leading:gAAAAA",
            f"enc:v1:{'a' * 33}:gAAAAA",
            "enc:v1:wxpay-2026-01:gAAAAA:extra",
            "enc:unknown",
        )
        for value in invalid_values:
            with self.subTest(value=value[:40]):
                self.assertEqual(classify_secret(value, SecretField.API_V3_KEY), SecretFormat.INVALID_OR_UNKNOWN)
                with self.assertRaises(SecretDecryptionError):
                    decrypt_secret(value, SecretField.API_V3_KEY)

    def test_unknown_key_and_corrupted_token_fail_closed_without_secret_in_error(self):
        valid = encrypt_secret(API_KEY, SecretField.API_V3_KEY)
        values = (
            valid.replace("wxpay-2026-01", "wxpay-2099-01", 1),
            valid[:-1] + ("A" if valid[-1] != "A" else "B"),
        )
        for value in values:
            with self.subTest(kind=value.split(":", 3)[2]):
                with self.assertRaises(SecretDecryptionError) as caught:
                    decrypt_secret(value, SecretField.API_V3_KEY)
                self.assertNotIn(API_KEY, str(caught.exception))
                self.assertNotIn(value, str(caught.exception))

    def test_plaintext_compatibility_is_field_validated_and_strict_mode_rejects_it(self):
        self.assertEqual(classify_secret(API_KEY, SecretField.API_V3_KEY), SecretFormat.LEGACY_PLAINTEXT)
        self.assertEqual(decrypt_secret(API_KEY, SecretField.API_V3_KEY), API_KEY)
        self.assertEqual(decrypt_secret(PRIVATE_KEY, SecretField.PRIVATE_KEY), PRIVATE_KEY)
        with self.assertRaises(SecretDecryptionError):
            decrypt_secret(API_KEY, SecretField.API_V3_KEY, allow_legacy_plaintext=False)
        for invalid in ("short", "汉" * 32, "-----BEGIN PRIVATE KEY-----\ninvalid\n"):
            with self.subTest(invalid=invalid[:12]):
                self.assertEqual(classify_secret(invalid, SecretField.API_V3_KEY), SecretFormat.INVALID_OR_UNKNOWN)

    def test_raw_fernet_uses_only_explicit_legacy_decryption_keys(self):
        legacy_key = Fernet.generate_key()
        self.keyring.close()
        self.keyring = SyntheticKeyring(legacy_key=legacy_key)
        settings.WXPAY_SECRET_KEYRING_PATH = str(self.keyring.path)
        get_keyring.cache_clear()
        token = Fernet(legacy_key).encrypt(API_KEY.encode()).decode()
        self.assertEqual(classify_secret(token, SecretField.API_V3_KEY), SecretFormat.LEGACY_RAW_FERNET)
        self.assertEqual(decrypt_secret(token, SecretField.API_V3_KEY), API_KEY)

        bad_token = Fernet(Fernet.generate_key()).encrypt(API_KEY.encode()).decode()
        with self.assertRaises(SecretDecryptionError):
            decrypt_secret(bad_token, SecretField.API_V3_KEY)

    def test_missing_or_invalid_keyring_rejects_write_but_valid_plaintext_read_survives(self):
        settings.WXPAY_SECRET_KEYRING_PATH = str(self.keyring.path.parent / "missing.json")
        get_keyring.cache_clear()
        with self.assertRaises(SecretEncryptionUnavailable):
            encrypt_secret(API_KEY, SecretField.API_V3_KEY)
        self.assertEqual(decrypt_secret(API_KEY, SecretField.API_V3_KEY), API_KEY)

        self.keyring.write({"formatVersion": 1, "activeKeyId": "missing", "keys": []})
        settings.WXPAY_SECRET_KEYRING_PATH = str(self.keyring.path)
        get_keyring.cache_clear()
        with self.assertRaises(SecretEncryptionUnavailable):
            encrypt_secret(API_KEY, SecretField.API_V3_KEY)

    def test_write_activation_false_rejects_without_legacy_fallback(self):
        settings.WXPAY_ENVELOPE_WRITE_ENABLED = False
        with self.assertRaises(SecretEncryptionUnavailable):
            encrypt_secret(API_KEY, SecretField.API_V3_KEY)

    def test_double_encryption_is_rejected(self):
        envelope = encrypt_secret(API_KEY, SecretField.API_V3_KEY)
        with self.assertRaises(SecretEncryptionUnavailable):
            encrypt_secret(envelope, SecretField.API_V3_KEY)

    def test_rotation_reads_old_envelope_but_new_writes_use_only_active_key(self):
        old = SyntheticKeyring(active_id="wxpay-2025-01")
        try:
            settings.WXPAY_SECRET_KEYRING_PATH = str(old.path)
            get_keyring.cache_clear()
            old_envelope = encrypt_secret(API_KEY, SecretField.API_V3_KEY)
            old_key = old.active_key

            self.keyring.close()
            self.keyring = SyntheticKeyring(legacy_key=old_key)
            settings.WXPAY_SECRET_KEYRING_PATH = str(self.keyring.path)
            get_keyring.cache_clear()
            self.assertEqual(decrypt_secret(old_envelope, SecretField.API_V3_KEY), API_KEY)
            self.assertIn(":wxpay-2026-01:", encrypt_secret(API_KEY, SecretField.API_V3_KEY))
        finally:
            old.close()

    def test_concurrent_reads_share_an_immutable_snapshot(self):
        envelope = encrypt_secret(API_KEY, SecretField.API_V3_KEY)
        snapshot = get_keyring()
        with self.assertRaises(TypeError):
            snapshot.keys["mutate"] = snapshot.active_key
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: decrypt_secret(envelope, SecretField.API_V3_KEY), range(64)))
        self.assertEqual(results, [API_KEY] * 64)

    def test_startup_initializes_the_process_snapshot_and_missing_file_is_nonfatal(self):
        from app.main import startup

        self.assertIn("initialize_keyring()", __import__("inspect").getsource(startup))
        self.assertEqual(initialize_keyring(), "CONFIGURED")
        self.assertIs(get_keyring(), get_keyring())

        settings.WXPAY_SECRET_KEYRING_PATH = str(self.keyring.path.parent / "missing.json")
        get_keyring.cache_clear()
        self.assertEqual(initialize_keyring(), "WXPAY_KEYRING_MISSING")

    def test_keyring_rejects_unknown_fields_duplicate_ids_bad_usage_and_insecure_mode(self):
        base_key = Fernet.generate_key().decode()
        invalid_payloads = (
            {"formatVersion": 1, "activeKeyId": "a", "keys": [], "extra": True},
            {
                "formatVersion": 1,
                "activeKeyId": "a",
                "keys": [
                    {"keyId": "a", "algorithm": "fernet", "usage": "encrypt-decrypt", "key": base_key},
                    {"keyId": "a", "algorithm": "fernet", "usage": "decrypt-only", "key": base_key},
                ],
            },
            {
                "formatVersion": 1,
                "activeKeyId": "a",
                "keys": [{"keyId": "a", "algorithm": "fernet", "usage": "encrypt", "key": base_key}],
            },
        )
        for payload in invalid_payloads:
            with self.subTest(payload=list(payload)):
                self.keyring.write(payload)
                with self.assertRaises(SecretEncryptionUnavailable):
                    load_keyring(self.keyring.path)

        self.keyring.write(
            {
                "formatVersion": 1,
                "activeKeyId": "a",
                "keys": [{"keyId": "a", "algorithm": "fernet", "usage": "encrypt-decrypt", "key": base_key}],
            }
        )
        os.chmod(self.keyring.path, 0o644)
        with self.assertRaises(SecretEncryptionUnavailable):
            load_keyring(self.keyring.path)

    def test_field_capacity_contract_covers_api_key_and_supported_pem_limit(self):
        self.assertLessEqual(envelope_length_for_plaintext(32), 256)
        self.assertGreater(envelope_length_for_plaintext(3072), 4096)
        self.assertLessEqual(envelope_length_for_plaintext(MAX_PRIVATE_KEY_PLAINTEXT_BYTES), 65535)
        self.assertGreater(envelope_length_for_plaintext(MAX_PRIVATE_KEY_PLAINTEXT_BYTES + 1), 65535)

        large_pem = private_key_pem(4096)
        large_envelope = encrypt_secret(large_pem, SecretField.PRIVATE_KEY)
        self.assertGreater(len(large_envelope), 4096)
        self.assertLessEqual(len(large_envelope), 65535)
        self.assertEqual(decrypt_secret(large_envelope, SecretField.PRIVATE_KEY), large_pem)


if __name__ == "__main__":
    unittest.main()
