import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dining import DiningParticipant, DiningSession
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
    async def list_session_orders(
        self,
        tenant_id: str,
        dining_session_id: int,
        participant_token: str | None = None,
        customer_id: int | None = None,
    ) -> list[dict]:
        session_result = await self.db.execute(
            select(DiningSession).where(
                DiningSession.id == dining_session_id,
                DiningSession.tenant_id == tenant_id,
            )
        )
        session = session_result.scalar_one_or_none()
        if not session:
            return []

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
                return []
        elif customer_id:
            participant_result = await self.db.execute(
                select(DiningParticipant).where(
                    DiningParticipant.tenant_id == tenant_id,
                    DiningParticipant.session_id == dining_session_id,
                    DiningParticipant.customer_id == customer_id,
                )
            )
            if not participant_result.scalar_one_or_none():
                return []
        else:
            return []

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
            return []

        order_ids = [order.id for order in orders]
        items_result = await self.db.execute(
            select(OrderItem).where(OrderItem.order_id.in_(order_ids))
        )
        items_by_order: dict[int, list[OrderItem]] = {}
        for item in items_result.scalars().all():
            items_by_order.setdefault(item.order_id, []).append(item)

        return [self._serialize_order(order, items_by_order.get(order.id, [])) for order in orders]

    async def _get_or_create_open_session(self, tenant_id: str, table_no: str, now: datetime) -> DiningSession:
        active_key = f"{tenant_id}:{table_no}"
        result = await self.db.execute(
            select(DiningSession)
            .where(DiningSession.active_key == active_key)
            .with_for_update()
        )
        session = result.scalar_one_or_none()
        if session:
            if session.last_activity_at and session.last_activity_at < now - timedelta(hours=SESSION_EXPIRE_HOURS):
                session.status = "EXPIRED"
                session.closed_at = now
                session.active_key = None
            else:
                return session

        session = DiningSession(
            tenant_id=tenant_id,
            table_no=table_no,
            status="OPEN",
            active_key=active_key,
            started_at=now,
            last_activity_at=now,
        )
        self.db.add(session)
        await self.db.flush()
        return session

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
            if not participant.guest_token_hash:
                participant.guest_token_hash = token_hash
            return participant, raw_token

        participant = DiningParticipant(
            tenant_id=session.tenant_id,
            session_id=session.id,
            customer_id=customer_id,
            openid=openid,
            guest_token_hash=token_hash,
            client_id=client_id or make_client_id(),
            joined_at=now,
            last_active_at=now,
        )
        self.db.add(participant)
        await self.db.flush()
        return participant, raw_token

    def _serialize_order(self, order: Order, order_items: list[OrderItem]) -> dict:
        return {
            "id": str(order.id),
            "order_no": str(order.id)[-4:],
            "table_no": order.table_no,
            "total": float(order.total or 0),
            "status": order.status,
            "merchant_note": order.merchant_note,
            "payment_status": order.payment_status,
            "payment_method": order.payment_method,
            "dining_session_id": str(order.dining_session_id) if order.dining_session_id else None,
            "participant_id": str(order.participant_id) if order.participant_id else None,
            "order_type": order.order_type,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "items": [
                {
                    "dish_id": str(item.dish_id) if item.dish_id else None,
                    "name": item.name,
                    "price": float(item.price or 0),
                    "qty": item.qty,
                }
                for item in order_items
            ],
        }

