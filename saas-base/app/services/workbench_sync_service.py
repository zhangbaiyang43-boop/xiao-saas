"""Workbench full snapshot + incremental changes (Phase 4C).

Delta is a performance optimization. FULL snapshot remains the source of truth
for reconciliation (including Phase 4B print recovery on the full endpoint).

Cursor model (v2):
  w = sync watermark (high-water updated_at second)
  u, i = pagination position within the current drain

Committed cursors (after Full / after has_more=false) use page position at
(window_start, 0) so the next poll re-scans the watermark second (+ overlap).
That closes the same-second late older-id gap without DATETIME(6) migration.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import ROLE_KITCHEN, ROLE_OWNER, ROLE_WAITER
from app.models.order import Order, OrderItem

logger = logging.getLogger(__name__)

WORKBENCH_CHANGES_LIMIT = 100
WORKBENCH_CURSOR_HEADER = "X-Workbench-Cursor"
# Re-scan this many seconds before the watermark so same-second late updates
# of older order ids are not skipped by (updated_at, id) pagination.
WORKBENCH_CURSOR_OVERLAP_SECONDS = 1
_CURSOR_VERSION = 2
_CURSOR_VERSION_V1 = 1

# Match admin-h5 Waiter/Kitchen filterStatuses (shared Full + Delta visibility).
_WAITER_STATUSES = frozenset({"pending", "preparing"})
_KITCHEN_STATUSES = frozenset({"pending", "preparing", "done"})
_OWNER_STATUSES = frozenset({"pending", "preparing", "done"})


def workbench_visible_statuses_for_role(role: str | None) -> frozenset[str]:
    value = (role or "").strip().lower()
    if value == ROLE_WAITER:
        return _WAITER_STATUSES
    if value == ROLE_KITCHEN:
        return _KITCHEN_STATUSES
    if value == ROLE_OWNER:
        return _OWNER_STATUSES
    # Unknown staff role: fail closed to kitchen-like fulfillment feed.
    return _KITCHEN_STATUSES


def is_order_visible_in_workbench(order: Any, role: str | None) -> bool:
    status = getattr(order, "status", None)
    return status in workbench_visible_statuses_for_role(role)


def _naive_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _iso_second(dt: datetime) -> str:
    return _naive_utc(dt).isoformat(sep="T", timespec="seconds")


def encode_workbench_cursor(
    watermark: datetime,
    page_updated_at: datetime,
    page_order_id: int,
) -> str:
    payload = {
        "v": _CURSOR_VERSION,
        "w": _iso_second(watermark),
        "u": _iso_second(page_updated_at),
        "i": int(page_order_id),
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_workbench_cursor(cursor: str | None) -> tuple[datetime, datetime, int]:
    """Return (watermark, page_updated_at, page_order_id)."""
    text = (cursor or "").strip()
    if not text:
        raise ValueError("empty cursor")
    pad = "=" * (-len(text) % 4)
    try:
        raw = base64.urlsafe_b64decode(text + pad)
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError("invalid cursor encoding") from exc
    if not isinstance(payload, dict):
        raise ValueError("cursor not object")
    version = int(payload.get("v") or 0)
    try:
        if version == _CURSOR_VERSION:
            w = _naive_utc(datetime.fromisoformat(str(payload["w"])))
            u = _naive_utc(datetime.fromisoformat(str(payload["u"])))
            i = int(payload["i"])
        elif version == _CURSOR_VERSION_V1:
            # Legacy: treat as high-water at (u,i); normalize to committed overlap form.
            u_legacy = _naive_utc(datetime.fromisoformat(str(payload["u"])))
            if u_legacy is None:
                raise ValueError("cursor updated_at invalid")
            w = u_legacy
            u = u_legacy - timedelta(seconds=WORKBENCH_CURSOR_OVERLAP_SECONDS)
            i = 0
        else:
            raise ValueError("unsupported cursor version")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("cursor field parse error") from exc
    if w is None or u is None:
        raise ValueError("cursor updated_at invalid")
    return w, u, i


def committed_cursor_from_watermark(watermark: datetime) -> str:
    """Cursor that re-scans [watermark - overlap, …] on the next poll."""
    w = _naive_utc(watermark) or datetime.utcnow()
    page_u = w - timedelta(seconds=WORKBENCH_CURSOR_OVERLAP_SECONDS)
    return encode_workbench_cursor(w, page_u, 0)


def cursor_from_orders(orders: list[Any], *, fallback_now: datetime | None = None) -> str:
    """Build committed opaque cursor from snapshot high-water updated_at."""
    best_u: datetime | None = None
    for order in orders or []:
        u = _naive_utc(getattr(order, "updated_at", None) or getattr(order, "created_at", None))
        if u is None:
            continue
        if best_u is None or u > best_u:
            best_u = u
    if best_u is None:
        best_u = _naive_utc(fallback_now) or datetime.utcnow()
    return committed_cursor_from_watermark(best_u)


def order_matches_delta_cursor(
    order: Any,
    *,
    watermark: datetime,
    page_u: datetime,
    page_i: int,
    overlap_seconds: int = WORKBENCH_CURSOR_OVERLAP_SECONDS,
) -> bool:
    """Pure predicate mirroring the SQL change filter (for unit tests)."""
    u = _naive_utc(getattr(order, "updated_at", None))
    oid = int(getattr(order, "id", 0) or 0)
    if u is None:
        return False
    window_start = watermark - timedelta(seconds=overlap_seconds)
    if u < window_start:
        return False
    if u > page_u:
        return True
    if u == page_u and oid > page_i:
        return True
    return False


def workbench_day_window_utc() -> tuple[datetime, datetime]:
    """Same local-day window as GET /orders/workbench (UTC+8 calendar day)."""
    utc8_now = datetime.now(timezone.utc) + timedelta(hours=8)
    today_local = utc8_now.date()
    day_start_utc = datetime(today_local.year, today_local.month, today_local.day) - timedelta(hours=8)
    day_end_utc = day_start_utc + timedelta(hours=24)
    return day_start_utc, day_end_utc


async def load_workbench_candidate_orders(
    db: AsyncSession,
    tenant_id: str,
) -> list[Order]:
    """Load today's / active fulfillment candidates (role filter applied by caller)."""
    day_start_utc, day_end_utc = workbench_day_window_utc()
    query = (
        select(Order)
        .where(Order.tenant_id == tenant_id)
        .where(
            or_(
                and_(Order.created_at >= day_start_utc, Order.created_at < day_end_utc),
                Order.status.in_(("pending", "preparing", "done")),
            )
        )
        .where(Order.status.in_(("pending", "preparing", "done", "settled")))
        .order_by(Order.created_at.asc())
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def load_order_items_by_order_ids(
    db: AsyncSession,
    order_ids: list[int],
) -> dict[int, list[OrderItem]]:
    items_by_order: dict[int, list[OrderItem]] = {}
    if not order_ids:
        return items_by_order
    items_result = await db.execute(select(OrderItem).where(OrderItem.order_id.in_(order_ids)))
    for item in items_result.scalars().all():
        items_by_order.setdefault(item.order_id, []).append(item)
    return items_by_order


def advance_cursor_after_page(
    page_orders: list[Any],
    previous_cursor: str,
    *,
    has_more: bool,
) -> str:
    try:
        watermark, _page_u, _page_i = decode_workbench_cursor(previous_cursor)
    except ValueError:
        watermark = datetime.utcnow()

    if not page_orders:
        return committed_cursor_from_watermark(watermark)

    last = page_orders[-1]
    last_u = _naive_utc(getattr(last, "updated_at", None)) or watermark
    last_i = int(getattr(last, "id", 0) or 0)
    if has_more:
        # Keep watermark; advance page position only.
        return encode_workbench_cursor(watermark, last_u, last_i)

    new_water = last_u if last_u > watermark else watermark
    for order in page_orders:
        u = _naive_utc(getattr(order, "updated_at", None))
        if u is not None and u > new_water:
            new_water = u
    return committed_cursor_from_watermark(new_water)


# Back-compat name used by older call sites / tests.
def advance_cursor_from_page(page_orders: list[Any], previous_cursor: str) -> str:
    return advance_cursor_after_page(page_orders, previous_cursor, has_more=False)


async def get_workbench_changes(
    db: AsyncSession,
    *,
    tenant_id: str,
    role: str | None,
    cursor: str | None,
    limit: int = WORKBENCH_CHANGES_LIMIT,
) -> dict[str, Any]:
    """Pure-read delta. Never triggers print reconciliation.

    No cursor → bootstrap only (empty items, current server cursor).
    """
    limit = max(1, min(int(limit or WORKBENCH_CHANGES_LIMIT), WORKBENCH_CHANGES_LIMIT))

    if cursor is None or str(cursor).strip() == "":
        # Bootstrap: do not dump historical updates as "changes".
        day_start_utc, _ = workbench_day_window_utc()
        result = await db.execute(
            select(Order.updated_at, Order.id)
            .where(Order.tenant_id == tenant_id)
            .where(Order.updated_at >= day_start_utc - timedelta(days=1))
            .order_by(Order.updated_at.desc(), Order.id.desc())
            .limit(1)
        )
        row = result.first()
        if row and row[0] is not None:
            next_cursor = committed_cursor_from_watermark(row[0])
        else:
            next_cursor = committed_cursor_from_watermark(datetime.utcnow())
        return {
            "items": [],
            "removed_ids": [],
            "next_cursor": next_cursor,
            "has_more": False,
            "bootstrap": True,
        }

    try:
        watermark, page_u, page_i = decode_workbench_cursor(cursor)
    except ValueError:
        raise

    window_start = watermark - timedelta(seconds=WORKBENCH_CURSOR_OVERLAP_SECONDS)
    change_clause = and_(
        Order.updated_at >= window_start,
        or_(
            Order.updated_at > page_u,
            and_(Order.updated_at == page_u, Order.id > page_i),
        ),
    )
    query = (
        select(Order)
        .where(Order.tenant_id == tenant_id)
        .where(change_clause)
        .order_by(Order.updated_at.asc(), Order.id.asc())
        .limit(limit + 1)
    )
    result = await db.execute(query)
    rows = list(result.scalars().all())
    has_more = len(rows) > limit
    page = rows[:limit]

    visible_ids: list[int] = []
    removed_ids: list[str] = []
    for order in page:
        if is_order_visible_in_workbench(order, role):
            visible_ids.append(int(order.id))
        else:
            removed_ids.append(str(order.id))

    items_by_order = await load_order_items_by_order_ids(db, visible_ids)
    next_cursor = advance_cursor_after_page(page, cursor, has_more=has_more)
    return {
        "orders": [o for o in page if is_order_visible_in_workbench(o, role)],
        "items_by_order": items_by_order,
        "removed_ids": removed_ids,
        "page_orders": page,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "bootstrap": False,
    }
