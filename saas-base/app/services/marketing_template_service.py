from datetime import datetime, timedelta
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import joinedload
from app.models.marketing_template import (
    MarketingTemplate,
    MarketingTemplateRule,
    MerchantTemplate,
    MerchantTemplateRule,
)
from app.models.coupon import Coupon
from app.models.customer import Customer
from app.services.base_service import BaseService
from app.core.exceptions import BusinessException


class MarketingTemplateService(BaseService):
    def __init__(self, db):
        super().__init__(db)

    async def get_templates(self):
        """获取所有营销模列表"""
        result = await self.db.execute(
            select(MarketingTemplate).filter(
                MarketingTemplate.tenant_id == "SYSTEM",
                MarketingTemplate.status == 1,
            )
        )
        return result.scalars().all()

    async def get_template_by_id(self, template_id: int):
        """根据获取模详情"""
        result = await self.db.execute(
            select(MarketingTemplate)
            .filter(MarketingTemplate.id == template_id)
            .options(joinedload(MarketingTemplate.rules))
        )
        return result.scalars().first()

    async def get_template_by_code(self, template_code: str):
        """根据编码获取模"""
        result = await self.db.execute(
            select(MarketingTemplate).filter(MarketingTemplate.template_code == template_code)
        )
        return result.scalars().first()

    async def get_template_rules(self, template_id: int):
        """获取模则列表"""
        result = await self.db.execute(
            select(MarketingTemplateRule)
            .filter(and_(
                MarketingTemplateRule.template_id == template_id,
                MarketingTemplateRule.status == 1
            ))
            .order_by(MarketingTemplateRule.sort_order)
        )
        return result.scalars().all()

    async def get_merchant_templates(self, tenant_id: int):
        """获取商家已启用的模列表"""
        result = await self.db.execute(
            select(MerchantTemplate)
            .filter(and_(
                MerchantTemplate.tenant_id == tenant_id,
                MerchantTemplate.status == 1
            ))
            .options(joinedload(MerchantTemplate.template))
        )
        return result.scalars().all()

    async def get_merchant_template(self, tenant_id: int, template_id: int):
        """获取商家特定模的启用状态"""
        result = await self.db.execute(
            select(MerchantTemplate).filter(and_(
                MerchantTemplate.tenant_id == tenant_id,
                MerchantTemplate.template_id == template_id,
                MerchantTemplate.status == 1
            ))
        )
        return result.scalars().first()

    async def enable_template(self, tenant_id: int, template_id: int):
        """启用营销模"""
        # 1. 检查是否已启用
        existing = await self.get_merchant_template(tenant_id, template_id)
        if existing:
            raise BusinessException("该模已启用")

        # 2. 获取模和则
        template = await self.get_template_by_id(template_id)
        if not template:
            raise BusinessException("模不存在")

        rules = await self.get_template_rules(template_id)
        if not rules:
            raise BusinessException("模则为空")

        # 3. 建商家模记录
        merchant_template = MerchantTemplate(
            tenant_id=tenant_id,
            template_id=template_id,
            status=1,
            enabled_at=datetime.now()
        )
        self.db.add(merchant_template)
        await self.db.flush()

        # 4. 建优惠券模板并绑定则
        from app.services.coupon_service import CouponService
        coupon_service = CouponService(self.db)
        coupon_service.set_tenant_id(tenant_id)

        for rule in rules:
            # 每条规则对应一个可复用的优惠券模板，实际发放时从这个模板发出具体的券
            end_time = datetime.now() + timedelta(days=rule.valid_days)
            coupon_template = await coupon_service.create_template(
                name=rule.rule_name,
                type='FIXED',
                value=rule.discount_amount,
                min_amount=rule.threshold_amount,
                total_stock=10 ** 8,  # 营销模板券不做库存限制，发放次数由规则触发条件控制
                start_time=datetime.now(),
                end_time=end_time,
                status=1,
            )

            # 建商家模则
            merchant_rule = MerchantTemplateRule(
                tenant_id=tenant_id,
                merchant_template_id=merchant_template.id,
                source_template_rule_id=rule.id,
                rule_code=rule.rule_code,
                rule_name=rule.rule_name,
                trigger_type=rule.trigger_type,
                coupon_template_id=coupon_template.id,
                trigger_delay_days=rule.trigger_delay_days,
                status=1
            )
            self.db.add(merchant_rule)

        await self.db.commit()
        return merchant_template

    async def disable_template(self, merchant_template_id: int, tenant_id: int):
        """停用商家模"""
        result = await self.db.execute(
            select(MerchantTemplate)
            .filter(and_(
                MerchantTemplate.id == merchant_template_id,
                MerchantTemplate.tenant_id == tenant_id
            ))
            .with_for_update()
        )
        merchant_template = result.scalars().first()
        
        if not merchant_template:
            raise BusinessException("模不存在")

        merchant_template.status = 0
        merchant_template.disabled_at = datetime.now()
        
        # 同时停用所有则
        await self.db.execute(
            MerchantTemplateRule.__table__.update()
            .where(MerchantTemplateRule.merchant_template_id == merchant_template_id)
            .values(status=0)
        )

        await self.db.commit()
        return merchant_template

    async def get_trigger_rules(self, tenant_id: int, trigger_type: str):
        """获取指定触发类型的则"""
        result = await self.db.execute(
            select(MerchantTemplateRule)
            .join(MerchantTemplate, and_(
                MerchantTemplate.id == MerchantTemplateRule.merchant_template_id,
                MerchantTemplate.status == 1
            ))
            .filter(and_(
                MerchantTemplateRule.tenant_id == tenant_id,
                MerchantTemplateRule.trigger_type == trigger_type,
                MerchantTemplateRule.status == 1
            ))
        )
        return result.scalars().all()

    async def check_coupon_already_issued(self, tenant_id: int, customer_id: int, rule_code: str):
        """检查优惠券是否已发放给该用户"""
        # 查询该则下的优惠券
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
                Coupon.template_id == rule.coupon_template_id,
                Coupon.status == "UNUSED",
                Coupon.expire_time > datetime.now()
            ))
        )
        return result.scalars().first() is not None

    async def issue_coupon_by_rule(self, tenant_id: int, customer_id: int, rule_code: str):
        """根据则发放优惠券"""
        # 获取则
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
            raise BusinessException("则不存在或未启用")

        # 检查是否已发放
        if await self.check_coupon_already_issued(tenant_id, customer_id, rule_code):
            raise BusinessException("该优惠券已发放")

        # 从规则绑定的优惠券模板真正发一张券给这个用户
        from app.services.coupon_service import CouponService
        coupon_service = CouponService(self.db)
        coupon_service.set_tenant_id(tenant_id)

        coupon_template = await coupon_service.get_template(rule.coupon_template_id)
        if not coupon_template:
            raise BusinessException("优惠券模板不存在")

        send_result = await coupon_service.send_coupons_with_result(
            coupon_template.id, [customer_id], source=f"marketing_template:{rule_code}"
        )
        if send_result.get("success_count", 0) < 1:
            raise BusinessException(send_result.get("reason") or "优惠券发放失败")
        return send_result

    async def process_recall_rules(self):
        """处理召回则（定时任务）"""
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
            # 查找需要召回的会员
            # 查询最近核销时间在 trigger_delay_days 天前的会员
            cutoff_time = now - timedelta(days=rule.trigger_delay_days)
            
            # 获取该商家下所有会员
            customers = await self.db.execute(
                select(Customer).filter(Customer.tenant_id == rule.tenant_id)
            )
            
            for customer in customers.scalars().all():
                # 检查该会员是否符合召回条件
                # 这里需要查询会员最近的核销记录
                # 简化实现：直接发放召回券（实际应检查核销记录）
                try:
                    await self.issue_coupon_by_rule(rule.tenant_id, customer.id, rule.rule_code)
                except BusinessException:
                    # 已发放或其他错误，跳过
                    continue

        await self.db.commit()
