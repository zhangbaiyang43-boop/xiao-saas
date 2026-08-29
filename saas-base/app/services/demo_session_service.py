"""Isolated, short-lived merchant Demo session allocation."""

from datetime import datetime, timedelta
import hashlib
import secrets
import time

from sqlalchemy import select

from app.config import settings
from app.core.redis_client import redis_client
from app.core.security import (
    create_demo_session_token,
    decode_demo_launch_code,
)
from app.models.dining import DiningSession
from app.models.entrance_code import EntranceCode
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.services.base_service import BaseService
from app.services.dining_session_service import DiningSessionService


class DemoUnavailableError(RuntimeError):
    pass


class DemoRateLimitedError(RuntimeError):
    pass


class DemoPoolFullError(RuntimeError):
    pass


class DemoInvalidLaunchError(RuntimeError):
    pass


class DemoOrderNotFoundError(RuntimeError):
    pass


class DemoActionDeniedError(RuntimeError):
    pass


async def enforce_demo_start_limit(ip: str, launch_code: str) -> None:
    if not settings.REDIS_ENABLED:
        raise DemoUnavailableError("体验服务暂不可用")

    fingerprint = hashlib.sha256(launch_code.encode("utf-8")).hexdigest()[:16]
    minute = int(time.time() // 60)
    limits = [
        (
            f"demo:start:ip:{ip}:{minute}",
            settings.DEMO_START_IP_LIMIT_PER_MINUTE,
        ),
        (
            f"demo:start:code:{fingerprint}:{minute}",
            settings.DEMO_START_CODE_LIMIT_PER_MINUTE,
        ),
    ]
    try:
        async with redis_client.pipeline(transaction=True) as pipeline:
            for key, _limit in limits:
                pipeline.incr(key)
                pipeline.expire(key, 90)
            values = await pipeline.execute()
    except Exception as exc:
        raise DemoUnavailableError("体验服务暂不可用") from exc

    counts = [int(values[0]), int(values[2])]
    if any(count > limit for count, (_key, limit) in zip(counts, limits)):
        raise DemoRateLimitedError("请求过于频繁，请稍后再试")


class DemoSessionService(BaseService):
    async def start_session(self, launch_code: str, client_ip: str) -> dict:
        demo_tenant_id = (settings.DEMO_TENANT_ID or "").strip()
        if not demo_tenant_id:
            raise DemoUnavailableError("体验服务暂不可用")
        if not decode_demo_launch_code((launch_code or "").strip()):
            raise DemoInvalidLaunchError("体验入口无效或已过期")

        await enforce_demo_start_limit(client_ip or "unknown", launch_code)

        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=settings.DEMO_SESSION_MINUTES)
        attempted_code_ids: list[int] = []

        try:
            tenant_result = await self.db.execute(
                select(Tenant).where(
                    Tenant.tenant_id == demo_tenant_id,
                    Tenant.status.is_(True),
                )
            )
            tenant = tenant_result.scalar_one_or_none()
            if tenant is None:
                raise DemoUnavailableError("体验服务暂不可用")

            for _index in range(settings.DEMO_TABLE_POOL_SIZE):
                code_query = (
                    select(EntranceCode)
                    .where(
                        EntranceCode.tenant_id == demo_tenant_id,
                        EntranceCode.channel == "DEMO",
                        EntranceCode.entry_type == "table",
                        EntranceCode.status == 1,
                    )
                    .order_by(EntranceCode.table_no, EntranceCode.id)
                    # plain FOR UPDATE, not SKIP LOCKED: production MySQL is < 8.0.
                    # Concurrent demo starts serialize on the locked row instead
                    # of skipping it; the attempted_code_ids exclusion + active-
                    # session re-check below still pick a different free table.
                    .with_for_update()
                    .limit(1)
                )
                if attempted_code_ids:
                    code_query = code_query.where(
                        EntranceCode.id.notin_(attempted_code_ids)
                    )
                code_result = await self.db.execute(code_query)
                entrance_code = code_result.scalar_one_or_none()
                if entrance_code is None:
                    break
                attempted_code_ids.append(int(entrance_code.id))

                table_no = (entrance_code.table_no or "").strip()
                if not table_no or not entrance_code.image_url:
                    continue

                session_result = await self.db.execute(
                    select(DiningSession)
                    .where(
                        DiningSession.tenant_id == demo_tenant_id,
                        DiningSession.table_no == table_no,
                        DiningSession.status == "OPEN",
                    )
                    .order_by(DiningSession.started_at.desc())
                    .with_for_update()
                    .limit(1)
                )
                active_session = session_result.scalar_one_or_none()
                if active_session is not None and active_session.started_at > cutoff:
                    continue
                if active_session is not None:
                    active_session.status = "EXPIRED"
                    active_session.active_key = None
                    active_session.closed_at = now
                    active_session.closed_by = "demo_timeout"
                    await self.db.flush()

                resolved = await DiningSessionService(self.db).resolve_session(
                    tenant_id=demo_tenant_id,
                    table_no=table_no,
                    client_id=f"demo-admin-{secrets.token_hex(8)}",
                )
                dining_session_id = str(resolved["dining_session_id"])
                expires_at = now + timedelta(minutes=settings.DEMO_SESSION_MINUTES)
                demo_token = create_demo_session_token(
                    tenant_id=demo_tenant_id,
                    dining_session_id=dining_session_id,
                    table_no=table_no,
                    expires_delta=timedelta(minutes=settings.DEMO_SESSION_MINUTES),
                )
                await self.db.commit()
                return {
                    "demoToken": demo_token,
                    "expiresAt": expires_at.isoformat(),
                    "diningSessionId": dining_session_id,
                    "tableNo": table_no,
                    "customerCodeImageUrl": entrance_code.image_url,
                    "shopName": tenant.name,
                }
        except Exception:
            await self.db.rollback()
            raise

        await self.db.rollback()
        raise DemoPoolFullError("体验人数较多，请稍后再试")

    async def get_session_snapshot(
        self, tenant_id: str, dining_session_id: int | str
    ) -> dict:
        session_result = await self.db.execute(
            select(DiningSession).where(
                DiningSession.id == int(dining_session_id),
                DiningSession.tenant_id == tenant_id,
            )
        )
        session = session_result.scalar_one_or_none()
        if session is None:
            raise DemoOrderNotFoundError("体验会话不存在")

        orders_result = await self.db.execute(
            select(Order)
            .where(
                Order.tenant_id == tenant_id,
                Order.dining_session_id == int(dining_session_id),
            )
            .order_by(Order.created_at, Order.id)
        )
        orders = list(orders_result.scalars().all())
        items_by_order = await self._load_items_by_order(orders)
        return {
            "diningSessionId": str(session.id),
            "tableNo": session.table_no or "",
            "sessionStatus": session.status,
            "orders": [
                self._serialize_demo_order(order, items_by_order.get(order.id, []))
                for order in orders
            ],
        }

    async def update_order_status(
        self,
        *,
        tenant_id: str,
        dining_session_id: int | str,
        order_id: int | str,
        status: str,
    ) -> dict:
        if status not in {"preparing", "done"}:
            raise DemoActionDeniedError("体验模式不允许此订单状态")
        order = await self._load_scoped_order(
            tenant_id=tenant_id,
            dining_session_id=dining_session_id,
            order_id=order_id,
        )

        from app.api.v1.orders import OrderStatusUpdate
        from app.services.order_lifecycle_service import OrderLifecycleService

        lifecycle = OrderLifecycleService(self.db)
        lifecycle.set_tenant_id(tenant_id)
        result = await lifecycle.update_order_status(
            int(order.id),
            OrderStatusUpdate(status=status),
            account_id=None,
            role="demo",
        )
        if result.code == 404:
            raise DemoOrderNotFoundError("订单不存在")
        if result.code != 200:
            raise DemoActionDeniedError(result.msg)
        return await self._load_serialized_order(
            tenant_id=tenant_id,
            dining_session_id=dining_session_id,
            order_id=order.id,
        )

    async def serve_order(
        self,
        *,
        tenant_id: str,
        dining_session_id: int | str,
        order_id: int | str,
    ) -> dict:
        order = await self._load_scoped_order(
            tenant_id=tenant_id,
            dining_session_id=dining_session_id,
            order_id=order_id,
        )

        from app.services.order_lifecycle_service import OrderLifecycleService

        lifecycle = OrderLifecycleService(self.db)
        lifecycle.set_tenant_id(tenant_id)
        result = await lifecycle.serve_order(
            int(order.id), account_id=None, role="demo"
        )
        if result.code == 404:
            raise DemoOrderNotFoundError("订单不存在")
        if result.code != 200:
            raise DemoActionDeniedError(result.msg)
        return await self._load_serialized_order(
            tenant_id=tenant_id,
            dining_session_id=dining_session_id,
            order_id=order.id,
        )

    async def _load_scoped_order(
        self,
        *,
        tenant_id: str,
        dining_session_id: int | str,
        order_id: int | str,
    ) -> Order:
        result = await self.db.execute(
            select(Order).where(
                Order.id == int(order_id),
                Order.tenant_id == tenant_id,
                Order.dining_session_id == int(dining_session_id),
            )
        )
        order = result.scalar_one_or_none()
        if order is None:
            raise DemoOrderNotFoundError("订单不存在")
        return order

    async def _load_serialized_order(
        self,
        *,
        tenant_id: str,
        dining_session_id: int | str,
        order_id: int | str,
    ) -> dict:
        order = await self._load_scoped_order(
            tenant_id=tenant_id,
            dining_session_id=dining_session_id,
            order_id=order_id,
        )
        items_by_order = await self._load_items_by_order([order])
        return self._serialize_demo_order(order, items_by_order.get(order.id, []))

    async def _load_items_by_order(
        self, orders: list[Order]
    ) -> dict[int, list[OrderItem]]:
        if not orders:
            return {}
        order_ids = [order.id for order in orders]
        result = await self.db.execute(
            select(OrderItem)
            .where(OrderItem.order_id.in_(order_ids))
            .order_by(OrderItem.id)
        )
        items_by_order: dict[int, list[OrderItem]] = {}
        for item in result.scalars().all():
            items_by_order.setdefault(item.order_id, []).append(item)
        return items_by_order

    @staticmethod
    def _serialize_demo_order(order: Order, items: list[OrderItem]) -> dict:
        return {
            "orderId": str(order.id),
            "displayOrderNo": str(order.id)[-4:],
            "tableNo": order.table_no or "",
            "status": order.status,
            "servedAt": order.served_at.isoformat() if order.served_at else None,
            "createdAt": order.created_at.isoformat() if order.created_at else None,
            "remark": order.remark or "",
            "items": [
                {
                    "name": item.name,
                    "quantity": item.qty,
                    "remark": item.item_remark or "",
                }
                for item in items
            ],
        }
