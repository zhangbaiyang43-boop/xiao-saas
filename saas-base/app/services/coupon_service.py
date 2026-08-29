import random
from contextlib import asynccontextmanager, AsyncExitStack
from datetime import datetime, timedelta
from sqlalchemy import func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import settings
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.services.anti_fraud_service import AntiFraudService
from app.utils.id_generator import generate_coupon_code, generate_snowflake_id
from app.core.logger import log_coupon_transition, logger
from app.core.lock import try_acquire_lock, redis_lock
from app.core.time_utils import to_utc_iso

from app.services.base_service import BaseService


class CouponService(BaseService):
    def __init__(self, db: AsyncSession):
        super().__init__(db)

    @staticmethod
    def normalize_weighted_coupon_options(rule_config: dict) -> list[dict]:
        raw_options = rule_config.get("weighted_coupons") or []
        if not raw_options:
            return []

        default_threshold = float(rule_config.get("threshold", 0) or 0)
        default_valid_days = int(rule_config.get("valid_days", 7) or 7)
        options = []
        for item in raw_options:
            try:
                amount = float(item.get("amount", item.get("value", 0)) or 0)
                weight = int(item.get("weight", 0) or 0)
                if amount <= 0 or weight <= 0:
                    continue
                options.append({
                    "name": item.get("name") or item.get("title") or "幸运券",
                    "amount": amount,
                    "threshold": float(item.get("threshold", default_threshold) or 0),
                    "valid_days": int(item.get("valid_days", default_valid_days) or default_valid_days),
                    "weight": weight,
                })
            except (TypeError, ValueError):
                continue
        return options

    @staticmethod
    def select_weighted_coupon(rule_config: dict) -> dict:
        if not rule_config.get("weighted_enabled", False):
            return dict(rule_config or {})

        options = CouponService.normalize_weighted_coupon_options(rule_config)
        if not options:
            return dict(rule_config or {})

        return random.choices(options, weights=[item["weight"] for item in options], k=1)[0]

    async def _recent_order_stats(self) -> tuple[float, int]:
        """近 AOV_LOOKBACK_DAYS 天的 (平均客单价, 有效订单数)，供 AOV 和发放量预测复用。"""
        from app.core.platform_rules import AOV_LOOKBACK_DAYS
        from app.models.order import Order
        tenant_id = self.require_tenant_id()
        cutoff = datetime.utcnow() - timedelta(days=AOV_LOOKBACK_DAYS)
        # 客单价按「应付/原价」口径：Order.total 是扣完优惠券的实付，要把
        # discount_amount 加回来，否则发券→用券→实付降→AOV 降→券越算越小的向下螺旋。
        result = await self.db.execute(
            select(
                func.avg(Order.total + func.coalesce(Order.discount_amount, 0)),
                func.count(Order.id),
            ).where(
                Order.tenant_id == tenant_id,
                Order.created_at >= cutoff,
                Order.status.notin_(["cancelled", "rejected"]),
            )
        )
        row = result.one()
        avg_val, count = row[0], row[1] or 0
        return float(avg_val or 0), int(count)

    async def _menu_price_estimate(self) -> float:
        """冷启动客单价估计：在售菜品价格的中位数 × 1.2（人均点一份多一点）。
        没有菜单返回 0，调用方再退到业态兜底。"""
        from app.models.menu_item import MenuItem
        tenant_id = self.require_tenant_id()
        rows = await self.db.execute(
            select(MenuItem.price).where(
                MenuItem.tenant_id == tenant_id,
                MenuItem.available.is_(True),
                MenuItem.price > 0,
            ).order_by(MenuItem.price)
        )
        prices = [float(p) for (p,) in rows.all() if p]
        if not prices:
            return 0.0
        mid = len(prices) // 2
        median = prices[mid] if len(prices) % 2 else (prices[mid - 1] + prices[mid]) / 2
        return round(median * 1.2, 2)

    async def get_merchant_aov(self) -> float:
        """该店的有效客单价估计（原价口径）。
        ≥ AOV_MIN_ORDERS 单：用真实近30天均值；
        否则：用菜单菜品价格中位数 × 1.2 估计；连菜单都没有：返回 0（业态兜底）。"""
        from app.core.platform_rules import AOV_MIN_ORDERS
        avg_val, count = await self._recent_order_stats()
        if count >= AOV_MIN_ORDERS and avg_val:
            return avg_val
        return await self._menu_price_estimate()

    async def _recent_discount_and_gmv(self) -> tuple[float, float, int]:
        """近30天 (优惠总额, GMV原价口径, 订单数)。"""
        from app.models.order import Order
        tenant_id = self.require_tenant_id()
        cutoff = datetime.utcnow() - timedelta(days=30)
        row = (await self.db.execute(
            select(
                func.coalesce(func.sum(func.coalesce(Order.discount_amount, 0)), 0),
                func.coalesce(func.sum(Order.total + func.coalesce(Order.discount_amount, 0)), 0),
                func.count(Order.id),
            ).where(
                Order.tenant_id == tenant_id,
                Order.created_at >= cutoff,
                Order.status.notin_(["cancelled", "rejected"]),
            )
        )).one()
        return float(row[0] or 0), float(row[1] or 0), int(row[2] or 0)

    async def within_discount_budget(self) -> bool:
        """月优惠预算总闸：近30天优惠总额 ≤ GMV × X%（X 随强度）。
        数据太少（冷启动）不设限，先把量做起来。这是「不亏钱」的总账防线，
        单张券的面额不再靠拍毛利率去卡。"""
        from app.core.platform_rules import (
            DISCOUNT_BUDGET_MIN_GMV,
            DISCOUNT_BUDGET_MIN_ORDERS,
            discount_budget_ratio,
        )
        discount, gmv, count = await self._recent_discount_and_gmv()
        if count < DISCOUNT_BUDGET_MIN_ORDERS or gmv < DISCOUNT_BUDGET_MIN_GMV:
            return True
        intensity = await self.get_marketing_intensity()
        return discount <= gmv * discount_budget_ratio(intensity)

    async def get_marketing_intensity(self) -> str:
        """商家选择的营销强度档位（保守/标准/激进），未设置时回落标准档。"""
        from app.core.platform_rules import resolve_intensity
        from app.services.tenant_service import TenantService
        tenant_service = TenantService(self.db)
        config = await tenant_service.get_tenant_config(self.tenant_id)
        business_info = (config.business_info or {}) if config else {}
        return resolve_intensity(business_info.get("marketing_intensity"))

    async def get_industry(self) -> str:
        """商家开店选的业态（面馆/快餐/火锅…），未设置回落 default。"""
        from app.core.platform_rules import resolve_industry
        from app.services.tenant_service import TenantService
        config = await TenantService(self.db).get_tenant_config(self.tenant_id)
        business_info = (config.business_info or {}) if config else {}
        return resolve_industry(business_info.get("industry"))

    async def get_coupon_tuning(self) -> dict:
        """核销率闭环调参的当前覆盖层（每类型 threshold_mult / amount_mult）。
        存在 business_info.coupon_tuning，不用单开表/迁移。没有则空 dict。"""
        from app.services.tenant_service import TenantService
        config = await TenantService(self.db).get_tenant_config(self.tenant_id)
        business_info = (config.business_info or {}) if config else {}
        tuning = business_info.get("coupon_tuning")
        return tuning if isinstance(tuning, dict) else {}

    async def get_coupon_rules(self) -> dict:
        from app.core.platform_rules import apply_tuning, build_dynamic_rules
        from app.services.tenant_service import TenantService, normalize_coupon_rules
        tenant_service = TenantService(self.db)
        config = await tenant_service.get_tenant_config(self.tenant_id)
        # 商户配置只认 enabled 开关；金额/门槛/有效期一律走 build_dynamic_rules。
        # normalize 把历史胖配置（含 locked / 写死金额 / weighted_coupons）就地清成
        # 只剩 enabled，老商户不用跑迁移也能立刻用上动态规则。
        merchant_rules = normalize_coupon_rules(config.coupon_rules) if config else {}
        # 动态则：根据该商户实际客单价 + 选择的营销强度生成，新商户用安全兜底值
        aov = await self.get_merchant_aov()
        intensity = await self.get_marketing_intensity()
        industry = await self.get_industry()
        platform_rules = build_dynamic_rules(aov, intensity, industry)
        # 核销率闭环调参：把每周微调出来的两个乘数叠加上去（仍受结算红线 + 预算闸约束）
        platform_rules = apply_tuning(platform_rules, (config.business_info or {}).get("coupon_tuning") if config else None)
        # 商户只有显式 locked 某条则时，才允许静态配置覆盖算法算出来的值；
        # 未 locked 时只认 enabled 开关，金额/门槛始终由算法算——这样商家开
        # 户时写入的那份历史默认值（旧版 DEFAULT_COUPON_RULES 种子数据）不会
        # 把算法结果顶掉，保证"傻瓜式"三档强度对所有商户都真正生效。
        merged = {}
        for key, platform_rule in platform_rules.items():
            merchant_override = merchant_rules.get(key, {})
            if merchant_override.get("locked"):
                merged[key] = {**platform_rule, **merchant_override}
            else:
                merged[key] = dict(platform_rule)
                if "enabled" in merchant_override:
                    merged[key]["enabled"] = merchant_override["enabled"]
        for key, rule in merchant_rules.items():
            if key not in merged:
                merged[key] = rule
        return merged

    async def resolve_consumption_coupon_rule_type(
        self,
        customer_id: int,
        *,
        exclude_order_id: int | None = None,
        exclude_consumption_id: int | None = None,
    ) -> str:
        """Return new_customer_coupon vs consumption_coupon from cross-channel history.

        Counts paid orders and manual consumptions together so online checkout and
        back-office entry stay in sync when deciding first-consumption rewards.
        """
        from app.models.consumption import Consumption
        from app.models.order import Order

        tenant_id = self.require_tenant_id()

        order_filters = [
            Order.tenant_id == tenant_id,
            Order.customer_id == customer_id,
            Order.payment_status == "paid",
        ]
        if exclude_order_id is not None:
            order_filters.append(Order.id != exclude_order_id)

        order_count_result = await self.db.execute(
            select(func.count(Order.id)).where(*order_filters)
        )
        order_count = int(order_count_result.scalar() or 0)

        consumption_filters = [
            Consumption.tenant_id == tenant_id,
            Consumption.customer_id == customer_id,
        ]
        if exclude_consumption_id is not None:
            consumption_filters.append(Consumption.id != exclude_consumption_id)

        consumption_count_result = await self.db.execute(
            select(func.count(Consumption.id)).where(*consumption_filters)
        )
        consumption_count = int(consumption_count_result.scalar() or 0)

        if order_count + consumption_count > 0:
            return "consumption_coupon"
        return "new_customer_coupon"

    async def preview_new_customer_coupon(self) -> dict | None:
        """未登录顾客也能看到的"首单钩子"文案数据源：只读、不发券、不查重复领取，
        单纯把 new_customer_coupon 这条则算出来的面额/门槛/有效期报给前端展示用。
        字段名对齐 miniapp.py 入会成功后真正发放的 new_customer_coupon（amount/min_amount），
        避免出现"登录前说的数字"和"登录后到手的数字"对不上的落差。"""
        rules = await self.get_coupon_rules()
        rule_config = rules.get("new_customer_coupon", {})
        if not rule_config.get("enabled", False):
            return None

        options = self.normalize_weighted_coupon_options(rule_config)
        if options:
            selected = max(options, key=lambda o: o["weight"])
        else:
            amount = float(rule_config.get("amount", 0) or 0)
            if amount <= 0:
                return None
            selected = {
                "name": rule_config.get("name") or "新客专享券",
                "amount": amount,
                "threshold": float(rule_config.get("threshold", 0) or 0),
                "valid_days": int(rule_config.get("valid_days", 3) or 3),
            }

        return {
            "name": selected.get("name") or "新客专享券",
            "amount": selected.get("amount", 0),
            "min_amount": selected.get("threshold", 0),
            "valid_days": selected.get("valid_days", 3),
        }

    async def estimate_intensity_outcomes(self) -> dict:
        """阶段二：三档强度各自的预测结果，供"选强度"卡片直接展示预测数字，
        而不是参数——商家看的是"预计花多少钱、换多少客户"，不是门槛/面额本身。

        成本估算用复购券（每单结账后都会触发，是量级最大的一条线）的加权平均
        面额 × 预计月订单数来近似，是方向性估算，不是精确财务口径。
        """
        from app.core.platform_rules import AOV_LOOKBACK_DAYS, AOV_MIN_ORDERS, INTENSITY_LABELS, INTENSITY_PRESETS, build_dynamic_rules

        aov, order_count = await self._recent_order_stats()
        has_enough_data = order_count >= AOV_MIN_ORDERS
        industry = await self.get_industry()
        # 客单价口径跟 get_merchant_aov 完全一致：够单量用真实均值，否则菜单菜品
        # 价中位数×1.2，连菜单都没有再退到业态兜底客单价（不再写死 30）。
        from app.core.platform_rules import INDUSTRY_PRESETS
        effective_aov = await self.get_merchant_aov() or float(INDUSTRY_PRESETS[industry]["fallback_aov"])
        monthly_orders = round(order_count / AOV_LOOKBACK_DAYS * 30, 1)
        current_intensity = await self.get_marketing_intensity()

        outcomes = []
        for key in INTENSITY_PRESETS:
            rules = build_dynamic_rules(effective_aov, key, industry)
            weighted = rules["consumption_coupon"]["weighted_coupons"]
            total_weight = sum(w["weight"] for w in weighted) or 1
            avg_amount = sum(w["amount"] * w["weight"] for w in weighted) / total_weight
            estimated_cost = round(avg_amount * monthly_orders, 2)
            estimated_revenue = monthly_orders * effective_aov
            cost_ratio = round(estimated_cost / estimated_revenue, 4) if estimated_revenue > 0 else 0.0

            outcomes.append({
                "intensity": key,
                "label": INTENSITY_LABELS[key],
                "is_current": key == current_intensity,
                "rules": rules,
                "estimated_monthly_coupons": monthly_orders,
                "estimated_cost_per_month": estimated_cost,
                "estimated_cost_ratio": cost_ratio,
            })

        return {
            "aov": round(aov, 1) if aov else None,
            "has_enough_data": has_enough_data,
            "current_intensity": current_intensity,
            "outcomes": outcomes,
        }

    async def _has_dup_after_lock(self, customer_id: int, rule_type: str) -> bool:
        """在拿到锁之后再查一次是否已持有同类未用券，供各去重发放入口复用。"""
        return bool(await self.get_available_auto_coupon(customer_id, rule_type))

    @asynccontextmanager
    async def _dedup_issue_lock(self, customer_id: int, rule_type: str):
        """包住"查是否已持有同类未用券 + 真正发放"这两步，防止两个并发请求都在
        检查那一刻看到"没有"从而各自发一张——纯应用层的 check-then-act 挡不住这种
        竞态，必须靠锁把这两步锁成一个原子操作。

        数据库行锁是最终安全边界，不管 Redis 是否可用都会生效：不然 Redis 挂了、
        或者同一进程内多个 worker/多台实例同时跑召回任务时，check-then-act 的
        竞态窗口会重新暴露出来，同一个业务事件被重复发券。Redis 分布式锁只是在
        此之上的第一层优化（能让"暂时抢不到锁"的请求快速失败返回，而不是排队等
        行锁释放），不是唯一防线。

        用 UPDATE（而不是 SELECT ... FOR UPDATE）来加这把锁：SQLite 语法上会接受
        FOR UPDATE 但直接忽略，测试环境下等于没锁；UPDATE 语句在 MySQL 上正常
        走行锁，在 SQLite 上会走它自己的写锁语义，两边都能真正拿到互斥，不用
        为了兼容测试环境单独维护一套逻辑。

        用法：
            async with self._dedup_issue_lock(customer_id, rule_type) as should_issue:
                if not should_issue:
                    return {"success_count": 0, "reason": "..."}
                ... 真正发放 ...
        """
        from sqlalchemy import update
        from app.models.customer import Customer

        tenant_id = self.require_tenant_id()
        # 锁住这个顾客的行，让同一顾客+同一租户的并发发放请求在数据库层面串行化，
        # 直到持锁事务提交/回滚才释放——这个锁会一直持有到调用方那次业务操作
        # （支付成功/结账/入会等）整体提交为止，这是有意为之：既然要保证"查+发"
        # 原子，锁就必须覆盖到发放真正落库的那一刻。
        await self.db.execute(
            update(Customer)
            .where(Customer.id == customer_id, Customer.tenant_id == tenant_id)
            .values(updated_at=datetime.utcnow())
        )

        if not settings.REDIS_ENABLED:
            yield not await self._has_dup_after_lock(customer_id, rule_type)
            return

        lock_key = f"coupon_issue:{tenant_id}:{customer_id}:{rule_type}"
        try:
            async with redis_lock(lock_key, timeout=10) as acquired:
                if not acquired:
                    yield False
                    return
                yield not await self._has_dup_after_lock(customer_id, rule_type)
        except RuntimeError:
            # Redis 在 settings.REDIS_ENABLED 为真之后突然不可用了，仍然有上面的
            # 数据库行锁兜底，不需要再退化成完全不加锁。
            yield not await self._has_dup_after_lock(customer_id, rule_type)

    async def issue_auto_coupon(
        self,
        customer_id: int,
        rule_type: str,
        consumption_amount: float = None,
        auto_commit: bool = True,
    ) -> dict:
        rules = await self.get_coupon_rules()
        rule_config = rules.get(rule_type, {})

        if not rule_config.get("enabled", False):
            return {"success_count": 0, "reason": "则未开启"}

        if not await self.within_discount_budget():
            return {"success_count": 0, "reason": "本月优惠预算已用尽，暂停自动发券"}

        if rule_type == "consumption_coupon" and consumption_amount is not None:
            trigger_amount = rule_config.get("trigger_amount", 0)
            if float(consumption_amount) < float(trigger_amount):
                return {"success_count": 0, "reason": f"消费金额{consumption_amount}未达触发门槛{trigger_amount}"}

        async def _do_issue() -> dict:
            selected_rule = self.select_weighted_coupon(rule_config)
            amount = selected_rule.get("amount", rule_config.get("amount", 0))
            threshold = selected_rule.get("threshold", rule_config.get("threshold", 0))
            valid_days = selected_rule.get("valid_days", rule_config.get("valid_days", 7))
            template_name = selected_rule.get("name")

            template = await self._get_or_create_auto_coupon_template(
                rule_type=rule_type,
                amount=amount,
                threshold=threshold,
                valid_days=valid_days,
                template_name=template_name,
                auto_commit=auto_commit,
            )

            if not template:
                return {"success_count": 0, "reason": "建优惠券模失败"}

            result = await self.send_coupons_with_result(
                template.id,
                [customer_id],
                source=rule_type,
                auto_commit=auto_commit,
            )

            if result["success_count"] > 0:
                result["source"] = rule_type
                result["weighted_coupon"] = {
                    "name": template_name,
                    "amount": amount,
                    "threshold": threshold,
                    "valid_days": valid_days,
                }

            return result

        # 去重：手上还有没用完的同类型自动券就不再发新的。门槛/金额是按当时实时客单价
        # 加权随机算出来的——不去重的话同一个客户每触发一次就多领一张金额、门槛都不一样
        # 的券，名下会员详情/小程序选券列表看到的"两张券"其实一直在变成新的两张。
        # entry_coupon 已经这样做了（见 issue_entry_coupon），这里对 issue_auto_coupon
        # 覆盖的所有 rule_type 统一补齐同样的保护——之前只对 consumption_coupon 生效，
        # new_customer_coupon 完全没有去重：入会时（miniapp.py /entry/join、
        # member.py /login-or-create）和首单支付成功时（orders.py _on_payment_success）
        # 是三条独立的发放入口，只有 /entry/join 自己在调用前手动查过一次是否已有，
        # 另外两条完全没查，导致一个新客户入会 + 完成首单，稳定拿到两张新客券。
        # 用分布式锁包住"查+发"两步，防止两个并发请求都在检查那一刻看到"没有"。
        async with self._dedup_issue_lock(customer_id, rule_type) as should_issue:
            if not should_issue:
                reason = "已持有未使用的复购券，本次不再发放" if rule_type == "consumption_coupon" else "已持有未使用的同类券，本次不再发放"
                return {"success_count": 0, "reason": reason, "skipped_duplicate": True}
            return await _do_issue()

    async def _existing_entry_coupon_payload(self, customer_id: int) -> dict | None:
        existing = await self.get_available_auto_coupon(customer_id, "entry_coupon")
        if not existing:
            return None
        from app.models.coupon_template import CouponTemplate as _Tpl
        tpl = await self.db.get(_Tpl, existing.template_id)
        return {
            "coupon_id": str(existing.id),
            "name": (tpl.name if tpl else None) or "今日专享券",
            "amount": float(tpl.value) if tpl else 0,
            "threshold": float(tpl.min_amount) if tpl else 0,
            "expire_time": to_utc_iso(existing.expire_time),
            "is_new": False,
        }

    async def issue_entry_coupon(self, customer_id: int) -> dict | None:
        """进店券：用户扫码进入菜单时静默发放，当日有效，去重（同一天同一租户只发一次）。"""
        rules = await self.get_coupon_rules()
        rule_config = rules.get("entry_coupon", {})
        if not rule_config.get("enabled", False):
            return None
        if not await self.within_discount_budget():
            return None

        # 去重：今天是否已持有进店券。用分布式锁包住"查+发"两步——两次几乎同时的
        # 扫码请求都可能在检查那一刻看到"没有"，不加锁的话会各自发一张。
        async with self._dedup_issue_lock(customer_id, "entry_coupon") as should_issue:
            if not should_issue:
                return await self._existing_entry_coupon_payload(customer_id)

            selected = self.select_weighted_coupon(rule_config)
            amount = float(selected.get("amount", 3))
            threshold = float(selected.get("threshold", 50))
            valid_days = int(selected.get("valid_days", 1))
            name = selected.get("name", "今日专享券")

            template = await self._get_or_create_auto_coupon_template(
                rule_type="entry_coupon",
                amount=amount,
                threshold=threshold,
                valid_days=valid_days,
                template_name=name,
            )
            if not template:
                return None

            result = await self.send_coupons_with_result(template.id, [customer_id], source="entry_coupon")
            if result.get("success_count", 0) > 0:
                sent = result["sent"][0]
                return {
                    "coupon_id": sent["id"],
                    "name": name,
                    "amount": amount,
                    "threshold": threshold,
                    "expire_time": to_utc_iso(sent.get("expire_time")),
                    "is_new": True,
                }
            return None

    async def get_available_auto_coupon(self, customer_id: int, rule_type: str) -> Coupon | None:
        """检查该会员是否已持有指定则类型的有效自动券（去重用）。

        BUG-D 修复：优先按 CouponTemplate.description == rule_type 匹配，
        兼容旧模（description 为 NULL）时退回按固定模名匹配，
        从而覆盖加权发券场景下各种不同的模名称。
        """
        from sqlalchemy import or_

        tenant_id = self.require_tenant_id()
        # 旧模的固定名称（向下兼容）
        legacy_names = {
            "new_customer_coupon": "新客券",
            "consumption_coupon": "消费后发券",
            "recall_coupon": "老客召回券",
            "entry_coupon": "今日专享券",
        }
        legacy_name = legacy_names.get(rule_type)
        if not legacy_name:
            return None

        now = datetime.utcnow()
        result = await self.db.execute(
            select(Coupon)
            .join(CouponTemplate, CouponTemplate.id == Coupon.template_id)
            .filter(
                Coupon.tenant_id == tenant_id,
                Coupon.customer_id == customer_id,
                Coupon.status == "UNUSED",
                Coupon.expire_time > now,
                CouponTemplate.tenant_id == tenant_id,
                CouponTemplate.status == 1,
                # 新模：description 存储了 rule_type；旧模：按固定名称兜底
                or_(
                    CouponTemplate.description == rule_type,
                    CouponTemplate.name == legacy_name,
                ),
            )
            .order_by(Coupon.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_or_create_auto_coupon_template(
        self,
        rule_type: str,
        amount: float,
        threshold: float,
        valid_days: int,
        template_name: str | None = None,
        auto_commit: bool = True,
    ) -> CouponTemplate:
        template_names = {
            "new_customer_coupon": "新客券",
            "consumption_coupon": "消费后发券",
            "recall_coupon": "老客召回券"
        }
        template_name = template_name or template_names.get(rule_type, "自动发券")
        
        now = datetime.utcnow()
        # BUG-E 修复：复用模时要求剩余有效期 >= valid_days，
        # 避免从老模发出的券实际有效天数短于配置值。
        min_end_time = now + timedelta(days=valid_days)
        result = await self.db.execute(
            select(CouponTemplate)
            .filter(
                CouponTemplate.tenant_id == self.tenant_id,
                CouponTemplate.name == template_name,
                CouponTemplate.type == "FIXED",
                CouponTemplate.value == amount,
                CouponTemplate.min_amount == threshold,
                CouponTemplate.status == 1,
                CouponTemplate.end_time >= min_end_time,
                CouponTemplate.total_stock > CouponTemplate.used_stock,
            )
            .order_by(CouponTemplate.created_at.desc())
            .limit(1)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing
        
        template = CouponTemplate(
            id=generate_snowflake_id(),
            tenant_id=self.tenant_id,
            name=template_name,
            type="FIXED",
            value=amount,
            min_amount=threshold,
            total_stock=9999,
            used_stock=0,
            start_time=now - timedelta(minutes=1),
            end_time=now + timedelta(days=valid_days),
            status=1,
            # BUG-D 修复：用 description 存储则类型，
            # 使去重查询不依赖模名称（加权券名称各不相同）
            description=rule_type,
        )
        self.db.add(template)
        if auto_commit:
            await self.db.commit()
        else:
            await self.db.flush()
        await self.db.refresh(template)
        return template

    @staticmethod
    def plan_recipients_by_stock(customer_ids: list, total_stock: int, used_stock: int) -> list:
        remaining = max(int(total_stock or 0) - int(used_stock or 0), 0)
        if remaining <= 0:
            return []
        return list(customer_ids or [])[:remaining]

    @staticmethod
    def build_send_result(
        requested_customer_ids: list,
        sent_coupons: list,
        failed: list,
        remaining_stock: int,
        reason: str | None = None,
    ) -> dict:
        return {
            "requested_count": len(requested_customer_ids or []),
            "success_count": len(sent_coupons or []),
            "failed_count": len(failed or []),
            "remaining_stock": max(int(remaining_stock or 0), 0),
            "reason": reason,
            "sent": sent_coupons or [],
            "failed": failed or [],
        }

    async def create_template(
        self,
        name: str,
        type: str,
        value: float,
        min_amount: float = 0,
        total_stock: int = 100,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        status: int = 1,
    ) -> CouponTemplate:
        from app.core.exceptions import BusinessException
        from app.core.platform_rules import assert_template_economics_safe

        tenant_id = self.require_tenant_id()
        try:
            assert_template_economics_safe(type, value, min_amount)
        except ValueError as exc:
            raise BusinessException(message=str(exc)) from exc

        template = CouponTemplate(
            tenant_id=tenant_id,
            name=name,
            type=type,
            value=value,
            min_amount=min_amount,
            total_stock=total_stock,
            used_stock=0,
            start_time=start_time or datetime.utcnow(),
            end_time=end_time or datetime.utcnow(),
            status=status,
        )

        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def assign_verify_code(self, coupon: Coupon) -> str:
        """为已入库的老券补生成 verify_code（历史兼容）。"""
        tenant_id = self.require_tenant_id()
        code = await self._generate_unique_verify_code(tenant_id)
        coupon.verify_code = code
        await self.db.commit()
        await self.db.refresh(coupon)
        return code

    async def issue_invite_reward_coupon(
        self,
        customer_id: int,
        amount: float,
        min_spend: float,
        valid_days: int,
        template_name: str,
        auto_commit: bool = True,
    ) -> bool:
        """为邀请奖励发放优惠券。

        发放成功返回 True，失败静默记录日志并返回 False（不抛异常），
        确保奖励发券失败不会影响主核销流程。
        """
        try:
            if amount <= 0:
                return False
            template = await self._get_or_create_auto_coupon_template(
                rule_type="invite_reward",
                amount=amount,
                threshold=min_spend,
                valid_days=valid_days,
                template_name=template_name,
                auto_commit=auto_commit,
            )
            if not template:
                logger.error(
                    f"invite_reward: 建模失败 "
                    f"tenant={self.tenant_id} customer={customer_id} amount={amount}"
                )
                return False
            result = await self.send_coupons_with_result(
                template.id,
                [customer_id],
                source="invite_reward",
                auto_commit=auto_commit,
            )
            ok = result.get("success_count", 0) > 0
            if not ok:
                logger.warning(
                    f"invite_reward: 发券未成功 "
                    f"tenant={self.tenant_id} customer={customer_id} "
                    f"reason={result.get('reason')}"
                )
            return ok
        except Exception as e:
            logger.error(
                f"invite_reward: 发券异常 "
                f"tenant={self.tenant_id} customer={customer_id} amount={amount} error={e}"
            )
            if not auto_commit:
                raise
            return False

    async def get_template(self, template_id: int) -> CouponTemplate | None:
        tenant_id = self.require_tenant_id()

        result = await self.db.execute(
            select(CouponTemplate).filter(
                CouponTemplate.id == template_id,
                CouponTemplate.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_templates_batch(self, template_ids: list) -> dict:
        """批量加载模，返回 {template_id: CouponTemplate} 字典。

        将券包列表的 N+1 查询降为 1 次 IN 查询。
        """
        if not template_ids:
            return {}
        tenant_id = self.require_tenant_id()
        unique_ids = list({int(tid) for tid in template_ids if tid is not None})
        if not unique_ids:
            return {}
        result = await self.db.execute(
            select(CouponTemplate).filter(
                CouponTemplate.id.in_(unique_ids),
                CouponTemplate.tenant_id == tenant_id,
            )
        )
        return {t.id: t for t in result.scalars().all()}

    async def list_templates(self, skip: int = 0, limit: int = 100) -> list:
        tenant_id = self.require_tenant_id()

        query = (
            select(CouponTemplate)
            .filter(CouponTemplate.tenant_id == tenant_id)
            .order_by(CouponTemplate.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_templates(self) -> int:
        tenant_id = self.require_tenant_id()

        query = (
            select(func.count())
            .select_from(CouponTemplate)
            .filter(CouponTemplate.tenant_id == tenant_id)
        )

        result = await self.db.execute(query)
        return int(result.scalar() or 0)

    async def update_template(self, template_id: int, **kwargs) -> CouponTemplate | None:
        from app.core.exceptions import BusinessException
        from app.core.platform_rules import assert_template_economics_safe

        template = await self.get_template(template_id)

        if not template:
            return None

        # 已发过券（used_stock > 0）的模板，禁止修改 type/value/min_amount 这三个
        # 核心权益字段：Coupon 实例本身不保存这几个字段的快照，顾客手上已经领到、
        # 还没用掉的券在下单/核销时是实时读模板拿这几个值的——商家改了模板就等于
        # 悄悄改变了已发放未使用券的实际权益。名称、描述、库存上限、有效期这些
        # 不影响"已发券值多少钱"的字段不受此限制。
        core_field_labels = {"type": "类型", "value": "面额", "min_amount": "使用门槛"}
        if int(template.used_stock or 0) > 0:
            for field, label in core_field_labels.items():
                if field not in kwargs:
                    continue
                current_value = getattr(template, field)
                new_value = kwargs[field]
                changed = (
                    str(new_value) != str(current_value)
                    if field == "type"
                    else float(new_value or 0) != float(current_value or 0)
                )
                if changed:
                    raise BusinessException(
                        message=f"该模板已发放过 {template.used_stock} 张券，不能再修改{label}，"
                        f"以免已发放但未使用的顾客券权益被悄悄改变"
                    )

        effective_type = kwargs.get("type", template.type)
        effective_value = kwargs.get("value", template.value)
        effective_min_amount = kwargs.get("min_amount", template.min_amount)
        try:
            assert_template_economics_safe(effective_type, effective_value, effective_min_amount)
        except ValueError as exc:
            raise BusinessException(message=str(exc)) from exc

        for key, value in kwargs.items():
            if hasattr(template, key):
                setattr(template, key, value)

        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def delete_template(self, template_id: int) -> bool:
        template = await self.get_template(template_id)

        if not template:
            return False

        await self.db.delete(template)
        await self.db.commit()
        return True

    async def _generate_unique_code(self) -> str:
        """生成全局唯一券码，最多重试 20 次，超限抛出异常。"""
        tenant_id = self.require_tenant_id()

        for attempt in range(20):
            code = generate_coupon_code()
            existing = await self.db.execute(
                select(Coupon).filter(
                    Coupon.code == code,
                    Coupon.tenant_id == tenant_id,
                )
            )
            if not existing.scalar_one_or_none():
                return code
            logger.warning(f"券码碰撞，重试第 {attempt + 1} 次: tenant={tenant_id}")

        raise RuntimeError(f"无法生成唯一券码（重试 20 次均碰撞），tenant={tenant_id}，请联系管理员")

    async def _generate_unique_verify_code(self, tenant_id, in_batch_codes: set | None = None) -> str:
        """生成在当前租户内唯一的 6 位短码，最多重试 5 次。

        in_batch_codes: 当前批量发券中已分配的短码集合，防止同批重复。
        """
        for attempt in range(5):
            code = AntiFraudService.generate_short_verify_code()
            if in_batch_codes and code in in_batch_codes:
                continue
            conflict = await self.db.execute(
                select(Coupon.id).filter(
                    Coupon.tenant_id == tenant_id,
                    Coupon.verify_code == code,
                )
            )
            if not conflict.scalar_one_or_none():
                return code
        # 5 次重试全部冲突（概率极低），生成一个随机码并记录 warning
        fallback = AntiFraudService.generate_short_verify_code()
        logger.warning(
            f"verify_code 生成 5 次重试均冲突，使用 fallback 随机码: "
            f"tenant_id={tenant_id}, fallback={fallback}"
        )
        return fallback

    async def send_coupons(self, template_id: int, customer_ids: list) -> list:
        result = await self.send_coupons_with_result(template_id, customer_ids)
        return result["sent"]

    async def send_coupons_with_result(
        self,
        template_id,
        customer_ids,
        source: str = None,
        auto_commit: bool = True,
    ) -> dict:
        tenant_id = self.require_tenant_id()

        # 安全转换 （支持 string 和 int）
        try:
            template_id = int(template_id)
        except (ValueError, TypeError):
            return {
                "requested_count": 0,
                "success_count": 0,
                "failed_count": 0,
                "remaining_stock": 0,
                "reason": "无效的优惠券模"
            }
        
        requested_customer_ids = []
        for cid in (customer_ids or []):
            try:
                cid_int = int(cid)
                requested_customer_ids.append(cid_int)
            except (ValueError, TypeError):
                pass
        requested_customer_ids = list(dict.fromkeys(requested_customer_ids))

        # P0 幂等修复：同一批发放请求（同一租户+模板+客户名单）短时间内只允许
        # 真正执行一次，防止商家后台网络重试或手抖双击导致重复发券、重复扣库存。
        # 锁在窗口内自然过期即可，不需要提前释放。Redis 不可用时不阻断发放
        # （这种情况下项目里其它同样依赖 Redis 的功能，如短信验证码，本来就已经
        # 不可用了），只是这一层幂等保护暂时失效。
        if settings.REDIS_ENABLED:
            dedup_key = "coupon_send:" + tenant_id + ":" + str(template_id) + ":" + ",".join(
                str(cid) for cid in requested_customer_ids
            )
            locked = await try_acquire_lock(dedup_key, timeout=10, max_retries=1)
            if not locked:
                return self.build_send_result(
                    requested_customer_ids,
                    [],
                    [{"customer_id": item, "reason": "请求重复提交，请稍后重试"} for item in requested_customer_ids],
                    0,
                    "重复提交，请勿短时间内重复发放",
                )

        result = await self.db.execute(
            select(CouponTemplate)
            .filter(
                CouponTemplate.id == template_id,
                CouponTemplate.tenant_id == tenant_id,
            )
            .with_for_update()
        )

        template = result.scalar_one_or_none()

        if not template or template.status != 1:
            failed = [
                {"customer_id": item, "reason": "优惠券不存在或未上架"}
                for item in requested_customer_ids
            ]
            return self.build_send_result(
                requested_customer_ids,
                [],
                failed,
                0,
                "优惠券不存在或未上架",
            )

        now = datetime.utcnow()

        if template.start_time and now < template.start_time:
            remaining = max(int(template.total_stock or 0) - int(template.used_stock or 0), 0)
            failed = [
                {"customer_id": item, "reason": "优惠券未开始"}
                for item in requested_customer_ids
            ]
            return self.build_send_result(
                requested_customer_ids,
                [],
                failed,
                remaining,
                "优惠券未开始",
            )

        if template.end_time and now > template.end_time:
            remaining = max(int(template.total_stock or 0) - int(template.used_stock or 0), 0)
            failed = [
                {"customer_id": item, "reason": "优惠券已过期"}
                for item in requested_customer_ids
            ]
            return self.build_send_result(
                requested_customer_ids,
                [],
                failed,
                remaining,
                "优惠券已过期",
            )

        selected_customer_ids = self.plan_recipients_by_stock(
            customer_ids=requested_customer_ids,
            total_stock=template.total_stock,
            used_stock=template.used_stock,
        )

        selected_set = set(selected_customer_ids)

        failed = [
            {"customer_id": item, "reason": "库存不足"}
            for item in requested_customer_ids
            if item not in selected_set
        ]

        if not selected_customer_ids:
            return self.build_send_result(
                requested_customer_ids,
                [],
                failed,
                0,
                "库存不足",
            )

        coupons = []
        in_batch_verify_codes: set = set()


        for customer_id in selected_customer_ids:
            if not await AntiFraudService.allow_daily_issue(tenant_id, customer_id):
                failed.append({"customer_id": customer_id, "reason": "今日领券次数过多"})
                continue

            # 每次循环前刷新 template，获取最新的 used_stock（防止同一事务内多次读取旧值）
            await self.db.refresh(template)

            verify_code = await self._generate_unique_verify_code(tenant_id, in_batch_verify_codes)
            in_batch_verify_codes.add(verify_code)

            coupon_kwargs = {
                "tenant_id": tenant_id,
                "template_id": template_id,
                "customer_id": customer_id,
                "code": await self._generate_unique_code(),
                "verify_code": verify_code,
                "status": "UNUSED",
                "expire_time": template.end_time,
            }

            # 只在有 source 字段时添加
            if hasattr(Coupon, "source"):
                coupon_kwargs["source"] = source

            coupon = Coupon(**coupon_kwargs)
            self.db.add(coupon)
            template.used_stock = int(template.used_stock or 0) + 1
            coupons.append(coupon)

        if auto_commit:
            await self.db.commit()
        else:
            await self.db.flush()

        for coupon in coupons:
            await self.db.refresh(coupon)

        remaining = max(int(template.total_stock or 0) - int(template.used_stock or 0), 0)

        sent = [
            {
                "id": str(coupon.id),
                "template_id": str(coupon.template_id),
                "customer_id": str(coupon.customer_id),
                "code": coupon.code,
                "status": coupon.status,
                "expire_time": coupon.expire_time,
            }
            for coupon in coupons
        ]

        return self.build_send_result(
            requested_customer_ids,
            sent,
            failed,
            remaining,
        )

    async def get_customer_coupons(
        self,
        customer_id: int,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list:
        tenant_id = self.require_tenant_id()

        query = select(Coupon).filter(
            Coupon.customer_id == customer_id,
            Coupon.tenant_id == tenant_id,
            Coupon.status.notin_(["REVOKED", "LOCKED"]),  # BUG-D: LOCKED 是支付中间态，不展示给用户
        )

        if status:
            query = query.filter(Coupon.status == status)

        query = query.order_by(Coupon.created_at.desc()).offset(skip).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_customer_coupons(
        self,
        customer_id: int,
        status: str | None = None,
        not_expired: bool = False,
    ) -> int:
        """统计该会员的券数量。

        not_expired=True 时，对 UNUSED 券额外过滤 expire_time > now，
        使"可用券数"与券包页的运行时分类逻辑一致。
        """
        tenant_id = self.require_tenant_id()

        query = select(func.count()).select_from(Coupon).filter(
            Coupon.customer_id == customer_id,
            Coupon.tenant_id == tenant_id,
            Coupon.status.notin_(["REVOKED", "LOCKED"]),
        )

        if status:
            query = query.filter(Coupon.status == status)

        if not_expired:
            now = datetime.utcnow()
            query = query.filter(Coupon.expire_time > now)

        result = await self.db.execute(query)
        return int(result.scalar() or 0)

    async def list_issued_coupons(
        self,
        customer_id: int | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 100,
        source: str | None = None,
        keyword: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list:
        from app.models.customer import Customer
        from app.models.customer_identity import CustomerIdentity
        from sqlalchemy import or_, and_
        
        tenant_id = self.require_tenant_id()

        query = select(Coupon).filter(Coupon.tenant_id == tenant_id)

        if customer_id:
            query = query.filter(Coupon.customer_id == customer_id)

        if status:
            query = query.filter(Coupon.status == status)

        # if source:
        #     query = query.filter(Coupon.source == source)

        if keyword:
            like = f"%{keyword}%"
            query = query.outerjoin(
                Customer,
                and_(Coupon.customer_id == Customer.id, Customer.tenant_id == tenant_id),
            ).outerjoin(
                CustomerIdentity,
                and_(Coupon.customer_id == CustomerIdentity.customer_id, CustomerIdentity.tenant_id == tenant_id),
            )
            query = query.filter(
                or_(
                    Customer.phone.like(like),
                    Customer.name.like(like),
                    CustomerIdentity.phone.like(like),
                    CustomerIdentity.channel_user_id.like(like),
                )
            ).distinct()

        if start_date:
            from datetime import datetime
            try:
                start_dt = datetime.fromisoformat(start_date)
                query = query.filter(Coupon.created_at >= start_dt)
            except:
                pass

        if end_date:
            from datetime import datetime, timedelta
            try:
                end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
                query = query.filter(Coupon.created_at < end_dt)
            except:
                pass

        query = query.order_by(Coupon.created_at.desc()).offset(skip).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_issued_coupons(
        self,
        customer_id: int | None = None,
        status: str | None = None,
        source: str | None = None,
        keyword: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        from app.models.customer import Customer
        from app.models.customer_identity import CustomerIdentity
        from sqlalchemy import or_, and_
        
        tenant_id = self.require_tenant_id()

        query = select(func.count(func.distinct(Coupon.id))).select_from(Coupon).filter(Coupon.tenant_id == tenant_id)

        if customer_id:
            query = query.filter(Coupon.customer_id == customer_id)

        if status:
            query = query.filter(Coupon.status == status)

        # if source:
        #     query = query.filter(Coupon.source == source)

        if keyword:
            like = f"%{keyword}%"
            query = query.outerjoin(
                Customer,
                and_(Coupon.customer_id == Customer.id, Customer.tenant_id == tenant_id),
            ).outerjoin(
                CustomerIdentity,
                and_(Coupon.customer_id == CustomerIdentity.customer_id, CustomerIdentity.tenant_id == tenant_id),
            )
            query = query.filter(
                or_(
                    Customer.phone.like(like),
                    Customer.name.like(like),
                    CustomerIdentity.phone.like(like),
                    CustomerIdentity.channel_user_id.like(like),
                )
            )

        if start_date:
            from datetime import datetime
            try:
                start_dt = datetime.fromisoformat(start_date)
                query = query.filter(Coupon.created_at >= start_dt)
            except:
                pass

        if end_date:
            from datetime import datetime, timedelta
            try:
                end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
                query = query.filter(Coupon.created_at < end_dt)
            except:
                pass

        result = await self.db.execute(query)
        return int(result.scalar() or 0)

    async def recall_coupon(self, coupon_id: int, reason: str) -> dict:
        tenant_id = self.require_tenant_id()

        result = await self.db.execute(
            select(Coupon)
            .filter(
                Coupon.id == coupon_id,
                Coupon.tenant_id == tenant_id,
            )
            .with_for_update()
        )

        coupon = result.scalar_one_or_none()

        if not coupon:
            return {
                "success": False,
                "message": "优惠券不存在",
                "coupon": None,
            }

        if coupon.status != "UNUSED":
            return {
                "success": False,
                "message": "只有未使用的券可以收回",
                "coupon": coupon,
            }

        template = await self.get_template(coupon.template_id)

        coupon.status = "REVOKED"
        coupon.revoke_time = datetime.utcnow()
        coupon.revoke_reason = reason

        if template and int(template.used_stock or 0) > 0:
            template.used_stock = int(template.used_stock or 0) - 1

        await self.db.commit()
        await self.db.refresh(coupon)

        return {
            "success": True,
            "message": "优惠券已收回",
            "coupon": coupon,
        }

    async def get_customer_coupon(self, coupon_id: int, customer_id: int) -> Coupon | None:
        tenant_id = self.require_tenant_id()

        result = await self.db.execute(
            select(Coupon).filter(
                Coupon.id == coupon_id,
                Coupon.customer_id == customer_id,
                Coupon.tenant_id == tenant_id,
            )
        )

        return result.scalar_one_or_none()

    async def request_expiry_reminder(self, coupon_id: int, customer_id: int) -> str | None:
        """顾客在支付成功页点了"提醒我别忘了用"之后调用：只做归属校验+标记，真正的
        推送由后台每日循环（_coupon_expiry_reminder_loop）扫描 remind_requested 的券来发。
        返回 None 表示可以标记成功，否则返回具体原因给前端展示。"""
        coupon = await self.get_customer_coupon(coupon_id, customer_id)
        if not coupon:
            return "优惠券不存在"
        if coupon.status != "UNUSED":
            return "这张券已经用掉或失效了"
        if coupon.remind_requested:
            return None
        coupon.remind_requested = True
        await self.db.flush()
        return None

    async def get_coupon_by_code(self, code: str) -> Coupon | None:
        tenant_id = self.require_tenant_id()

        result = await self.db.execute(
            select(Coupon).filter(
                Coupon.code == code,
                Coupon.tenant_id == tenant_id,
            )
        )

        return result.scalar_one_or_none()

    async def get_inactive_customers(self, inactive_days: int, limit: int = 100) -> list:
        from app.models.customer import Customer
        from app.models.member_account import MemberAccount

        tenant_id = self.require_tenant_id()
        cutoff_date = datetime.utcnow() - timedelta(days=inactive_days)

        # "沉睡召回"针对的是"以前来过、现在不来了"的老客，不是"从来没消费过"的新客。
        # 原来这里用 Consumption 表（LEFT JOIN + IS NULL）判断"最近有没有消费"，但
        # Consumption 表只有后台手动录入消费才会写，小程序自助点餐支付成功走的是
        # membership_service.apply_consumption()，只更新 MemberAccount，从来不建
        # Consumption 记录——所以任何一个只走自助下单的顾客，无论下过多少单，在
        # Consumption 表里永远查不到"最近消费"，会被这条批量任务当成沉睡客户，
        # 新客户入会当天就可能连续收到好几张"幸运券"。
        # 换成 MemberAccount.last_consume_time——这是 apply_consumption() 每次
        # 真实消费（不管走自助下单还是后台手动录入）都会更新的字段，才是真正覆盖
        # 主链路的"最近一次消费时间"。last_consume_time 为空说明这个账户从没消费过，
        # 直接排除在外，不当沉睡客户召回。
        result = await self.db.execute(
            select(Customer)
            .join(
                MemberAccount,
                and_(
                    MemberAccount.customer_id == Customer.id,
                    MemberAccount.tenant_id == Customer.tenant_id,
                ),
            )
            .filter(
                Customer.tenant_id == tenant_id,
                Customer.status != -1,
                MemberAccount.last_consume_time.isnot(None),
                MemberAccount.last_consume_time < cutoff_date,
            )
            .limit(limit)
        )

        return list(result.scalars().all())

    async def batch_issue_recall_coupon(self, inactive_days: int = None, limit: int = 100) -> dict:
        rules = await self.get_coupon_rules()
        recall_config = rules.get("recall_coupon", {})

        if not recall_config.get("enabled", False):
            return {"success_count": 0, "fail_count": 0, "reason": "老客召回券未开启", "customers": []}

        if inactive_days is None:
            inactive_days = recall_config.get("inactive_days", 7)

        customers = await self.get_inactive_customers(inactive_days, limit)

        if not customers:
            return {"success_count": 0, "fail_count": 0, "reason": "没有符合条件的沉睡客户", "customers": []}

        # 去重：沉睡客户手上还有没用完的召回券，就先别再发新的。这个批量任务每天跑
        # 一次，客户不来就一直"沉睡"，不去重的话会每天都按当时的实时客单价重新加权
        # 随机算一张新的召回券——跟 consumption_coupon 是同一类问题（见上面
        # issue_auto_coupon 里的去重），这里补齐同样的保护。
        #
        # 这个批量任务除了每天定时跑一次，商家后台还有一个手动触发入口
        # （coupons.py 里调用这个函数的那个 API），两边可能在差不多的时间重叠
        # 执行——所以不能只做一次性检查，要用分布式锁把"筛选名单"到"真正发放"
        # 之间的整段时间锁住，锁一直拿到发放完成才释放（AsyncExitStack），
        # 否则两次重叠的批量执行仍然可能各自筛出同一个客户、各发一张。
        async with AsyncExitStack() as stack:
            eligible_customers = []
            for c in customers:
                should_issue = await stack.enter_async_context(self._dedup_issue_lock(c.id, "recall_coupon"))
                if should_issue:
                    eligible_customers.append(c)

            if not eligible_customers:
                return {"success_count": 0, "fail_count": 0, "reason": "沉睡客户名下都已持有未用的召回券", "customers": []}

            customer_ids = [c.id for c in eligible_customers]

            selected_rule = self.select_weighted_coupon(recall_config)
            amount = selected_rule.get("amount", recall_config.get("amount", 15))
            threshold = selected_rule.get("threshold", recall_config.get("threshold", 50))
            valid_days = selected_rule.get("valid_days", recall_config.get("valid_days", 7))
            template_name = selected_rule.get("name")

            template = await self._get_or_create_auto_coupon_template(
                rule_type="recall_coupon",
                amount=amount,
                threshold=threshold,
                valid_days=valid_days,
                template_name=template_name
            )

            if not template:
                return {"success_count": 0, "fail_count": len(customer_ids), "reason": "建优惠券模失败", "customers": []}

            result = await self.send_coupons_with_result(template.id, customer_ids, source="recall_coupon")

            result["source"] = "recall_coupon"
            result["weighted_coupon"] = {
                "name": template_name,
                "amount": amount,
                "threshold": threshold,
                "valid_days": valid_days,
            }
            result["customers"] = [
                {"id": str(c.id), "name": c.name or "", "phone": c.phone or ""}
                for c in eligible_customers
            ][:result["success_count"]]

            return result


async def _set_order_coupon_status_if_locked(order, db: AsyncSession, status: str) -> None:
    if not getattr(order, "coupon_id", None):
        return
    from app.models.coupon import Coupon

    coupon_result = await db.execute(
        select(Coupon)
        .where(
            Coupon.id == order.coupon_id,
            Coupon.tenant_id == str(order.tenant_id),
        )
        .with_for_update()
    )
    coupon = coupon_result.scalar_one_or_none()
    if coupon and coupon.status == "LOCKED":
        from_status = coupon.status
        coupon.status = status
        reason = "order_redeem" if status == "USED" else "order_release"
        log_coupon_transition(
            coupon_id=coupon.id,
            tenant_id=str(order.tenant_id),
            member_id=getattr(order, "customer_id", None),
            order_id=getattr(order, "id", None),
            from_status=from_status,
            to_status=status,
            reason=reason,
        )


async def _unlock_order_coupon_if_locked(order, db: AsyncSession) -> None:
    await _set_order_coupon_status_if_locked(order, db, "UNUSED")


async def _mark_order_coupon_used_if_locked(order, db: AsyncSession) -> None:
    await _set_order_coupon_status_if_locked(order, db, "USED")
