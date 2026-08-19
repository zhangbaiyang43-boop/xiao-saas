"""Phase F1G-CM-RF2 -- SuperAdmin CORS allow_headers contract.

CM-RF found that real cross-origin local testing (admin dev server on one
origin, backend on another, no Vite proxy -- exactly how it must work for
SuperAdmin.vue's canonical-origin fix to be verifiable at all) was blocked
at the browser's CORS preflight stage: every authenticated SuperAdmin call
carries X-Super-Token, which was missing from CORSMiddleware's allow_headers
in app/main.py. This proves the minimal fix -- X-Super-Token is now allowed
-- without it having become a wildcard: an arbitrary unrelated header must
still be rejected, and the rest of the existing allow_headers/allow_origins
contract must be untouched.
"""

from __future__ import annotations

import unittest

from starlette.testclient import TestClient

from app.main import app

ALLOWED_DEV_ORIGIN = "http://localhost:8989"


class SuperAdminCorsTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _preflight(self, path: str, method: str, request_headers: str):
        return self.client.options(
            path,
            headers={
                "Origin": ALLOWED_DEV_ORIGIN,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": request_headers,
            },
        )

    def test_x_super_token_preflight_allowed_for_pending_list(self):
        res = self._preflight("/api/super/billing/manual-payments", "GET", "x-super-token")
        self.assertEqual(res.status_code, 200)
        allow_headers = res.headers.get("access-control-allow-headers", "")
        self.assertIn("X-Super-Token", allow_headers)
        self.assertEqual(res.headers.get("access-control-allow-origin"), ALLOWED_DEV_ORIGIN)

    def test_x_super_token_preflight_allowed_for_confirm(self):
        res = self._preflight(
            "/api/super/billing/manual-payments/123/confirm", "POST", "x-super-token,content-type"
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("X-Super-Token", res.headers.get("access-control-allow-headers", ""))

    def test_x_super_token_preflight_allowed_for_reject(self):
        res = self._preflight(
            "/api/super/billing/manual-payments/123/reject", "POST", "x-super-token,content-type"
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("X-Super-Token", res.headers.get("access-control-allow-headers", ""))

    def test_not_a_wildcard_unrelated_header_still_rejected(self):
        res = self._preflight(
            "/api/super/billing/manual-payments", "GET", "x-super-token,x-totally-unrelated-header"
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Disallowed CORS headers", res.text)

    def test_existing_allow_headers_contract_untouched(self):
        res = self._preflight("/api/super/billing/manual-payments", "GET", "authorization,content-type")
        self.assertEqual(res.status_code, 200)
        allow_headers = {h.strip() for h in res.headers.get("access-control-allow-headers", "").split(",")}
        for expected in ("Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With", "X-Super-Token"):
            self.assertIn(expected, allow_headers)

    def test_no_wildcard_origin_introduced(self):
        res = self._preflight("/api/super/billing/manual-payments", "GET", "x-super-token")
        self.assertNotEqual(res.headers.get("access-control-allow-origin"), "*")

    def test_cors_allows_header_but_does_not_bypass_authentication(self):
        # CORS_AUTHORIZATION_SEPARATION: allowing the header on preflight is
        # not the same as being authenticated -- the actual GET must still
        # be rejected without a valid X-Super-Token.
        res = self.client.get(
            "/api/super/billing/manual-payments",
            headers={"Origin": ALLOWED_DEV_ORIGIN, "X-Super-Token": "garbage.invalid.token"},
        )
        self.assertEqual(res.status_code, 401)

        res_no_token = self.client.get(
            "/api/super/billing/manual-payments", headers={"Origin": ALLOWED_DEV_ORIGIN}
        )
        self.assertEqual(res_no_token.status_code, 422)


if __name__ == "__main__":
    unittest.main()
