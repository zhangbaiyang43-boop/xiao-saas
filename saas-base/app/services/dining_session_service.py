import hashlib
import secrets
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dining import DiningParticipant, DiningSession
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem


SESSION_EXPIRE_HOURS = 12


def hash_participant_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def make_client_id() -> str:
    return secrets.token_urlsafe(24)


def make_participant_token() -> str:
    return secrets.token_urlsafe(32)


class DiningSessionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    async def get_participant_ordinals(db: AsyncSession, tenant_id: str, session_ids: list) -> dict:
        """给一批桌台会话里的每个参与者，按各自加入这一桌的时间顺序编号（从 1 开始）——
        纯粹用来给顾客端"已点菜品"和商户端接单页显示"这道菜是第几位点的"，不落库，
        每次现算，保证两端看到的编号永远是同一套算法算出来的，不会对不上。

        编号只是"这一桌第几个加入的人"，跟真实身份（是不是会员、叫什么名字）无关——
        同桌可能互相不认识（比如工作饭局），不适合直接把真实姓名亮给同桌其他人看。
        """
        if not session_ids:
            return {}
        result = await db.execute(
            select(DiningParticipant.id, DiningParticipant.session_id)
            .where(
                DiningParticipant.tenant_id == tenant_id,
                DiningParticipant.session_id.in_(session_ids),
            )
            .order_by(DiningParticipant.session_id, DiningParticipant.joined_at, DiningParticipant.id)
        )
        ordinal_by_participant_id = {}
        counter_by_session = {}
        for participant_id, session_id in result.all():
            counter_by_session[session_id] = counter_by_session.get(session_id, 0) + 1
            ordinal_by_participant_id[participant_id] = counter_by_session[session_id]
        return ordinal_by_participant_id

    async def resolve_session(
        self,
        tenant_id: str,
        table_no: str,
        client_id: str | None = None,
        participant_token: str | None = None,
        customer_id: int | None = None,
        openid: str | None = None,
    ) -> dict:
        now = datetime.utcnow()
        table_no = (table_no or "").strip()
        if not tenant_id or not table_no:
            raise ValueError("缺少门店或桌号")

        session = await self._get_or_create_open_session(tenant_id, table_no, now)
        participant, raw_token = await self._get_or_create_participant(
            session=session,
            now=now,
            client_id=(client_id or "").strip() or None,
            participant_token=(participant_token or "").strip() or None,
            customer_id=customer_id,
            openid=openid,
        )
        session.last_activity_at = now
        await self.db.flush()
        return {
            "dining_session_id": str(session.id),
            "participant_id": str(participant.id),
            "participant_token": raw_token,
            "client_id": participant.client_id,
            "tenant_id": tenant_id,
            "table_no": table_no,
            "session_status": session.status,
        }

    async def get_or_create_open_session_for_staff(self, tenant_id: str, table_no: str) -> DiningSession:
        """服务员在 admin-h5 代客加单时调用：只拿到（或建好）这一桌当前 OPEN 的会话，
        不像顾客扫码那样创建/绑定 participant——代点单不冒充某个具体顾客的身份，
        只挂在桌台会话下，跟顾客自己点的单一起累计进桌台总账。"""
        table_no = (table_no or "").strip()
        if not tenant_id or not table_no:
            raise ValueError("缺少门店或桌号")
        now = datetime.utcnow()
        session = await self._get_or_create_open_session(tenant_id, table_no, now)
        session.last_activity_at = now
        await self.db.flush()
        return session

    async def bind_participant_to_customer(
        self,
        tenant_id: str,
        participant_token: str,
        customer_id: int,
        openid: str | None = None,
    ) -> DiningParticipant | None:
        token_hash = hash_participant_token(participant_token)
        result = await self.db.execute(
            select(DiningParticipant).where(
                DiningParticipant.tenant_id == tenant_id,
                DiningParticipant.guest_token_hash == token_hash,
            )
        )
        participant = result.scalar_one_or_none()
        if not participant:
            return None
        participant.customer_id = customer_id
        if openid:
            participant.openid = openid
        participant.last_active_at = datetime.utcnow()
        await self.db.flush()
        return participant

    async def get_session_status(self, tenant_id: str, dining_session_id: int) -> str | None:
        result = await self.db.execute(
            select(DiningSession.status).where(
                DiningSession.id == dining_session_id,
                DiningSession.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_checkout_requested_at(self, tenant_id: str, dining_session_id: int) -> datetime | None:
        result = await self.db.execute(
            select(DiningSession.checkout_requested_at).where(
                DiningSession.id == dining_session_id,
                DiningSession.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_closed_at(self, tenant_id: str, dining_session_id: int) -> datetime | None:
        """真正的结账时间（商家点"结账"那一刻），区别于订单的下单时间——
        顾客端"查看结账详情"要展示的就是这个，不是 created_at。"""
        result = await self.db.execute(
            select(DiningSession.closed_at).where(
                DiningSession.id == dining_session_id,
                DiningSession.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def set_checkout_request(
        self,
        tenant_id: str,
        dining_session_id: int,
        requested: bool,
        participant_token: str | None = None,
        customer_id: int | None = None,
    ) -> dict | None:
        """顾客点"吃好了，去结账"时调用：只在本桌参与者身份校验通过、且会话仍 OPEN 时才记录请求时间，
        商家后台据此给这一桌一个"顾客催结账"的可见信号，而不是像过去那样只弹一句本地提示就结束了。"""
        session_result = await self.db.execute(
            select(DiningSession).where(
                DiningSession.id == dining_session_id,
                DiningSession.tenant_id == tenant_id,
            ).with_for_update()
        )
        session = session_result.scalar_one_or_none()
        if not session or session.status != "OPEN":
            return None

        if participant_token:
            token_hash = hash_participant_token(participant_token)
            participant_result = await self.db.execute(
                select(DiningParticipant).where(
                    DiningParticipant.tenant_id == tenant_id,
                    DiningParticipant.session_id == dining_session_id,
                    DiningParticipant.guest_token_hash == token_hash,
                )
            )
            if not participant_result.scalar_one_or_none():
                return None
        elif customer_id:
            participant_result = await self.db.execute(
                select(DiningParticipant).where(
                    DiningParticipant.tenant_id == tenant_id,
                    DiningParticipant.session_id == dining_session_id,
                    DiningParticipant.customer_id == customer_id,
                )
            )
            if not participant_result.scalar_one_or_none():
                return None
        else:
            return None

        if requested:
            if not session.checkout_requested_at:
                session.checkout_requested_at = datetime.utcnow()
        else:
            session.checkout_requested_at = None
        await self.db.flush()
        return {
            "dining_session_id": str(session.id),
            "checkout_requested_at": session.checkout_requested_at.isoformat() if session.checkout_requested_at else None,
        }
    async def list_session_orders(
        self,
        tenant_id: str,
        dining_session_id: int,
        participant_token: str | None = None,
        customer_id: int | None = None,
    ) -> dict:
        empty_result = {"orders": [], "table_total": "0.00", "item_count": 0}

        session_result = await self.db.execute(
            select(DiningSession).where(
                DiningSession.id == dining_session_id,
                DiningSession.tenant_id == tenant_id,
            )
        )
        session = session_result.scalar_one_or_none()
        # identity_mismatch 区分"这一桌真的还没人点单"和"调用方的本桌身份对不上号"——
        # 两者对客户端来说必须是不同的信号：前者就该显示空列表，后者需要客户端重新
        # 建立本桌身份再重试，不然会一直静默展示一张空桌子，顾客也不知道发生了什么。
        if not session:
            return {**empty_result, "identity_mismatch": True}

        if participant_token:
            token_hash = hash_participant_token(participant_token)
            participant_result = await self.db.execute(
                select(DiningParticipant).where(
                    DiningParticipant.tenant_id == tenant_id,
                    DiningParticipant.session_id == dining_session_id,
                    DiningParticipant.guest_token_hash == token_hash,
                )
            )
            if not participant_result.scalar_one_or_none():
                return {**empty_result, "identity_mismatch": True}
        elif customer_id:
            participant_result = await self.db.execute(
                select(DiningParticipant).where(
                    DiningParticipant.tenant_id == tenant_id,
                    DiningParticipant.session_id == dining_session_id,
                    DiningParticipant.customer_id == customer_id,
                )
            )
            if not participant_result.scalar_one_or_none():
                return {**empty_result, "identity_mismatch": True}
        else:
            return {**empty_result, "identity_mismatch": True}

        # 本桌当前人数：在"没有订单"分支之前算，因为"第一个人还没点单、第二个人扫码
        # 加入"这个时刻恰恰是最需要提示的场景——如果放在下面 `if not orders` 之后算，
        # 这种情况会直接命中空结果提前返回，永远算不到人数变化。
        participant_count_result = await self.db.execute(
            select(func.count()).select_from(DiningParticipant).where(
                DiningParticipant.tenant_id == tenant_id,
                DiningParticipant.session_id == dining_session_id,
            )
        )
        participant_count = int(participant_count_result.scalar() or 0)
        empty_result = {**empty_result, "participant_count": participant_count}

        orders_result = await self.db.execute(
            select(Order)
            .where(
                Order.tenant_id == tenant_id,
                Order.dining_session_id == dining_session_id,
            )
            .order_by(Order.created_at.desc())
        )
        orders = list(orders_result.scalars().all())
        if not orders:
            return empty_result

        order_ids = [order.id for order in orders]
        items_result = await self.db.execute(
            select(OrderItem).where(OrderItem.order_id.in_(order_ids))
        )
        items_by_order: dict[int, list[OrderItem]] = {}
        for item in items_result.scalars().all():
            items_by_order.setdefault(item.order_id, []).append(item)

        # OrderItem 只保留下单时的名称/价格快照，没有存图——顾客端"本桌已点菜品"要显示
        # 菜品图就得回菜单表按 dish_id 查一次，查不到（菜品后来被删了）就让前端退回占位图。
        dish_ids = {item.dish_id for items in items_by_order.values() for item in items if item.dish_id}
        dish_images: dict[int, str] = {}
        if dish_ids:
            menu_items_result = await self.db.execute(
                select(MenuItem.id, MenuItem.image).where(
                    MenuItem.tenant_id == tenant_id,
                    MenuItem.id.in_(dish_ids),
                )
            )
            dish_images = {row[0]: row[1] for row in menu_items_result.all() if row[1]}

        participant_ordinals = await self.get_participant_ordinals(self.db, tenant_id, [dining_session_id])

        serialized_orders = [
            self._serialize_order(
                order,
                items_by_order.get(order.id, []),
                dish_images,
                participant_ordinals.get(order.participant_id),
            )
            for order in orders
        ]

        # 桌台累计金额/份数统计"共用一本账"的两种模式——桌台账单和餐后付款（后端结账时
        # 都是走 settle_table 按整桌一次性结清），且未取消/未拒单的子订单；取消的子订单仍然
        # 原样返回给前端展示（标记"已取消"），但不计入有效金额和份数。
        valid_orders = [
            order for order in orders
            if order.payment_mode in ("table_account", "postpay") and order.status not in ("cancelled", "rejected")
        ]
        table_total = sum(
            (Decimal(str(order.total or 0)) for order in valid_orders), Decimal("0")
        )
        item_count = sum(
            (item.qty or 0)
            for order in valid_orders
            for item in items_by_order.get(order.id, [])
        )

        return {
            "orders": serialized_orders,
            "table_total": str(table_total.quantize(Decimal("0.01"))),
            "item_count": item_count,
            "participant_count": participant_count,
        }

    async def _get_or_create_open_session(self, tenant_id: str, table_no: str, now: datetime) -> DiningSession:
        active_key = f"{tenant_id}:{table_no}"
        result = await self.db.execute(
            select(DiningSession)
            .where(DiningSession.active_key == active_key)
            .with_for_update()
        )
        session = result.scalar_one_or_none()
        if session:
            is_stale = bool(
                session.last_activity_at and session.last_activity_at < now - timedelta(hours=SESSION_EXPIRE_HOURS)
            )
            if is_stale:
                # 静默把超过 12 小时没动静的桌台标成 EXPIRED 之前，先确认这一桌没有还没
                # 走完结账流程的订单（哪怕只是"已出餐、等结账"）——不然这条订单挂在一个
                # 已经过期关闭的 session 下，settle_table 只认 status=="OPEN"，以后再也
                # 没有任何流程能捞到它，商家做了菜却收不到这笔钱，还完全不知道原因。
                unsettled_result = await self.db.execute(
                    select(func.count(Order.id)).where(
                        Order.dining_session_id == session.id,
                        Order.status.notin_(("settled", "cancelled", "rejected")),
                    )
                )
                has_unsettled_orders = int(unsettled_result.scalar() or 0) > 0
                if not has_unsettled_orders:
                    session.status = "EXPIRED"
                    session.closed_at = now
                    session.active_key = None
                    from app.services.pickup_no_service import PickupNoService
                    await PickupNoService(self.db).release_session_assignment(
                        tenant_id, session, clear_session_field=True
                    )
                else:
                    return session
            else:
                return session

        new_session = DiningSession(
            tenant_id=tenant_id,
            table_no=table_no,
            status="OPEN",
            active_key=active_key,
            started_at=now,
            last_activity_at=now,
        )
        try:
            async with self.db.begin_nested():
                self.db.add(new_session)
                await self.db.flush()
        except IntegrityError:
            # 同一桌两个人几乎同时扫码，另一个并发请求已经抢先建好了会话，直接复用它，
            # 而不是让这一次请求报错——active_key 上的唯一约束是最后一道防线，这里接住它。
            result = await self.db.execute(
                select(DiningSession)
                .where(DiningSession.active_key == active_key)
                .with_for_update()
            )
            existing = result.scalar_one_or_none()
            if not existing:
                raise
            return existing
        return new_session

    async def _get_or_create_participant(
        self,
        session: DiningSession,
        now: datetime,
        client_id: str | None,
        participant_token: str | None,
        customer_id: int | None,
        openid: str | None,
    ) -> tuple[DiningParticipant, str]:
        raw_token = participant_token or make_participant_token()
        token_hash = hash_participant_token(raw_token)

        participant = None
        if participant_token:
            result = await self.db.execute(
                select(DiningParticipant).where(
                    DiningParticipant.session_id == session.id,
                    DiningParticipant.guest_token_hash == token_hash,
                )
            )
            participant = result.scalar_one_or_none()
            if not participant:
                raw_token = make_participant_token()
                token_hash = hash_participant_token(raw_token)

        if not participant and customer_id:
            result = await self.db.execute(
                select(DiningParticipant).where(
                    DiningParticipant.session_id == session.id,
                    DiningParticipant.customer_id == customer_id,
                )
            )
            participant = result.scalar_one_or_none()

        if not participant and client_id:
            result = await self.db.execute(
                select(DiningParticipant).where(
                    DiningParticipant.session_id == session.id,
                    DiningParticipant.client_id == client_id,
                )
            )
            participant = result.scalar_one_or_none()

        if participant:
            participant.last_active_at = now
            if customer_id and not participant.customer_id:
                participant.customer_id = customer_id
            if openid and not participant.openid:
                participant.openid = openid
            # 必须让 DB hash 与返回给客户端的 raw_token 一致。
            # 旧逻辑只在 hash 为空时写入：当客户端 token 对不上、却靠 customer_id/
            # client_id 找回同一人时，前面已经 mint 了新 token，若不覆盖 hash，
            # 客户端会存下无效 token，后续 createOrder 永久 409。
            if participant.guest_token_hash != token_hash:
                participant.guest_token_hash = token_hash
            return participant, raw_token

        new_participant = DiningParticipant(
            tenant_id=session.tenant_id,
            session_id=session.id,
            customer_id=customer_id,
            openid=openid,
            guest_token_hash=token_hash,
            client_id=client_id or make_client_id(),
            joined_at=now,
            last_active_at=now,
        )
        try:
            async with self.db.begin_nested():
                self.db.add(new_participant)
                await self.db.flush()
        except IntegrityError:
            # 同一桌两个请求几乎同时建同一个人的 participant 记录（比如同一 customer_id
            # 或同一 client_id 重复扫码），另一个并发请求已经抢先建好了，直接复用它。
            existing = None
            if customer_id:
                result = await self.db.execute(
                    select(DiningParticipant).where(
                        DiningParticipant.session_id == session.id,
                        DiningParticipant.customer_id == customer_id,
                    )
                )
                existing = result.scalar_one_or_none()
            if not existing and client_id:
                result = await self.db.execute(
                    select(DiningParticipant).where(
                        DiningParticipant.session_id == session.id,
                        DiningParticipant.client_id == client_id,
                    )
                )
                existing = result.scalar_one_or_none()
            if not existing:
                raise
            existing.last_active_at = now
            if existing.guest_token_hash != token_hash:
                existing.guest_token_hash = token_hash
            return existing, raw_token
        return new_participant, raw_token

    def _serialize_order(
        self,
        order: Order,
        order_items: list[OrderItem],
        dish_images: dict[int, str] | None = None,
        participant_no: int | None = None,
    ) -> dict:
        dish_images = dish_images or {}
        return {
            "id": str(order.id),
            "order_no": str(order.id)[-4:],
            "table_no": order.table_no,
            "total": float(order.total or 0),
            "discount_amount": float(order.discount_amount) if order.discount_amount else 0,
            "status": order.status,
            "merchant_note": order.merchant_note,
            "payment_status": order.payment_status,
            "payment_mode": order.payment_mode,
            "payment_method": order.payment_method,
            "dining_session_id": str(order.dining_session_id) if order.dining_session_id else None,
            "participant_id": str(order.participant_id) if order.participant_id else None,
            # 这一单是这一桌第几位加入的人点的（从1开始），纯展示用，跟真实身份无关。
            "participant_no": participant_no,
            "order_type": order.order_type,
            "source": getattr(order, "source", "miniprogram"),
            "staff_note": getattr(order, "staff_note", None),
            "pickup_no": getattr(order, "pickup_no", None),
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "items": [
                {
                    "dish_id": str(item.dish_id) if item.dish_id else None,
                    "name": item.name,
                    "price": float(item.price or 0),
                    "qty": item.qty,
                    "image": dish_images.get(item.dish_id) or None,
                }
                for item in order_items
            ],
        }

