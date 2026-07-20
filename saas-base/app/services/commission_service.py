import logging
import random
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.future import select

from app.models.commission_record import CommissionRecord
from app.models.customer import Customer
from app.models.tenant_config import TenantConfig
from app.services.base_service import BaseService

logger = logging.getLogger(__name__)

# 邀请码字符表（同 customer_service，保持一致）
_INVITE_CODE_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


DEFAULT_DISTRIBUTION_RULES = {
    "invite_reward_enabled": False,
    "inviter_reward_amount": 5.0,
    "invitee_reward_amount": 5.0,
    "invite_reward_min_spend": 0.0,
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

    async def get_distribution_rules(self) -> dict:
        tenant_id = self.require_tenant_id()
        result = await self.db.execute(
            select(TenantConfig).filter(TenantConfig.tenant_id == tenant_id)
        )
        config = result.scalar_one_or_none()
        settings = {}
        if config:
            settings = ((config.plugin_settings or {}).get("distribution") or {})
        merged = {**DEFAULT_DISTRIBUTION_RULES, **settings}
        # Migrate legacy 'enabled' field
        if "invite_reward_enabled" not in settings and "enabled" in settings:
            merged["invite_reward_enabled"] = settings["enabled"]
        return merged

    async def update_distribution_rules(self, data: dict) -> dict:
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
        current = {**DEFAULT_DISTRIBUTION_RULES, **(plugin_settings.get("distribution") or {})}
        cleaned = {
            "invite_reward_enabled": bool(data.get("invite_reward_enabled", current["invite_reward_enabled"])),
            "inviter_reward_amount": float(data.get("inviter_reward_amount", current["inviter_reward_amount"]) or 0),
            "invitee_reward_amount": float(data.get("invitee_reward_amount", current["invitee_reward_amount"]) or 0),
            "invite_reward_min_spend": float(data.get("invite_reward_min_spend", current["invite_reward_min_spend"]) or 0),
            "invite_reward_valid_days": int(data.get("invite_reward_valid_days", current["invite_reward_valid_days"]) or 30),
            "invite_reward_trigger": "FIRST_VERIFY",
        }
        plugin_settings["distribution"] = cleaned
        config.plugin_settings = plugin_settings
        await self.db.commit()
        await self.db.refresh(config)
        return cleaned

    async def bind_inviter_for_new_customer(self, customer: Customer, invite_code: str | None) -> Customer:
        tenant_id = self.require_tenant_id()
        if not customer or customer.inviter_id or not invite_code:
            return customer

        invite_code = str(invite_code).strip()
        inviter: Customer | None = None

        # 优先按短邀请码查找（新格式：6 位字母数字，不区分大小写）
        short_code = invite_code.upper()
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

        if not inviter or inviter.id == customer.id:
            return customer

        customer.inviter_id = inviter.id
        customer.inviter_parent_id = inviter.inviter_id
        await self.db.commit()
        await self.db.refresh(customer)
        return customer

    async def record_after_verify(self, coupon, template=None) -> list[CommissionRecord]:
        tenant_id = self.require_tenant_id()
        rules = await self.get_distribution_rules()

        enabled = rules.get("invite_reward_enabled", rules.get("enabled", False))
        if not enabled:
            return []

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
        inviter_amount = Decimal(str(rules.get("inviter_reward_amount") or 0))
        invitee_amount = Decimal(str(rules.get("invitee_reward_amount") or 0))
        min_spend = float(rules.get("invite_reward_min_spend") or 0)
        valid_days = int(rules.get("invite_reward_valid_days") or 30)

        created = []

        if inviter_amount > 0:
            record = CommissionRecord(
                tenant_id=tenant_id,
                user_id=customer.id,
                order_id=str(coupon.id),
                amount=spend_amount,
                level=1,
                receiver_id=customer.inviter_id,
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

        # ── 第二步：实际发放优惠券，成功则同步结算 ────────────────────────
        # 发券失败时记录保留为 PENDING（可人工补发），不影响核销主流程
        try:
            from app.services.coupon_service import CouponService
            from app.core.logger import logger

            coupon_svc = CouponService(self.db)
            coupon_svc.set_tenant_id(tenant_id)

            reward_map = {
                1: {
                    "receiver_id": customer.inviter_id,
                    "amount": float(inviter_amount),
                    "template_name": "邀请奖励券",
                    "log_role": "邀请人",
                },
                2: {
                    "receiver_id": customer.id,
                    "amount": float(invitee_amount),
                    "template_name": "到店奖励券",
                    "log_role": "被邀请人",
                },
            }

            now = datetime.utcnow()
            any_settled = False
            for rec in created:
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
        tenant_id = self.require_tenant_id()

        base_filter = (
            Customer.tenant_id == tenant_id,
            Customer.inviter_id.isnot(None),
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

    async def list_records(self, receiver_id: int | None = None, skip: int = 0, limit: int = 50) -> tuple[list[CommissionRecord], int]:
        tenant_id = self.require_tenant_id()
        query = select(CommissionRecord).filter(CommissionRecord.tenant_id == tenant_id)
        if receiver_id:
            query = query.filter(CommissionRecord.receiver_id == receiver_id)
        total_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = int(total_result.scalar() or 0)
        result = await self.db.execute(
            query.order_by(CommissionRecord.created_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

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
            inviter_reward_text = "邀请奖励活动暂未开启"
            invitee_reward_text = ""
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
