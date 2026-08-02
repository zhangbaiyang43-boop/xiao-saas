import time
import unittest
from datetime import datetime
from unittest.mock import patch

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

    def test_today_key_uses_beijing_day_not_utc_day_late_evening(self):
        # 北京时间 23:00 (UTC 15:00) 还是"今天"，不该已经跨到 UTC 的下一天。
        with patch("app.services.anti_fraud_service.datetime") as mock_dt:
            mock_dt.utcnow.return_value = datetime(2026, 3, 5, 15, 0, 0)  # UTC 15:00 = 北京 3/5 23:00
            self.assertEqual(AntiFraudService.today_key(), "20260305")

    def test_today_key_does_not_reset_early_at_utc_midnight(self):
        # UTC 跨天到 3/6 00:30，但北京时间还是 3/6 08:30——"今天"的额度不该因为这个
        # 提前重置（旧实现会在这里错误地翻到 3/6，本身没问题；真正的边界在下一条）。
        with patch("app.services.anti_fraud_service.datetime") as mock_dt:
            mock_dt.utcnow.return_value = datetime(2026, 3, 6, 0, 30, 0)
            self.assertEqual(AntiFraudService.today_key(), "20260306")

    def test_today_key_does_not_reset_early_before_beijing_midnight(self):
        # UTC 3/5 23:30 = 北京时间 3/6 07:30，仍然是北京的"今天"(3/6)，不能因为
        # UTC 还没跨天就仍然算成 3/5——这正是修复前的实际 bug：旧实现在这个时刻会
        # 返回 "20260305"，导致额度提前 8 小时"续锁"到第二天早上。
        with patch("app.services.anti_fraud_service.datetime") as mock_dt:
            mock_dt.utcnow.return_value = datetime(2026, 3, 5, 23, 30, 0)
            self.assertEqual(AntiFraudService.today_key(), "20260306")


if __name__ == "__main__":
    unittest.main()
