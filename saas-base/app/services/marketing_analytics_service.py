"""自动发券的归因闭环 + 核销率闭环调参。

见 docs/prelaunch/AUTO_MARKETING_STRATEGY_SPEC.md 第 8~9 步。

- attribution_summary(): 用券客人 vs 没用券客人的回头率/客单价对比 + 每类型
  核销率 + 粗略 ROI。纯实时计算，不落表。
- compute_and_apply_tuning(): 每周按核销率/复购率对每类型的 threshold_mult /
  amount_mult 做一小步调整，写回 business_info.coupon_tuning（含 _log 审计）。
  ROI < 1 时回滚上一次“加码”动作。
"""

from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.future import select

from app.core.logger import logger
from app.core.platform_rules import TUNING_TUNABLE_KEYS, clamp_tuning_adjustment
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.order import Order
from app.services.base_service import BaseService

AUTO_COUPON_SOURCES = (
    "entry_coupon",
    "new_customer_coupon",
    "consumption_coupon",
    "recall_coupon",
    "points_reward_coupon",
)

# 调参前置门槛：数据太少不动
TUNING_MIN_ISSUED = 30
TUNING_MIN_SETTLED = 15
# 同一类型两次调整至少间隔这么多天（留时间看效果）
TUNING_COOLDOWN_DAYS = 14
# 每类型 _log 最多保留多少条
TUNING_LOG_CAP = 20

_VALID_ORDER = Order.status.notin_(["cancelled", "rejected"])
_GROSS = Order.total + func.coalesce(Order.discount_amount, 0)


