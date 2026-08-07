from sqlalchemy import func, select
from datetime import datetime, timedelta

from app.models.commission_record import CommissionRecord
from app.models.consumption import Consumption
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.models.dining import DiningSession
from app.models.order import Order, OrderItem
from app.models.point_ledger import PointLedger
from app.services.base_service import BaseService

# 同一桌同一天出现这么多个"首单新客"，就值得商家点开看一眼是不是真的一桌坐了
# 这么多人——不是硬性拦截线，只是给人工核实用的提示阈值，正常大桌聚餐很容易
# 超过，不代表一定有问题。
TABLE_NEW_CUSTOMER_ALERT_THRESHOLD = 4

MARKETING_RULE_ORDER = [
    "entry_coupon",
    "consumption_coupon",
    "new_customer_coupon",
    "recall_coupon",
    "points_reward_coupon",
    "invite_reward",
    "staff_referral",
]

MARKETING_RULE_LABELS = {
    "entry_coupon": "进店券",
    "consumption_coupon": "复购券",
    "new_customer_coupon": "新客券",
    "recall_coupon": "召回券",
    "points_reward_coupon": "积分兑券",
    "invite_reward": "老带新",
    "staff_referral": "员工推荐",
}

COUPON_MARKETING_RULE_TYPES = {
    "entry_coupon",
    "consumption_coupon",
    "new_customer_coupon",
    "recall_coupon",
    "points_reward_coupon",
    "invite_reward",
}


