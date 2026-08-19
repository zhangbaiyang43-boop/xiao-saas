"""F1G-CF-C1 -- platform WXPAY config schema + fail-closed readiness audit.

Scope: app/services/billing_payment_provider.py's platform_payment_config_audit()
and PROVIDER_IMPLEMENTATION_READY. Proves the readiness truth table stays
FALSE under every combination of config short of a real code implementation
landing (PROVIDER_IMPLEMENTATION_READY is a code constant, never
env-configurable), and that WX_SP_APPID never falls back to WECHAT_APP_ID.

Every test mutates `settings` attributes directly and restores them in
tearDown -- this module reads a single shared Settings singleton
(app.config.settings), the same pattern already used by
test_p0_11_same_table_multi_participant_acceptance.py etc. for
ALLOW_MOCK_MONEY_ENDPOINTS.
"""

from __future__ import annotations

import unittest

from app.config import settings
from app.services.billing_payment_provider import (
    PROVIDER_IMPLEMENTATION_READY,
    PlatformWxPayBillingProvider,
    platform_notify_url,
    platform_payment_config_audit,
)

# Deliberately shaped to be obviously non-real (never a plausible production
# secret) -- see F1G-CF-C1 Phase 15.
TEST_ONLY_DUMMY = "TEST_ONLY_DUMMY_VALUE_NOT_A_REAL_CREDENTIAL"

_FIELDS = (
    "WX_SP_MCHID", "WX_SP_APPID", "WX_SP_API_KEY_V3", "WX_SP_CERT_SERIAL",
    "WX_SP_PRIVATE_KEY", "WX_SP_PUBLIC_KEY_ID", "WX_SP_PUBLIC_KEY",
)


