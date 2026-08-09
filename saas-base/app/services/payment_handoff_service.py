from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.order import Order, OrderItem
from app.models.staff_assisted_payment_handoff import StaffAssistedPaymentHandoff
from app.services.base_service import BaseService

HANDOFF_TTL_MINUTES = 10
HANDOFF_PAGE = "subpkg-order/pages/payment-handoff"
ACTIVE_HANDOFF_STATUSES = ("PENDING_SCAN", "CLAIMED")


def hash_handoff_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _new_scene_token() -> str:
    return secrets.token_hex(12)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


class PaymentHandoffService(BaseService):
    async def create_for_order(
        self,
        *,
        tenant_id: str,
        order_id: int,
        actor_account_id: int | None,
        actor_role: str | None,
    ) -> dict[str, Any]:
        order = await self._load_order_for_staff_handoff(tenant_id, order_id)
        await self._cancel_active_handoffs(tenant_id, order_id)
        token = _new_scene_token()
        row = StaffAssistedPaymentHandoff(
            tenant_id=tenant_id,
            order_id=int(order.id),
            token_hash=hash_handoff_token(token),
            status="PENDING_SCAN",
            created_by_account_id=actor_account_id,
            created_by_role=actor_role,
            expires_at=datetime.utcnow() + timedelta(minutes=HANDOFF_TTL_MINUTES),
        )
        self.db.add(row)
        await self.db.flush()
        return await self._serialize(row, token=token, order=order)

    async def resolve(self, token: str) -> dict[str, Any]:
        row = await self._load_by_token(token)
        order = await self._load_order_by_id(int(row.order_id))
        await self._expire_if_needed(row, order)
        return await self._serialize(row, token=token, order=order)

    async def resolve_latest_for_order(self, *, tenant_id: str, order_id: int) -> dict[str, Any] | None:
        result = await self.db.execute(
            select(StaffAssistedPaymentHandoff)
            .where(
                StaffAssistedPaymentHandoff.tenant_id == tenant_id,
                StaffAssistedPaymentHandoff.order_id == int(order_id),
            )
            .order_by(StaffAssistedPaymentHandoff.created_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        order = await self._load_order_by_id(int(row.order_id))
        await self._expire_if_needed(row, order)
        return await self._serialize(row, token=None, order=order)

    async def claim(self, *, token: str, customer_id: int, openid: str | None) -> dict[str, Any]:
        row = await self._load_by_token(token, for_update=True)
        order = await self._load_order_by_id(int(row.order_id), for_update=True)
        await self._expire_if_needed(row, order)
        if row.status == "EXPIRED":
            raise ValueError("支付二维码已过期，请联系服务员重新生成")
        if row.status == "CANCELLED" or order.status != "pending_payment" or order.payment_status == "paid":
            raise ValueError("该订单已失效或已支付")
        if row.claimed_customer_id and int(row.claimed_customer_id) != int(customer_id):
            raise ValueError("该支付单已被其他顾客领取")

        customer_result = await self.db.execute(
            select(Customer).where(
                Customer.id == int(customer_id),
                Customer.tenant_id == str(order.tenant_id),
                Customer.status == 1,
            )
        )
        if not customer_result.scalar_one_or_none():
            raise ValueError("会员不存在或已停用")

        if order.customer_id and int(order.customer_id) != int(customer_id):
            raise ValueError("该订单已绑定其他顾客")
        order.customer_id = int(customer_id)
        row.status = "CLAIMED"
        row.claimed_customer_id = int(customer_id)
        row.claimed_openid = (openid or "")[:128] or None
        row.claimed_at = row.claimed_at or datetime.utcnow()
        await self.db.flush()
        return await self._serialize(row, token=token, order=order)

    async def mark_order_paid(self, order_id: int) -> None:
        result = await self.db.execute(
            select(StaffAssistedPaymentHandoff)
            .where(
                StaffAssistedPaymentHandoff.order_id == int(order_id),
                StaffAssistedPaymentHandoff.status.in_(ACTIVE_HANDOFF_STATUSES),
            )
            .order_by(StaffAssistedPaymentHandoff.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        row = result.scalar_one_or_none()
        if not row:
            return
        row.status = "PAID"
        row.paid_at = row.paid_at or datetime.utcnow()
        await self.db.flush()

    async def _load_order_for_staff_handoff(self, tenant_id: str, order_id: int) -> Order:
        order = await self._load_order_by_id(order_id, for_update=True)
        if str(order.tenant_id) != str(tenant_id):
            raise ValueError("无权操作该订单")
        if order.source != "staff_assisted" or order.payment_mode != "prepay":
            raise ValueError("该订单不是员工代客预付加菜单")
        if order.status != "pending_payment" or order.payment_status == "paid":
            raise ValueError("该订单已支付或已取消")
        if not order.created_by_account_id:
            raise ValueError("缺少员工建单审计信息")
        return order

    async def _cancel_active_handoffs(self, tenant_id: str, order_id: int) -> None:
        result = await self.db.execute(
            select(StaffAssistedPaymentHandoff)
            .where(
                StaffAssistedPaymentHandoff.tenant_id == tenant_id,
                StaffAssistedPaymentHandoff.order_id == int(order_id),
                StaffAssistedPaymentHandoff.status.in_(ACTIVE_HANDOFF_STATUSES),
            )
            .with_for_update()
        )
        now = datetime.utcnow()
        for row in result.scalars().all():
            row.status = "CANCELLED"
            row.cancelled_at = now

    async def _load_by_token(self, token: str, *, for_update: bool = False) -> StaffAssistedPaymentHandoff:
        token = (token or "").strip()
        if not token:
            raise ValueError("缺少支付二维码")
        stmt = select(StaffAssistedPaymentHandoff).where(
            StaffAssistedPaymentHandoff.token_hash == hash_handoff_token(token)
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            raise ValueError("支付二维码无效")
        return row

    async def _load_order_by_id(self, order_id: int, *, for_update: bool = False) -> Order:
        stmt = select(Order).where(Order.id == int(order_id))
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.db.execute(stmt)
        order = result.scalar_one_or_none()
        if not order:
            raise ValueError("订单不存在")
        return order

    async def _expire_if_needed(self, row: StaffAssistedPaymentHandoff, order: Order) -> None:
        if row.status in ("PAID", "CANCELLED", "EXPIRED"):
            return
        if order.payment_status == "paid":
            row.status = "PAID"
            row.paid_at = row.paid_at or datetime.utcnow()
            await self.db.flush()
            return
        if row.expires_at < datetime.utcnow():
            row.status = "EXPIRED"
            await self.db.flush()

    async def _serialize(
        self,
        row: StaffAssistedPaymentHandoff,
        *,
        token: str | None,
        order: Order,
    ) -> dict[str, Any]:
        items_result = await self.db.execute(select(OrderItem).where(OrderItem.order_id == int(order.id)))
        items = [
            {
                "dish_id": str(item.dish_id) if item.dish_id else None,
                "name": item.name,
                "price": float(item.price),
                "qty": int(item.qty),
            }
            for item in items_result.scalars().all()
        ]
        data: dict[str, Any] = {
            "id": str(row.id),
            "order_id": str(order.id),
            "tenant_id": str(order.tenant_id),
            "table_no": order.table_no,
            "amount": float(order.total or 0),
            "status": row.status,
            "order_status": order.status,
            "payment_status": order.payment_status,
            "page": HANDOFF_PAGE,
            "expires_at": _iso(row.expires_at),
            "claimed_customer_id": str(row.claimed_customer_id) if row.claimed_customer_id else None,
            "items": items,
        }
        if token:
            data["scene"] = token
        return data
