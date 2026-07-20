from datetime import datetime, timedelta, timezone
from typing import Optional
import secrets
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.orm import defer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.logger import logger
from app.models.queue_ticket import QueueTicket
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig

ACTIVE_STATUSES = ("waiting", "called")
FINAL_STATUSES = ("seated", "skipped", "cancelled")
QUERY_FINAL_EXPIRE_HOURS = 2
KUAIMAI_QUEUE_TEMPLATE_ID = "1634997391"

DEFAULT_MERCHANT_NAME = "\u7075\u5b9dXX\u996d\u5e97"
DEFAULT_QUEUE_QRCODE_TIP = "\u626b\u7801\u67e5\u770b\u5b9e\u65f6\u6392\u961f\u8fdb\u5ea6"
QUEUE_TYPE_NAMES = {"A": "\u5c0f\u684c", "B": "\u4e2d\u684c", "C": "\u5927\u684c"}
STATUS_TEXT = {
    "waiting": "\u7b49\u5f85\u4e2d",
    "called": "\u5df2\u53eb\u53f7",
    "seated": "\u5df2\u5c31\u9910",
    "skipped": "\u5df2\u8fc7\u53f7",
    "cancelled": "\u5df2\u53d6\u6d88",
}


class QueueCallBlocked(Exception):
    def __init__(self, active_ticket: QueueTicket):
        self.active_ticket = active_ticket
        super().__init__("please seat or skip current called queue ticket first")


def get_queue_type(party_size: int) -> str:
    if party_size <= 2:
        return "A"
    if party_size <= 4:
        return "B"
    return "C"


def _today_local_date():
    return (datetime.now(timezone.utc) + timedelta(hours=8)).date()


def _now_utc():
    return datetime.utcnow()


def generate_queue_query_token() -> str:
    return secrets.token_urlsafe(24)


def _public_base_url(public_base_url: str | None = None) -> str:
    return (public_base_url or settings.PUBLIC_BASE_URL or settings.H5_ORDER_BASE_URL).rstrip("/")


def build_queue_query_url(query_token: str, public_base_url: str | None = None) -> str:
    return f"{_public_base_url(public_base_url)}/queue/status?token={quote(str(query_token), safe='')}"


def queue_type_name(queue_type: str | None) -> str:
    return QUEUE_TYPE_NAMES.get((queue_type or "").upper(), queue_type or "-")


def _estimated_wait_minutes(ahead_count: int, status: str | None) -> int:
    if status in FINAL_STATUSES:
        return 0
    if status == "called":
        return 0
    return max(5, (max(0, ahead_count) + 1) * 5)


def _estimated_wait_text(ahead_count: int, status: str | None) -> str:
    if status == "called":
        return "请尽快到前台就餐"
    if status in FINAL_STATUSES:
        return "-"
    return f"约{_estimated_wait_minutes(ahead_count, status)}分钟"


def _queue_settings(business_info: dict | None) -> dict:
    info = business_info or {}
    return {
        "queue_query_enabled": info.get("queue_query_enabled", True),
        "queue_ticket_qrcode_enabled": info.get("queue_ticket_qrcode_enabled", True),
        "queue_qrcode_tip": info.get("queue_qrcode_tip") or DEFAULT_QUEUE_QRCODE_TIP,
    }


def _created_at_text(ticket: QueueTicket) -> str:
    created = ticket.created_at or _now_utc()
    return created.strftime("%Y-%m-%d %H:%M")