class MarketingAnalyticsService(BaseService):
    async def _auto_template_source_map(self) -> dict[int, str]:
        """template_id -> rule_type，只含自动发券的模板。"""
        rows = await self.db.execute(
            select(CouponTemplate.id, CouponTemplate.description).where(
                CouponTemplate.tenant_id == self.require_tenant_id(),
                CouponTemplate.description.in_(AUTO_COUPON_SOURCES),
            )
        )
        return {tid: desc for tid, desc in rows.all()}

    # ────────────────────────── 归因 ──────────────────────────
    async def attribution_summary(self, days: int = 30) -> dict:
        tenant_id = self.require_tenant_id()
        cutoff = datetime.utcnow() - timedelta(days=days)
        tpl_map = await self._auto_template_source_map()

        per_source: dict[str, dict] = {
            s: {"issued": 0, "redeemed": 0, "redemption_rate": None, "discount_total": 0.0}
            for s in AUTO_COUPON_SOURCES
        }
        user_customer_ids: set[int] = set()

        if tpl_map:
            crows = await self.db.execute(
                select(Coupon.template_id, Coupon.status, Coupon.customer_id).where(
                    Coupon.tenant_id == tenant_id,
                    Coupon.template_id.in_(list(tpl_map.keys())),
                    Coupon.created_at >= cutoff,
                )
            )
            for tpl_id, status, customer_id in crows.all():
                src = tpl_map.get(tpl_id)
                if not src:
                    continue
                per_source[src]["issued"] += 1
                if status == "USED":
                    per_source[src]["redeemed"] += 1
                    if customer_id:
                        user_customer_ids.add(int(customer_id))

            # 每类型的实际优惠支出：orders -> coupon -> template.description
            drows = await self.db.execute(
                select(
                    CouponTemplate.description,
                    func.coalesce(func.sum(func.coalesce(Order.discount_amount, 0)), 0),
                )
                .select_from(Order)
                .join(Coupon, Order.coupon_id == Coupon.id)
                .join(CouponTemplate, Coupon.template_id == CouponTemplate.id)
                .where(
                    Order.tenant_id == tenant_id,
                    Order.created_at >= cutoff,
                    _VALID_ORDER,
                    CouponTemplate.description.in_(AUTO_COUPON_SOURCES),
                )
                .group_by(CouponTemplate.description)
            )
            for src, total in drows.all():
                if src in per_source:
                    per_source[src]["discount_total"] = float(total or 0)

        for s in per_source.values():
            # MVP：核销率分母用已发（保守偏低，也把还没到期的算进去了），够看趋势
            s["redemption_rate"] = round(s["redeemed"] / s["issued"], 4) if s["issued"] else None

        # 两组人：用过自动券的 vs 同期有单但没用过自动券的
        orows = await self.db.execute(
            select(
                Order.customer_id,
                func.count(Order.id),
                func.coalesce(func.sum(_GROSS), 0),
            )
            .where(
                Order.tenant_id == tenant_id,
                Order.created_at >= cutoff,
                _VALID_ORDER,
                Order.customer_id.isnot(None),
            )
            .group_by(Order.customer_id)
        )
        users = {"n": 0, "orders": 0, "gross": 0.0, "repeat": 0}
        nonusers = {"n": 0, "orders": 0, "gross": 0.0, "repeat": 0}
        for customer_id, ordn, gross in orows.all():
            bucket = users if int(customer_id) in user_customer_ids else nonusers
            bucket["n"] += 1
            bucket["orders"] += int(ordn or 0)
            bucket["gross"] += float(gross or 0)
            if int(ordn or 0) >= 2:
                bucket["repeat"] += 1

        def cohort(b: dict) -> dict:
            n = b["n"] or 0
            orders = b["orders"] or 0
            return {
                "n": n,
                "orders_per_customer": round(orders / n, 2) if n else 0.0,
                "repeat_rate": round(b["repeat"] / n, 4) if n else None,
                "avg_aov_gross": round(b["gross"] / orders, 2) if orders else 0.0,
            }

        cu, nu = cohort(users), cohort(nonusers)
        auto_discount_total = round(sum(s["discount_total"] for s in per_source.values()), 2)

        est_incremental = 0.0
        if cu["n"] and nu["n"] and nu["avg_aov_gross"] > 0:
            delta_freq = cu["orders_per_customer"] - nu["orders_per_customer"]
            est_incremental = round(max(delta_freq, 0.0) * nu["avg_aov_gross"] * cu["n"], 2)
        roi = None
        if auto_discount_total > 0:
            roi = round((est_incremental - auto_discount_total) / auto_discount_total, 2)

        return {
            "window_days": days,
            "per_source": per_source,
            "cohorts": {"coupon_users": cu, "non_users": nu},
            "auto_discount_total": auto_discount_total,
            "est_incremental_revenue": est_incremental,
            "roi": roi,
            "note": "观察性对比，用券组本身更活跃会高估，方向性参考",
        }

    # ────────────────────────── 调参 ──────────────────────────
    async def _tuning_signal(self, rule_type: str, days: int = 45) -> dict:
        tenant_id = self.require_tenant_id()
        now = datetime.utcnow()
        cutoff = now - timedelta(days=days)

        tpl_rows = await self.db.execute(
            select(CouponTemplate.id).where(
                CouponTemplate.tenant_id == tenant_id,
                CouponTemplate.description == rule_type,
            )
        )
        tpl_ids = [tid for (tid,) in tpl_rows.all()]
        if not tpl_ids:
            return {"issued": 0, "settled": 0, "redemption_rate": None, "repeat_rate": None}

        rows = await self.db.execute(
            select(Coupon.status, Coupon.expire_time, Coupon.use_time, Coupon.customer_id).where(
                Coupon.tenant_id == tenant_id,
                Coupon.template_id.in_(tpl_ids),
                Coupon.created_at >= cutoff,
            )
        )
        issued = used = settled = 0
        used_customers: set[int] = set()
        for status, expire_time, use_time, customer_id in rows.all():
            issued += 1
            if status == "USED":
                used += 1
                settled += 1
                if customer_id:
                    used_customers.add(int(customer_id))
            elif expire_time and expire_time < now:
                settled += 1

        redemption_rate = round(used / settled, 4) if settled else None

        repeat_rate = None
        if used_customers:
            orows = await self.db.execute(
                select(Order.customer_id, func.count(Order.id))
                .where(
                    Order.tenant_id == tenant_id,
                    Order.created_at >= cutoff,
                    _VALID_ORDER,
                    Order.customer_id.in_(list(used_customers)),
                )
                .group_by(Order.customer_id)
            )
            repeat = sum(1 for _, n in orows.all() if int(n or 0) >= 2)
            repeat_rate = round(repeat / len(used_customers), 4)

        return {
            "issued": issued,
            "settled": settled,
            "redemption_rate": redemption_rate,
            "repeat_rate": repeat_rate,
        }

    @staticmethod
    def _decide(current: dict, signal: dict) -> tuple[dict | None, str]:
        """按核销率/复购率出一小步调整。返回 (新的 {threshold_mult,amount_mult} 或 None, 原因)。"""
        r = signal.get("redemption_rate")
        rr = signal.get("repeat_rate") or 0.0
        t = float(current.get("threshold_mult", 1.0))
        a = float(current.get("amount_mult", 1.0))
        if r is None:
            return None, "no_signal"
        if r < 0.10:
            return {"threshold_mult": t * 0.93, "amount_mult": a}, f"redemption_low({r})_lower_threshold"
        if r > 0.65 and rr < 0.30:
            return {"threshold_mult": t, "amount_mult": a * 0.92}, f"redemption_high_repeat_flat({r}/{rr})_trim_amount"
        return None, f"healthy({r})"

    async def compute_and_apply_tuning(self, *, write: bool = True) -> dict:
        """对每个可调类型跑一轮。write=False 只算不落库（总开关关时用）。"""
        from sqlalchemy.orm.attributes import flag_modified

        from app.services.tenant_service import TenantService

        tenant_id = self.require_tenant_id()
        ts = TenantService(self.db)
        config = await ts.get_tenant_config(tenant_id)
        if not config:
            return {"decisions": [], "skipped": "no_config"}

        business_info = dict(config.business_info or {})
        tuning = dict(business_info.get("coupon_tuning") or {})
        log = list(tuning.get("_log") or [])
        now = datetime.utcnow()

        attribution = await self.attribution_summary(days=30)
        decisions = []
        changed = False

        for rule_type in TUNING_TUNABLE_KEYS:
            signal = await self._tuning_signal(rule_type)
            if signal["issued"] < TUNING_MIN_ISSUED or signal["settled"] < TUNING_MIN_SETTLED:
                decisions.append({"rule": rule_type, "action": "skip", "reason": "insufficient_data", "signal": signal})
                continue

            last = next((e for e in reversed(log) if e.get("rule") == rule_type and e.get("to")), None)
            if last:
                try:
                    last_ts = datetime.fromisoformat(last["ts"])
                except (ValueError, KeyError, TypeError):
                    last_ts = None
                if last_ts and (now - last_ts).days < TUNING_COOLDOWN_DAYS:
                    decisions.append({"rule": rule_type, "action": "skip", "reason": "cooldown", "signal": signal})
                    continue

            current = clamp_tuning_adjustment(tuning.get(rule_type))

            # 步骤 4：ROI < 1 且上一步是“加码”（amount_mult 调高）→ 回滚那一步
            src_roi = (attribution.get("per_source", {}).get(rule_type) or {})
            roi = attribution.get("roi")
            if (
                roi is not None
                and roi < 1.0
                and last
                and float((last.get("to") or {}).get("amount_mult", 1.0)) > float((last.get("from") or {}).get("amount_mult", 1.0))
            ):
                reverted = clamp_tuning_adjustment({
                    "threshold_mult": current["threshold_mult"],
                    "amount_mult": (float(last["from"].get("amount_mult", 1.0)) + current["amount_mult"]) / 2,
                })
                if reverted != current:
                    entry = {"ts": now.isoformat(), "rule": rule_type, "from": current, "to": reverted,
                             "redemption_rate": signal["redemption_rate"], "repeat_rate": signal["repeat_rate"],
                             "reason": f"roi_rollback(roi={roi})"}
                    tuning[rule_type] = reverted
                    log.append(entry)
                    decisions.append({"rule": rule_type, "action": "rollback", **entry})
                    changed = True
                    continue

            proposed, reason = self._decide(current, signal)
            if proposed is None:
                decisions.append({"rule": rule_type, "action": "hold", "reason": reason, "signal": signal})
                continue
            new = clamp_tuning_adjustment(proposed)
            if new == current:
                decisions.append({"rule": rule_type, "action": "hold", "reason": f"{reason}_at_clamp", "signal": signal})
                continue
            entry = {"ts": now.isoformat(), "rule": rule_type, "from": current, "to": new,
                     "redemption_rate": signal["redemption_rate"], "repeat_rate": signal["repeat_rate"],
                     "reason": reason}
            tuning[rule_type] = new
            log.append(entry)
            decisions.append({"rule": rule_type, "action": "adjust", **entry})
            changed = True

        if changed and write:
            tuning["_log"] = log[-TUNING_LOG_CAP:]
            business_info["coupon_tuning"] = tuning
            config.business_info = business_info
            flag_modified(config, "business_info")
            await self.db.commit()

        return {"decisions": decisions, "wrote": bool(changed and write), "roi": attribution.get("roi")}
