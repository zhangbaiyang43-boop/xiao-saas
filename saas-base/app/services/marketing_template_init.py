"""营销模初始化服务"""
from sqlalchemy import select
from app.models.marketing_template import MarketingTemplate, MarketingTemplateRule

SYSTEM_TENANT_ = "SYSTEM"


class MarketingTemplateInitService:
    def __init__(self, db):
        self.db = db

    async def init_default_templates(self):
        """初始化默认营销模"""
        await self._init_catering_repurchase_template()

    async def _init_catering_repurchase_template(self):
        """初始化餐饮复购模 V1"""
        # 检查是否已存在
        result = await self.db.execute(
            select(MarketingTemplate).filter(MarketingTemplate.template_code == 'catering_repurchase_v1')
        )
        if result.scalar_one_or_none():
            return

        # 建模
        template = MarketingTemplate(
            tenant_id=SYSTEM_TENANT_,
            template_code='catering_repurchase_v1',
            template_name='餐饮复购模 V1',
            industry='面馆 / 快餐 / 小吃 / 饭店',
            description='让顾客吃过一次后，3天内再次到店',
            target_customer_price_min=8,
            target_customer_price_max=20,
            status=1
        )
        self.db.add(template)
        await self.db.flush()

        # 建则
        rules = [
            {
                'rule_code': 'new_customer_coupon',
                'rule_name': '新客券',
                'trigger_type': 'first_scan',
                'coupon_type': 'new_customer',
                'discount_type': 'amount_threshold',
                'threshold_amount': 10,
                'discount_amount': 2,
                'valid_days': 1,
                'trigger_delay_days': 0,
                'sort_order': 1
            },
            {
                'rule_code': 'after_consumption_coupon',
                'rule_name': '消费后券',
                'trigger_type': 'after_verify',
                'coupon_type': 'after_consumption',
                'discount_type': 'amount_threshold',
                'threshold_amount': 10,
                'discount_amount': 2,
                'valid_days': 2,
                'trigger_delay_days': 0,
                'sort_order': 2
            },
            {
                'rule_code': 'recall_3days_coupon',
                'rule_name': '3天召回券',
                'trigger_type': 'no_verify_after_days',
                'coupon_type': 'recall',
                'discount_type': 'amount_threshold',
                'threshold_amount': 10,
                'discount_amount': 3,
                'valid_days': 2,
                'trigger_delay_days': 3,
                'sort_order': 3
            },
            {
                'rule_code': 'recall_7days_coupon',
                'rule_name': '7天召回券',
                'trigger_type': 'no_verify_after_days',
                'coupon_type': 'recall',
                'discount_type': 'amount_threshold',
                'threshold_amount': 10,
                'discount_amount': 4,
                'valid_days': 2,
                'trigger_delay_days': 7,
                'sort_order': 4
            }
        ]

        for rule_data in rules:
            rule = MarketingTemplateRule(
                tenant_id=SYSTEM_TENANT_,
                template_id=template.id,
                **rule_data,
                status=1
            )
            self.db.add(rule)

        await self.db.commit()
        return template
