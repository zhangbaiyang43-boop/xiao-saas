"""P0-16 Phase B1 -- T01: PII redaction.

Phase A confirmed raw phone numbers and WeChat openid/unionid values were being
logged in plaintext at saas-base/app/api/v1/miniapp.py (lines 115, 147, 354)
and saas-base/app/services/customer_identity_service.py (7 distinct logger
calls spanning lines 235-330). This is a real, confirmed PII leak into
30-day-rotated log files.

Uses synthetic, obviously-fake values -- never real user data.
"""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

SYNTHETIC_PHONE = "13812345678"
SYNTHETIC_OPENID = "oTEST_FULL_OPENID_SECRET_VALUE"
SYNTHETIC_UNIONID = "uTEST_FULL_UNIONID_SECRET_VALUE"


class MaskHelperBehaviorTest(unittest.TestCase):
    """Executed proof the mask helpers themselves never emit the full value."""

    def test_mask_phone_never_contains_the_full_number(self):
        from app.core.logger import mask_phone

        masked = mask_phone(SYNTHETIC_PHONE)
        self.assertNotIn(SYNTHETIC_PHONE, masked)
        # still useful for diagnostics: last 4 digits recoverable
        self.assertIn(SYNTHETIC_PHONE[-4:], masked)

    def test_mask_phone_handles_none_and_short_values_without_crashing(self):
        from app.core.logger import mask_phone

        self.assertEqual(mask_phone(None), "***")
        self.assertNotIn("None", mask_phone(None))
        self.assertEqual(mask_phone(""), "***")
        self.assertEqual(mask_phone("12"), "***")

    def test_mask_wechat_identity_never_contains_the_full_value(self):
        from app.core.logger import mask_wechat_identity

        masked_openid = mask_wechat_identity(SYNTHETIC_OPENID)
        masked_unionid = mask_wechat_identity(SYNTHETIC_UNIONID)
        self.assertNotIn(SYNTHETIC_OPENID, masked_openid)
        self.assertNotIn(SYNTHETIC_UNIONID, masked_unionid)
        # short, bounded diagnostic form only
        self.assertLess(len(masked_openid), len(SYNTHETIC_OPENID))

    def test_mask_wechat_identity_handles_none_without_crashing(self):
        from app.core.logger import mask_wechat_identity

        self.assertEqual(mask_wechat_identity(None), "")
        self.assertEqual(mask_wechat_identity(""), "")


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


class MiniappLoggingSourceTest(unittest.TestCase):
    """Source-text proof that the exact call sites Phase A identified no
    longer interpolate a raw phone/openid/unionid field. Full-endpoint
    execution (entry_join) would require WeChat-service + DB mocking heavy
    enough to obscure the actual assertion; the source-text check directly
    verifies the specific lines, matching this codebase's own established
    pattern (see test_order_amount_security_contracts.py) for cases where
    exact-line verification is clearer than an integration test."""

    def setUp(self):
        self.source = _read("app/api/v1/miniapp.py")

    def test_entry_join_request_log_no_longer_interpolates_raw_phone(self):
        line = next(l for l in self.source.splitlines() if "entry_join 请求" in l)
        self.assertNotIn("{data.phone}", line)
        self.assertIn("mask_phone(data.phone)", line)

    def test_code2session_log_no_longer_interpolates_raw_openid_or_unionid(self):
        line = next(l for l in self.source.splitlines() if "code2session 结果" in l)
        self.assertNotIn("{openid}", line)
        self.assertNotIn("{unionid}", line)
        self.assertIn("mask_wechat_identity(openid)", line)
        self.assertIn("mask_wechat_identity(unionid)", line)

    def test_entry_join_exception_log_no_longer_interpolates_raw_phone(self):
        line = next(l for l in self.source.splitlines() if "entry_join 顶层异常" in l)
        self.assertNotIn("{data.phone}", line)
        self.assertIn("mask_phone(data.phone)", line)


class CustomerIdentityServiceLoggingSourceTest(unittest.TestCase):
    def setUp(self):
        self.source = _read("app/services/customer_identity_service.py")

    def test_no_bare_phone_field_remains_in_any_logger_statement(self):
        # A bare `phone: {phone}`/`{existing_customer.phone}`/`{customer.phone}`
        # inside a logger.*(...) call would mean the raw value still reaches
        # the log. Walk each logger.*( ... ) block (may span multiple lines)
        # and assert no unmasked phone-field interpolation remains.
        blocks = re.findall(r"logger\.\w+\(\s*f?\"[\s\S]*?\)\s*\n", self.source)
        offending = [b for b in blocks if re.search(r"\{[\w\.]*phone[\w\.]*\}", b, re.IGNORECASE)
                     and "mask_phone(" not in b]
        self.assertEqual(offending, [], f"unmasked phone interpolation found:\n{offending}")

    def test_no_bare_openid_field_remains_in_any_logger_statement(self):
        blocks = re.findall(r"logger\.\w+\(\s*f?\"[\s\S]*?\)\s*\n", self.source)
        offending = [b for b in blocks if re.search(r"\{openid\}", b) and "mask_wechat_identity(" not in b]
        self.assertEqual(offending, [], f"unmasked openid interpolation found:\n{offending}")

    def test_mask_helpers_are_imported(self):
        self.assertIn("mask_phone", self.source)
        self.assertIn("mask_wechat_identity", self.source)


if __name__ == "__main__":
    unittest.main()
