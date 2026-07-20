import unittest

from app.core.security import create_customer_access_token, verify_token
from app.middleware.auth_middleware import WHITELIST


class MemberClientContractsTest(unittest.TestCase):
    def test_customer_token_contains_tenant_customer_and_role(self):
        token = create_customer_access_token("tenant-001", 99)
        payload = verify_token(token)

        self.assertEqual(payload["tenant_id"], "tenant-001")
        self.assertEqual(payload["customer_id"], 99)
        self.assertEqual(payload["role"], "customer")
        self.assertEqual(payload["sub"], "customer:99")

    def test_member_login_or_create_is_public_entry(self):
        self.assertIn("/api/v1/member/login-or-create", WHITELIST)


if __name__ == "__main__":
    unittest.main()
