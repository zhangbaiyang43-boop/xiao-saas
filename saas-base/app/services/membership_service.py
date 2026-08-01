from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.models.benefit_template import BenefitTemplate
from app.models.customer import Customer
from app.models.member_account import MemberAccount
from app.models.point_ledger import PointLedger
from app.services.base_service import BaseService


LEVELS = [
    {"code": "LV1", "name": "普通会员", "threshold": 0, "point_multiplier": 1.0},
    {"code": "LV2", "name": "银卡会员", "threshold": 299, "point_multiplier": 1.2},
    {"code": "LV3", "name": "金卡会员", "threshold": 999, "point_multiplier": 1.5},
]

POINT_RULES = {
    "consumption": {"points_per_yuan": 1, "expire_days": 365},
    "store_checkin": {"points": 5, "expire_days": 365},
    "douyin_follow": {"points": 10, "expire_days": 365},
    "share_friend": {"points": 10, "expire_days": 365},
    "register": {"points": 20, "expire_days": 365},
}

POINT_REDEEM_RULE = {
    "points_per_yuan": 100,
    "max_order_discount_rate": 0.3,
    "exclusive_coupon_stack": False,
}

# 积分兑换走"方案C"：不建自由兑换商城（结账时顾客自己选花多少积分抵多少钱，
# 需要商家/店员多一层核销判断），改成攒够固定门槛就自动换一张现成的自动券
# （platform_rules.py 里的 points_reward_coupon），复用 issue_auto_coupon 已有的
# 去重、模板、安全上限这套机制。上面的 POINT_REDEEM_RULE 是更早以前设计的另一套
# "按比例自由兑换"方案，从来没有接口真正执行过，跟这里是两套不同的机制，别混着看。
POINTS_REWARD_THRESHOLD = 1000

DEFAULT_BENEFITS = [
    {"level_code": "LV1", "name": "新人券", "type": "coupon", "value": 10, "condition": "新人可用", "channel": "ALL", "cycle": "once"},
    {"level_code": "LV2", "name": "成长券", "type": "coupon", "value": 20, "condition": "每月1张", "channel": "ALL", "cycle": "monthly"},
    {"level_code": "LV2", "name": "积分加速", "type": "points_multiplier", "value": 1.2, "condition": "消费积分1.2倍", "channel": "ALL", "cycle": None},
    {"level_code": "LV3", "name": "VIP券", "type": "coupon", "value": 50, "condition": "每月1张", "channel": "ALL", "cycle": "monthly"},
    {"level_code": "LV3", "name": "积分加速", "type": "points_multiplier", "value": 1.5, "condition": "消费积分1.5倍", "channel": "ALL", "cycle": None},
    {"level_code": "LV3", "name": "生日礼包", "type": "gift", "value": 0, "condition": "生日月可用", "channel": "ALL", "cycle": "yearly"},
]


