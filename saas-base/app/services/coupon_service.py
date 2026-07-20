import random
from datetime import datetime, timedelta
from sqlalchemy import func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import settings
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.services.anti_fraud_service import AntiFraudService
from app.utils.id_generator import generate_coupon_code, generate_snowflake_id
from app.core.logger import logger
from app.core.lock import try_acquire_lock

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

    async def get_merchant_aov(self) -> float:
        """计算该商户近30天平均客单价，订单数不足时返回0（调用方兜底）。"""
        from app.core.platform_rules import AOV_LOOKBACK_DAYS, AOV_MIN_ORDERS
        from app.models.order import Order
        tenant_id = self.require_tenant_id()
        cutoff = datetime.utcnow() - timedelta(days=AOV_LOOKBACK_DAYS)
        result = await self.db.execute(
            select(func.avg(Order.total), func.count(Order.id)).where(
                Order.tenant_id == tenant_id,
                Order.created_at >= cutoff,
                Order.status.notin_(["cancelled", "rejected"]),
            )
        )
        row = result.one()
        avg_val, count = row[0], row[1]
        if not count or count < AOV_MIN_ORDERS or not avg_val:
            return 0.0
        return float(avg_val)

    async def get_coupon_rules(self) -> dict:
        from app.core.platform_rules import build_dynamic_rules
        from app.services.tenant_service import TenantService
        tenant_service = TenantService(self.db)
        config = await tenant_service.get_tenant_config(self.tenant_id)
        merchant_rules = (config.coupon_rules or {}) if config else {}
        # 动态则：根据该商户实际客单价生成，新商户用安全兜底值
        aov = await self.get_merchant_aov()
        platform_rules = build_dynamic_rules(aov)
        # 商户在后台显式配置的同名字段优先覆盖动态值
        merged = {}
        for key, platform_rule in platform_rules.items():
            merchant_override = merchant_rules.get(key, {})
            merged[key] = {**platform_rule, **merchant_override}
        for key, rule in merchant_rules.items():
            if key not in merged:
                merged[key] = rule
        return merged

    async def issue_auto_coupon(self, customer_id: int, rule_type: str, consumption_amount: float = None) -> dict:
        rules = await self.get_coupon_rules()
        rule_config = rules.get(rule_type, {})
        
        if not rule_config.get("enabled", False):
            return {"success_count": 0, "reason": "则未开启"}
        
        if rule_type == "consumption_coupon" and consumption_amount is not None:
            trigger_amount = rule_config.get("trigger_amount", 0)
            if float(consumption_amount) < float(trigger_amount):
                return {"success_count": 0, "reason": f"消费金额{consumption_amount}未达触发门槛{trigger_amount}"}
        
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
            template_name=template_name
        )
        
        if not template:
            return {"success_count": 0, "reason": "建优惠券模失败"}
        
        result = await self.send_coupons_with_result(template.id, [customer_id], source=rule_type)
        
        if result["success_count"] > 0:
            coupon_info = result["sent"][0] if result["sent"] else {}
            result["source"] = rule_type
            result["weighted_coupon"] = {
                "name": template_name,
                "amount": amount,
                "threshold": threshold,
                "valid_days": valid_days,
            }
        
        return result

    async def issue_entry_coupon(self, customer_id: int) -> dict | None:
        """进店券：用户扫码进入菜单时静默发放，当日有效，去重（同一天同一租户只发一次）。"""
        rules = await self.get_coupon_rules()
        rule_config = rules.get("entry_coupon", {})
        if not rule_config.get("enabled", False):
            return None

        # 去重：今天是否已持有进店券
        existing = await self.get_available_auto_coupon(customer_id, "entry_coupon")
        if existing:
            from app.models.coupon_template import CouponTemplate as _Tpl
            tpl = await self.db.get(_Tpl, existing.template_id)
            return {
                "coupon_id": str(existing.id),
                "amount": float(tpl.value) if tpl else 0,
                "threshold": float(tpl.min_amount) if tpl else 0,
                "expire_time": existing.expire_time.isoformat() if existing.expire_time else None,
                "is_new": False,
            }

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
                "amount": amount,
                "threshold": threshold,
                "expire_time": sent.get("expire_time").isoformat() if sent.get("expire_time") else None,
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
        template_name: str | None = None
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
        await self.db.commit()
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
        tenant_id = self.require_tenant_id()

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
            )
            if not template:
                logger.error(
                    f"invite_reward: 建模失败 "
                    f"tenant={self.tenant_id} customer={customer_id} amount={amount}"
                )
                return False
            result = await self.send_coupons_with_result(
                template.id, [customer_id], source="invite_reward"
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
        template = await self.get_template(template_id)

        if not template:
            return None

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

    async def send_coupons_with_result(self, template_id, customer_ids, source: str = None) -> dict:
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

        await self.db.commit()

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
        from app.models.consumption import Consumption
        from sqlalchemy import and_, not_

        tenant_id = self.require_tenant_id()
        cutoff_date = datetime.utcnow() - timedelta(days=inactive_days)

        result = await self.db.execute(
            select(Customer)
            .outerjoin(
                Consumption,
                and_(
                    Consumption.customer_id == Customer.id,
                    Consumption.consume_time >= cutoff_date,
                )
            )
            .filter(
                Customer.tenant_id == tenant_id,
                Customer.status != -1,
                Consumption.id.is_(None),
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

        customer_ids = [c.id for c in customers]

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
            for c in customers
        ][:result["success_count"]]

        return result
