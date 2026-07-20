# 平台托管营销则 —— 所有商户默认生效，无需商户配置
#
# 核心设计：券的门槛和面额根据每个商家的实际客单价(AOV)动态计算
# 让"刚好再多花一点"成为用户自然的行为，而不是强迫凑单
#
# 使用方式：调用 build_dynamic_rules(aov) 获取该商户的动态则


def _clean(val: float, minimum: float = 1.0) -> float:
    """四舍五入到整数，不低于minimum。"""
    return max(round(val), minimum)


def build_dynamic_rules(aov: float) -> dict:
    """
    根据商户平均客单价(AOV)动态生成券则。
    aov=0 或无历史订单时使用安全兜底值。
    """
    if aov < 10:
        # 新商户/低价商户兜底：极低门槛，确保券能被用掉
        aov = 30.0

    # ── 进店券（Plan B）：当次用餐有效，促进凑单 ──────────────────
    # 三档加权：50%概率低档（容易达到）、35%中档、15%高档（惊喜感）
    e_low_thr   = _clean(aov * 1.1)
    e_mid_thr   = _clean(aov * 1.3)
    e_high_thr  = _clean(aov * 1.6)
    e_low_amt   = _clean(e_low_thr  * 0.06, 1)
    e_mid_amt   = _clean(e_mid_thr  * 0.07, 1)
    e_high_amt  = _clean(e_high_thr * 0.08, 1)

    # ── 复购券（Plan A）：结账后发，绑定下次回来 ──────────────────
    # 门槛 ≈ AOV，下次正常消费就能用，减少"用不到"的挫败感
    r_low_thr   = _clean(aov * 0.9)
    r_mid_thr   = _clean(aov * 1.1)
    r_high_thr  = _clean(aov * 1.4)
    r_low_amt   = _clean(r_low_thr  * 0.06, 1)
    r_mid_amt   = _clean(r_mid_thr  * 0.07, 1)
    r_high_amt  = _clean(r_high_thr * 0.08, 1)

    # ── 新客券：首单后发，门槛比AOV低20%，确保新客能用上 ──────────
    nc_thr = _clean(aov * 0.8)
    nc_amt = _clean(nc_thr * 0.07, 1)

    return {
        "entry_coupon": {
            "enabled": True,
            "weighted_enabled": True,
            "weighted_coupons": [
                {"name": "今日专享券", "amount": e_low_amt,  "threshold": e_low_thr,  "valid_days": 1, "weight": 50},
                {"name": "幸运优惠券", "amount": e_mid_amt,  "threshold": e_mid_thr,  "valid_days": 1, "weight": 35},
                {"name": "超值大礼券", "amount": e_high_amt, "threshold": e_high_thr, "valid_days": 1, "weight": 15},
            ],
        },
        "consumption_coupon": {
            "enabled": True,
            "trigger_amount": 0,
            "weighted_enabled": True,
            "weighted_coupons": [
                {"name": "下次专享券", "amount": r_low_amt,  "threshold": r_low_thr,  "valid_days": 7,  "weight": 50},
                {"name": "感谢惠顾券", "amount": r_mid_amt,  "threshold": r_mid_thr,  "valid_days": 7,  "weight": 35},
                {"name": "超值回馈券", "amount": r_high_amt, "threshold": r_high_thr, "valid_days": 14, "weight": 15},
            ],
        },
        "new_customer_coupon": {
            "enabled": True,
            "weighted_enabled": True,
            "weighted_coupons": [
                {"name": "新客专享券", "amount": nc_amt, "threshold": nc_thr, "valid_days": 3, "weight": 100},
            ],
        },
    }


# 安全边界：单张券面额不超过订单实际金额的此比例
MAX_DISCOUNT_RATIO = 0.20

# 计算AOV时取近N天的订单
AOV_LOOKBACK_DAYS = 30
AOV_MIN_ORDERS = 5      # 至少5笔订单才用动态值，否则用兜底
