import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from pydantic import ValidationError

from app.schemas.coupon import CreateCouponTemplateRequest
from app.services.coupon_service import CouponService
from app.services.tenant_service import apply_coupon_rule_locks
from app.services.verify_service import VERIFY_FAILURE_MESSAGES, VerifyService


class CouponLoopContractsTest(unittest.TestCase):
    def test_send_plan_never_exceeds_remaining_stock(self):
        selected = CouponService.plan_recipients_by_stock(
            customer_ids=[1, 2, 3],
            total_stock=2,
            used_stock=1,
        )

        self.assertEqual(selected, [1])

    def test_send_plan_keeps_order_and_allows_exact_remaining_stock(self):
        selected = CouponService.plan_recipients_by_stock(
            customer_ids=[3, 2, 1],
            total_stock=5,
            used_stock=2,
        )

        self.assertEqual(selected, [3, 2, 1])

    def test_send_result_reports_success_and_failures(self):
        result = CouponService.build_send_result(
            requested_customer_ids=[1, 2, 3],
            sent_coupons=[{"customer_id": 1}, {"customer_id": 2}],
            failed=[{"customer_id": 3, "reason": "库存不足"}],
            remaining_stock=0,
            reason=None,
        )

        self.assertEqual(result["requested_count"], 3)
        self.assertEqual(result["success_count"], 2)
        self.assertEqual(result["failed_count"], 1)
        self.assertEqual(result["remaining_stock"], 0)
        self.assertEqual(result["failed"][0]["reason"], "库存不足")

    def test_coupon_template_rejects_invalid_effective_range(self):
        start = datetime.utcnow()
        end = start - timedelta(days=1)

        with self.assertRaises(ValidationError):
            CreateCouponTemplateRequest(
                name="测试券",
                type="FIXED",
                value=10,
                min_amount=0,
                total_stock=10,
                start_time=start.isoformat(),
                end_time=end.isoformat(),
            )

    def test_verify_failure_messages_are_specific(self):
        self.assertEqual(VERIFY_FAILURE_MESSAGES["NOT_FOUND"], "核销码不存在")
        self.assertEqual(VERIFY_FAILURE_MESSAGES["USED"], "优惠券已核销")
        self.assertEqual(VERIFY_FAILURE_MESSAGES["EXPIRED"], "优惠券已过期")
        self.assertEqual(VERIFY_FAILURE_MESSAGES["INVALID"], "核销码无效")

    def test_verify_record_item_supports_revoke_and_abnormal_fields(self):
        class CouponStub:
            id = 1
            customer_id = 2
            template_id = 3
            code = "ABC123"
            created_at = datetime(2026, 4, 29, 9, 0, 0)
            updated_at = datetime(2026, 4, 29, 10, 5, 0)
            status = "UNUSED"
            use_time = datetime(2026, 4, 29, 10, 0, 0)
            expire_time = datetime(2026, 5, 1, 10, 0, 0)
            revoke_time = datetime(2026, 4, 29, 10, 5, 0)
            revoke_reason = "店员误操作"
            abnormal_reason = "客户反馈重复扫码"

        item = VerifyService.build_record_item(CouponStub())

        self.assertEqual(item["verify_status"], "REVOKED")
        self.assertEqual(item["revoke_reason"], "店员误操作")
        self.assertEqual(item["abnormal_reason"], "客户反馈重复扫码")

    def test_verify_service_has_consumption_coupon_trigger_hook(self):
        self.assertTrue(hasattr(VerifyService, "_trigger_consumption_coupon"))

    def test_weighted_coupon_selection_uses_random_choices_weights(self):
        rule_config = {
            "amount": 3,
            "threshold": 16,
            "valid_days": 2,
            "weighted_enabled": True,
            "weighted_coupons": [
                {"name": "幸运券", "amount": 2, "threshold": 16, "weight": 50},
                {"name": "今日手气不错", "amount": 3, "threshold": 16, "weight": 35},
                {"name": "尊享券", "amount": 5, "threshold": 16, "weight": 15},
            ],
        }

        with patch("app.services.coupon_service.random.choices") as random_choices:
            random_choices.return_value = [rule_config["weighted_coupons"][2]]
            selected = CouponService.select_weighted_coupon(rule_config)

        random_choices.assert_called_once()
        _, kwargs = random_choices.call_args
        self.assertEqual(kwargs["weights"], [50, 35, 15])
        self.assertEqual(kwargs["k"], 1)
        self.assertEqual(selected["name"], "尊享券")
        self.assertEqual(selected["amount"], 5)

    def test_locked_coupon_rule_only_allows_enabled_toggle(self):
        current_rules = {
            "consumption_coupon": {
                "enabled": True,
                "amount": 3,
                "threshold": 16,
                "valid_days": 2,
                "locked": True,
                "weighted_coupons": [
                    {"name": "幸运券", "amount": 2, "threshold": 16, "weight": 50}
                ],
            }
        }

        patch_rules = {
            "consumption_coupon": {
                "enabled": False,
                "amount": 8,
                "threshold": 30,
                "weighted_coupons": [
                    {"name": "尊享券", "amount": 9, "threshold": 30, "weight": 100}
                ],
            }
        }

        locked = apply_coupon_rule_locks(current_rules, patch_rules)

        self.assertFalse(locked["consumption_coupon"]["enabled"])
        self.assertEqual(locked["consumption_coupon"]["amount"], 3)
        self.assertEqual(locked["consumption_coupon"]["threshold"], 16)
        self.assertEqual(locked["consumption_coupon"]["weighted_coupons"][0]["amount"], 2)

    def test_locked_coupon_rule_can_be_explicitly_unlocked_without_changing_cost(self):
        current_rules = {
            "new_customer_coupon": {
                "enabled": True,
                "amount": 2,
                "threshold": 10,
                "valid_days": 1,
                "locked": True,
                "locked_at": "2026-05-08T00:00:00",
            }
        }

        patch_rules = {
            "new_customer_coupon": {
                "unlock_locked": True,
                "amount": 99,
                "threshold": 99,
            }
        }

        unlocked = apply_coupon_rule_locks(current_rules, patch_rules)

        self.assertFalse(unlocked["new_customer_coupon"]["locked"])
        self.assertEqual(unlocked["new_customer_coupon"]["amount"], 2)
        self.assertEqual(unlocked["new_customer_coupon"]["threshold"], 10)
        self.assertTrue(unlocked["new_customer_coupon"]["unlocked_at"])

    def test_default_auto_coupon_rules_all_use_weighted_random(self):
        from app.services.tenant_service import DEFAULT_COUPON_RULES

        for rule_key in ["new_customer_coupon", "consumption_coupon", "recall_coupon"]:
            self.assertTrue(DEFAULT_COUPON_RULES[rule_key]["weighted_enabled"])
            self.assertEqual(len(DEFAULT_COUPON_RULES[rule_key]["weighted_coupons"]), 3)


if __name__ == "__main__":
    unittest.main()