class MembershipService(BaseService):
    def get_config(self) -> dict:
        return {
            "principles": {
                "member_id_source": "phone_or_unionid",
                "single_points_account": True,
                "single_level_system": True,
                "unified_benefit_pool": True,
                "channels_are_entries": ["douyin", "wechat", "store"],
            },
            "levels": LEVELS,
            "points": {
                "earn": POINT_RULES,
                "redeem": POINT_REDEEM_RULE,
            },
            "quick_upgrade": {
                "register_days": 7,
                "target_amount": 299,
                "target_level": "LV2",
            },
            "downgrade": {
                "period_days": 365,
                "rule": "连续365天未达当前等级消费则降级",
            },
        }

    def resolve_level(self, yearly_amount: Decimal, created_at: datetime = None, now: datetime = None) -> dict:
        now = now or datetime.utcnow()
        level = LEVELS[0]
        for item in LEVELS:
            if yearly_amount >= Decimal(str(item["threshold"])):
                level = item

        if created_at and now - created_at <= timedelta(days=7) and yearly_amount >= Decimal("299"):
            quick_level = next(item for item in LEVELS if item["code"] == "LV2")
            # P0 修复：快速升级规则只能当"至少给到 LV2"的下限用，不能覆盖掉按
            # 消费额已经算出来的更高等级——原来的写法会把新客户第一周消费满
            # 999（本该是 LV3）的人强行降级成 LV2，少享受权益、少算积分倍率。
            if LEVELS.index(quick_level) > LEVELS.index(level):
                level = quick_level

        return level

    async def ensure_account(self, customer: Customer) -> MemberAccount:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(MemberAccount).filter(
                MemberAccount.tenant_id == tenant_id,
                MemberAccount.customer_id == customer.id,
            )
        )
        account = result.scalar_one_or_none()
        if account:
            return account

        member_id = customer.phone or customer.openid or str(customer.id)
        account = MemberAccount(
            tenant_id=tenant_id,
            customer_id=customer.id,
            member_id=member_id,
            level_code="LV1",
            level_name="普通会员",
            total_consumption=Decimal("0"),
            yearly_consumption=Decimal("0"),
            points_balance=0,
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        await self.add_points(account, "register", POINT_RULES["register"]["points"], "ALL", remark="首次注册")
        return account

    async def add_points(
        self,
        account: MemberAccount,
        event_type: str,
        points: int,
        source_channel: str = "STORE",
        ref_id: str = None,
        remark: str = None,
    ) -> PointLedger:
        tenant_id = self.require_tenant_id()
        balance_before = int(account.points_balance or 0)
        # P0 修复：原来是在内存里读出 points_balance 再加再存回去（丢失更新）。
        # 同一个顾客两笔订单几乎同时支付成功时，后提交的一次会覆盖掉前一次的
        # 积分变动。改成数据库原子自增，跟 apply_consumption 里
        # total_consumption/yearly_consumption 的做法保持一致，不依赖内存旧值。
        account.points_balance = MemberAccount.points_balance + int(points)
        await self.db.flush()
        await self.db.refresh(account)

        expire_at = datetime.utcnow() + timedelta(days=POINT_RULES.get(event_type, {}).get("expire_days", 365))
        ledger = PointLedger(
            tenant_id=tenant_id,
            customer_id=account.customer_id,
            member_id=account.member_id,
            event_type=event_type,
            points=int(points),
            balance_after=account.points_balance,
            source_channel=source_channel,
            ref_id=ref_id,
            expire_at=expire_at,
            remark=remark,
        )
        self.db.add(ledger)
        await self.db.commit()
        await self.db.refresh(account)
        await self.db.refresh(ledger)

        # 积分兑换（方案C）：加完积分之后顺手判断一下是不是攒够门槛了，够了就自动
        # 换一张券。放在 add_points 里而不是 apply_consumption 里，是因为 add_points
        # 是所有加积分场景（消费、签到、分享……）共用的唯一入口，不管以后从哪个渠道
        # 加的积分，都会经过这里，不用每个加积分的地方都单独补一遍判断。
        await self._maybe_reward_points_milestone(account, balance_before)
        return ledger

    async def _maybe_reward_points_milestone(self, account: MemberAccount, balance_before: int) -> dict | None:
        """攒够 POINTS_REWARD_THRESHOLD 积分自动换一张券——复用 CouponService 现成的
        自动发券引擎（去重、模板、cap_discount_amount 安全上限全部照用），不新建
        一套独立的积分商城。

        用"跨过了几个门槛"而不是"余额是否 >= 门槛"来判断，这样一次性加入大量积分
        （比如后台手动调整、活动加倍）跨过多个门槛时不会漏发；发出几张就扣掉对应
        倍数的积分，没发出去的（比如手上还有未用的同类券，被 issue_auto_coupon
        内置的去重挡住）不扣分，留着等那张用掉后下次再重新判断。

        任何异常都不能影响积分本身已经加成功这个事实——失败了只是这一次没换成
        券，积分还在，下次加积分时余额还是够门槛，会重新尝试。
        """
        balance_after = int(account.points_balance or 0)
        crossed = balance_after // POINTS_REWARD_THRESHOLD - balance_before // POINTS_REWARD_THRESHOLD
        if crossed <= 0:
            return None

        from app.core.logger import logger
        from app.services.coupon_service import CouponService

        coupon_data = None
        issued_count = 0
        try:
            coupon_svc = CouponService(self.db)
            coupon_svc.set_tenant_id(self.require_tenant_id())
            for _ in range(crossed):
                issue_result = await coupon_svc.issue_auto_coupon(account.customer_id, "points_reward_coupon")
                if not (issue_result and issue_result.get("success_count", 0) > 0):
                    break
                issued_count += 1
                sent_item = (issue_result.get("sent") or [{}])[0]
                wc = issue_result.get("weighted_coupon") or {}
                coupon_data = {
                    "id": sent_item.get("id"),
                    "name": wc.get("name") or "积分好礼券",
                    "amount": wc.get("amount", 0),
                    "min_amount": wc.get("threshold", 0),
                    "expired_at": sent_item.get("expire_time"),
                }
        except Exception:
            logger.exception(f"积分兑换券发放异常 customer_id={account.customer_id}")

        if issued_count > 0:
            account.points_balance = MemberAccount.points_balance - issued_count * POINTS_REWARD_THRESHOLD
            await self.db.commit()
            await self.db.refresh(account)

        return coupon_data

    async def apply_consumption(self, customer: Customer, amount: float, consumption_id: int = None) -> MemberAccount:
        tenant_id = self.require_tenant_id()
        
        # 使用 SELECT FOR UPDATE 加行锁，防止并发消费导致的积分计算错误
        result = await self.db.execute(
            select(MemberAccount).filter(
                MemberAccount.tenant_id == tenant_id,
                MemberAccount.customer_id == customer.id,
            ).with_for_update()
        )
        account = result.scalar_one_or_none()
        
        if not account:
            account = MemberAccount(
                tenant_id=tenant_id,
                customer_id=customer.id,
                member_id=customer.phone or customer.openid or str(customer.id),
                level_code="LV1",
                level_name="普通会员",
                total_consumption=Decimal("0"),
                yearly_consumption=Decimal("0"),
                points_balance=0,
            )
            self.db.add(account)
            await self.db.flush()
        
        # 记录消费前的年度消费额，用于计算消费前等级
        old_yearly = Decimal(account.yearly_consumption or 0)
        old_level = self.resolve_level(old_yearly, customer.created_at)
        
        consume_amount = Decimal(str(amount or 0))
        # 使用数据库原子更新，避免 Python 层累加导致的丢失更新
        account.total_consumption = MemberAccount.total_consumption + consume_amount
        account.yearly_consumption = MemberAccount.yearly_consumption + consume_amount
        account.last_consume_time = datetime.utcnow()
        
        # 消费后等级基于新的年度消费额计算
        new_yearly = old_yearly + consume_amount
        new_level = self.resolve_level(new_yearly, customer.created_at)
        
        account.level_code = new_level["code"]
        account.level_name = new_level["name"]
        account.level_checked_at = datetime.utcnow()
        
        # 积分计算：消费积分基于当前（消费后）等级的计算倍率
        points = int(consume_amount * Decimal(str(new_level["point_multiplier"])))
        
        await self.db.commit()
        await self.db.refresh(account)
        
        if points > 0:
            await self.add_points(account, "consumption", points, "STORE", ref_id=str(consumption_id or ""), remark="消费积分")
        return account

    async def reverse_consumption(self, customer_id: int, amount: float, consumption_id: int) -> MemberAccount | None:
        """订单退款后回滚 apply_consumption() 记的账：扣回消费额并收回对应积分。

        按 ref_id=str(consumption_id) 定位这一单当时实际记的积分流水来确定要收回
        多少积分，不按当前等级倍率重新算一遍——等级在这期间可能已经变化，重新算
        会扣多或扣少。
        """
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(MemberAccount).filter(
                MemberAccount.tenant_id == tenant_id,
                MemberAccount.customer_id == customer_id,
            ).with_for_update()
        )
        account = result.scalar_one_or_none()
        if not account:
            return None

        # 幂等保护：同一笔消费的退款回滚只应该生效一次。之前完全没有这层检查——调用方
        # 标记"这单已经退款过"的落库时机比这个函数内部提交要晚，中间这段窗口如果进程
        # 崩溃/请求超时后客户端重试了取消/拒单，已经提交的扣款不会跟着回滚，重放会把
        # 消费额和积分再扣一次。检查放在拿到账户行锁之后，跟并发的同一笔重放请求正确
        # 串行；下面固定写一条 refund_reversal 流水当"已处理"标记，即使这笔消费当初
        # 一分积分没赚到也写（不然 0 积分的消费永远没有标记可查，一样会被重放扣消费额）。
        existing_reversal = await self.db.execute(
            select(PointLedger.id).filter(
                PointLedger.tenant_id == tenant_id,
                PointLedger.customer_id == customer_id,
                PointLedger.event_type == "refund_reversal",
                PointLedger.ref_id == str(consumption_id or ""),
            )
        )
        if existing_reversal.scalar_one_or_none():
            return account

        ledger_result = await self.db.execute(
            select(func.coalesce(func.sum(PointLedger.points), 0)).filter(
                PointLedger.tenant_id == tenant_id,
                PointLedger.customer_id == customer_id,
                PointLedger.event_type == "consumption",
                PointLedger.ref_id == str(consumption_id or ""),
            )
        )
        earned_points = int(ledger_result.scalar() or 0)
        # 这笔消费当初记的积分，可能已经被"满额自动兑券"提前花掉了（见
        # _maybe_reward_points_milestone）——退款时不能无条件倒扣当初赚了多少，只能扣
        # 回账户里实际还剩的部分，否则 points_balance 会被扣成负数。
        points_to_deduct = min(earned_points, int(account.points_balance or 0)) if earned_points > 0 else 0

        consume_amount = Decimal(str(amount or 0))
        account.total_consumption = MemberAccount.total_consumption - consume_amount
        account.yearly_consumption = MemberAccount.yearly_consumption - consume_amount
        if points_to_deduct:
            account.points_balance = MemberAccount.points_balance - points_to_deduct
        await self.db.commit()
        await self.db.refresh(account)

        customer_result = await self.db.execute(
            select(Customer).filter(Customer.id == customer_id, Customer.tenant_id == tenant_id)
        )
        customer = customer_result.scalar_one_or_none()
        new_level = self.resolve_level(Decimal(account.yearly_consumption or 0), customer.created_at if customer else None)
        account.level_code = new_level["code"]
        account.level_name = new_level["name"]
        account.level_checked_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(account)

        remark = "订单退款收回积分"
        if 0 < points_to_deduct < earned_points:
            remark = "订单退款收回积分（部分已被自动兑券消耗，仅收回剩余部分）"
        ledger = PointLedger(
            tenant_id=tenant_id,
            customer_id=account.customer_id,
            member_id=account.member_id,
            event_type="refund_reversal",
            points=-points_to_deduct,
            balance_after=account.points_balance,
            source_channel="STORE",
            ref_id=str(consumption_id or ""),
            expire_at=datetime.utcnow(),
            remark=remark,
        )
        self.db.add(ledger)
        await self.db.commit()

        return account

    async def get_account_by_customer(self, customer_id: int) -> MemberAccount:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(MemberAccount).filter(
                MemberAccount.tenant_id == tenant_id,
                MemberAccount.customer_id == customer_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create_account(self, customer_id: int) -> MemberAccount:
        """按 customer_id 获取会员账户，不存在则自动建（BUG-A 修复）。"""
        account = await self.get_account_by_customer(customer_id)
        if not account:
            from app.services.customer_service import CustomerService
            customer = await CustomerService(self.db).get_customer(customer_id)
            if customer:
                account = await self.ensure_account(customer)
        return account

    async def list_point_ledger(self, customer_id: int, limit: int = 50) -> list:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(PointLedger)
            .filter(PointLedger.tenant_id == tenant_id, PointLedger.customer_id == customer_id)
            .order_by(PointLedger.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def ensure_default_benefits(self) -> list:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(select(BenefitTemplate).filter(BenefitTemplate.tenant_id == tenant_id))
        existing = result.scalars().all()
        if existing:
            return existing

        benefits = []
        for item in DEFAULT_BENEFITS:
            benefit = BenefitTemplate(
                tenant_id=tenant_id,
                name=item["name"],
                level_code=item["level_code"],
                type=item["type"],
                value=item["value"],
                condition=item["condition"],
                channel=item["channel"],
                cycle=item["cycle"],
                config={"standard": True},
                status=1,
            )
            self.db.add(benefit)
            benefits.append(benefit)
        await self.db.commit()
        for benefit in benefits:
            await self.db.refresh(benefit)
        return benefits

    async def list_benefits(self) -> list:
        await self.ensure_default_benefits()
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(BenefitTemplate)
            .filter(BenefitTemplate.tenant_id == tenant_id, BenefitTemplate.status == 1)
            .order_by(BenefitTemplate.level_code.asc(), BenefitTemplate.id.asc())
        )
        return result.scalars().all()
