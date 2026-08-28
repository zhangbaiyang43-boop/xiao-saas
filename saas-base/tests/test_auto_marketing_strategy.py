"""自动化营销策略 P0 —— 见 docs/prelaunch/AUTO_MARKETING_STRATEGY_SPEC.md

覆盖：
- P0-2 冷启动客单价：菜单菜品价格中位数 × 1.2 优先，业态 INDUSTRY_PRESETS.fallback_aov 只兜底兜底
- P0-3 低客单价（≤20）发无门槛立减，不发满减
- P0-4 新客券有效期 21 天
- P0-5 已撤销：不再用拍的毛利率去卡单张券
- P0-6 月优惠预算总闸：近 30 天优惠总额 > GMV × X% 时暂停自动发券
"""

import asyncio
import unittest
from unittest.mock import AsyncMock

from app.core.platform_rules import (
    build_dynamic_rules,
    resolve_industry,
    INDUSTRY_PRESETS,
    MICRO_BAND_MAX,
    discount_budget_ratio,
)
from app.services.coupon_service import CouponService


class AutoMarketingStrategyP0Test(unittest.TestCase):
    def _new_customer(self, rules):
        return rules["new_customer_coupon"]["weighted_coupons"][0]

    def _entry(self, rules):
        return rules["entry_coupon"]["weighted_coupons"]

    def test_resolve_industry_falls_back_to_default(self):
        self.assertEqual(resolve_industry("noodle"), "noodle")
        self.assertEqual(resolve_industry("不存在"), "default")
        self.assertEqual(resolve_industry(None), "default")

    def test_cold_start_uses_industry_fallback_aov_not_hardcoded_30(self):
        # 0 单的面馆：门槛/面额应当围绕 14 元算，而不是写死的 30
        noodle = build_dynamic_rules(0, "standard", "noodle")
        hotpot = build_dynamic_rules(0, "standard", "hotpot")
        # 面馆是 micro band → 无门槛；火锅门槛应当在 ~90 附近，明显 > 30
        self.assertEqual(self._new_customer(noodle)["threshold"], 0)
        self.assertGreater(self._new_customer(hotpot)["threshold"], 45)

    def test_micro_band_issues_zero_threshold_instant_discount(self):
        for key in ("noodle", "fastfood", "breakfast", "drink"):
            self.assertLessEqual(INDUSTRY_PRESETS[key]["fallback_aov"], MICRO_BAND_MAX)
            rules = build_dynamic_rules(0, "standard", key)
            # 新客券无门槛立减
            self.assertEqual(self._new_customer(rules)["threshold"], 0)
            tiers = self._entry(rules)
            # 进店券是盲盒三档：至少两档无门槛（常规 + 手气爆棚），最多一档"加菜小券"带低门槛
            zero_thr = [t for t in tiers if t["threshold"] == 0]
            self.assertGreaterEqual(len(zero_thr), 2)
            for tier in tiers:
                self.assertGreaterEqual(tier["amount"], 1)
            # 带门槛的那档门槛必须 > 客单价（逼一次加购），不能低于客单价白送
            aov = INDUSTRY_PRESETS[key]["fallback_aov"]
            for tier in tiers:
                if tier["threshold"] > 0:
                    self.assertGreater(tier["threshold"], aov)

    def test_non_micro_band_still_uses_threshold_coupons(self):
        rules = build_dynamic_rules(0, "standard", "hotpot")  # aov 90
        self.assertGreater(self._new_customer(rules)["threshold"], 0)
        for tier in self._entry(rules):
            self.assertGreater(tier["threshold"], 0)

    def test_new_customer_coupon_valid_days_is_21(self):
        for industry in INDUSTRY_PRESETS:
            rules = build_dynamic_rules(0, "standard", industry)
            self.assertEqual(self._new_customer(rules)["valid_days"], 21)

    def test_industry_presets_no_longer_carry_margin(self):
        # P0-5 撤销：毛利率红线连同 margin 字段一起移除
        for meta in INDUSTRY_PRESETS.values():
            self.assertNotIn("margin", meta)

    # ── ③ 进店券门槛不再高于客单价 ────────────────────────────────────
    def test_entry_coupon_threshold_never_far_above_aov(self):
        # 旧 bug：火锅 aov 90，最高档进店券门槛 满144（1.6×aov）→ "多花54省12"负体感
        rules = build_dynamic_rules(90, "standard", "hotpot")
        for tier in self._entry(rules):
            # 任何一档门槛都不允许超过客单价的 1.2 倍
            self.assertLessEqual(tier["threshold"], 90 * 1.2 + 1)

    # ── ① 进店券带门槛那档：面额 ≈ 门槛与客单价的差（"白得一道菜"）──────
    def test_entry_addon_tier_discount_roughly_covers_the_gap(self):
        for aov, industry in [(40, "default"), (90, "hotpot"), (110, "dinner")]:
            rules = build_dynamic_rules(aov, "standard", industry)
            addon = next(t for t in self._entry(rules) if t["threshold"] > aov)
            gap = addon["threshold"] - aov
            # 折扣至少覆盖差额的 70%，让"加的那道菜"接近白送
            self.assertGreaterEqual(addon["amount"], gap * 0.7)

    # ── ② 盲盒：手气爆棚档明显大于常规档，且概率低 ──────────────────────
    def test_entry_blind_box_has_a_real_jackpot_tier(self):
        for aov, industry in [(40, "default"), (90, "hotpot"), (110, "dinner")]:
            tiers = self._entry(build_dynamic_rules(aov, "standard", industry))
            common = max(tiers, key=lambda t: t["weight"])
            jackpot = max(tiers, key=lambda t: t["amount"])
            # 大额档权重是最低的（稀有）
            self.assertEqual(jackpot["weight"], min(t["weight"] for t in tiers))
            # 大额档面额至少是常规档的 1.6 倍
            self.assertGreaterEqual(jackpot["amount"], common["amount"] * 1.6)

    def test_recall_coupon_is_the_strongest_relative_to_threshold(self):
        # 召回券：低门槛 + 贴近结算红线的力度
        rules = build_dynamic_rules(90, "standard", "hotpot")
        rc = rules["recall_coupon"]["weighted_coupons"][0]
        self.assertLess(rc["threshold"], 90)  # 门槛低于客单价，好用掉
        self.assertGreaterEqual(rc["amount"] / max(rc["threshold"], 1), 0.15)

    def test_intensity_dial_changes_what_consumer_sees(self):
        # 三档强度必须让进店券的加权期望值肉眼可分
        def entry_ev(intensity):
            tiers = self._entry(build_dynamic_rules(90, intensity, "hotpot"))
            tw = sum(t["weight"] for t in tiers)
            return sum(t["amount"] * t["weight"] for t in tiers) / tw
        self.assertLess(entry_ev("conservative"), entry_ev("standard"))
        self.assertLess(entry_ev("standard"), entry_ev("aggressive"))

    # ── P0-2 菜单估价优先 ────────────────────────────────────────────
    def test_get_merchant_aov_prefers_menu_estimate_when_orders_scarce(self):
        svc = CouponService(db=None)
        svc._recent_order_stats = AsyncMock(return_value=(0.0, 0))
        svc._menu_price_estimate = AsyncMock(return_value=17.5)
        aov = asyncio.run(svc.get_merchant_aov())
        self.assertEqual(aov, 17.5)

    def test_get_merchant_aov_uses_real_average_when_enough_orders(self):
        svc = CouponService(db=None)
        svc._recent_order_stats = AsyncMock(return_value=(42.0, 30))
        svc._menu_price_estimate = AsyncMock(return_value=17.5)
        aov = asyncio.run(svc.get_merchant_aov())
        self.assertEqual(aov, 42.0)

    # ── P0-6 月优惠预算总闸 ─────────────────────────────────────────
    def test_within_discount_budget_true_during_cold_start(self):
        svc = CouponService(db=None)
        # 单量不足 → 不设限
        svc._recent_discount_and_gmv = AsyncMock(return_value=(999.0, 100.0, 3))
        self.assertTrue(asyncio.run(svc.within_discount_budget()))

    def test_within_discount_budget_false_when_over_ratio(self):
        svc = CouponService(db=None)
        # 30 单、GMV 1000、优惠 80 → 8% > 标准档 4%
        svc._recent_discount_and_gmv = AsyncMock(return_value=(80.0, 1000.0, 30))
        svc.get_marketing_intensity = AsyncMock(return_value="standard")
        self.assertFalse(asyncio.run(svc.within_discount_budget()))
        self.assertEqual(discount_budget_ratio("standard"), 0.05)

    def test_within_discount_budget_true_when_under_ratio(self):
        svc = CouponService(db=None)
        svc._recent_discount_and_gmv = AsyncMock(return_value=(30.0, 1000.0, 30))
        svc.get_marketing_intensity = AsyncMock(return_value="standard")
        self.assertTrue(asyncio.run(svc.within_discount_budget()))

    def test_issue_auto_coupon_skips_when_budget_exhausted(self):
        svc = CouponService(db=None)
        svc.get_coupon_rules = AsyncMock(return_value={"new_customer_coupon": {"enabled": True}})
        svc.within_discount_budget = AsyncMock(return_value=False)
        result = asyncio.run(svc.issue_auto_coupon(customer_id=1, rule_type="new_customer_coupon"))
        self.assertEqual(result["success_count"], 0)
        self.assertIn("预算", result["reason"])

    def test_issue_entry_coupon_returns_none_when_budget_exhausted(self):
        svc = CouponService(db=None)
        svc.get_coupon_rules = AsyncMock(return_value={"entry_coupon": {"enabled": True}})
        svc.within_discount_budget = AsyncMock(return_value=False)
        result = asyncio.run(svc.issue_entry_coupon(customer_id=1))
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