class PlatformPaymentConfigReadinessTest(unittest.TestCase):
    def setUp(self):
        self._saved = {name: getattr(settings, name) for name in _FIELDS}
        self._saved["SAAS_PAYMENT_MODE"] = settings.SAAS_PAYMENT_MODE
        self._saved["SAAS_REAL_PAYMENT_ENABLED"] = settings.SAAS_REAL_PAYMENT_ENABLED
        self._saved["WECHAT_APP_ID"] = settings.WECHAT_APP_ID
        self._saved["PUBLIC_BASE_URL"] = settings.PUBLIC_BASE_URL
        self._clear_all()

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(settings, name, value)

    def _clear_all(self):
        for name in _FIELDS:
            setattr(settings, name, "")
        settings.SAAS_PAYMENT_MODE = "JSAPI"
        settings.SAAS_REAL_PAYMENT_ENABLED = False

    def _fill_all_credentials(self):
        for name in _FIELDS:
            setattr(settings, name, TEST_ONLY_DUMMY)

    # ---- Phase 0: single source of truth for enabled ----------------------

    def test_provider_enabled_mirrors_audit_real_payment_enabled(self):
        self.assertEqual(PlatformWxPayBillingProvider().enabled, platform_payment_config_audit()["real_payment_enabled"])

    def test_provider_implementation_ready_is_a_code_constant_false(self):
        self.assertIs(PROVIDER_IMPLEMENTATION_READY, False)

    # ---- Phase 16 Case A: release switch false, all config absent ---------

    def test_case_a_release_switch_false_all_absent(self):
        audit = platform_payment_config_audit()
        self.assertFalse(audit["real_payment_enabled"])
        self.assertFalse(audit["config_complete"])

    # ---- Case B: release switch false, all config present -----------------

    def test_case_b_release_switch_false_all_present(self):
        self._fill_all_credentials()
        audit = platform_payment_config_audit()
        self.assertTrue(audit["config_complete"], "config presence itself must not depend on the release switch")
        self.assertFalse(audit["real_payment_enabled"], "release switch off must still block real payment")

    # ---- Case C: release switch true, config incomplete -------------------

    def test_case_c_release_switch_true_config_incomplete(self):
        settings.SAAS_REAL_PAYMENT_ENABLED = True
        settings.WX_SP_MCHID = TEST_ONLY_DUMMY  # only one field set
        audit = platform_payment_config_audit()
        self.assertFalse(audit["config_complete"])
        self.assertFalse(audit["real_payment_enabled"])

    # ---- Case D: release switch true, config complete, provider not ready -

    def test_case_d_release_switch_true_config_complete_provider_not_ready(self):
        settings.SAAS_REAL_PAYMENT_ENABLED = True
        self._fill_all_credentials()
        audit = platform_payment_config_audit()
        self.assertTrue(audit["config_complete"])
        self.assertFalse(audit["provider_implementation_ready"])
        self.assertFalse(audit["real_payment_enabled"], "provider_implementation_ready is a code constant env cannot fake")

    # ---- Cases E-I: each individually-missing required field ---------------

    def _complete_except(self, missing_field: str):
        settings.SAAS_REAL_PAYMENT_ENABLED = True
        self._fill_all_credentials()
        setattr(settings, missing_field, "")

    def test_case_e_missing_mchid(self):
        self._complete_except("WX_SP_MCHID")
        audit = platform_payment_config_audit()
        self.assertFalse(audit["mchid_present"])
        self.assertFalse(audit["config_complete"])
        self.assertFalse(audit["real_payment_enabled"])

    def test_case_f_missing_appid(self):
        self._complete_except("WX_SP_APPID")
        audit = platform_payment_config_audit()
        self.assertFalse(audit["appid_present"])
        self.assertFalse(audit["config_complete"])
        self.assertFalse(audit["real_payment_enabled"])

    def test_case_g_missing_api_v3_key(self):
        self._complete_except("WX_SP_API_KEY_V3")
        audit = platform_payment_config_audit()
        self.assertFalse(audit["api_v3_key_present"])
        self.assertFalse(audit["config_complete"])
        self.assertFalse(audit["real_payment_enabled"])

    def test_case_h_missing_private_key(self):
        self._complete_except("WX_SP_PRIVATE_KEY")
        audit = platform_payment_config_audit()
        self.assertFalse(audit["private_key_present"])
        self.assertFalse(audit["config_complete"])
        self.assertFalse(audit["real_payment_enabled"])

    def test_case_i_missing_cert_serial(self):
        self._complete_except("WX_SP_CERT_SERIAL")
        audit = platform_payment_config_audit()
        self.assertFalse(audit["cert_serial_present"])
        self.assertFalse(audit["config_complete"])
        self.assertFalse(audit["real_payment_enabled"])

    # ---- Case J: missing verification material -----------------------------

    def test_case_j_missing_verification_material(self):
        settings.SAAS_REAL_PAYMENT_ENABLED = True
        self._fill_all_credentials()
        settings.WX_SP_PUBLIC_KEY_ID = ""
        settings.WX_SP_PUBLIC_KEY = ""
        audit = platform_payment_config_audit()
        self.assertFalse(audit["verification_material_present"])
        self.assertFalse(audit["config_complete"])
        self.assertFalse(audit["real_payment_enabled"])

    def test_api_v3_key_alone_is_not_verification_material(self):
        # Explicit regression for F1G-CF-C1 Phase 11's warning: APIv3 key
        # presence must never be conflated with verification-key readiness.
        settings.SAAS_REAL_PAYMENT_ENABLED = True
        self._fill_all_credentials()
        settings.WX_SP_PUBLIC_KEY_ID = ""
        settings.WX_SP_PUBLIC_KEY = ""
        audit = platform_payment_config_audit()
        self.assertTrue(audit["api_v3_key_present"])
        self.assertFalse(audit["verification_material_present"])
        self.assertFalse(audit["real_payment_enabled"])

    # ---- Case K: H5 mode must fail closed -----------------------------------

    def test_case_k_h5_mode_fails_closed(self):
        settings.SAAS_REAL_PAYMENT_ENABLED = True
        self._fill_all_credentials()
        settings.SAAS_PAYMENT_MODE = "H5"
        audit = platform_payment_config_audit()
        self.assertFalse(audit["payment_mode_valid"])
        self.assertFalse(audit["config_complete"])
        self.assertFalse(audit["real_payment_enabled"])

    def test_unknown_mode_also_fails_closed(self):
        settings.SAAS_REAL_PAYMENT_ENABLED = True
        self._fill_all_credentials()
        settings.SAAS_PAYMENT_MODE = "NATIVE"
        audit = platform_payment_config_audit()
        self.assertFalse(audit["payment_mode_valid"])
        self.assertFalse(audit["real_payment_enabled"])

    def test_jsapi_and_miniprogram_modes_are_valid(self):
        settings.SAAS_PAYMENT_MODE = "JSAPI"
        self.assertTrue(platform_payment_config_audit()["payment_mode_valid"])
        settings.SAAS_PAYMENT_MODE = "MINIPROGRAM"
        self.assertTrue(platform_payment_config_audit()["payment_mode_valid"])
        settings.SAAS_PAYMENT_MODE = "miniprogram"  # case-insensitive
        self.assertTrue(platform_payment_config_audit()["payment_mode_valid"])

    # ---- Case L: no fallback to WECHAT_APP_ID -------------------------------

    def test_case_l_restaurant_appid_present_saas_appid_missing_no_fallback(self):
        settings.WECHAT_APP_ID = "wx_restaurant_appid_should_never_be_read"
        settings.WX_SP_APPID = ""
        audit = platform_payment_config_audit()
        self.assertFalse(audit["appid_present"], "WX_SP_APPID missing must never fall back to WECHAT_APP_ID")
        self.assertFalse(audit["real_payment_enabled"])

    def test_saas_appid_setting_independent_of_restaurant_appid_value(self):
        settings.WECHAT_APP_ID = "wx_restaurant_appid"
        settings.WX_SP_APPID = TEST_ONLY_DUMMY
        audit = platform_payment_config_audit()
        self.assertTrue(audit["appid_present"])
        # The audit's appid_present must reflect WX_SP_APPID's own value,
        # never equal to / derived from WECHAT_APP_ID.
        self.assertNotEqual(settings.WX_SP_APPID, settings.WECHAT_APP_ID)

    # ---- Callback URL authority ---------------------------------------------

    def test_callback_url_valid_requires_https_public_base_url(self):
        settings.PUBLIC_BASE_URL = "http://not-https.example.com"
        self.assertFalse(platform_payment_config_audit()["callback_url_valid"])
        settings.PUBLIC_BASE_URL = "https://saas.zhangbaiyang.com"
        self.assertTrue(platform_payment_config_audit()["callback_url_valid"])

    def test_platform_notify_url_reuses_public_base_url_not_a_second_field(self):
        settings.PUBLIC_BASE_URL = "https://saas.zhangbaiyang.com"
        self.assertEqual(platform_notify_url(), "https://saas.zhangbaiyang.com/api/v1/billing/wxpay-notify")

    # ---- Secret safety: audit never carries actual secret values -----------

    def test_audit_never_carries_secret_values_only_booleans(self):
        self._fill_all_credentials()
        settings.SAAS_REAL_PAYMENT_ENABLED = True
        audit = platform_payment_config_audit()
        serialized = str(audit)
        self.assertNotIn(TEST_ONLY_DUMMY, serialized)
        for key, value in audit.items():
            if key in ("payment_mode", "blocked_reason"):
                continue
            self.assertIsInstance(value, bool, f"{key} must be a boolean, not a raw config value")


if __name__ == "__main__":
    unittest.main()
