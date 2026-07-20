"""营销模定时任务服务"""
from datetime import datetime, timedelta
from sqlalchemy import select, and_, func
from app.models.marketing_template import MerchantTemplateRule, MerchantTemplate
from app.models.coupon import Coupon
from app.models.customer import Customer


class MarketingSchedulerService:
    def __init__(self, db):
        self.db = db

    async def process_recall_rules(self):
        """处理召回则（每天凌晨执行）"""
        now = datetime.now()
        
        # 获取所有启用的召回则
        result = await self.db.execute(
            select(MerchantTemplateRule)
            .join(MerchantTemplate, and_(
                MerchantTemplate.id == MerchantTemplateRule.merchant_template_id,
                MerchantTemplate.status == 1
            ))
            .filter(and_(
                MerchantTemplateRule.trigger_type == 'no_verify_after_days',
                MerchantTemplateRule.status == 1,
                MerchantTemplateRule.trigger_delay_days > 0
            ))
        )
        rules = result.scalars().all()

        for rule in rules:
            await self._process_single_recall_rule(rule, now)

        await self.db.commit()

    async def _process_single_recall_rule(self, rule, now):
        """处理单个召回则"""
        tenant_id = rule.tenant_id
        delay_days = rule.trigger_delay_days
        
        # 查询该租户下所有会员
        customers = await self.db.execute(
            select(Customer).filter(Customer.tenant_id == tenant_id)
        )
        
        for customer in customers.scalars().all():
            # 检查会员是否需要召回
            if await self._should_recall_customer(tenant_id, customer.id, delay_days, now):
                # 检查是否已发放该召回券
                if not await self._has_recall_coupon(tenant_id, customer.id, rule.rule_code):
                    # 发放召回券
                    await self._issue_recall_coupon(tenant_id, customer.id, rule)

    async def _should_recall_customer(self, tenant_id, customer_id, delay_days, now):
        """判断会员是否需要召回（最近核销时间超过delay_days天）"""
        # 查询会员最近的核销时间
        result = await self.db.execute(
            select(func.max(Coupon.use_time))
            .filter(and_(
                Coupon.tenant_id == tenant_id,
                Coupon.customer_id == customer_id,
                Coupon.status == 'USED'
            ))
        )
        last_verify_time = result.scalar_one_or_none()
        
        if not last_verify_time:
            # 从未核销过，不需要召回
            return False
        
        cutoff_time = now - timedelta(days=delay_days)
        return last_verify_time < cutoff_time

    async def _has_recall_coupon(self, tenant_id, customer_id, rule_code):
        """检查会员是否已拥有该召回券"""
        # 查询商家模则
        result = await self.db.execute(
            select(MerchantTemplateRule)
            .join(MerchantTemplate, and_(
                MerchantTemplate.id == MerchantTemplateRule.merchant_template_id,
                MerchantTemplate.status == 1
            ))
            .filter(and_(
                MerchantTemplateRule.tenant_id == tenant_id,
                MerchantTemplateRule.rule_code == rule_code,
                MerchantTemplateRule.status == 1
            ))
        )
        rule = result.scalars().first()
        
        if not rule:
            return False

        # 检查用户是否已有该优惠券且未过期
        result = await self.db.execute(
            select(Coupon)
            .filter(and_(
                Coupon.tenant_id == tenant_id,
                Coupon.customer_id == customer_id,
                Coupon.template_id == rule.coupon_id,
                Coupon.status == 'UNUSED',
                Coupon.expire_time > datetime.now()
            ))
        )
        return result.scalars().first() is not None

    async def _issue_recall_coupon(self, tenant_id, customer_id, rule):
        """发放召回券"""
        try:
            from app.services.coupon_service import CouponService
            from app.models.coupon import Coupon as CouponModel
            
            coupon_service = CouponService(self.db)
            
            # 获取优惠券模信息
            result = await self.db.execute(
                select(CouponModel).filter(CouponModel.id == rule.coupon_id)
            )
            coupon_template = result.scalars().first()
            
            if not coupon_template:
                return

            end_time = datetime.now() + timedelta(days=coupon_template.valid_days) if hasattr(coupon_template, 'valid_days') else coupon_template.end_time
            
            await coupon_service.create_coupon(
                tenant_id=tenant_id,
                customer_id=customer_id,
                name=coupon_template.name,
                type=coupon_template.type,
                value=coupon_template.value,
                min_amount=coupon_template.min_amount,
                start_time=datetime.now(),
                end_time=end_time,
                status=1
            )
        except Exception as e:
            from app.core.logger import logger
            logger.error(f"发放召回券失败: {e}")