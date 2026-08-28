"""自动化营销策略 P0 —— 见 docs/prelaunch/AUTO_MARKETING_STRATEGY_SPEC.md

覆盖：
- P0-2 业态兜底客单价（冷启动用 INDUSTRY_PRESETS.fallback_aov，不再写死 30）
- P0-3 低客单价（≤20）发无门槛立减，不发满减
- P0-4 新客券有效期 21 天
- P0-5 毛利率红线：券面额 ≤ 单均毛利 × 安全比例
"""

import unittest

from app.core.platform_rules import (
    build_dynamic_rules,
    resolve_industry,
    INDUSTRY_PRESETS,
    MARGIN_SAFETY_BY_INTENSITY,
    MICRO_BAND_MAX,
)


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
            # 新客券 + 进店券三档全部无门槛
            self.assertEqual(self._new_customer(rules)["threshold"], 0)
            for tier in self._entry(rules):
                self.assertEqual(tier["threshold"], 0)
                self.assertGreaterEqual(tier["amount"], 1)

    def test_non_micro_band_still_uses_threshold_coupons(self):
        rules = build_dynamic_rules(0, "standard", "hotpot")  # aov 90
        self.assertGreater(self._new_customer(rules)["threshold"], 0)
        for tier in self._entry(rules):
            self.assertGreater(tier["threshold"], 0)

    def test_new_customer_coupon_valid_days_is_21(self):
        for industry in INDUSTRY_PRESETS:
            rules = build_dynamic_rules(0, "standard", industry)
            self.assertEqual(self._new_customer(rules)["valid_days"], 21)

    def test_margin_red_line_caps_amount_by_gross_margin(self):
        # 快餐毛利 0.35，激进档安全比例 0.40 → 券面额不得超过 单均毛利 × 0.40
        for intensity, safety in MARGIN_SAFETY_BY_INTENSITY.items():
            for industry, meta in INDUSTRY_PRESETS.items():
                rules = build_dynamic_rules(0, intensity, industry)
                aov = meta["fallback_aov"]
                margin_cap = max(round(aov * meta["margin"] * safety), 1)
                for rule_key in ("entry_coupon", "new_customer_coupon", "consumption_coupon", "recall_coupon"):
                    for tier in rules[rule_key]["weighted_coupons"]:
                        self.assertLessEqual(
                            tier["amount"], margin_cap + 1e-6,
                            f"{industry}/{intensity}/{rule_key} 面额 {tier['amount']} 超过毛利红线 {margin_cap}",
                        )

    def test_low_margin_industry_gets_smaller_coupons_than_high_margin(self):
        # 毛利红线咬住时（保守档），毛利 30% 的快餐面额 <= 毛利 65% 的饮品。
        # 用保守档：此时 margin_cap 明显小于 aov×0.15 的立减基数，红线起决定作用。
        fast = self._new_customer(build_dynamic_rules(0, "conservative", "fastfood"))["amount"]
        drink = self._new_customer(build_dynamic_rules(0, "conservative", "drink"))["amount"]
        self.assertLessEqual(fast, drink)


if __name__ == "__main__":
    unittest.main()
