import asyncio
import inspect
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from app.core.platform_rules import cap_discount_amount
from app.schemas.coupon import CreateCouponTemplateRequest
from app.services.coupon_service import CouponService
from app.services.tenant_service import apply_coupon_rule_locks
from app.services.verify_service import VERIFY_FAILURE_MESSAGES, VerifyService


class FakeSession:
    """跟 test_tenant_account_contracts.py 里那个一样的最小假 DB session——
    这些测试全部通过 mock 掉真正touch数据库的方法来验证发券逻辑本身，
    不需要真的连数据库。"""

    def __init__(self):
        self.added = []
        self.commits = 0
        self.refreshed = []
        self.executed = []

    def add(self, entity):
        self.added.append(entity)

    async def commit(self):
        self.commits += 1

    async def refresh(self, entity):
        self.refreshed.append(entity)

    async def execute(self, statement):
        # _dedup_issue_lock 现在会先发一条 UPDATE 当行锁——这些测试都是通过 mock
        # 掉更上层的方法（get_available_auto_coupon 等）来验证发放逻辑本身，不需要
        # 真的执行这条语句，记录下来以备将来断言即可。
        self.executed.append(statement)
        return None


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
            verify_code = "VC1234"
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

    # ── 去重回归：客户手上还有未用的同类型自动券，不应该再发新的 ──────────
    # 背景：consumption_coupon（每笔订单支付成功都会触发）和 recall_coupon
    # （每天定时扫沉睡客户）曾经完全没有去重，导致同一客户名下堆积出金额、
    # 门槛都不一样的多张"复购券"/"召回券"，商家后台和小程序端看到的因此对不上号。

    def _consumption_rule_config(self):
        return {
            "consumption_coupon": {
                "enabled": True,
                "trigger_amount": 0,
                "weighted_enabled": True,
                "weighted_coupons": [
                    {"name": "下次专享券", "amount": 5, "threshold": 30, "valid_days": 7, "weight": 100},
                ],
            }
        }

    def test_consumption_coupon_skipped_when_customer_already_holds_one_unused(self):
        service = CouponService(FakeSession())
        service.set_tenant_id("tenant-001")

        with patch.object(service, "get_coupon_rules", AsyncMock(return_value=self._consumption_rule_config())), \
             patch.object(service, "get_available_auto_coupon", AsyncMock(return_value=object())), \
             patch.object(service, "send_coupons_with_result", AsyncMock()) as send_mock, \
             patch("app.services.coupon_service.settings.REDIS_ENABLED", False):
            result = asyncio.run(
                service.issue_auto_coupon(customer_id=1, rule_type="consumption_coupon", consumption_amount=50)
            )

        send_mock.assert_not_called()
        self.assertEqual(result["success_count"], 0)
        self.assertTrue(result.get("skipped_duplicate"))

    def test_consumption_coupon_issues_when_customer_has_no_unused_one(self):
        service = CouponService(FakeSession())
        service.set_tenant_id("tenant-001")

        fake_template = SimpleNamespace(id=999)
        send_result = {"success_count": 1, "sent": [{"id": "coupon-1"}]}

        with patch.object(service, "get_coupon_rules", AsyncMock(return_value=self._consumption_rule_config())), \
             patch.object(service, "get_available_auto_coupon", AsyncMock(return_value=None)), \
             patch.object(service, "_get_or_create_auto_coupon_template", AsyncMock(return_value=fake_template)), \
             patch.object(service, "send_coupons_with_result", AsyncMock(return_value=send_result)) as send_mock, \
             patch("app.services.coupon_service.settings.REDIS_ENABLED", False):
            result = asyncio.run(
                service.issue_auto_coupon(customer_id=1, rule_type="consumption_coupon", consumption_amount=50)
            )

        send_mock.assert_called_once()
        self.assertEqual(result["success_count"], 1)
        self.assertEqual(result["weighted_coupon"]["amount"], 5)

    def test_recall_coupon_batch_excludes_customers_who_already_hold_one(self):
        service = CouponService(FakeSession())
        service.set_tenant_id("tenant-001")

        already_has_one = SimpleNamespace(id=1, name="老客甲", phone="13800000001")
        sleeping_no_coupon = SimpleNamespace(id=2, name="老客乙", phone="13800000002")

        rule_config = {
            "recall_coupon": {
                "enabled": True,
                "inactive_days": 7,
                "weighted_enabled": True,
                "weighted_coupons": [{"name": "幸运券", "amount": 8, "threshold": 40, "valid_days": 7, "weight": 100}],
            }
        }
        fake_template = SimpleNamespace(id=888)
        send_result = {"success_count": 1, "sent": [{"id": "coupon-2"}]}

        async def fake_get_available_auto_coupon(customer_id, rule_type):
            return object() if customer_id == already_has_one.id else None

        with patch.object(service, "get_coupon_rules", AsyncMock(return_value=rule_config)), \
             patch.object(service, "get_inactive_customers",
                           AsyncMock(return_value=[already_has_one, sleeping_no_coupon])), \
             patch.object(service, "get_available_auto_coupon", side_effect=fake_get_available_auto_coupon), \
             patch.object(service, "_get_or_create_auto_coupon_template", AsyncMock(return_value=fake_template)), \
             patch.object(service, "send_coupons_with_result", AsyncMock(return_value=send_result)) as send_mock, \
             patch("app.services.coupon_service.settings.REDIS_ENABLED", False):
            result = asyncio.run(service.batch_issue_recall_coupon())

        send_mock.assert_called_once()
        called_customer_ids = send_mock.call_args[0][1]
        self.assertEqual(called_customer_ids, [sleeping_no_coupon.id])
        self.assertEqual(result["customers"], [
            {"id": str(sleeping_no_coupon.id), "name": sleeping_no_coupon.name, "phone": sleeping_no_coupon.phone}
        ])

    # ── 并发去重：两个几乎同时的请求不应该都发出去 ──────────────────────
    # 单纯的"先查后发"挡不住这个场景——两个请求都可能在检查那一刻看到"没有"。

    def test_dedup_lock_skips_issuance_when_lock_cannot_be_acquired(self):
        service = CouponService(FakeSession())
        service.set_tenant_id("tenant-001")

        class _FakeAcquireFalseLock:
            async def __aenter__(self):
                return False

            async def __aexit__(self, *exc):
                return False

        with patch.object(service, "get_available_auto_coupon", AsyncMock(return_value=None)), \
             patch("app.services.coupon_service.settings.REDIS_ENABLED", True), \
             patch("app.services.coupon_service.redis_lock", return_value=_FakeAcquireFalseLock()):
            async def run():
                async with service._dedup_issue_lock(1, "consumption_coupon") as should_issue:
                    return should_issue

            should_issue = asyncio.run(run())

        # 锁没抢到——即便数据库里查不到重复券，也不应该放行发放，
        # 否则两个并发请求都会各自查到"没有"然后都发一张。
        self.assertFalse(should_issue)

    def test_dedup_lock_falls_back_to_plain_check_when_redis_unavailable(self):
        service = CouponService(FakeSession())
        service.set_tenant_id("tenant-001")

        with patch.object(service, "get_available_auto_coupon", AsyncMock(return_value=None)), \
             patch("app.services.coupon_service.settings.REDIS_ENABLED", True), \
             patch("app.services.coupon_service.redis_lock", side_effect=RuntimeError("redis down")):
            async def run():
                async with service._dedup_issue_lock(1, "consumption_coupon") as should_issue:
                    return should_issue

            should_issue = asyncio.run(run())

        # Redis 真的不可用时不能因此完全拒绝发券——退化成不加锁的检查，
        # 跟 send_coupons_with_result 的幂等保护是同一个取舍。
        self.assertTrue(should_issue)

    # ── 两套发券系统只保留一套：营销模板引擎的自动触发已经停用 ──────────
    # 背景：MarketingTemplate/MerchantTemplateRule 这套规则引擎（first_scan/
    # after_verify）曾经和 CouponService 自己的 rule_type 发券同时挂在扫码
    # 入会、核销这两个事件上，两边各算各的随机金额，导致商家后台和小程序
    # 看到的优惠券对不上号。管理这套模板引擎的界面已经被删除、没人能再开关
    # 它，所以直接停用触发点，只保留 CouponService 这一套有界面管控的系统。

    def test_first_scan_marketing_template_trigger_is_disabled(self):
        from app.services.entrance_code_service import EntranceCodeService

        source = inspect.getsource(EntranceCodeService.record_member_conversion)
        self.assertIn("# await self._trigger_first_scan_marketing_template(", source)

    def test_after_verify_marketing_template_trigger_is_disabled(self):
        source = inspect.getsource(VerifyService)
        self.assertIn(
            '# await self._trigger_marketing_template(coupon.tenant_id, coupon.customer_id, "after_verify")',
            source,
        )

    def test_recall_scheduler_uses_coupon_service_not_marketing_template_engine(self):
        import app.main as main_module

        source = inspect.getsource(main_module._marketing_recall_loop)
        self.assertIn("CouponService", source)
        self.assertNotIn("MarketingTemplateService", source)

    # ── 商家不亏钱的最后一道红线：结算减免不能超过实付金额的约定比例 ─────

    def test_cap_discount_amount_never_exceeds_ratio_of_order_total(self):
        capped = cap_discount_amount(discount=50, order_total=100, ratio=0.20)
        self.assertEqual(capped, 20)

    def test_cap_discount_amount_passes_through_when_under_cap(self):
        capped = cap_discount_amount(discount=5, order_total=100, ratio=0.20)
        self.assertEqual(capped, 5)

    def test_cap_discount_amount_returns_zero_for_non_positive_order_total(self):
        self.assertEqual(cap_discount_amount(discount=10, order_total=0), 0.0)
        self.assertEqual(cap_discount_amount(discount=10, order_total=-5), 0.0)


if __name__ == "__main__":
    unittest.main()