def serialize_queue_ticket(ticket: QueueTicket, ahead_count: Optional[int] = None) -> dict:
    phone = ticket.phone or ""
    created_at = ticket.created_at.isoformat() if ticket.created_at else None
    called_at = ticket.called_at.isoformat() if ticket.called_at else None
    seated_at = ticket.seated_at.isoformat() if ticket.seated_at else None
    skipped_at = ticket.skipped_at.isoformat() if ticket.skipped_at else None
    wait_minutes = 0
    if ticket.created_at:
        wait_minutes = max(0, int((_now_utc() - ticket.created_at).total_seconds() // 60))

    data = {
        "id": str(ticket.id),
        "tenant_id": ticket.tenant_id,
        "queue_no": ticket.queue_no,
        "queue_type": ticket.queue_type,
        "party_size": ticket.party_size,
        "phone": phone or None,
        "phone_tail": phone[-4:] if len(phone) >= 4 else None,
        "note": ticket.note,
        "status": ticket.status,
        "wait_minutes": wait_minutes,
        "created_at": created_at,
        "called_at": called_at,
        "seated_at": seated_at,
        "skipped_at": skipped_at,
    }
    if ahead_count is not None:
        data["ahead_count"] = ahead_count
    return data


def serialize_queue_ticket_query(ticket: QueueTicket, merchant_name: str, ahead_count: int) -> dict:
    return {
        "shop_name": merchant_name or DEFAULT_MERCHANT_NAME,
        "queue_number": ticket.queue_no,
        "queue_no": ticket.queue_no,
        "queue_type": ticket.queue_type,
        "queue_type_name": queue_type_name(ticket.queue_type),
        "party_size": ticket.party_size,
        "party_size_text": f"{ticket.party_size}\u4eba",
        "ahead_count": max(0, ahead_count),
        "waiting_text": f"前方等待{max(0, ahead_count)}桌",
        "estimated_wait_minutes": _estimated_wait_minutes(ahead_count, ticket.status),
        "estimated_wait_text": _estimated_wait_text(ahead_count, ticket.status),
        "status": ticket.status,
        "status_text": STATUS_TEXT.get(ticket.status, ticket.status),
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "created_at_text": _created_at_text(ticket),
        "skipped_tip": "\u5df2\u8fc7\u53f7\uff0c\u8bf7\u8054\u7cfb\u524d\u53f0\u91cd\u65b0\u5b89\u6392" if ticket.status == "skipped" else "\u8fc7\u53f7\u8bf7\u8054\u7cfb\u524d\u53f0\u5904\u7406",
    }


def build_queue_print_fields(
    ticket: QueueTicket,
    merchant_name: str,
    ahead_count: int,
    queue_url: str = "",
    queue_notice: str = DEFAULT_QUEUE_QRCODE_TIP,
) -> dict:
    return {
        "shop_name": merchant_name or DEFAULT_MERCHANT_NAME,
        "queue_type_name": queue_type_name(ticket.queue_type),
        "queue_number": ticket.queue_no,
        "waiting_count": max(0, ahead_count),
        "waiting_text": f"前方等待{max(0, ahead_count)}桌",
        "party_size": ticket.party_size,
        "party_size_text": f"{ticket.party_size}\u4eba",
        "estimated_wait_minutes": _estimated_wait_minutes(ahead_count, ticket.status),
        "estimated_wait_text": _estimated_wait_text(ahead_count, ticket.status),
        "created_at": _created_at_text(ticket),
        "queue_status": STATUS_TEXT.get(ticket.status, ticket.status),
        "queue_url": queue_url or "",
        "queue_notice": queue_notice or DEFAULT_QUEUE_QRCODE_TIP,
    }


def build_queue_ticket_content(
    ticket: QueueTicket,
    merchant_name: str = DEFAULT_MERCHANT_NAME,
    ahead_count: int = 0,
    queue_url: str = "",
    queue_notice: str = DEFAULT_QUEUE_QRCODE_TIP,
) -> str:
    fields = build_queue_print_fields(ticket, merchant_name, ahead_count, queue_url, queue_notice)
    lines = [
        fields["shop_name"],
        "",
        f"排位号：{fields['queue_number']}",
        f"桌型：{fields['queue_type_name']}",
        f"就餐人数：{fields['party_size_text']}",
        fields["waiting_text"],
        f"预计等待：{fields['estimated_wait_text']}",
        "",
        "请留意前台叫号",
        "过号请重新联系前台",
    ]
    if fields["queue_url"]:
        lines.extend(["", fields["queue_notice"], fields["queue_url"]])
    lines.extend(["", f"取号时间：{fields['created_at']}"])
    return "\n".join(lines)


def build_queue_template_render_data(
    ticket: QueueTicket,
    merchant_name: str,
    ahead_count: int,
    queue_url: str = "",
    queue_notice: str = DEFAULT_QUEUE_QRCODE_TIP,
) -> dict:
    return build_queue_print_fields(ticket, merchant_name, ahead_count, queue_url, queue_notice)


async def _get_tenant_print_context(db: AsyncSession, tenant_id: str) -> tuple[Tenant | None, dict]:
    tenant_result = await db.execute(select(Tenant).where(Tenant.tenant_id == str(tenant_id)))
    tenant = tenant_result.scalar_one_or_none()
    config_result = await db.execute(select(TenantConfig).where(TenantConfig.tenant_id == str(tenant_id)))
    config = config_result.scalar_one_or_none()
    business_info = (config.business_info or {}) if config else {}
    return tenant, business_info


async def print_queue_ticket(db: AsyncSession, ticket: QueueTicket, ahead_count: int) -> dict:
    try:
        tenant, business_info = await _get_tenant_print_context(db, str(ticket.tenant_id))
        merchant_name = tenant.name if tenant else DEFAULT_MERCHANT_NAME
        provider = business_info.get("printer_provider") or "feieyun"

        logger.warning("[PRINT_TEST_PROVIDER_SELECTED] tenant_id=%s provider=%s", ticket.tenant_id, provider)

        queue_settings = _queue_settings(business_info)
        queue_url = ""
        if queue_settings["queue_query_enabled"] and queue_settings["queue_ticket_qrcode_enabled"] and ticket.query_token:
            queue_url = build_queue_query_url(ticket.query_token)
        content = build_queue_ticket_content(
            ticket,
            merchant_name=merchant_name,
            ahead_count=ahead_count,
            queue_url=queue_url,
            queue_notice=queue_settings["queue_qrcode_tip"],
        )
        if provider == "kuaimai":
            logger.warning("[PRINT_TEST_CALL_PROVIDER] provider=kuaimai")
            from app.services.kuaimai_service import print_template_order

            kuaimai = business_info.get("kuaimai_printer") or {}
            render_data = build_queue_template_render_data(
                ticket,
                merchant_name=merchant_name,
                ahead_count=ahead_count,
                queue_url=queue_url,
                queue_notice=queue_settings["queue_qrcode_tip"],
            )
            render_data_wrapped = {"排队取号": [render_data]}
            result = await print_template_order(
                kuaimai.get("app_id") or "",
                kuaimai.get("app_secret") or "",
                kuaimai.get("sn") or "",
                KUAIMAI_QUEUE_TEMPLATE_ID,
                render_data_wrapped,
            )
            logger.warning("[PRINT_TEST_PROVIDER_RESULT] success=%s", result.get("success"))
            return result
        elif tenant and tenant.feieyun_sn and tenant.feieyun_key:
            logger.warning("[PRINT_TEST_CALL_PROVIDER] provider=feieyun")
            from app.services.feieyun_service import print_order

            success = await print_order(tenant.feieyun_sn, tenant.feieyun_key, content)
            logger.warning("[PRINT_TEST_PROVIDER_RESULT] success=%s", success)
            return {"success": success, "provider": "feieyun"}
        logger.warning("[PRINT_TEST_PROVIDER_RESULT] provider=None config incomplete")
        return {"success": False, "error": "printer config incomplete"}
    except Exception as exc:
        logger.exception("[PRINT_TEST_EXCEPTION] type=%s error=%s", type(exc).__name__, str(exc))
        return {"success": False, "error": str(exc)}


async def print_queue_test_ticket(db: AsyncSession, tenant_id: str) -> dict:
    ticket = QueueTicket(
        tenant_id=str(tenant_id),
        queue_no="B000",
        queue_type="B",
        queue_date=_today_local_date(),
        daily_sequence=0,
        party_size=3,
        status="waiting",
        query_token=None,
        created_at=_now_utc(),
    )
    return await print_queue_ticket(db, ticket, ahead_count=2)


class QueueService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_ticket(self, tenant_id: str, party_size: int, phone: str | None, note: str | None) -> tuple[QueueTicket, int]:
        queue_type = get_queue_type(party_size)
        today = _today_local_date()

        for _ in range(3):
            max_result = await self.db.execute(
                select(func.max(QueueTicket.daily_sequence)).where(
                    QueueTicket.tenant_id == tenant_id,
                    QueueTicket.queue_date == today,
                    QueueTicket.queue_type == queue_type,
                )
            )
            next_sequence = (max_result.scalar() or 0) + 1
            ticket = QueueTicket(
                tenant_id=tenant_id,
                queue_no=f"{queue_type}{next_sequence:03d}",
                queue_type=queue_type,
                queue_date=today,
                daily_sequence=next_sequence,
                party_size=party_size,
                phone=(phone or "").strip() or None,
                note=(note or "").strip() or None,
                status="waiting",
                query_token=generate_queue_query_token(),
            )
            self.db.add(ticket)
            try:
                await self.db.flush()
                ahead_count = await self.count_ahead(ticket)
                await self.db.commit()
                await self.db.refresh(ticket)
                await print_queue_ticket(self.db, ticket, ahead_count)
                return ticket, ahead_count
            except Exception:
                await self.db.rollback()
                logger.warning("queue ticket create retry after duplicate or flush error")

        raise RuntimeError("queue ticket create failed, please retry")

    async def list_tickets(self, tenant_id: str, status: str | None = None) -> list[QueueTicket]:
        query = select(QueueTicket).options(defer(QueueTicket.query_token)).where(QueueTicket.tenant_id == tenant_id)
        if status:
            query = query.where(QueueTicket.status == status)
        query = query.order_by(QueueTicket.created_at.asc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_ahead(self, ticket: QueueTicket) -> int:
        result = await self.db.execute(
            select(func.count(QueueTicket.id)).where(
                QueueTicket.tenant_id == ticket.tenant_id,
                QueueTicket.queue_date == ticket.queue_date,
                QueueTicket.queue_type == ticket.queue_type,
                QueueTicket.status.in_(ACTIVE_STATUSES),
                QueueTicket.created_at < ticket.created_at,
            )
        )
        return int(result.scalar() or 0)

    async def call_next(self, tenant_id: str, queue_type: str) -> QueueTicket | None:
        queue_type = queue_type.upper()
        now = _now_utc()
        active_result = await self.db.execute(
            select(QueueTicket).options(defer(QueueTicket.query_token))
            .where(
                QueueTicket.tenant_id == tenant_id,
                QueueTicket.queue_type == queue_type,
                QueueTicket.status == "called",
            )
            .order_by(QueueTicket.called_at.asc(), QueueTicket.created_at.asc())
            .limit(1)
        )
        active_ticket = active_result.scalar_one_or_none()
        if active_ticket:
            raise QueueCallBlocked(active_ticket)

        result = await self.db.execute(
            select(QueueTicket).options(defer(QueueTicket.query_token))
            .where(
                QueueTicket.tenant_id == tenant_id,
                QueueTicket.queue_type == queue_type,
                QueueTicket.status == "waiting",
            )
            .order_by(QueueTicket.created_at.asc())
            .limit(1)
        )
        ticket = result.scalar_one_or_none()
        if not ticket:
            return None
        ticket.status = "called"
        ticket.called_at = now
        await self.db.commit()
        await self.db.refresh(ticket)
        return ticket

    async def mark_status(self, tenant_id: str, ticket_id: int, status: str) -> QueueTicket | None:
        result = await self.db.execute(
            select(QueueTicket).options(defer(QueueTicket.query_token)).where(QueueTicket.id == ticket_id, QueueTicket.tenant_id == tenant_id)
        )
        ticket = result.scalar_one_or_none()
        if not ticket:
            return None
        now = _now_utc()
        ticket.status = status
        if status == "seated":
            ticket.seated_at = now
        elif status == "skipped":
            ticket.skipped_at = now
        await self.db.commit()
        await self.db.refresh(ticket)
        return ticket

    async def get_status(self, tenant_id: str) -> dict:
        tickets = await self.list_tickets(tenant_id)
        current = next((t for t in reversed(tickets) if t.status == "called"), None)
        next_waiting = next((t for t in tickets if t.status == "waiting"), None)
        waiting = [t for t in tickets if t.status == "waiting"]
        return {
            "current_called": current.queue_no if current else None,
            "next": next_waiting.queue_no if next_waiting else None,
            "waiting_count": len(waiting),
            "small_count": len([t for t in waiting if t.queue_type == "A"]),
            "medium_count": len([t for t in waiting if t.queue_type == "B"]),
            "large_count": len([t for t in waiting if t.queue_type == "C"]),
        }

    async def get_status_by_token(self, query_token: str) -> dict | None:
        token = (query_token or "").strip()
        if not token:
            return None
        result = await self.db.execute(select(QueueTicket).where(QueueTicket.query_token == token))
        ticket = result.scalar_one_or_none()
        if not ticket:
            return None

        tenant, business_info = await _get_tenant_print_context(self.db, str(ticket.tenant_id))
        queue_settings = _queue_settings(business_info)
        if not queue_settings["queue_query_enabled"]:
            return None

        ended_at = ticket.seated_at or ticket.skipped_at
        if ticket.status in FINAL_STATUSES and ended_at and ended_at < _now_utc() - timedelta(hours=QUERY_FINAL_EXPIRE_HOURS):
            return None

        ahead_count = await self.count_ahead(ticket) if ticket.status in ACTIVE_STATUSES else 0
        merchant_name = tenant.name if tenant else DEFAULT_MERCHANT_NAME
        return serialize_queue_ticket_query(ticket, merchant_name=merchant_name, ahead_count=ahead_count)

    async def seed_demo_data(self, tenant_id: str = "1") -> dict:
        today = _today_local_date()
        existing = await self.db.execute(
            select(func.count(QueueTicket.id)).where(
                QueueTicket.tenant_id == tenant_id,
                QueueTicket.queue_date == today,
            )
        )
        if int(existing.scalar() or 0) > 0:
            return {"seeded": False, "message": "queue demo data already exists"}

        rows = [
            ("A001", "A", 1, 2, "waiting"),
            ("B001", "B", 1, 3, "waiting"),
            ("B002", "B", 2, 4, "called"),
            ("C001", "C", 1, 6, "waiting"),
        ]
        for queue_no, queue_type, sequence, party_size, status in rows:
            ticket = QueueTicket(
                tenant_id=tenant_id,
                queue_no=queue_no,
                queue_type=queue_type,
                queue_date=today,
                daily_sequence=sequence,
                party_size=party_size,
                status=status,
                query_token=generate_queue_query_token(),
                called_at=_now_utc() if status == "called" else None,
            )
            self.db.add(ticket)
        await self.db.commit()
        return {"seeded": True, "count": len(rows)}