class StatisticsService(BaseService):
    async def _second_order_conversion(self, tenant_id: str, window_days: int = 30) -> dict:
        """首单→二单转化率：新客最该被盯的一个指标，比注册数、领券数都更能反映
        "菜品/价格/门店是不是真的留得住人"。

        队列口径：只统计"首单发生在 [cohort_start, cohort_end) 区间"的顾客，cohort_end
        往前留出整整 window_days 天缓冲——不这么做的话，最近几天才首单、还没到期的
        新顾客会被错误地当成"没转化"，拉低数字，其实他们只是还没到时间。
        """
        now = datetime.utcnow()
        result = await self.db.execute(
            select(Order.customer_id, Order.created_at)
            .where(
                Order.tenant_id == tenant_id,
                Order.payment_status == "paid",
                Order.customer_id.isnot(None),
            )
            .order_by(Order.customer_id, Order.created_at)
        )
        rows = result.all()

        orders_by_customer: dict = {}
        for customer_id, created_at in rows:
            orders_by_customer.setdefault(customer_id, []).append(created_at)

        cohort_end = now - timedelta(days=window_days)
        cohort_start = cohort_end - timedelta(days=window_days)

        cohort_size = 0
        converted_count = 0
        for timestamps in orders_by_customer.values():
            first_at = timestamps[0]  # 已按 created_at 升序排列，第一条就是该顾客真正的首单
            if not (cohort_start <= first_at < cohort_end):
                continue
            cohort_size += 1
            deadline = first_at + timedelta(days=window_days)
            if any(first_at < ts <= deadline for ts in timestamps[1:]):
                converted_count += 1

        rate = round(converted_count / cohort_size, 4) if cohort_size else None
        return {
            "cohort_size": cohort_size,
            "converted_count": converted_count,
            "rate": rate,
            "window_days": window_days,
        }

    async def table_coupon_activity(self, day: datetime | None = None) -> dict:
        """按桌统计当天有多少个"首单新客"扎堆在同一桌——不是硬性拦截，只是给人工核实
        用的可观测数据（拆单薅券这类问题很难靠规则精确识别，容易误伤正常大桌聚餐，
        所以选择"观察 + 人工介入"而不是自动拦截）。

        口径：一个客户名下所有已支付订单里，created_at 最早的那一条如果就是今天这一条，
        就算"今天在这一桌完成了首单"——跟 orders.py _on_payment_success 里判断
        is_new_customer 是同一套口径，保证这里统计出来的"新客"跟实际发首单/进店券的
        客户是同一批人。
        """
        tenant_id = self.require_tenant_id()
        target_day = (day or datetime.utcnow())
        day_start = target_day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        rows = (await self.db.execute(
            select(Order.dining_session_id, Order.customer_id, Order.created_at)
            .where(
                Order.tenant_id == tenant_id,
                Order.payment_status == "paid",
                Order.dining_session_id.isnot(None),
                Order.customer_id.isnot(None),
                Order.created_at >= day_start,
                Order.created_at < day_end,
            )
        )).all()

        if not rows:
            return {"date": day_start.date().isoformat(), "threshold": TABLE_NEW_CUSTOMER_ALERT_THRESHOLD, "tables": []}

        customer_ids = {r.customer_id for r in rows}
        first_paid_rows = (await self.db.execute(
            select(Order.customer_id, func.min(Order.created_at))
            .where(
                Order.tenant_id == tenant_id,
                Order.payment_status == "paid",
                Order.customer_id.in_(customer_ids),
            )
            .group_by(Order.customer_id)
        )).all()
        first_paid_at = {customer_id: first_at for customer_id, first_at in first_paid_rows}

        sessions: dict = {}
        for r in rows:
            bucket = sessions.setdefault(r.dining_session_id, {"orders": 0, "customers": set(), "new_customers": set()})
            bucket["orders"] += 1
            bucket["customers"].add(r.customer_id)
            if first_paid_at.get(r.customer_id) == r.created_at:
                bucket["new_customers"].add(r.customer_id)

        table_no_rows = (await self.db.execute(
            select(DiningSession.id, DiningSession.table_no).where(DiningSession.id.in_(sessions.keys()))
        )).all()
        table_no_map = {sid: table_no for sid, table_no in table_no_rows}

        tables = [
            {
                "dining_session_id": str(sid),
                "table_no": table_no_map.get(sid, ""),
                "order_count": bucket["orders"],
                "customer_count": len(bucket["customers"]),
                "new_customer_count": len(bucket["new_customers"]),
                "flagged": len(bucket["new_customers"]) >= TABLE_NEW_CUSTOMER_ALERT_THRESHOLD,
            }
            for sid, bucket in sessions.items()
        ]
        tables.sort(key=lambda t: t["new_customer_count"], reverse=True)

        return {"date": day_start.date().isoformat(), "threshold": TABLE_NEW_CUSTOMER_ALERT_THRESHOLD, "tables": tables}

    async def dashboard(self) -> dict:
        tenant_id = self.require_tenant_id()
        
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # 今日消费金额
        today_consumption = await self.db.scalar(
            select(func.coalesce(func.sum(Consumption.amount), 0))
            .filter(
                Consumption.tenant_id == tenant_id,
                Consumption.created_at >= today_start
            )
        )
        
        # 今日新增会员
        today_new_members = await self.db.scalar(
            select(func.count()).select_from(Customer)
            .filter(
                Customer.tenant_id == tenant_id,
                Customer.created_at >= today_start
            )
        )
        
        # 今日核销数（已使用的优惠券）
        today_redeem_count = await self.db.scalar(
            select(func.count()).select_from(Coupon)
            .filter(
                Coupon.tenant_id == tenant_id,
                Coupon.status == "USED",
                Coupon.updated_at >= today_start
            )
        )
        
        # 本月新增会员
        month_new_members = await self.db.scalar(
            select(func.count()).select_from(Customer)
            .filter(
                Customer.tenant_id == tenant_id,
                Customer.created_at >= month_start
            )
        )
        
        # 本月发放优惠券
        month_coupon_send = await self.db.scalar(
            select(func.count()).select_from(Coupon)
            .filter(
                Coupon.tenant_id == tenant_id,
                Coupon.created_at >= month_start
            )
        )
        
        # 本月核销优惠券
        month_coupon_redeem = await self.db.scalar(
            select(func.count()).select_from(Coupon)
            .filter(
                Coupon.tenant_id == tenant_id,
                Coupon.status == "USED",
                Coupon.updated_at >= month_start
            )
        )

        week_start = now - timedelta(days=7)
        recent_customer_rows = (await self.db.execute(
            select(Order.customer_id)
            .where(
                Order.tenant_id == tenant_id,
                Order.payment_status == "paid",
                Order.customer_id.isnot(None),
                Order.created_at >= week_start,
            )
            .distinct()
        )).all()
        recent_customer_ids = [row[0] for row in recent_customer_rows]
        if recent_customer_ids:
            first_paid_rows = (await self.db.execute(
                select(Order.customer_id, func.min(Order.created_at))
                .where(
                    Order.tenant_id == tenant_id,
                    Order.payment_status == "paid",
                    Order.customer_id.in_(recent_customer_ids),
                )
                .group_by(Order.customer_id)
            )).all()
            repeat_customers_7d = sum(
                1 for _, first_at in first_paid_rows if first_at < week_start
            )
        else:
            repeat_customers_7d = 0

        points_issued_month = int(await self.db.scalar(
            select(func.coalesce(func.sum(PointLedger.points), 0))
            .where(
                PointLedger.tenant_id == tenant_id,
                PointLedger.points > 0,
                PointLedger.created_at >= month_start,
            )
        ) or 0)

        points_redeemed_coupons_month = int(await self.db.scalar(
            select(func.count(Coupon.id))
            .join(CouponTemplate, CouponTemplate.id == Coupon.template_id)
            .where(
                Coupon.tenant_id == tenant_id,
                CouponTemplate.description == "points_reward_coupon",
                Coupon.created_at >= month_start,
            )
        ) or 0)

        return {
            "today_consumption": float(today_consumption or 0),
            "today_new_members": int(today_new_members or 0),
            "today_redeem_count": int(today_redeem_count or 0),
            "month_new_members": int(month_new_members or 0),
            "month_coupon_send": int(month_coupon_send or 0),
            "month_coupon_redeem": int(month_coupon_redeem or 0),
            # 保留原字段以确保兼容性
            "customer_count": int(await self.db.scalar(
                select(func.count()).select_from(Customer).filter(Customer.tenant_id == tenant_id)
            ) or 0),
            "coupon_template_count": int(await self.db.scalar(
                select(func.count()).select_from(CouponTemplate).filter(CouponTemplate.tenant_id == tenant_id)
            ) or 0),
            "unused_coupon_count": int(await self.db.scalar(
                select(func.count()).select_from(Coupon).filter(
                    Coupon.tenant_id == tenant_id,
                    Coupon.status == "UNUSED",
                )
            ) or 0),
            "used_coupon_count": int(await self.db.scalar(
                select(func.count()).select_from(Coupon).filter(
                    Coupon.tenant_id == tenant_id,
                    Coupon.status == "USED",
                )
            ) or 0),
            "consumption_amount": float(await self.db.scalar(
                select(func.coalesce(func.sum(Consumption.amount), 0)).filter(Consumption.tenant_id == tenant_id)
            ) or 0),
            "repeat_customers_7d": int(repeat_customers_7d),
            "points_issued_month": points_issued_month,
            "points_redeemed_coupons_month": points_redeemed_coupons_month,
            "second_order_conversion": await self._second_order_conversion(tenant_id),
        }

    async def order_overview(self) -> dict:
        """真正基于订单表的营业概况：今日/昨日订单数与营业额对比、客单价、近7天
        趋势、近7天热销榜。

        用 payment_status == 'paid' 判定"钱真的到账了"，不用订单的业务状态
        （pending/preparing/done/settled）——那个字段在三种收款模式下含义不一样，
        postpay/table_account 建单时永远是 unpaid，只有 payment_status 是三种
        模式通用的"钱有没有真的收到"的判断依据。之前后台首页的"今日营收"是前端
        自己拿业务状态瞎判断算出来的，取消/拒单的订单会被误计入营业额，结账后
        （settled）的订单反而被漏算，这里重新按 payment_status 算一遍替换掉它。
        """
        tenant_id = self.require_tenant_id()

        # 跟 orders.py::list_orders 的"today"口径保持一致，用 UTC+8 本地日界
        utc8_now = datetime.utcnow() + timedelta(hours=8)
        today_local = utc8_now.date()

        def day_range_utc(d):
            start_utc = datetime(d.year, d.month, d.day) - timedelta(hours=8)
            return start_utc, start_utc + timedelta(hours=24)

        async def order_count(start, end, paid_only=False):
            conditions = [
                Order.tenant_id == tenant_id,
                Order.created_at >= start,
                Order.created_at < end,
                Order.status.notin_(["cancelled", "rejected"]),
            ]
            if paid_only:
                conditions.append(Order.payment_status == "paid")
            return int(await self.db.scalar(select(func.count(Order.id)).where(*conditions)) or 0)

        async def revenue(start, end):
            return float(await self.db.scalar(
                select(func.coalesce(func.sum(Order.total), 0)).where(
                    Order.tenant_id == tenant_id,
                    Order.payment_status == "paid",
                    Order.created_at >= start,
                    Order.created_at < end,
                )
            ) or 0)

        def pct_change(curr, prev):
            # 昨天是 0 的话算百分比没有意义（除零/无穷大），交给前端显示"—"
            if prev <= 0:
                return None
            return round((curr - prev) / prev * 100, 1)

        today_start, today_end = day_range_utc(today_local)
        yesterday_start, yesterday_end = day_range_utc(today_local - timedelta(days=1))

        today_order_count = await order_count(today_start, today_end)
        today_paid_count = await order_count(today_start, today_end, paid_only=True)
        today_revenue = await revenue(today_start, today_end)
        yesterday_order_count = await order_count(yesterday_start, yesterday_end)
        yesterday_revenue = await revenue(yesterday_start, yesterday_end)
        today_aov = round(today_revenue / today_paid_count, 2) if today_paid_count else 0.0

        trend_7d = []
        for offset in range(6, -1, -1):
            d = today_local - timedelta(days=offset)
            start, end = day_range_utc(d)
            trend_7d.append({"date": d.isoformat(), "revenue": await revenue(start, end)})

        week_start, _ = day_range_utc(today_local - timedelta(days=6))
        dish_result = await self.db.execute(
            select(OrderItem.name, func.sum(OrderItem.qty))
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                Order.tenant_id == tenant_id,
                Order.payment_status == "paid",
                Order.created_at >= week_start,
            )
            .group_by(OrderItem.name)
            .order_by(func.sum(OrderItem.qty).desc())
            .limit(5)
        )
        top_dishes_7d = [{"name": name, "qty": int(qty or 0)} for name, qty in dish_result.all()]

        return {
            "today_order_count": today_order_count,
            "today_revenue": today_revenue,
            "today_aov": today_aov,
            "yesterday_order_count": yesterday_order_count,
            "yesterday_revenue": yesterday_revenue,
            "order_count_change_pct": pct_change(today_order_count, yesterday_order_count),
            "revenue_change_pct": pct_change(today_revenue, yesterday_revenue),
            "trend_7d": trend_7d,
            "top_dishes_7d": top_dishes_7d,
        }

    async def _coupon_rule_window_stats(
        self,
        tenant_id: str,
        rule_type: str,
        start: datetime,
        end: datetime,
    ) -> tuple[int, float | None, float]:
        coupon_filters = [
            Coupon.tenant_id == tenant_id,
            CouponTemplate.tenant_id == tenant_id,
            CouponTemplate.description == rule_type,
            Coupon.created_at >= start,
            Coupon.created_at < end,
        ]
        issued_count = int(await self.db.scalar(
            select(func.count(Coupon.id))
            .join(CouponTemplate, CouponTemplate.id == Coupon.template_id)
            .where(*coupon_filters)
        ) or 0)
        redeemed_count = int(await self.db.scalar(
            select(func.count(Coupon.id))
            .join(CouponTemplate, CouponTemplate.id == Coupon.template_id)
            .where(*coupon_filters, Coupon.status == "USED")
        ) or 0)
        redemption_rate = round(redeemed_count / issued_count, 4) if issued_count > 0 else None
        gmv = float(await self.db.scalar(
            select(func.coalesce(func.sum(Order.total), 0))
            .select_from(Order)
            .join(Coupon, Order.coupon_id == Coupon.id)
            .join(CouponTemplate, Coupon.template_id == CouponTemplate.id)
            .where(
                Order.tenant_id == tenant_id,
                Order.payment_status == "paid",
                *coupon_filters,
            )
        ) or 0)
        return issued_count, redemption_rate, gmv

    async def _referral_headcount(
        self,
        tenant_id: str,
        inviter_type: str,
        start: datetime,
        end: datetime,
    ) -> int:
        return int(await self.db.scalar(
            select(func.count(Customer.id)).where(
                Customer.tenant_id == tenant_id,
                Customer.inviter_type == inviter_type,
                Customer.created_at >= start,
                Customer.created_at < end,
            )
        ) or 0)

    async def _referral_invitee_gmv(
        self,
        tenant_id: str,
        inviter_type: str,
        start: datetime,
        end: datetime,
    ) -> float:
        invitee_ids_result = await self.db.execute(
            select(Customer.id).where(
                Customer.tenant_id == tenant_id,
                Customer.inviter_type == inviter_type,
                Customer.created_at >= start,
                Customer.created_at < end,
            )
        )
        invitee_ids = [row[0] for row in invitee_ids_result.all()]
        if not invitee_ids:
            return 0.0
        return float(await self.db.scalar(
            select(func.coalesce(func.sum(Order.total), 0)).where(
                Order.tenant_id == tenant_id,
                Order.payment_status == "paid",
                Order.customer_id.in_(invitee_ids),
                Order.created_at >= start,
                Order.created_at < end,
            )
        ) or 0)

    async def _staff_commission_window_stats(
        self,
        tenant_id: str,
        start: datetime,
        end: datetime,
    ) -> tuple[int, float | None]:
        base_filters = [
            CommissionRecord.tenant_id == tenant_id,
            CommissionRecord.receiver_type == "staff",
            CommissionRecord.source_type == "FIRST_VERIFY",
            CommissionRecord.level == 1,
            CommissionRecord.created_at >= start,
            CommissionRecord.created_at < end,
        ]
        issued_count = int(await self.db.scalar(
            select(func.count(CommissionRecord.id)).where(*base_filters)
        ) or 0)
        settled_count = int(await self.db.scalar(
            select(func.count(CommissionRecord.id)).where(
                *base_filters,
                CommissionRecord.status == "SETTLED",
            )
        ) or 0)
        redemption_rate = round(settled_count / issued_count, 4) if issued_count > 0 else None
        return issued_count, redemption_rate

    async def marketing_effectiveness(self, start: datetime, end: datetime) -> list[dict]:
        tenant_id = self.require_tenant_id()
        rows: list[dict] = []

        for rule_type in MARKETING_RULE_ORDER:
            if rule_type in COUPON_MARKETING_RULE_TYPES:
                issued_count, redemption_rate, gmv = await self._coupon_rule_window_stats(
                    tenant_id, rule_type, start, end
                )
                referral_headcount = None
                if rule_type == "invite_reward":
                    referral_headcount = await self._referral_headcount(
                        tenant_id, "customer", start, end
                    )
                    gmv = await self._referral_invitee_gmv(tenant_id, "customer", start, end)
                rows.append({
                    "rule_type": rule_type,
                    "label": MARKETING_RULE_LABELS[rule_type],
                    "metric_kind": "coupon",
                    "issued_count": issued_count,
                    "redemption_rate": redemption_rate,
                    "gmv": round(gmv, 2),
                    "referral_headcount": referral_headcount,
                })
                continue

            issued_count, redemption_rate = await self._staff_commission_window_stats(
                tenant_id, start, end
            )
            referral_headcount = await self._referral_headcount(tenant_id, "staff", start, end)
            gmv = await self._referral_invitee_gmv(tenant_id, "staff", start, end)
            rows.append({
                "rule_type": rule_type,
                "label": MARKETING_RULE_LABELS[rule_type],
                "metric_kind": "commission",
                "issued_count": issued_count,
                "redemption_rate": redemption_rate,
                "gmv": round(gmv, 2),
                "referral_headcount": referral_headcount,
            })

        return rows
