from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.models.benefit_template import BenefitTemplate
from app.models.customer import Customer
from app.models.member_account import MemberAccount
from app.models.point_ledger import PointLedger
from app.services.base_service import BaseService


LEVELS = [
    {"code": "LV1", "name": "普通会员", "threshold": 0, "point_multiplier": 1.0},
    {"code": "LV2", "name": "成长会员", "threshold": 299, "point_multiplier": 1.2},
    {"code": "LV3", "name": "VIP会员", "threshold": 999, "point_multiplier": 1.5},
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
            level = next(item for item in LEVELS if item["code"] == "LV2")

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
        account.points_balance = int(account.points_balance or 0) + int(points)
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
        return ledger

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
