import logging
import random
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_
from sqlalchemy.future import select

from app.models.commission_record import CommissionRecord
from app.models.customer import Customer
from app.models.staff import Staff
from app.models.tenant_config import TenantConfig
from app.services.base_service import BaseService

logger = logging.getLogger(__name__)

# 邀请码字符表（同 customer_service，保持一致）
_INVITE_CODE_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


# 历史遗留：迁移老配置（老字段名 'enabled'、locked 覆盖时的兜底）用，
# 正常路径下金额/门槛已经不再从这里取，全部由 build_dynamic_rules 实时算。
DEFAULT_DISTRIBUTION_RULES = {
    "invite_reward_enabled": False,
    "inviter_reward_amount": 5.0,
    "invitee_reward_amount": 5.0,
    "invite_reward_min_spend": 20.0,
    "invite_reward_valid_days": 30,
    "invite_reward_trigger": "FIRST_VERIFY",
}


class CommissionService(BaseService):

    # ------------------------------------------------------------------
    # 短邀请码辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _make_short_invite_code() -> str:
        """生成 6 位随机短邀请码。"""
        return ''.join(random.choices(_INVITE_CODE_CHARS, k=6))

    async def _ensure_short_invite_code(self, customer: Customer) -> str:
        """
        确保 customer 拥有短邀请码。
        对于迁移前已存在、short_invite_code 为 NULL 的老用户，惰性生成并写库。
        """
        if customer.short_invite_code:
            return customer.short_invite_code

        # 最多尝试 5 次，避免极小概率的同租户碰撞
        tenant_id = customer.tenant_id
        for _ in range(5):
            code = self._make_short_invite_code()
            dup = await self.db.execute(
                select(Customer).filter(
                    Customer.tenant_id == tenant_id,
                    Customer.short_invite_code == code,
                )
            )
            if not dup.scalar_one_or_none():
                customer.short_invite_code = code
                try:
                    await self.db.commit()
                    await self.db.refresh(customer)
                except Exception:
                    await self.db.rollback()
                return code

        # 兜底：用  末 6 位（不入库）
        fallback = str(customer.id)[-6:]
        logger.warning(f"invite_code: 无法为 customer {customer.id} 生成唯一短码，使用  末位回退")
        return fallback

    # ------------------------------------------------------------------

    async def get_distribution_intensity(self) -> str:
        """商户为"邀请奖励"单独选的强度档位——跟另外四类券的 marketing_intensity 分开
        设置，因为老带新裂变和进店/复购发券是完全不同的运营场景，调一个不该牵动另一个。"""
        from app.core.platform_rules import resolve_intensity
        from app.services.tenant_service import TenantService
        tenant_service = TenantService(self.db)
        config = await tenant_service.get_tenant_config(self.tenant_id)
        business_info = (config.business_info or {}) if config else {}
        return resolve_intensity(business_info.get("distribution_intensity"))

    async def get_distribution_rules(self) -> dict:
        """跟 CouponService.get_coupon_rules() 同一套模式：金额/门槛由算法（客单价 +
        商户为邀请奖励单独选的强度档位）实时算，商户只有显式 locked 时才允许静态值
        覆盖——默认情况下商户能改的只有"要不要开启"这个开关和强度档位，改不了具体金额，
        从"填四个数字"变成"选一档"，跟另外四类营销券的操作体验保持一致。"""
        from app.core.platform_rules import build_dynamic_rules
        from app.services.coupon_service import CouponService

        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(TenantConfig).filter(TenantConfig.tenant_id == tenant_id)
        )
        config = result.scalar_one_or_none()
        merchant_rules = ((config.plugin_settings or {}).get("distribution") or {}) if config else {}
        # 老字段名迁移：以前唯一的开关字段叫 'enabled'
        if "invite_reward_enabled" not in merchant_rules and "enabled" in merchant_rules:
            merchant_rules = {**merchant_rules, "invite_reward_enabled": merchant_rules["enabled"]}

        aov_service = CouponService(self.db)
        aov_service.set_tenant_id(tenant_id)
        aov = await aov_service.get_merchant_aov()
        intensity = await self.get_distribution_intensity()
        platform_rule = dict(build_dynamic_rules(aov, intensity)["invite_reward"])
        platform_default_enabled = platform_rule.pop("enabled", False)

        if merchant_rules.get("locked"):
            merged = {**platform_rule, **{k: v for k, v in merchant_rules.items() if k != "invite_reward_enabled"}}
        else:
            merged = dict(platform_rule)

        merged["invite_reward_enabled"] = bool(merchant_rules.get("invite_reward_enabled", platform_default_enabled))
        merged["invite_reward_trigger"] = "FIRST_VERIFY"
        return merged

    async def get_distribution_preview(self) -> dict:
        """给"邀请奖励"强度选择器用：三档强度各自算出来的真实金额/门槛，不编造
        "预计发多少张、花多少钱"这类没有历史邀请数据支撑的预测——邀请转化量级
        依赖顾客的真实社交行为，不像复购券那样能直接按订单量近似，与其编一个
        不准的数字，不如老老实实只展示每档算出来的具体面额，让商户自己判断。"""
        from app.core.platform_rules import INTENSITY_LABELS, INTENSITY_PRESETS, build_dynamic_rules
        from app.services.coupon_service import CouponService

        tenant_id = self.require_tenant_id()
        aov_service = CouponService(self.db)
        aov_service.set_tenant_id(tenant_id)
        aov = await aov_service.get_merchant_aov()
        current_intensity = await self.get_distribution_intensity()

        outcomes = []
        for key in INTENSITY_PRESETS:
            rule = build_dynamic_rules(aov, key)["invite_reward"]
            outcomes.append({
                "intensity": key,
                "label": INTENSITY_LABELS[key],
                "is_current": key == current_intensity,
                "inviter_reward_amount": rule["inviter_reward_amount"],
                "invitee_reward_amount": rule["invitee_reward_amount"],
                "invite_reward_min_spend": rule["invite_reward_min_spend"],
                "invite_reward_valid_days": rule["invite_reward_valid_days"],
            })

        return {
            "aov": round(aov, 1) if aov else None,
            "has_enough_data": bool(aov),
            "current_intensity": current_intensity,
            "outcomes": outcomes,
        }

    async def update_distribution_rules(self, data: dict) -> dict:
        """商户能通过这个接口改的只剩"要不要开启"这一个开关——金额/门槛/有效期全部
        交给算法算，强度档位走 tenant 的 business_info.distribution_intensity（跟
        marketing_intensity 一样，通过 /v1/tenant/settings 那个通用接口设置，不在这里管）。"""
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(TenantConfig).filter(TenantConfig.tenant_id == tenant_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            config = TenantConfig(
                tenant_id=tenant_id,
                member_rules={},
                coupon_rules={},
                business_info={},
                plugin_settings={},
            )
            self.db.add(config)

        plugin_settings = dict(config.plugin_settings or {})
        current = dict(plugin_settings.get("distribution") or {})
        if "invite_reward_enabled" in data:
            current["invite_reward_enabled"] = bool(data["invite_reward_enabled"])
        plugin_settings["distribution"] = current
        config.plugin_settings = plugin_settings
        await self.db.commit()
        await self.db.refresh(config)
        return await self.get_distribution_rules()

    # ------------------------------------------------------------------
    # 员工推荐佣金——跟上面的顾客老带新（distribution）是同一套强度算法框架，
    # 单独开关、单独强度档位存放，互不影响；员工那一侧不发券，只在
    # record_after_verify 里记一笔待商家线下结算的现金。
    # ------------------------------------------------------------------

    async def get_staff_referral_intensity(self) -> str:
        from app.core.platform_rules import resolve_intensity
        from app.services.tenant_service import TenantService
        tenant_service = TenantService(self.db)
        config = await tenant_service.get_tenant_config(self.tenant_id)
        business_info = (config.business_info or {}) if config else {}
        return resolve_intensity(business_info.get("staff_referral_intensity"))

    async def get_staff_referral_rules(self) -> dict:
        from app.core.platform_rules import build_dynamic_rules
        from app.services.coupon_service import CouponService

        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(TenantConfig).filter(TenantConfig.tenant_id == tenant_id)
        )
        config = result.scalar_one_or_none()
        merchant_rules = ((config.plugin_settings or {}).get("staff_referral") or {}) if config else {}

        aov_service = CouponService(self.db)
        aov_service.set_tenant_id(tenant_id)
        aov = await aov_service.get_merchant_aov()
        intensity = await self.get_staff_referral_intensity()
        platform_rule = dict(build_dynamic_rules(aov, intensity)["staff_referral"])
        platform_default_enabled = platform_rule.pop("enabled", False)

        merged = dict(platform_rule)
        merged["enabled"] = bool(merchant_rules.get("enabled", platform_default_enabled))
        return merged

    async def get_staff_referral_preview(self) -> dict:
        from app.core.platform_rules import INTENSITY_LABELS, INTENSITY_PRESETS, build_dynamic_rules
        from app.services.coupon_service import CouponService

        tenant_id = self.require_tenant_id()
        aov_service = CouponService(self.db)
        aov_service.set_tenant_id(tenant_id)
        aov = await aov_service.get_merchant_aov()
        current_intensity = await self.get_staff_referral_intensity()

        outcomes = []
        for key in INTENSITY_PRESETS:
            rule = build_dynamic_rules(aov, key)["staff_referral"]
            outcomes.append({
                "intensity": key,
                "label": INTENSITY_LABELS[key],
                "is_current": key == current_intensity,
                "staff_commission_amount": rule["staff_commission_amount"],
            })

        return {
            "aov": round(aov, 1) if aov else None,
            "has_enough_data": bool(aov),
            "current_intensity": current_intensity,
            "outcomes": outcomes,
        }

    async def update_staff_referral_rules(self, data: dict) -> dict:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(TenantConfig).filter(TenantConfig.tenant_id == tenant_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            config = TenantConfig(
                tenant_id=tenant_id,
                member_rules={},
                coupon_rules={},
                business_info={},
                plugin_settings={},
            )
            self.db.add(config)

        plugin_settings = dict(config.plugin_settings or {})
        current = dict(plugin_settings.get("staff_referral") or {})
        if "enabled" in data:
            current["enabled"] = bool(data["enabled"])
        plugin_settings["staff_referral"] = current
        config.plugin_settings = plugin_settings
        await self.db.commit()
        await self.db.refresh(config)
        return await self.get_staff_referral_rules()

    # ------------------------------------------------------------------
    # 员工 CRUD——员工不需要登录，只是一个挂着专属推荐码的轻量身份。
    # ------------------------------------------------------------------

    async def create_staff(self, name: str) -> Staff:
        from app.utils.id_generator import generate_snowflake_id

        tenant_id = self.require_tenant_id()
        code = ""
        for _ in range(5):
            candidate = self._make_short_invite_code()
            dup = await self.db.execute(
                select(Staff).filter(
                    Staff.tenant_id == tenant_id,
                    Staff.invite_code == candidate,
                )
            )
            if not dup.scalar_one_or_none():
                code = candidate
                break
        staff = Staff(
            id=generate_snowflake_id(),
            tenant_id=tenant_id,
            name=name,
            invite_code=code,
            status=1,
        )
        self.db.add(staff)
        await self.db.commit()
        await self.db.refresh(staff)

        # 配套生成一张"员工分享码"——员工扫这张码进小程序的分享页，点右上角
        # 转发出去的就是原生小程序卡片，顾客点开零输入直接绑定推荐关系，
        # 不用再靠员工口头念邀请码。生成失败（比如微信小程序码没配置）不影响
        # 员工本身已经建好，商家可以在列表页里重新生成。
        from app.services.entrance_code_service import EntranceCodeService

        entrance_service = EntranceCodeService(self.db)
        entrance_service.set_tenant_id(tenant_id)
        try:
            await entrance_service.create_entrance_code(
                name=f"员工分享-{name}",
                channel="OTHER",
                entry_type="staff_share",
                target_page="subpkg-member/pages/staff-share",
                staff_id=staff.id,
            )
        except Exception as exc:
            logger.error(f"staff_referral: 员工分享码生成失败 tenant={tenant_id} staff={staff.id} error={exc}")
        return staff

    async def list_staff(self) -> list[dict]:
        from app.models.entrance_code import EntranceCode

        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(Staff).filter(Staff.tenant_id == tenant_id).order_by(Staff.created_at.desc())
        )
        staff_list = list(result.scalars().all())
        if not staff_list:
            return []

        staff_ids = [s.id for s in staff_list]
        code_result = await self.db.execute(
            select(EntranceCode).filter(
                EntranceCode.tenant_id == tenant_id,
                EntranceCode.entry_type == "staff_share",
                EntranceCode.staff_id.in_(staff_ids),
            )
        )
        # 一个员工理论上只会有一张分享码；万一因为历史重试等原因有多张，
        # 取最新创建的那张展示，不是关键路径不用做去重清理。
        code_by_staff = {}
        for code in code_result.scalars().all():
            existing = code_by_staff.get(code.staff_id)
            if not existing or code.created_at > existing.created_at:
                code_by_staff[code.staff_id] = code

        rows = []
        for s in staff_list:
            code = code_by_staff.get(s.id)
            rows.append({
                "id": s.id,
                "name": s.name,
                "invite_code": s.invite_code,
                "status": s.status,
                "created_at": s.created_at,
                "share_code_id": str(code.id) if code else None,
                "share_image_url": code.image_url if code else None,
                "share_generation_status": code.generation_status if code else None,
                "share_generation_error": code.generation_error if code else None,
            })
        return rows

    async def update_staff_status(self, staff_id: int, status: int) -> Staff | None:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(Staff).filter(Staff.tenant_id == tenant_id, Staff.id == staff_id)
        )
        staff = result.scalar_one_or_none()
        if not staff:
            return None
        staff.status = status
        await self.db.commit()
        await self.db.refresh(staff)
        return staff

    async def bind_inviter_for_new_customer(self, customer: Customer, invite_code: str | None) -> Customer:
        tenant_id = self.require_tenant_id()
        if not customer or customer.inviter_id or not invite_code:
            return customer

        invite_code = str(invite_code).strip()
        short_code = invite_code.upper()

        inviter: Customer | None = None

        # 优先按短邀请码查找（新格式：6 位字母数字，不区分大小写）——顾客码的查找
        # 优先级保持不变，员工码只在顾客码查不到的时候才查，避免万一两边生成器
        # 撞出同一个码时改变现有顾客邀请顾客的行为。
        if len(short_code) <= 8:
            result = await self.db.execute(
                select(Customer).filter(
                    Customer.tenant_id == tenant_id,
                    Customer.short_invite_code == short_code,
                    Customer.status != -1,
                )
            )
            inviter = result.scalar_one_or_none()

        # 兼容旧格式：纯数字 → 直接当 customer.id 解析
        if not inviter:
            try:
                inviter_id = int(invite_code)
                if inviter_id != int(customer.id):
                    result = await self.db.execute(
                        select(Customer).filter(
                            Customer.tenant_id == tenant_id,
                            Customer.id == inviter_id,
                            Customer.status != -1,
                        )
                    )
                    inviter = result.scalar_one_or_none()
            except (TypeError, ValueError):
                pass

        if inviter and inviter.id != customer.id:
            customer.inviter_id = inviter.id
            customer.inviter_parent_id = inviter.inviter_id
            customer.inviter_type = "customer"
            await self.db.commit()
            await self.db.refresh(customer)
            return customer

        # 顾客码没查到：再查一次员工推荐码——员工码是商家在后台专门生成的，
        # 员工不参与多级邀请链，不设置 inviter_parent_id。
        if len(short_code) <= 8:
            staff_result = await self.db.execute(
                select(Staff).filter(
                    Staff.tenant_id == tenant_id,
                    Staff.invite_code == short_code,
                    Staff.status == 1,
                )
            )
            staff = staff_result.scalar_one_or_none()
            if staff:
                customer.inviter_id = staff.id
                customer.inviter_type = "staff"
                await self.db.commit()
                await self.db.refresh(customer)
                return customer

        return customer

    async def record_after_verify(self, coupon, template=None) -> list[CommissionRecord]:
        tenant_id = self.require_tenant_id()

        customer_result = await self.db.execute(
            select(Customer).filter(
                Customer.tenant_id == tenant_id,
                Customer.id == coupon.customer_id,
                Customer.status != -1,
            )
        )
        customer = customer_result.scalar_one_or_none()
        if not customer or not customer.inviter_id:
            return []

        is_staff_referrer = customer.inviter_type == "staff"

        rules = await self.get_distribution_rules()
        invite_enabled = rules.get("invite_reward_enabled", rules.get("enabled", False))

        staff_rules = await self.get_staff_referral_rules() if is_staff_referrer else None
        staff_enabled = bool(staff_rules and staff_rules.get("enabled"))

        # 员工推荐：邀请人（员工）那一侧看 staff_referral 开关，走"记账不发券"；
        # 被邀请人自己的欢迎券仍然看 distribution 开关——两个开关各管各的角色，
        # 商户可以只开员工推荐、不开顾客老带新，反之亦然。顾客推荐顾客的老路径
        # 完全不变，两侧都只看 distribution 开关。
        if is_staff_referrer:
            if not staff_enabled and not invite_enabled:
                return []
        elif not invite_enabled:
            return []

        # 用 FOR UPDATE 加锁，防止并发核销时重复触发首次奖励（BUG-03）
        existing_result = await self.db.execute(
            select(CommissionRecord).filter(
                CommissionRecord.tenant_id == tenant_id,
                CommissionRecord.user_id == customer.id,
                CommissionRecord.source_type == "FIRST_VERIFY",
            ).with_for_update()
        )
        if existing_result.scalar_one_or_none():
            return []

        spend_amount = Decimal(str(getattr(template, "min_amount", None) or getattr(template, "value", 0) or 0))
        min_spend = float(rules.get("invite_reward_min_spend") or 0)
        valid_days = int(rules.get("invite_reward_valid_days") or 30)

        invitee_amount = Decimal(str(rules.get("invitee_reward_amount") or 0)) if invite_enabled else Decimal("0")
        if is_staff_referrer:
            inviter_amount = Decimal(str(staff_rules.get("staff_commission_amount") or 0)) if staff_enabled else Decimal("0")
        else:
            inviter_amount = Decimal(str(rules.get("inviter_reward_amount") or 0)) if invite_enabled else Decimal("0")

        created = []

        if inviter_amount > 0:
            record = CommissionRecord(
                tenant_id=tenant_id,
                user_id=customer.id,
                order_id=str(coupon.id),
                amount=spend_amount,
                level=1,
                receiver_id=customer.inviter_id,
                receiver_type="staff" if is_staff_referrer else "customer",
                commission_amount=inviter_amount,
                status="PENDING",
                source_type="FIRST_VERIFY",
                source_coupon_id=coupon.id,
            )
            self.db.add(record)
            created.append(record)

        if invitee_amount > 0:
            record2 = CommissionRecord(
                tenant_id=tenant_id,
                user_id=customer.id,
                order_id=str(coupon.id),
                amount=spend_amount,
                level=2,
                receiver_id=customer.id,
                receiver_type="customer",
                commission_amount=invitee_amount,
                status="PENDING",
                source_type="FIRST_VERIFY",
                source_coupon_id=coupon.id,
            )
            self.db.add(record2)
            created.append(record2)

        if not created:
            return []

        # ── 第一步：先落库 PENDING 记录，确保奖励凭证不丢失 ──────────────
        await self.db.commit()
        for item in created:
            await self.db.refresh(item)

        # ── 第二步：顾客侧实际发放优惠券，员工侧只记账不发券 ────────────
        # 发券失败时记录保留为 PENDING（可人工补发），不影响核销主流程；员工那条
        # 佣金记录本来就该一直留 PENDING，直到商家线下打款后手动标记已发放。
        try:
            from app.services.coupon_service import CouponService
            from app.core.logger import logger

            coupon_svc = CouponService(self.db)
            coupon_svc.set_tenant_id(tenant_id)

            reward_map = {2: {
                "receiver_id": customer.id,
                "amount": float(invitee_amount),
                "template_name": "到店奖励券",
                "log_role": "被邀请人",
            }}
            if not is_staff_referrer:
                reward_map[1] = {
                    "receiver_id": customer.inviter_id,
                    "amount": float(inviter_amount),
                    "template_name": "邀请奖励券",
                    "log_role": "邀请人",
                }

            now = datetime.utcnow()
            any_settled = False
            for rec in created:
                if is_staff_referrer and rec.level == 1:
                    logger.info(
                        f"staff_referral: 待发放佣金已记账 tenant={tenant_id} "
                        f"staff={rec.receiver_id} amount={rec.commission_amount} record_id={rec.id}"
                    )
                    continue
                info = reward_map.get(rec.level)
                if not info:
                    continue
                ok = await coupon_svc.issue_invite_reward_coupon(
                    customer_id=info["receiver_id"],
                    amount=info["amount"],
                    min_spend=min_spend,
                    valid_days=valid_days,
                    template_name=info["template_name"],
                )
                if ok:
                    rec.status = "SETTLED"
                    rec.settled_at = now
                    any_settled = True
                    logger.info(
                        f"invite_reward: {info['log_role']}奖励券发放成功 "
                        f"tenant={tenant_id} receiver={info['receiver_id']} "
                        f"amount={info['amount']} record_id={rec.id}"
                    )
                else:
                    logger.warning(
                        f"invite_reward: {info['log_role']}奖励券发放失败，保留PENDING "
                        f"tenant={tenant_id} receiver={info['receiver_id']} record_id={rec.id}"
                    )

            if any_settled:
                await self.db.commit()
                for item in created:
                    await self.db.refresh(item)

        except Exception as exc:
            from app.core.logger import logger
            logger.error(
                f"invite_reward: 发券阶段异常，记录保留为PENDING "
                f"tenant={tenant_id} user={customer.id} error={exc}"
            )
            # 不 re-raise，主核销流程不受影响

        return created

    async def summary_for_customer(self, customer_id: int) -> dict:
        tenant_id = self.require_tenant_id()
        invited_result = await self.db.execute(
            select(func.count()).select_from(Customer).filter(
                Customer.tenant_id == tenant_id,
                Customer.inviter_id == customer_id,
                Customer.status != -1,
            )
        )
        total_result = await self.db.execute(
            select(func.coalesce(func.sum(CommissionRecord.commission_amount), 0)).filter(
                CommissionRecord.tenant_id == tenant_id,
                CommissionRecord.receiver_id == customer_id,
            )
        )
        settled_result = await self.db.execute(
            select(func.coalesce(func.sum(CommissionRecord.commission_amount), 0)).filter(
                CommissionRecord.tenant_id == tenant_id,
                CommissionRecord.receiver_id == customer_id,
                CommissionRecord.status == "SETTLED",
            )
        )
        # 获取该用户的短邀请码（惰性生成）
        customer_q = await self.db.execute(
            select(Customer).filter(
                Customer.tenant_id == tenant_id,
                Customer.id == customer_id,
            )
        )
        customer_obj = customer_q.scalar_one_or_none()
        invite_code = await self._ensure_short_invite_code(customer_obj) if customer_obj else str(customer_id)[-6:]

        total_commission = Decimal(str(total_result.scalar() or 0))
        settled_commission = Decimal(str(settled_result.scalar() or 0))
        return {
            "invite_code": invite_code,
            "invited_count": int(invited_result.scalar() or 0),
            "total_commission": float(total_commission),
            "settled_commission": float(settled_commission),
            "pending_commission": float(total_commission - settled_commission),
        }

    async def list_records_for_admin(self, skip: int = 0, limit: int = 50) -> tuple[list[dict], int]:
        """顾客老带新列表——员工推荐的顾客走独立的"员工推荐"列表
        （list_staff_commission_records），这里排除掉，避免混在一起时
        邀请人查不到对应的 Customer 行、显示成来路不明的"会员xxxx"。"""
        tenant_id = self.require_tenant_id()

        base_filter = (
            Customer.tenant_id == tenant_id,
            Customer.inviter_id.isnot(None),
            # NULL 老数据（迁移前的顾客邀请顾客记录）也要保留在这份列表里——
            # inviter_type != 'staff' 在 SQL 里对 NULL 永远不成立，必须显式放行 NULL。
            or_(Customer.inviter_type != "staff", Customer.inviter_type.is_(None)),
            Customer.status != -1,
        )

        total_result = await self.db.execute(
            select(func.count()).select_from(Customer).filter(*base_filter)
        )
        total = int(total_result.scalar() or 0)

        invitees_result = await self.db.execute(
            select(Customer)
            .filter(*base_filter)
            .order_by(Customer.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        invitees = list(invitees_result.scalars().all())

        if not invitees:
            return [], total

        invitee_ids = [c.id for c in invitees]
        inviter_ids = list({c.inviter_id for c in invitees if c.inviter_id})

        records_result = await self.db.execute(
            select(CommissionRecord).filter(
                CommissionRecord.tenant_id == tenant_id,
                CommissionRecord.user_id.in_(invitee_ids),
                CommissionRecord.level == 1,
                CommissionRecord.source_type == "FIRST_VERIFY",
            )
        )
        records_by_user = {r.user_id: r for r in records_result.scalars().all()}

        inviters_result = await self.db.execute(
            select(Customer).filter(
                Customer.tenant_id == tenant_id,
                Customer.id.in_(inviter_ids),
            )
        )
        inviters_by_id = {c.id: c for c in inviters_result.scalars().all()}

        rows = []
        for invitee in invitees:
            record = records_by_user.get(invitee.id)
            inviter = inviters_by_id.get(invitee.inviter_id)
            rows.append({
                "invitee_id": str(invitee.id),
                "invitee_name": invitee.name or f"会员{str(invitee.id)[-4:]}",
                "invitee_phone": invitee.phone or "",
                "inviter_id": str(invitee.inviter_id) if invitee.inviter_id else "",
                "inviter_name": (inviter.name if inviter else None) or f"会员{str(invitee.inviter_id)[-4:]}",
                "inviter_phone": inviter.phone if inviter else "",
                "has_visited": record is not None,
                "reward_status": record.status if record else None,
                "reward_amount": float(record.commission_amount) if record else None,
                "record_id": str(record.id) if record else None,
                "first_verify_at": record.created_at.isoformat() if record else None,
                "settled_at": record.settled_at.isoformat() if record and record.settled_at else None,
                "joined_at": invitee.created_at.isoformat() if invitee.created_at else None,
            })

        return rows, total

    async def list_records(
        self, receiver_id: int | None = None, receiver_type: str | None = None,
        skip: int = 0, limit: int = 50,
    ) -> tuple[list[CommissionRecord], int]:
        tenant_id = self.require_tenant_id()
        query = select(CommissionRecord).filter(CommissionRecord.tenant_id == tenant_id)
        if receiver_id:
            query = query.filter(CommissionRecord.receiver_id == receiver_id)
        if receiver_type:
            query = query.filter(CommissionRecord.receiver_type == receiver_type)
        total_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = int(total_result.scalar() or 0)
        result = await self.db.execute(
            query.order_by(CommissionRecord.created_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    async def list_staff_commission_records(self, skip: int = 0, limit: int = 50) -> tuple[list[dict], int]:
        """给"员工推荐"后台页用：员工佣金记录 + 谁推荐的顾客 + 员工姓名，一次拼好。"""
        tenant_id = self.require_tenant_id()
        records, total = await self.list_records(receiver_type="staff", skip=skip, limit=limit)
        if not records:
            return [], total

        staff_ids = list({r.receiver_id for r in records})
        staff_result = await self.db.execute(
            select(Staff).filter(Staff.tenant_id == tenant_id, Staff.id.in_(staff_ids))
        )
        staff_by_id = {s.id: s for s in staff_result.scalars().all()}

        customer_ids = list({r.user_id for r in records})
        customer_result = await self.db.execute(
            select(Customer).filter(Customer.tenant_id == tenant_id, Customer.id.in_(customer_ids))
        )
        customer_by_id = {c.id: c for c in customer_result.scalars().all()}

        rows = []
        for r in records:
            staff = staff_by_id.get(r.receiver_id)
            invitee = customer_by_id.get(r.user_id)
            rows.append({
                "record_id": str(r.id),
                "staff_id": str(r.receiver_id),
                "staff_name": staff.name if staff else f"员工{str(r.receiver_id)[-4:]}",
                "invitee_name": (invitee.name if invitee else None) or f"会员{str(r.user_id)[-4:]}",
                "commission_amount": float(r.commission_amount),
                "status": r.status,
                "first_verify_at": r.created_at.isoformat() if r.created_at else None,
                "settled_at": r.settled_at.isoformat() if r.settled_at else None,
            })
        return rows, total

    async def get_invite_summary_for_member(self, customer_id: int) -> dict:
        tenant_id = self.require_tenant_id()
        rules = await self.get_distribution_rules()

        invited_q = await self.db.execute(
            select(func.count()).select_from(Customer).filter(
                Customer.tenant_id == tenant_id,
                Customer.inviter_id == customer_id,
                Customer.status != -1,
            )
        )
        invited_count = int(invited_q.scalar() or 0)

        invitee_ids_q = await self.db.execute(
            select(Customer.id).filter(
                Customer.tenant_id == tenant_id,
                Customer.inviter_id == customer_id,
                Customer.status != -1,
            )
        )
        invitee_ids = [row[0] for row in invitee_ids_q.fetchall()]

        visited_count = 0
        reward_count = 0
        if invitee_ids:
            visited_q = await self.db.execute(
                select(func.count()).select_from(CommissionRecord).filter(
                    CommissionRecord.tenant_id == tenant_id,
                    CommissionRecord.user_id.in_(invitee_ids),
                    CommissionRecord.level == 1,
                    CommissionRecord.source_type == "FIRST_VERIFY",
                )
            )
            visited_count = int(visited_q.scalar() or 0)
            reward_q = await self.db.execute(
                select(func.count()).select_from(CommissionRecord).filter(
                    CommissionRecord.tenant_id == tenant_id,
                    CommissionRecord.user_id.in_(invitee_ids),
                    CommissionRecord.level == 1,
                    CommissionRecord.source_type == "FIRST_VERIFY",
                    CommissionRecord.status == "SETTLED",
                )
            )
            reward_count = int(reward_q.scalar() or 0)

        inviter_amount = float(rules.get("inviter_reward_amount") or 0)
        invitee_amount = float(rules.get("invitee_reward_amount") or 0)
        min_spend = float(rules.get("invite_reward_min_spend") or 0)
        enabled = rules.get("invite_reward_enabled", False)

        if not enabled:
            # 两行文案必须口径一致——之前 invitee_reward_text 给的是空字符串，前端
            # 兜底逻辑会把它换成默认的"双方均可获得奖励"，跟上面这行"暂未开启"自相矛盾。
            inviter_reward_text = "邀请奖励活动暂未开启"
            invitee_reward_text = "邀请奖励活动暂未开启"
        elif min_spend > 0:
            inviter_reward_text = f"好友首次到店后，你得满{min_spend:.0f}减{inviter_amount:.0f}优惠券"
            invitee_reward_text = f"好友首次到店后，好友再得满{min_spend:.0f}减{invitee_amount:.0f}优惠券"
        else:
            inviter_reward_text = f"好友首次到店后，你得{inviter_amount:.0f}元优惠券"
            invitee_reward_text = f"好友首次到店后，好友再得{invitee_amount:.0f}元优惠券"

        # 获取该用户的短邀请码（惰性生成）
        customer_q = await self.db.execute(
            select(Customer).filter(
                Customer.tenant_id == tenant_id,
                Customer.id == customer_id,
            )
        )
        customer_obj = customer_q.scalar_one_or_none()
        invite_code = await self._ensure_short_invite_code(customer_obj) if customer_obj else str(customer_id)[-6:]

        return {
            "invite_code": invite_code,
            "invited_count": invited_count,
            "visited_count": visited_count,
            "reward_count": reward_count,
            "pending_count": max(0, invited_count - visited_count),
            "inviter_reward_text": inviter_reward_text,
            "invitee_reward_text": invitee_reward_text,
            "invite_reward_enabled": enabled,
        }

    async def list_invite_records_for_member(self, customer_id: int, skip: int = 0, limit: int = 50) -> list[dict]:
        tenant_id = self.require_tenant_id()

        invitees_q = await self.db.execute(
            select(Customer).filter(
                Customer.tenant_id == tenant_id,
                Customer.inviter_id == customer_id,
                Customer.status != -1,
            ).order_by(Customer.created_at.desc()).offset(skip).limit(limit)
        )
        invitees = list(invitees_q.scalars().all())
        if not invitees:
            return []

        invitee_ids = [c.id for c in invitees]
        records_q = await self.db.execute(
            select(CommissionRecord).filter(
                CommissionRecord.tenant_id == tenant_id,
                CommissionRecord.user_id.in_(invitee_ids),
                CommissionRecord.level == 1,
                CommissionRecord.source_type == "FIRST_VERIFY",
            )
        )
        records_by_user = {r.user_id: r for r in records_q.scalars().all()}

        rows = []
        for invitee in invitees:
            record = records_by_user.get(invitee.id)
            phone = invitee.phone or ""
            masked_phone = f"{phone[:3]}****{phone[-4:]}" if len(phone) >= 7 else ""
            name = invitee.name or (f"尾号{phone[-4:]}会员" if len(phone) >= 4 else "会员")
            if record is None:
                reward_status_text = "等待好友到店"
            elif record.status == "PENDING":
                reward_status_text = "奖励待发放"
            else:
                reward_status_text = "奖励已发放"
            rows.append({
                "invitee_id": str(invitee.id),
                "invitee_name": name,
                "invitee_phone_masked": masked_phone,
                "joined_at": invitee.created_at.strftime("%Y-%m-%d %H:%M") if invitee.created_at else "",
                "has_visited": record is not None,
                "reward_status": reward_status_text,
                "visited_at": record.created_at.strftime("%Y-%m-%d %H:%M") if record and record.created_at else "",
            })
        return rows

    async def settle_record(self, record_id: int) -> CommissionRecord | None:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(CommissionRecord).filter(
                CommissionRecord.tenant_id == tenant_id,
                CommissionRecord.id == record_id,
            )
        )
        record = result.scalar_one_or_none()
        if not record:
            return None
        record.status = "SETTLED"
        record.settled_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(record)
        return record
