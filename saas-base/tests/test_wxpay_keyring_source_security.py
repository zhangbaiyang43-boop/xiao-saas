"""P1-A (keyring file trust) and P1-B (one-shot keyring lifecycle) regressions.

POSIX only: the contract is built on O_NOFOLLOW / dir_fd / fstat ownership.
Systemd LoadCredential ownership is covered by the isolated systemd CI job.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

from app.config import settings
from app.core import wxpay_secret_crypto as crypto
from app.core.wxpay_secret_crypto import (
    SecretDecryptionError,
    SecretEncryptionUnavailable,
    SecretField,
    decrypt_secret,
    encrypt_secret,
    get_keyring,
    initialize_keyring,
    load_keyring,
)

API_KEY = "A" * 32
POSIX = hasattr(os, "geteuid") and hasattr(os, "O_NOFOLLOW")
EUID = os.geteuid() if POSIX else 0
TEST_POLICY = crypto.KeyringSourcePolicy(extra_trusted_uids=frozenset({EUID}), verify_ancestors=False)


def keyring_payload(active_id: str = "wxpay-2026-01", key: bytes | None = None) -> dict:
    return {
        "formatVersion": 1,
        "activeKeyId": active_id,
        "keys": [
            {
                "keyId": active_id,
                "algorithm": "fernet",
                "usage": "encrypt-decrypt",
                "key": (key or Fernet.generate_key()).decode(),
            }
        ],
    }


@unittest.skipUnless(POSIX, "POSIX descriptor semantics required")
class KeyringBase(unittest.TestCase):
    def setUp(self):
        self.original_path = settings.WXPAY_SECRET_KEYRING_PATH
        self.original_write = settings.WXPAY_ENVELOPE_WRITE_ENABLED
        self.original_legacy = settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED
        self.original_policy = crypto.KEYRING_SOURCE_POLICY
        settings.WXPAY_ENVELOPE_WRITE_ENABLED = True
        settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED = True
        crypto.KEYRING_SOURCE_POLICY = TEST_POLICY
        self.directory = Path(os.path.realpath(tempfile.mkdtemp(prefix="wxpay-keyring-")))
        self.path = self.directory / "keyring.json"
        get_keyring.cache_clear()

    def tearDown(self):
        settings.WXPAY_SECRET_KEYRING_PATH = self.original_path
        settings.WXPAY_ENVELOPE_WRITE_ENABLED = self.original_write
        settings.WXPAY_LEGACY_PLAINTEXT_READ_ENABLED = self.original_legacy
        crypto.KEYRING_SOURCE_POLICY = self.original_policy
        get_keyring.cache_clear()
        shutil.rmtree(self.directory, ignore_errors=True)

    def write(self, payload, mode: int = 0o600, path: Path | None = None) -> Path:
        target = path or self.path
        target.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
        os.chmod(target, mode)
        return target

    def reason(self, callable_, *args) -> str:
        with self.assertRaises(SecretEncryptionUnavailable) as caught:
            callable_(*args)
        return caught.exception.reason_code


class KeyringFileSecurityTest(KeyringBase):
    def test_trusted_regular_file_loads(self):
        self.write(keyring_payload())
        self.assertEqual(load_keyring(self.path).active_key_id, "wxpay-2026-01")

    def test_symlinked_file_is_rejected(self):
        real = self.write(keyring_payload(), path=self.directory / "real.json")
        self.path.symlink_to(real)
        self.assertEqual(self.reason(load_keyring, self.path), "WXPAY_KEYRING_PERMISSION_DENIED")

    def test_symlinked_directory_component_is_rejected(self):
        real_dir = self.directory / "real"
        real_dir.mkdir()
        self.write(keyring_payload(), path=real_dir / "keyring.json")
        (self.directory / "link").symlink_to(real_dir)
        self.assertEqual(
            self.reason(load_keyring, self.directory / "link" / "keyring.json"),
            "WXPAY_KEYRING_PERMISSION_DENIED",
        )

    def test_group_or_other_accessible_modes_are_rejected(self):
        for mode in (0o640, 0o604, 0o660, 0o644, 0o700):
            with self.subTest(mode=oct(mode)):
                self.write(keyring_payload(), mode=mode)
                self.assertEqual(self.reason(load_keyring, self.path), "WXPAY_KEYRING_PERMISSION_DENIED")

    def test_read_only_owner_mode_is_accepted(self):
        self.write(keyring_payload(), mode=0o400)
        self.assertEqual(load_keyring(self.path).active_key_id, "wxpay-2026-01")

    def test_hard_linked_file_is_rejected(self):
        self.write(keyring_payload())
        os.link(self.path, self.directory / "second-name.json")
        self.assertEqual(self.reason(load_keyring, self.path), "WXPAY_KEYRING_PERMISSION_DENIED")

    def test_non_regular_files_are_rejected_without_blocking(self):
        os.mkfifo(self.path, 0o600)
        self.assertEqual(self.reason(load_keyring, self.path), "WXPAY_KEYRING_PERMISSION_DENIED")
        self.path.unlink()
        self.path.mkdir()
        self.assertEqual(self.reason(load_keyring, self.path), "WXPAY_KEYRING_PERMISSION_DENIED")

    def test_untrusted_owner_is_rejected_by_default_policy(self):
        if EUID == 0:
            self.skipTest("running as root; owner uid 0 is the trusted source")
        self.write(keyring_payload())
        strict = crypto.KeyringSourcePolicy(verify_ancestors=False)
        self.assertEqual(self.reason(load_keyring, self.path, strict), "WXPAY_KEYRING_PERMISSION_DENIED")

    def _credentials_layout(self, unit: str = "u.service", parent: Path | None = None) -> Path:
        unit_dir = (parent or self.directory / "credentials") / unit
        unit_dir.mkdir(parents=True)
        return self.write(keyring_payload(), path=unit_dir / "key")

    def test_service_owned_file_outside_systemd_credentials_is_not_trusted(self):
        if EUID == 0:
            self.skipTest("running as root; owner uid 0 is the trusted source")
        self.write(keyring_payload())
        strict = crypto.KeyringSourcePolicy(verify_ancestors=False)  # real /run/credentials root
        with patch.dict(os.environ, {"CREDENTIALS_DIRECTORY": str(self.directory)}):
            self.assertEqual(self.reason(load_keyring, self.path, strict), "WXPAY_KEYRING_PERMISSION_DENIED")

    def test_service_owned_credential_layout_requires_matching_credentials_directory(self):
        if EUID == 0:
            self.skipTest("running as root; owner uid 0 is the trusted source")
        key = self._credentials_layout()
        policy = crypto.KeyringSourcePolicy(credentials_root=str(self.directory / "credentials"), verify_ancestors=False)
        with patch.dict(os.environ, {"CREDENTIALS_DIRECTORY": str(key.parent)}):
            self.assertEqual(load_keyring(key, policy).active_key_id, "wxpay-2026-01")
        with patch.dict(os.environ, {"CREDENTIALS_DIRECTORY": str(self.directory / "elsewhere")}):
            self.assertEqual(self.reason(load_keyring, key, policy), "WXPAY_KEYRING_PERMISSION_DENIED")
        with patch.dict(os.environ, clear=False):
            os.environ.pop("CREDENTIALS_DIRECTORY", None)
            self.assertEqual(self.reason(load_keyring, key, policy), "WXPAY_KEYRING_PERMISSION_DENIED")

    def test_credentials_root_is_matched_by_path_component_not_string_prefix(self):
        if EUID == 0:
            self.skipTest("running as root; owner uid 0 is the trusted source")
        lookalike = self._credentials_layout(parent=self.directory / "credentials-evil")
        policy = crypto.KeyringSourcePolicy(credentials_root=str(self.directory / "credentials"), verify_ancestors=False)
        with patch.dict(os.environ, {"CREDENTIALS_DIRECTORY": str(lookalike.parent)}):
            self.assertEqual(self.reason(load_keyring, lookalike, policy), "WXPAY_KEYRING_PERMISSION_DENIED")

    def test_credential_file_must_sit_directly_in_the_unit_directory(self):
        if EUID == 0:
            self.skipTest("running as root; owner uid 0 is the trusted source")
        key = self._credentials_layout()
        nested_dir = key.parent / "nested"
        nested_dir.mkdir()
        nested = self.write(keyring_payload(), path=nested_dir / "key")
        policy = crypto.KeyringSourcePolicy(credentials_root=str(self.directory / "credentials"), verify_ancestors=False)
        with patch.dict(os.environ, {"CREDENTIALS_DIRECTORY": str(nested_dir)}):
            self.assertEqual(self.reason(load_keyring, nested, policy), "WXPAY_KEYRING_PERMISSION_DENIED")

    def test_group_or_other_writable_ancestor_is_rejected_by_default_policy(self):
        open_dir = self.directory / "open"
        open_dir.mkdir()
        os.chmod(open_dir, 0o777)
        target = self.write(keyring_payload(), path=open_dir / "keyring.json")
        strict = crypto.KeyringSourcePolicy(extra_trusted_uids=frozenset({EUID}))
        self.assertEqual(self.reason(load_keyring, target, strict), "WXPAY_KEYRING_PERMISSION_DENIED")

    def test_relative_and_traversal_paths_are_rejected(self):
        self.write(keyring_payload())
        self.assertEqual(self.reason(load_keyring, "keyring.json"), "WXPAY_KEYRING_INVALID")
        self.assertEqual(
            self.reason(load_keyring, str(self.directory / ".." / self.directory.name / "keyring.json")),
            "WXPAY_KEYRING_INVALID",
        )

    def test_oversize_file_is_rejected_before_parsing(self):
        self.write("x" * (crypto.MAX_KEYRING_BYTES + 1))
        self.assertEqual(self.reason(load_keyring, self.path), "WXPAY_KEYRING_INVALID")

    def test_missing_file_reports_missing(self):
        self.assertEqual(self.reason(load_keyring, self.directory / "absent.json"), "WXPAY_KEYRING_MISSING")

    def test_checked_descriptor_is_the_one_that_is_read(self):
        """TOCTOU: swapping the path after open must not change what is loaded."""
        self.write(keyring_payload("original-key"))
        replacement = self.write(keyring_payload("attacker-key"), path=self.directory / "attacker.json")
        real_read = os.read
        swapped = []

        def swapping_read(fd, size):
            if not swapped:
                swapped.append(True)
                os.replace(replacement, self.path)
            return real_read(fd, size)

        with patch.object(crypto.os, "read", swapping_read):
            snapshot = load_keyring(self.path)
        self.assertTrue(swapped)
        self.assertEqual(snapshot.active_key_id, "original-key")

    def test_in_place_modification_during_read_is_rejected(self):
        self.write(keyring_payload())
        real_read = os.read
        touched = []

        def mutating_read(fd, size):
            data = real_read(fd, size)
            if not touched:
                touched.append(True)
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(" ")
            return data

        with patch.object(crypto.os, "read", mutating_read):
            self.assertEqual(self.reason(load_keyring, self.path), "WXPAY_KEYRING_INVALID")

    def test_failures_never_expose_path_or_key_material(self):
        key = Fernet.generate_key()
        payload = keyring_payload(key=key)
        payload["extra"] = True
        self.write(payload)
        with self.assertRaises(SecretEncryptionUnavailable) as caught:
            load_keyring(self.path)
        text = f"{caught.exception!s}{caught.exception!r}"
        self.assertNotIn(key.decode(), text)
        self.assertNotIn(str(self.directory), text)


class KeyringLifecycleTest(KeyringBase):
    def configure(self, payload=None, mode: int = 0o600) -> None:
        settings.WXPAY_SECRET_KEYRING_PATH = str(self.path)
        if payload is not None:
            self.write(payload, mode=mode)
        get_keyring.cache_clear()

    def test_every_first_failure_is_sticky_until_restart(self):
        valid = keyring_payload()
        cases = {
            "WXPAY_KEYRING_MISSING": (None, 0o600),
            "WXPAY_KEYRING_INVALID_JSON": ("{not json", 0o600),
            "WXPAY_KEYRING_PERMISSION_DENIED": (valid, 0o644),
            "WXPAY_KEYRING_ACTIVE_KEY_INVALID": ({**keyring_payload(), "activeKeyId": "other"}, 0o600),
            "WXPAY_KEYRING_INVALID": ({"formatVersion": 2}, 0o600),
        }
        for expected, (payload, mode) in cases.items():
            with self.subTest(expected=expected):
                if self.path.exists():
                    self.path.unlink()
                self.configure(payload, mode)
                self.assertEqual(self.reason(get_keyring), expected)
                self.assertEqual(initialize_keyring(), expected)

                # The disk is repaired in place, but this process never re-reads it.
                self.write(keyring_payload())
                with patch.object(crypto, "load_keyring", side_effect=AssertionError("reloaded")):
                    self.assertEqual(self.reason(get_keyring), expected)
                    self.assertEqual(self.reason(encrypt_secret, API_KEY, SecretField.API_V3_KEY), expected)
                self.assertEqual(initialize_keyring(), expected)

                get_keyring.cache_clear()  # simulates a process restart
                self.assertEqual(initialize_keyring(), "CONFIGURED")

    def test_failed_process_keeps_legacy_plaintext_reads_but_fails_closed_for_envelopes_and_writes(self):
        self.configure(None)
        self.assertEqual(self.reason(get_keyring), "WXPAY_KEYRING_MISSING")
        self.assertEqual(decrypt_secret(API_KEY, SecretField.API_V3_KEY), API_KEY)
        self.assertEqual(self.reason(encrypt_secret, API_KEY, SecretField.API_V3_KEY), "WXPAY_KEYRING_MISSING")
        with self.assertRaises(SecretDecryptionError) as caught:
            decrypt_secret("enc:v1:wxpay-2026-01:gAAAAA", SecretField.API_V3_KEY)
        self.assertNotEqual(caught.exception.reason_code, "CONFIGURED")

    def test_successful_snapshot_is_immutable_for_the_process(self):
        self.configure(keyring_payload())
        first = get_keyring()
        self.path.unlink()
        self.write(keyring_payload("wxpay-2099-01"))
        self.assertIs(get_keyring(), first)
        self.assertEqual(get_keyring().active_key_id, "wxpay-2026-01")

    def test_unknown_key_id_fails_closed_without_changing_the_snapshot(self):
        self.configure(keyring_payload())
        foreign = f"enc:v1:wxpay-2025-12:{Fernet(Fernet.generate_key()).encrypt(API_KEY.encode()).decode()}"
        with self.assertRaises(SecretDecryptionError) as caught:
            decrypt_secret(foreign, SecretField.API_V3_KEY)
        self.assertEqual(caught.exception.reason_code, "WXPAY_SECRET_KEY_UNKNOWN")
        self.assertEqual(get_keyring().active_key_id, "wxpay-2026-01")
        self.assertTrue(encrypt_secret(API_KEY, SecretField.API_V3_KEY).startswith("enc:v1:wxpay-2026-01:"))

    def test_concurrent_first_load_reads_the_disk_once_and_is_consistent(self):
        self.configure(keyring_payload())
        real = crypto.load_keyring
        calls = []

        def slow_load(path, policy=None):
            calls.append(path)
            time.sleep(0.05)
            return real(path, policy)

        barrier = threading.Barrier(24)

        def worker(_):
            barrier.wait()
            return get_keyring()

        with patch.object(crypto, "load_keyring", slow_load):
            with ThreadPoolExecutor(max_workers=24) as pool:
                snapshots = list(pool.map(worker, range(24)))
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(snapshot is snapshots[0] for snapshot in snapshots))

    def test_concurrent_first_failure_is_one_consistent_failure(self):
        self.configure(None)
        real = crypto.load_keyring
        calls = []

        def slow_load(path, policy=None):
            calls.append(path)
            time.sleep(0.05)
            return real(path, policy)

        barrier = threading.Barrier(24)

        def worker(_):
            barrier.wait()
            try:
                get_keyring()
            except SecretEncryptionUnavailable as exc:
                return exc.reason_code
            return "UNEXPECTED_SUCCESS"

        with patch.object(crypto, "load_keyring", slow_load):
            with ThreadPoolExecutor(max_workers=24) as pool:
                outcomes = list(pool.map(worker, range(24)))
        self.assertEqual(len(calls), 1)
        self.assertEqual(set(outcomes), {"WXPAY_KEYRING_MISSING"})

    def test_failure_text_is_only_the_sanitized_reason_code(self):
        key = Fernet.generate_key()
        payload = keyring_payload(key=key)
        payload["activeKeyId"] = "missing-id"
        self.configure(payload)
        with self.assertRaises(SecretEncryptionUnavailable) as caught:
            get_keyring()
        self.assertEqual(str(caught.exception), "WXPAY_KEYRING_ACTIVE_KEY_INVALID")
        self.assertNotIn(key.decode(), repr(caught.exception))
        self.assertNotIn(str(self.path), repr(caught.exception))


if __name__ == "__main__":
    unittest.main()
