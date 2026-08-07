from datetime import datetime

from sqlalchemy import func, or_
from sqlalchemy.future import select

from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.services.anti_fraud_service import AntiFraudService
from app.services.base_service import BaseService

VERIFY_FAILURE_MESSAGES = {
    "NOT_FOUND": "核销码不存在",
    "USED": "优惠券已核销",
    "EXPIRED": "优惠券已过期",
    "REVOKED": "优惠券已收回",
    "CUSTOMER_DISABLED": "会员已停用，不能核销",
    "INVAL": "核销码无效",
    "INVALID": "核销码无效",
    "CODE_EXPIRED": "核销码已过期，请让顾客刷新后重试",
    "NOT_USED": "优惠券尚未核销，不能撤销",
}


class VerifyService(BaseService):
    @staticmethod
    def build_record_item(coupon: Coupon, template: CouponTemplate | None = None, customer: Customer | None = None) -> dict:
        verify_status = coupon.status
        if coupon.status == "USED":
            verify_status = "USED"
        if coupon.revoke_time:
            verify_status = "REVOKED"
        if coupon.abnormal_reason and coupon.status == "USED":
            verify_status = "ABNORMAL"

        return {
            "id": str(coupon.id),
            "customer_id": str(coupon.customer_id),
            "customer_name": customer.name if customer else "",
            "customer_phone": customer.phone if customer else "",
            "template_id": str(coupon.template_id),
            "template_name": template.name if template else "优惠券",
            "code": coupon.code,
            "verify_code": coupon.verify_code,
            "status": coupon.status,
            "verify_status": verify_status,
            "use_time": coupon.use_time,
            "expire_time": coupon.expire_time,
            "revoke_time": coupon.revoke_time,
            "revoke_reason": coupon.revoke_reason,
            "abnormal_reason": coupon.abnormal_reason,
            "created_at": coupon.created_at,
            "updated_at": coupon.updated_at,
        }

    async def _build_record_item(self, coupon: Coupon | None) -> dict | None:
        if not coupon:
            return None
        tenant_id = self.require_tenant_id()
        template_result = await self.db.execute(
            select(CouponTemplate).filter(
                CouponTemplate.tenant_id == tenant_id,
                CouponTemplate.id == coupon.template_id,
            )
        )
        customer_result = await self.db.execute(
            select(Customer).filter(
                Customer.tenant_id == tenant_id,
                Customer.id == coupon.customer_id,
            )
        )
        return self.build_record_item(coupon, template_result.scalar_one_or_none(), customer_result.scalar_one_or_none())

    async def get_verify_status(self, code: str) -> tuple[Coupon | None, str | None]:
        tenant_id = self.require_tenant_id()
        normalized_code = (code or "").strip().upper()
        use_verify_code_lookup = False

        if AntiFraudService.is_dynamic_verify_code(code):
            try:
                payload = AntiFraudService.parse_dynamic_verify_code(code)
            except ValueError as e:
                if "过期" in str(e):
                    return None, "CODE_EXPIRED"
                return None, "INVAL"
            if str(payload.get("tenant_id")) != str(tenant_id):
                return None, "INVAL"
            normalized_code = str(payload.get("coupon_code") or "").strip().upper()
        elif len(normalized_code) <= 10:
            use_verify_code_lookup = True

        if use_verify_code_lookup:
            result = await self.db.execute(
                select(Coupon)
                .filter(
                    Coupon.verify_code == normalized_code,
                    Coupon.tenant_id == tenant_id,
                )
                .with_for_update()
            )
        else:
            result = await self.db.execute(
                select(Coupon)
                .filter(
                    Coupon.code == normalized_code,
                    Coupon.tenant_id == tenant_id,
                )
                .with_for_update()
            )
        coupon = result.scalar_one_or_none()

        if not coupon:
            return None, "NOT_FOUND"
        if coupon.status == "USED":
            return coupon, "USED"
        if coupon.status == "REVOKED":
            return coupon, "REVOKED"
        if coupon.status == "EXPIRED" or datetime.utcnow() > coupon.expire_time:
            coupon.status = "EXPIRED"
            await self.db.commit()
            await self.db.refresh(coupon)
            return coupon, "EXPIRED"
        if coupon.status != "UNUSED":
            return coupon, "INVAL"

        customer_result = await self.db.execute(
            select(Customer).filter(
                Customer.id == coupon.customer_id,
                Customer.tenant_id == tenant_id,
            )
        )
        customer = customer_result.scalar_one_or_none()
        if not customer or customer.status == -1:
            return coupon, "CUSTOMER_DISABLED"

        return coupon, None

    async def verify_coupon(self, code: str) -> Coupon | None:
        result = await self.verify_coupon_with_result(code)
        return result["coupon"] if result["success"] else None

    async def verify_coupon_with_result(self, code: str) -> dict:
        coupon, failure = await self.get_verify_status(code)
        if failure:
            return {
                "success": False,
                "reason": failure,
                "message": VERIFY_FAILURE_MESSAGES[failure],
                "coupon": await self._build_record_item(coupon),
            }

        if not await AntiFraudService.allow_daily_verify(coupon.tenant_id, coupon.customer_id):
            return {
                "success": False,
                "reason": "INVAL",
                "message": "今日核销次数过多，请明天再试",
                "coupon": await self._build_record_item(coupon),
            }

        coupon.status = "USED"
        coupon.use_time = datetime.utcnow()
        coupon.revoke_time = None
        coupon.revoke_reason = None
        await self.db.commit()
        await self.db.refresh(coupon)
        await self._update_customer_last_consume(coupon.customer_id)
        template = await self._get_template_for_coupon(coupon)
        await self._trigger_commission(coupon, template)
        await self._trigger_consumption_coupon(coupon)

        return {
            "success": True,
            "reason": None,
            "message": "核销成功",
            "coupon": await self._build_record_item(coupon),
        }

    async def revoke_verification(self, coupon_id: int, reason: str) -> dict:
        coupon = await self._get_coupon_for_update(coupon_id)
        if not coupon:
            return {"success": False, "reason": "NOT_FOUND", "message": VERIFY_FAILURE_MESSAGES["NOT_FOUND"], "coupon": None}
        if coupon.status != "USED":
            return {
                "success": False,
                "reason": "NOT_USED",
                "message": VERIFY_FAILURE_MESSAGES["NOT_USED"],
                "coupon": await self._build_record_item(coupon),
            }

        coupon.status = "UNUSED"
        coupon.revoke_time = datetime.utcnow()
        coupon.revoke_reason = reason
        await self.db.commit()
        await self.db.refresh(coupon)
        return {"success": True, "reason": None, "message": "撤销核销成功", "coupon": await self._build_record_item(coupon)}

    async def mark_abnormal(self, coupon_id: int, reason: str) -> dict:
        coupon = await self._get_coupon_for_update(coupon_id)
        if not coupon:
            return {"success": False, "reason": "NOT_FOUND", "message": VERIFY_FAILURE_MESSAGES["NOT_FOUND"], "coupon": None}

        coupon.abnormal_reason = reason
        await self.db.commit()
        await self.db.refresh(coupon)
        return {"success": True, "reason": None, "message": "异常原因已记录", "coupon": await self._build_record_item(coupon)}

    async def list_verify_records(self, skip: int = 0, limit: int = 50) -> list:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(Coupon, CouponTemplate, Customer)
            .join(CouponTemplate, CouponTemplate.id == Coupon.template_id)
            .outerjoin(Customer, Customer.id == Coupon.customer_id)
            .filter(
                Coupon.tenant_id == tenant_id,
                CouponTemplate.tenant_id == tenant_id,
                or_(Coupon.status == "USED", Coupon.use_time.isnot(None), Coupon.revoke_time.isnot(None)),
            )
            .order_by(
                Coupon.use_time.desc(),
                Coupon.updated_at.desc(),
            )
            .offset(skip)
            .limit(limit)
        )
        return [self.build_record_item(coupon, template, customer) for coupon, template, customer in result.all()]

    async def count_verify_records(self) -> int:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(func.count()).select_from(Coupon).filter(
                Coupon.tenant_id == tenant_id,
                or_(Coupon.status == "USED", Coupon.use_time.isnot(None), Coupon.revoke_time.isnot(None)),
            )
        )
        return int(result.scalar_one() or 0)

    async def _get_coupon_for_update(self, coupon_id: int) -> Coupon | None:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(Coupon)
            .filter(
                Coupon.id == coupon_id,
                Coupon.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def _get_template_for_coupon(self, coupon: Coupon) -> CouponTemplate | None:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(CouponTemplate).filter(
                CouponTemplate.tenant_id == tenant_id,
                CouponTemplate.id == coupon.template_id,
            )
        )
        return result.scalar_one_or_none()

    async def _trigger_commission(self, coupon: Coupon, template: CouponTemplate | None):
        try:
            from app.services.commission_service import CommissionService

            service = CommissionService(self.db)
            service.set_tenant_id(coupon.tenant_id)
            await service.record_after_verify(coupon, template)
        except Exception as e:
            from app.core.logger import logger

            logger.error(f"分销分佣生成失败: {e}")

    async def _trigger_consumption_coupon(self, coupon: Coupon):
        try:
            from app.services.coupon_service import CouponService

            service = CouponService(self.db)
            service.set_tenant_id(coupon.tenant_id)
            await service.issue_auto_coupon(coupon.customer_id, "consumption_coupon")
        except Exception as e:
            from app.core.logger import logger

            logger.error(f"核销后消费券发放失败: {e}")

    async def _update_customer_last_consume(self, customer_id: int):
        tenant_id = self.require_tenant_id()
        customer = await self.db.execute(
            select(Customer)
            .filter(
                Customer.id == customer_id,
                Customer.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        customer = customer.scalar_one_or_none()
        if customer:
            customer.last_consume_time = datetime.utcnow()
            await self.db.commit()
            await self.db.refresh(customer)
