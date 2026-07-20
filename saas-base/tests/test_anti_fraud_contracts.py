import time
import unittest

from app.services.anti_fraud_service import AntiFraudService


class AntiFraudContractsTest(unittest.TestCase):
    def test_dynamic_verify_code_round_trip_and_expires(self):
        code = AntiFraudService.build_dynamic_verify_code(
            tenant_id="tenant-001",
            coupon_id=123,
            customer_id=456,
            coupon_code="ABC123",
            ttl_seconds=60,
            now=1_000,
        )

        payload = AntiFraudService.parse_dynamic_verify_code(code, now=1_030)

        self.assertEqual(payload["tenant_id"], "tenant-001")
        self.assertEqual(payload["coupon_id"], 123)
        self.assertEqual(payload["customer_id"], 456)
        self.assertEqual(payload["coupon_code"], "ABC123")

        with self.assertRaises(ValueError):
            AntiFraudService.parse_dynamic_verify_code(code, now=1_061)

    def test_dynamic_verify_code_rejects_tampering(self):
        code = AntiFraudService.build_dynamic_verify_code(
            tenant_id="tenant-001",
            coupon_id=123,
            customer_id=456,
            coupon_code="ABC123",
            ttl_seconds=60,
            now=int(time.time()),
        )

        tampered = code[:-2] + "xx"

        with self.assertRaises(ValueError):
            AntiFraudService.parse_dynamic_verify_code(tampered)


if __name__ == "__main__":
    unittest.main()
