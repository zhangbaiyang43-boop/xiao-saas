from sqlalchemy import func, select
from datetime import datetime, timedelta

from app.models.consumption import Consumption
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.services.base_service import BaseService


class StatisticsService(BaseService):
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
        }
