# 平台托管营销则 —— 所有商户默认生效，无需商户配置
#
# 核心设计：券的门槛和面额根据每个商家的实际客单价(AOV)动态计算
# 让"刚好再多花一点"成为用户自然的行为，而不是强迫凑单
#
# 商家侧只暴露一个决策——营销强度（保守/标准/激进），不暴露具体参数。
# 使用方式：调用 build_dynamic_rules(aov, intensity) 获取该商户的动态则

# 安全边界：单张券面额不超过订单实际金额的此比例（结算时 cap_discount_amount 强制生效）
MAX_DISCOUNT_RATIO = 0.20

# 三档强度内部预留的安全边际：动态算出来的面额/门槛比例不允许触碰到 MAX_DISCOUNT_RATIO，
# 留出缓冲区，避免"激进"档在极端 AOV 下算出来的值被结算时的红线反过来砍掉，
# 让商家看到的预期和实际到手的优惠不一致。
SAFE_INTENSITY_CEILING = 0.15

# 计算AOV时取近N天的订单
AOV_LOOKBACK_DAYS = 30
AOV_MIN_ORDERS = 5      # 至少5笔订单才用动态值，否则用兜底

DEFAULT_INTENSITY = "standard"

# 三档强度 = 一个乘数作用在门槛系数和面额比例上，商家只需要在这三个里选一个。
# threshold_mult：门槛松紧（越低越容易凑单，让利感越强）
# amount_ratio_mult：面额相对门槛的比例（越高让利越多）
INTENSITY_PRESETS = {
    "conservative": {"threshold_mult": 1.15, "amount_ratio_mult": 0.7},
    "standard":     {"threshold_mult": 1.0,  "amount_ratio_mult": 1.0},
    "aggressive":   {"threshold_mult": 0.9,  "amount_ratio_mult": 1.4},
}

INTENSITY_LABELS = {
    "conservative": "保守",
    "standard": "标准",
    "aggressive": "激进",
}


def _clean(val: float, minimum: float = 1.0) -> float:
    """四舍五入到整数，不低于minimum。"""
    return max(round(val), minimum)


def _safe_amount(threshold: float, ratio: float, minimum: float = 1.0) -> float:
    """面额 = 门槛 × 比例，但永远不超过 SAFE_INTENSITY_CEILING，留出安全边际。"""
    capped_ratio = min(ratio, SAFE_INTENSITY_CEILING)
    return _clean(threshold * capped_ratio, minimum)


def resolve_intensity(intensity: str | None) -> str:
    """把任意输入归一化成合法档位，非法/缺失一律回落到标准档，绝不报错。"""
    if intensity in INTENSITY_PRESETS:
        return intensity
    return DEFAULT_INTENSITY


def build_dynamic_rules(aov: float, intensity: str = DEFAULT_INTENSITY) -> dict:
    """
    根据商户平均客单价(AOV) + 商户选择的营销强度动态生成券则。
    aov=0 或无历史订单时使用安全兜底值。intensity 非法时回落标准档。
    """
    preset = INTENSITY_PRESETS[resolve_intensity(intensity)]
    threshold_mult = preset["threshold_mult"]
    amount_ratio_mult = preset["amount_ratio_mult"]

    if aov < 10:
        # 新商户/低价商户兜底：极低门槛，确保券能被用掉
        aov = 30.0

    # ── 进店券（Plan B）：当次用餐有效，促进凑单 ──────────────────
    # 三档加权：50%概率低档（容易达到）、35%中档、15%高档（惊喜感）
    e_low_thr   = _clean(aov * 1.1 * threshold_mult)
    e_mid_thr   = _clean(aov * 1.3 * threshold_mult)
    e_high_thr  = _clean(aov * 1.6 * threshold_mult)
    e_low_amt   = _safe_amount(e_low_thr,  0.06 * amount_ratio_mult)
    e_mid_amt   = _safe_amount(e_mid_thr,  0.07 * amount_ratio_mult)
    e_high_amt  = _safe_amount(e_high_thr, 0.08 * amount_ratio_mult)

    # ── 复购券（Plan A）：结账后发，绑定下次回来 ──────────────────
    # 门槛 ≈ AOV，下次正常消费就能用，减少"用不到"的挫败感
    r_low_thr   = _clean(aov * 0.9 * threshold_mult)
    r_mid_thr   = _clean(aov * 1.1 * threshold_mult)
    r_high_thr  = _clean(aov * 1.4 * threshold_mult)
    r_low_amt   = _safe_amount(r_low_thr,  0.06 * amount_ratio_mult)
    r_mid_amt   = _safe_amount(r_mid_thr,  0.07 * amount_ratio_mult)
    r_high_amt  = _safe_amount(r_high_thr, 0.08 * amount_ratio_mult)

    # ── 新客券：首单后发，门槛比AOV低20%，确保新客能用上 ──────────
    nc_thr = _clean(aov * 0.8 * threshold_mult)
    nc_amt = _safe_amount(nc_thr, 0.07 * amount_ratio_mult)

    # ── 召回券：沉睡客户唤回，门槛比AOV更低，降低回来的门槛 ────────
    rc_thr = _clean(aov * 0.7 * threshold_mult)
    rc_amt = _safe_amount(rc_thr, 0.07 * amount_ratio_mult)

    # ── 邀请奖励（老带新双边奖励）：邀请人和新顾客两张券共用同一个消费门槛，
    # 门槛比AOV低20%（跟新客券同样的道理，确保新顾客首次到店真能用上，
    # 邀请人下次消费也大概率能达到）。两边面额各自走同一套安全上限，
    # 默认关闭——是否开启邀请裂变是商户的决定，不该被平台替他做主。
    ir_thr = _clean(aov * 0.8 * threshold_mult)
    ir_inviter_amt = _safe_amount(ir_thr, 0.08 * amount_ratio_mult)
    ir_invitee_amt = _safe_amount(ir_thr, 0.08 * amount_ratio_mult)

    # ── 员工推荐佣金：员工/亲友带来的新顾客首次到店消费后，给推荐人一笔现金佣金
    # （不是券）。不走 _safe_amount 那套"面额不超过订单实际金额某比例"的安全上限——
    # 那条红线是为了防止代金券让商户倒贴订单本身的钱，员工佣金是给第三方的
    # 现金支出，跟订单折扣是两回事，不受那条红线约束。三档直接按客单价的不同
    # 比例给一个整数金额，比例本身拉开梯度（8%/15%/25%），保证在客单价较低
    # （比如客单价 15-30 元的简餐店）时三档也不会被同一个保底值糊平成一个数。
    _SR_RATIO = {"conservative": 0.08, "standard": 0.15, "aggressive": 0.25}
    sr_amt = _clean(aov * _SR_RATIO[resolve_intensity(intensity)], 1.0)

    # ── 积分好礼券：顾客攒够 membership_service.POINTS_REWARD_THRESHOLD 积分后
    # 自动兑换（在 add_points() 里触发，不新建一套独立的积分商城）。门槛定在
    # 客单价附近保证下次正常消费就能用，面额比其他自动券更慷慨——这是顾客真金
    # 白银攒出来的里程碑奖励，不是获客/召回场景下"随手发发看"的小额撒券。
    pr_thr = _clean(aov * 1.0 * threshold_mult)
    pr_amt = _safe_amount(pr_thr, 0.12 * amount_ratio_mult)

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
        "recall_coupon": {
            "enabled": True,
            "inactive_days": 7,
            "weighted_enabled": True,
            "weighted_coupons": [
                {"name": "幸运券", "amount": rc_amt, "threshold": rc_thr, "valid_days": 7, "weight": 100},
            ],
        },
        "invite_reward": {
            "enabled": False,
            "inviter_reward_amount": ir_inviter_amt,
            "invitee_reward_amount": ir_invitee_amt,
            "invite_reward_min_spend": ir_thr,
            "invite_reward_valid_days": 30,
        },
        "staff_referral": {
            "enabled": False,
            "staff_commission_amount": sr_amt,
        },
        "points_reward_coupon": {
            "enabled": True,
            "weighted_enabled": True,
            "weighted_coupons": [
                {"name": "积分好礼券", "amount": pr_amt, "threshold": pr_thr, "valid_days": 30, "weight": 100},
            ],
        },
    }


def cap_discount_amount(discount: float, order_total: float, ratio: float = MAX_DISCOUNT_RATIO) -> float:
    """核心红线：任何优惠券结算都必须经过这里。

    不管模板当初怎么配置的，实际减免金额不允许超过*这一单实付金额*的
    ratio。这是保证商家不亏钱的最后一道、且唯一以真实订单金额为准的防线，
    在结算时强制生效，不依赖商家或运营是否正确配置了模板。
    """
    order_total = float(order_total or 0)
    if order_total <= 0:
        return 0.0
    return min(float(discount or 0), round(order_total * ratio, 2))


def assert_template_economics_safe(coupon_type: str, value: float, min_amount: float) -> None:
    """创建/更新券模板时的经济性红线检查，尽量在商家配置错误的第一时间拦住，
    而不是等到顾客核销时才靠 cap_discount_amount 兜底。

    找不到可比较的门槛金额时（无门槛且是全新商户）放行——结算时的
    cap_discount_amount 仍会兜底，保证不亏钱。
    """
    value = float(value or 0)
    if coupon_type == "PERCENT":
        safe_max_percent = MAX_DISCOUNT_RATIO * 100
        if value > safe_max_percent:
            raise ValueError(f"折扣力度过大：{value:.0f}% 已超过安全上限 {safe_max_percent:.0f}%，存在亏本风险")
        return

    reference_amount = float(min_amount or 0)
    if reference_amount <= 0:
        return
    safe_max_value = round(reference_amount * MAX_DISCOUNT_RATIO, 2)
    if value > safe_max_value:
        raise ValueError(
            f"优惠金额¥{value:.2f} 相对于门槛¥{reference_amount:.2f} 过高，存在亏本风险，建议不超过¥{safe_max_value:.2f}"
        )
