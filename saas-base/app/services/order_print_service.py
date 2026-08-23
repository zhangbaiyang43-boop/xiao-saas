import asyncio
import json
import uuid
from collections.abc import Coroutine
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.future import select

from app.core.logger import logger
from app.core.tenant_context import TenantContext
from app.models.order import Order

PRINT_META_MARKER = "\n__PRINT_META__="
MAX_PRINT_RETRY_ATTEMPTS = 3
PRINT_RETRY_COOLDOWN_SECONDS = 30
PRINT_RECONCILE_GRACE_SECONDS = 15
PRINT_RECONCILE_BATCH_LIMIT = 8
PRINT_SENDING_STALE_SECONDS = 30
PRINT_RECOVERY_INTERVAL_SECONDS = 15
MYSQL_TEXT_MAX_BYTES = 65535
MERCHANT_NOTE_MAX_CHARS = 4096
MANUAL_REPRINT_HISTORY_LIMIT = 5
PRINT_ERROR_CODE_MAX_CHARS = 128
PRINT_ERROR_MAX_CHARS = 512
PRINT_IDENTIFIER_MAX_CHARS = 128
PRINT_OPERATOR_MAX_CHARS = 64

_KUAIMAI_UNKNOWN_CODES = frozenset({
    "KUAIMAI_TIMEOUT",
    "KUAIMAI_CONNECTION_ERROR",
    "KUAIMAI_HTTP_5XX",
    "KUAIMAI_EMPTY_RESPONSE",
    "KUAIMAI_UNKNOWN_ERROR",
    "KUAIMAI_INVALID_RESPONSE",
})
_AUTO_RECONCILE_STATUSES = frozenset({"pending", "preparing", "done"})
_FULFILLABLE_STATUSES = frozenset({"pending", "preparing", "done", "settled"})


def supports_independent_print_session(db: AsyncSession) -> bool:
    """SQLite StaticPool cannot safely run a concurrent session on one connection."""
    bind = getattr(db, "bind", None)
    dialect = getattr(bind, "dialect", None)
    return str(getattr(dialect, "name", "") or "").lower() != "sqlite"


def can_reprint_order(order: Order, print_type: str = "kitchen") -> tuple[bool, str | None]:
    status = getattr(order, "status", None)
    payment_mode = getattr(order, "payment_mode", "prepay") or "prepay"
    payment_status = getattr(order, "payment_status", None)
    if status in ("cancelled", "rejected"):
        return False, "order cancelled"
    if print_type == "receipt":
        return (payment_status == "paid", None if payment_status == "paid" else "order not paid")
    if print_type == "kitchen":
        if payment_mode == "prepay":
            return (payment_status == "paid", None if payment_status == "paid" else "order not paid")
        if payment_mode in ("postpay", "table_account"):
            return True, None
    return False, "unsupported print type"


def evaluate_print_eligibility(
    order: Order,
    *,
    defer_kitchen_print: bool = False,
    manual: bool = False,
) -> dict:
    """Decide whether an order may be printed (auto or manual)."""
    status = getattr(order, "status", None)
    payment_mode = getattr(order, "payment_mode", "prepay") or "prepay"
    payment_status = getattr(order, "payment_status", None)
    db_print_status = str(getattr(order, "print_status", "") or "").upper()
    meta = _get_print_meta(order)

    if status in ("cancelled", "rejected"):
        return {"code": "NOT_PRINTABLE", "reason": "order cancelled or rejected"}

    if not manual and (db_print_status == "SUCCESS" or meta.get("status") == "printed"):
        return {"code": "ALREADY_SUCCESS", "reason": "already printed successfully"}

    if defer_kitchen_print and not manual:
        return {"code": "WAITING_PICKUP_NO", "reason": "waiting for pickup number before kitchen print"}

    if payment_mode == "prepay" and payment_status != "paid":
        return {"code": "NOT_YET_PAYABLE", "reason": "prepay order not paid"}

    if status == "pending_payment":
        return {"code": "NOT_YET_PAYABLE", "reason": "order still pending payment"}

    # postpay / table_account unpaid OR paid → eligible in fulfillable statuses
    if status in _FULFILLABLE_STATUSES:
        return {"code": "ELIGIBLE", "reason": "eligible for print"}

    return {"code": "NOT_PRINTABLE", "reason": f"status {status!r} is not printable"}


def build_staff_print_summary(order: Order, *, defer_kitchen_print: bool = False) -> dict:
    """Safe print fields for staff workbench DTOs — no raw meta / secrets / traces."""
    meta = _get_print_meta(order)
    initial = _initial_print_meta(meta) if meta else {}
    db_status = str(getattr(order, "print_status", "") or "").upper()
    meta_status = meta.get("status") if meta else None

    print_status: str | None
    if db_status in ("SUCCESS", "FAILED", "UNKNOWN", "PENDING", "SENDING", "NOT_ELIGIBLE"):
        print_status = db_status
    elif meta_status == "printed":
        print_status = "SUCCESS"
    elif meta_status == "failed":
        print_status = "FAILED"
    elif meta_status == "unknown":
        print_status = "UNKNOWN"
    elif meta_status in ("printing", "not_started"):
        print_status = "PENDING"
    else:
        print_status = None

    waiting = bool(
        defer_kitchen_print
        and print_status not in ("SUCCESS",)
        and meta_status != "printed"
    )

    print_issue = None
    if print_status == "FAILED" or meta_status == "failed":
        print_issue = "failed"
    elif print_status == "UNKNOWN" or meta_status == "unknown":
        print_issue = "unknown"
    elif waiting:
        print_issue = "waiting_pickup"

    if print_issue == "waiting_pickup":
        label = "等待桌牌后打印"
    elif print_status == "SUCCESS":
        label = "已提交打印"
    elif print_status == "FAILED":
        label = "打印失败"
    elif print_status == "UNKNOWN":
        label = "打印状态未知"
    else:
        label = ""

    can_reprint, _ = can_reprint_order(order, print_type="kitchen")
    return {
        "print_status": print_status,
        "print_status_label": label,
        "print_attempts": int(initial.get("attempts") or 0),
        "print_issue": print_issue,
        "can_reprint": bool(can_reprint),
        "print_error_code": initial.get("last_error_code"),
        "print_last_attempt_at": initial.get("last_attempt_at"),
        "print_provider": (initial.get("route") or {}).get("provider"),
        "print_printer_identifier": (initial.get("route") or {}).get("printer_identifier"),
        "manual_reprint_count": int(meta.get("manual_reprint_count") or 0),
        "manual_reprint_last_status": (
            (meta.get("manual_reprints") or [{}])[-1].get("status")
            if meta.get("manual_reprints")
            else None
        ),
    }


def _split_merchant_note_and_print_meta(raw_note: str | None) -> tuple[str | None, dict]:
    raw = raw_note or ""
    if PRINT_META_MARKER not in raw:
        return (raw.strip() or None), {}
    note, meta_raw = raw.rsplit(PRINT_META_MARKER, 1)
    try:
        meta = json.loads(meta_raw) if meta_raw.strip() else {}
        if not isinstance(meta, dict):
            meta = {}
    except Exception:
        meta = {}
    return (note.strip() or None), meta


def _compose_merchant_note_with_print_meta(note: str | None, meta: dict | None) -> str | None:
    clean_note = (note or "").strip()
    if len(clean_note) > MERCHANT_NOTE_MAX_CHARS:
        raise ValueError("MERCHANT_NOTE_TOO_LONG")
    if not meta:
        return clean_note or None
    meta = dict(meta)
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    composed = f"{clean_note}{PRINT_META_MARKER}{json.dumps(meta, ensure_ascii=False, separators=(',', ':'))}"
    if len(composed.encode("utf-8")) > MYSQL_TEXT_MAX_BYTES:
        raise ValueError("PRINT_META_CAPACITY_EXCEEDED")
    return composed


def _get_print_meta(order: Order) -> dict:
    _, meta = _split_merchant_note_and_print_meta(getattr(order, "merchant_note", None))
    return meta


def _set_print_meta(order: Order, meta: dict, note: str | None = None) -> dict:
    current_note, _ = _split_merchant_note_and_print_meta(getattr(order, "merchant_note", None))
    order.merchant_note = _compose_merchant_note_with_print_meta(current_note if note is None else note, meta)
    return meta


def _bounded(value: Any, max_chars: int) -> str | None:
    if value in (None, ""):
        return None
    return str(value)[:max_chars]


def _initial_print_meta(meta: dict) -> dict:
    initial = meta.get("initial_print")
    if isinstance(initial, dict):
        return initial
    # Read old Phase-A flat metadata without losing its initial-print fact.
    initial = {
        "status": {
            "printed": "SUCCESS",
            "failed": "FAILED",
            "unknown": "UNKNOWN",
            "printing": "SENDING",
        }.get(str(meta.get("status") or "").lower(), "PENDING"),
        "attempts": int(meta.get("attempts") or 0),
        "last_attempt_at": meta.get("last_attempt_at"),
        "last_error_code": meta.get("last_error_code"),
        "last_error": meta.get("last_error"),
        "provider_task_id": meta.get("provider_task_id"),
        "printed_at": meta.get("printed_at"),
        "route": meta.get("route"),
    }
    meta["initial_print"] = initial
    meta.setdefault("version", 2)
    return initial


def _sync_legacy_initial_fields(meta: dict) -> None:
    initial = _initial_print_meta(meta)
    status = str(initial.get("status") or "PENDING").upper()
    meta["status"] = {
        "SUCCESS": "printed",
        "FAILED": "failed",
        "UNKNOWN": "unknown",
        "SENDING": "printing",
        "NOT_ELIGIBLE": "not_started",
    }.get(status, "not_started")
    for key in (
        "attempts",
        "last_attempt_at",
        "last_error_code",
        "last_error",
        "provider_task_id",
        "printed_at",
    ):
        meta[key] = initial.get(key)


async def _load_print_route_and_credentials(
    db: AsyncSession,
    tenant_id: str,
) -> tuple[dict[str, Any], dict[str, Any], Any]:
    from app.models.tenant import Tenant
    from app.models.tenant_config import TenantConfig
    from app.services.kuaimai_service import KUAIMAI_ORDER_TEMPLATE_ID

    tenant_result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    config_result = await db.execute(select(TenantConfig).where(TenantConfig.tenant_id == tenant_id))
    config = config_result.scalar_one_or_none()
    business_info: dict[str, Any] = (config.business_info or {}) if config else {}
    provider = str(business_info.get("printer_provider") or "feieyun")
    if provider == "kuaimai":
        printer = business_info.get("kuaimai_printer") or {}
        route = {
            "provider": "kuaimai",
            "printer_identifier": _bounded(printer.get("sn"), PRINT_IDENTIFIER_MAX_CHARS) or "",
            "template_or_route_mode": _bounded(
                printer.get("order_template_id") or KUAIMAI_ORDER_TEMPLATE_ID,
                PRINT_IDENTIFIER_MAX_CHARS,
            ) or KUAIMAI_ORDER_TEMPLATE_ID,
            "copies": 1,
        }
        credentials = {
            "app_id": str(printer.get("app_id") or ""),
            "credential": str(printer.get("app_secret") or ""),
            "sn": str(printer.get("sn") or ""),
        }
    else:
        route = {
            "provider": "feieyun",
            "printer_identifier": _bounded(getattr(tenant, "feieyun_sn", None), PRINT_IDENTIFIER_MAX_CHARS) or "",
            "template_or_route_mode": "text",
            "copies": 1,
        }
        credentials = {
            "sn": str(getattr(tenant, "feieyun_sn", "") or ""),
            "credential": str(getattr(tenant, "feieyun_key", "") or ""),
        }
    return route, credentials, tenant


async def ensure_initial_print_intent(
    order: Order,
    db: AsyncSession,
    *,
    eligible: bool,
    reason: str,
) -> dict:
    """Create the route-frozen initial intent inside the caller's transaction."""
    meta = _get_print_meta(order)
    initial = meta.get("initial_print")
    if isinstance(initial, dict) and initial.get("route"):
        if eligible and str(initial.get("status") or "").upper() == "NOT_ELIGIBLE":
            initial["status"] = "PENDING"
            initial["eligible_at"] = datetime.now(timezone.utc).isoformat()
            initial["last_reason"] = reason
            _mark_order_print_state(order, "PENDING")
            _sync_legacy_initial_fields(meta)
            _set_print_meta(order, meta)
        return initial

    route, _, _ = await _load_print_route_and_credentials(db, str(order.tenant_id))
    now_iso = datetime.now(timezone.utc).isoformat()
    db_status = str(getattr(order, "print_status", "") or "").upper()
    legacy_status = str(meta.get("status") or "").lower()
    initial_status = {
        "printed": "SUCCESS",
        "failed": "FAILED",
        "unknown": "UNKNOWN",
        "printing": "SENDING",
    }.get(legacy_status)
    if not initial_status and db_status in {
        "PENDING", "SENDING", "SUCCESS", "FAILED", "UNKNOWN", "NOT_ELIGIBLE"
    }:
        initial_status = db_status
    if not initial_status:
        initial_status = "PENDING" if eligible else "NOT_ELIGIBLE"
    elif not eligible and initial_status == "PENDING":
        # Column default PENDING is not a provider-eligible intent.
        initial_status = "NOT_ELIGIBLE"
    initial = {
        "intent_created_at": now_iso,
        "eligible_at": now_iso if eligible and initial_status != "NOT_ELIGIBLE" else None,
        "status": initial_status,
        "attempts": int(meta.get("attempts") or 0),
        "last_attempt_at": meta.get("last_attempt_at"),
        "last_error_code": meta.get("last_error_code"),
        "last_error": meta.get("last_error"),
        "provider_task_id": meta.get("provider_task_id"),
        "printed_at": meta.get("printed_at") or getattr(order, "printed_at", None),
        "last_reason": reason,
        "route": route,
    }
    meta.update({"version": 2, "initial_print": initial})
    meta.setdefault("manual_reprint_count", 0)
    meta.setdefault("manual_reprints", [])
    _sync_legacy_initial_fields(meta)
    _mark_order_print_state(order, initial["status"])
    _set_print_meta(order, meta)
    return initial


def mark_initial_print_eligible(order: Order, *, reason: str) -> bool:
    meta = _get_print_meta(order)
    initial = _initial_print_meta(meta)
    if str(initial.get("status") or "").upper() != "NOT_ELIGIBLE":
        return False
    initial["status"] = "PENDING"
    initial["eligible_at"] = datetime.now(timezone.utc).isoformat()
    initial["last_reason"] = reason
    _mark_order_print_state(order, "PENDING")
    _sync_legacy_initial_fields(meta)
    _set_print_meta(order, meta)
    return True


async def _park_waiting_pickup_print_intent(
    db: AsyncSession,
    *,
    order_id: int,
    tenant_id: str,
) -> bool:
    """Move a still-waiting PENDING intent to the durable wait state.

    Historical Case A rows were written PENDING while pickup was required and
    unset. Recovery must not keep them as provider candidates. This does not
    claim, increment attempts, or call the provider. Pickup assignment still
    unlocks via mark_initial_print_eligible.
    """
    from app.services.pickup_no_service import load_pickup_settings, should_defer_kitchen_print

    result = await db.execute(
        select(Order)
        .where(Order.id == order_id, Order.tenant_id == tenant_id)
        .with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        return False
    await db.refresh(order)
    if str(getattr(order, "print_status", "") or "").upper() != "PENDING":
        return False
    pickup_settings = await load_pickup_settings(db, tenant_id)
    if not should_defer_kitchen_print(order, pickup_settings):
        return False
    meta = _get_print_meta(order)
    initial = _initial_print_meta(meta)
    initial_status = str(initial.get("status") or "PENDING").upper()
    if initial_status not in {"PENDING", "NOT_ELIGIBLE"}:
        return False
    initial["status"] = "NOT_ELIGIBLE"
    initial["last_reason"] = "startup_recovery_waiting_pickup"
    _mark_order_print_state(order, "NOT_ELIGIBLE")
    _sync_legacy_initial_fields(meta)
    _set_print_meta(order, meta)
    await db.commit()
    return True


def _db_print_status_to_meta_status(order: Order) -> str | None:
    status = str(getattr(order, "print_status", "") or "").upper()
    if status == "SUCCESS":
        return "printed"
    if status == "FAILED":
        return "failed"
    if status == "UNKNOWN":
        return "unknown"
    return None


def _mark_order_print_state(
    order: Order, status: str, printed_at: datetime | None = None
) -> None:
    if hasattr(order, "print_status"):
        order.print_status = status
    if status == "SUCCESS" and hasattr(order, "printed_at"):
        order.printed_at = printed_at or datetime.utcnow()


def _serialize_print_meta(order: Order) -> dict:
    note, meta = _split_merchant_note_and_print_meta(getattr(order, "merchant_note", None))
    initial = _initial_print_meta(meta) if meta else {}
    status = _db_print_status_to_meta_status(order)
    if not status:
        status = meta.get("status") if meta else None
    if not status and getattr(order, "payment_status", None) == "paid":
        status = "not_started"
    return {
        "merchant_note": note,
        "print_status": status,
        "print_attempts": int(meta.get("attempts") or 0) if meta else 0,
        "print_error_code": meta.get("last_error_code") if meta else None,
        "print_error": meta.get("last_error") if meta else None,
        "print_provider_task_id": meta.get("provider_task_id") if meta else None,
        "print_manual_reprint": bool(meta.get("manual_reprint")) if meta else False,
        "print_manual_reprint_by": meta.get("manual_reprint_by") if meta else None,
        "print_manual_reprint_at": meta.get("manual_reprint_at") if meta else None,
        "print_last_reason": meta.get("last_reason") if meta else None,
        "print_last_attempt_at": initial.get("last_attempt_at"),
        "print_provider": (initial.get("route") or {}).get("provider"),
        "print_printer_identifier": (initial.get("route") or {}).get("printer_identifier"),
        "print_template_or_route_mode": (initial.get("route") or {}).get("template_or_route_mode"),
        "print_manual_reprint_count": int(meta.get("manual_reprint_count") or 0) if meta else 0,
        "print_manual_reprint_last_status": (
            (meta.get("manual_reprints") or [{}])[-1].get("status")
            if meta and meta.get("manual_reprints")
            else None
        ),
    }


class PrintResultUnknownError(RuntimeError):
    """飞鹅云请求超时/网络异常导致没拿到响应——不知道这次到底有没有打印成功，跟"服务端
    明确说打印失败"是两码事，调用方必须分开处理（不能自动重试，见 print_order 的说明）。"""


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _eligible_at_for_reconcile(order: Order) -> datetime | None:
    payment_mode = getattr(order, "payment_mode", "prepay") or "prepay"
    if payment_mode == "prepay":
        return _parse_dt(getattr(order, "payment_time", None)) or _parse_dt(getattr(order, "created_at", None))
    return _parse_dt(getattr(order, "created_at", None))


def _is_unknown_print_exception(exc: BaseException) -> bool:
    if isinstance(exc, PrintResultUnknownError):
        return True
    code = str(getattr(exc, "code", None) or "").strip()
    if code in _KUAIMAI_UNKNOWN_CODES:
        return True
    message = str(exc or "").strip()
    if message in _KUAIMAI_UNKNOWN_CODES:
        return True
    return False


async def _claim_initial_print_attempt(
    order_id: int,
    tenant_id: str,
    db: AsyncSession,
    *,
    reason: str,
) -> tuple[Order | None, dict]:
    locked_result = await db.execute(
        select(Order)
        .where(Order.id == order_id, Order.tenant_id == tenant_id)
        .with_for_update()
    )
    order = locked_result.scalar_one_or_none()
    if not order:
        return None, {"success": False, "skipped": True, "code": "ORDER_NOT_FOUND"}
    await db.refresh(order)
    if str(getattr(order, "status", "") or "") in {"cancelled", "rejected"}:
        return None, {"success": False, "skipped": True, "code": "ORDER_TERMINAL"}
    meta = _get_print_meta(order)
    initial = _initial_print_meta(meta)
    status = str(initial.get("status") or getattr(order, "print_status", "PENDING")).upper()
    attempts = int(initial.get("attempts") or 0)
    if status == "SUCCESS":
        return None, {"success": True, "skipped": True, "status": "printed"}
    if status in {"UNKNOWN", "SENDING", "NOT_ELIGIBLE"}:
        return None, {"success": False, "skipped": True, "code": f"PRINT_{status}"}
    if attempts >= MAX_PRINT_RETRY_ATTEMPTS:
        return None, {"success": False, "skipped": True, "code": "PRINT_RETRY_LIMIT"}
    last_at = _parse_dt(initial.get("last_attempt_at"))
    if status == "FAILED" and last_at:
        if (datetime.now(timezone.utc) - last_at).total_seconds() < PRINT_RETRY_COOLDOWN_SECONDS:
            return None, {"success": False, "skipped": True, "code": "PRINT_RETRY_COOLDOWN"}

    now_iso = datetime.now(timezone.utc).isoformat()
    initial.update({
        "status": "SENDING",
        "attempts": attempts + 1,
        "last_attempt_at": now_iso,
        "last_reason": reason,
        "claim_id": uuid.uuid4().hex,
    })
    _mark_order_print_state(order, "SENDING")
    _sync_legacy_initial_fields(meta)
    _set_print_meta(order, meta)
    # This commit is the durable no-resend boundary and must precede provider I/O.
    await db.commit()
    return order, {"success": True, "claimed": True, "attempts": attempts + 1}


async def _execute_provider_with_frozen_route(
    order: Order,
    db: AsyncSession,
    initial_print: dict,
) -> str | None:
    from app.models.order import OrderItem
    from app.services.feieyun_service import build_order_ticket, print_order

    route = initial_print.get("route") or {}
    provider = str(route.get("provider") or "")
    printer_identifier = str(route.get("printer_identifier") or "")
    template_or_route_mode = str(route.get("template_or_route_mode") or "")
    current_route, credentials, tenant = await _load_print_route_and_credentials(
        db, str(order.tenant_id)
    )
    if (
        provider not in {"kuaimai", "feieyun"}
        or str(current_route.get("provider") or "") != provider
        or str(current_route.get("printer_identifier") or "") != printer_identifier
    ):
        raise RuntimeError("PRINT_ROUTE_UNAVAILABLE")
    if not printer_identifier or not credentials.get("credential"):
        raise RuntimeError("PRINTER_CONFIG_INCOMPLETE")

    items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    order_items = list(items_result.scalars().all())
    if provider == "kuaimai":
        from app.services.kuaimai_service import (
            build_order_template_render_data,
            print_template_order,
            validate_order_template_render_data,
        )

        if not credentials.get("app_id") or not template_or_route_mode:
            raise RuntimeError("PRINTER_CONFIG_INCOMPLETE")
        render_data = build_order_template_render_data(
            order,
            order_items,
            shop_name=getattr(tenant, "name", "") if tenant else "",
        )
        valid, error_code = validate_order_template_render_data(render_data, order)
        if not valid:
            raise RuntimeError(error_code)
        result = await print_template_order(
            credentials["app_id"],
            credentials["credential"],
            printer_identifier,
            template_or_route_mode,
            render_data,
        )
        if not result or result.get("success") is not True:
            error_code = (
                result.get("code") or result.get("error") or "PRINT_PROVIDER_FAILED"
                if result
                else "PRINT_PROVIDER_FAILED"
            )
            if str(error_code) in _KUAIMAI_UNKNOWN_CODES:
                raise PrintResultUnknownError(str(error_code))
            raise RuntimeError(str(error_code))
        return _bounded(result.get("provider_task_id"), PRINT_IDENTIFIER_MAX_CHARS)

    result = await print_order(
        printer_identifier,
        credentials["credential"],
        build_order_ticket(order, order_items),
    )
    if result == "unknown":
        raise PrintResultUnknownError("FEIEYUN_PRINT_RESULT_UNKNOWN")
    if result != "success":
        raise RuntimeError("FEIEYUN_PRINT_FAILED")
    return None


def _record_manual_reprint_result(
    meta: dict,
    *,
    attempt_id: str,
    status: str,
    error_code: str | None,
    error: str | None,
    provider_task_id: str | None,
) -> dict:
    events = list(meta.get("manual_reprints") or [])
    for event in events:
        if event.get("attempt_id") == attempt_id:
            event.update({
                "status": status,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error_code": _bounded(error_code, PRINT_ERROR_CODE_MAX_CHARS),
                "error": _bounded(error, PRINT_ERROR_MAX_CHARS),
                "provider_task_id": _bounded(provider_task_id, PRINT_IDENTIFIER_MAX_CHARS),
            })
            break
    meta.setdefault("manual_reprint_count", len(events))
    meta["manual_reprints"] = events[-MANUAL_REPRINT_HISTORY_LIMIT:]
    return meta


async def _persist_initial_print_result(
    db: AsyncSession,
    *,
    order_id: int,
    tenant_id: str,
    status: str,
    error_code: str | None = None,
    error: str | None = None,
    provider_task_id: str | None = None,
) -> dict:
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id, Order.tenant_id == tenant_id)
        .with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        return {"success": False, "code": "ORDER_NOT_FOUND"}
    await db.refresh(order)
    meta = _get_print_meta(order)
    initial = _initial_print_meta(meta)
    if str(initial.get("status") or "").upper() != "SENDING":
        return {"success": False, "skipped": True, "code": "PRINT_CLAIM_LOST"}
    now_iso = datetime.now(timezone.utc).isoformat()
    initial.update({
        "status": status,
        "last_error_code": _bounded(error_code, PRINT_ERROR_CODE_MAX_CHARS),
        "last_error": _bounded(error, PRINT_ERROR_MAX_CHARS),
        "provider_task_id": _bounded(provider_task_id, PRINT_IDENTIFIER_MAX_CHARS),
        "completed_at": now_iso,
    })
    if status == "SUCCESS":
        initial["printed_at"] = now_iso
        _mark_order_print_state(order, "SUCCESS", datetime.utcnow())
    else:
        _mark_order_print_state(order, status)
    _sync_legacy_initial_fields(meta)
    _set_print_meta(order, meta)
    await db.commit()
    return {
        "success": status == "SUCCESS",
        "status": {"SUCCESS": "printed", "FAILED": "failed", "UNKNOWN": "unknown"}[status],
        "attempts": initial.get("attempts"),
        "code": error_code,
        "provider_task_id": provider_task_id,
    }


async def _print_paid_order_ticket(
    order: Order,
    db: AsyncSession,
    *,
    manual: bool = False,
    reason: str = "auto",
    operator: str | None = None,
    operator_role: str | None = None,
    _fresh_session: bool = False,
) -> dict:
    """Durable initial print or independent manual reprint."""
    if not order:
        return {"success": False, "skipped": True, "code": "ORDER_NOT_FOUND"}
    tenant_id = str(order.tenant_id)
    if not manual and not _fresh_session:
        bound_engine = getattr(db, "bind", None)
        session_factory = (
            async_sessionmaker(bind=bound_engine, expire_on_commit=False)
            if bound_engine is not None
            else None
        )
        if session_factory is None:
            try:
                from app.core.database import AsyncSessionLocal as session_factory
            except ImportError:
                session_factory = None
        if session_factory is not None:
            async with session_factory() as print_db:
                fresh_result = await print_db.execute(
                    select(Order).where(Order.id == order.id, Order.tenant_id == tenant_id)
                )
                fresh_order = fresh_result.scalar_one_or_none()
                if not fresh_order:
                    return {"success": False, "skipped": True, "code": "ORDER_NOT_FOUND"}
                return await _print_paid_order_ticket(
                    fresh_order,
                    print_db,
                    reason=reason,
                    _fresh_session=True,
                )

    from app.services.pickup_no_service import load_pickup_settings, should_defer_kitchen_print

    pickup_settings = await load_pickup_settings(db, tenant_id)
    defer = should_defer_kitchen_print(order, pickup_settings)
    eligibility = evaluate_print_eligibility(order, defer_kitchen_print=defer, manual=manual)
    if eligibility.get("code") != "ELIGIBLE" and not (
        manual and eligibility.get("code") == "ALREADY_SUCCESS"
    ):
        code = eligibility.get("code") or "NOT_PRINTABLE"
        if code == "ALREADY_SUCCESS":
            return {"success": True, "skipped": True, "status": "printed"}
        return {"success": False, "skipped": True, "code": code}

    # Entitlement only gates the auto-print attempt itself, after business/workflow
    # eligibility (NOT_YET_PAYABLE, WAITING_PICKUP_NO, ...) has already had its say --
    # those structured codes carry real staff-facing meaning and must not be masked
    # by a plan-tier skip. Manual reprint is ungated here; it already has its own
    # interactive (F1F-B) capability check upstream of this function.
    if not manual:
        from app.core.plan_capabilities import CAP_KITCHEN_PRINT
        from app.services.optional_entitlement import optional_capability_enabled

        if not await optional_capability_enabled(tenant_id, CAP_KITCHEN_PRINT):
            return {"success": False, "skipped": True, "code": "PLAN_CAPABILITY_DISABLED"}

    meta = _get_print_meta(order)
    existing_initial = meta.get("initial_print")
    if not isinstance(existing_initial, dict) or not existing_initial.get("route"):
        await ensure_initial_print_intent(order, db, eligible=not defer, reason=reason)
        await db.commit()
        meta = _get_print_meta(order)

    if manual:
        locked_result = await db.execute(
            select(Order)
            .where(Order.id == order.id, Order.tenant_id == tenant_id)
            .with_for_update()
        )
        locked = locked_result.scalar_one_or_none()
        if not locked:
            return {"success": False, "skipped": True, "code": "ORDER_NOT_FOUND"}
        await db.refresh(locked)
        meta = _get_print_meta(locked)
        initial = _initial_print_meta(meta)
        attempt_id = uuid.uuid4().hex
        now_iso = datetime.now(timezone.utc).isoformat()
        event = {
            "attempt_id": attempt_id,
            "time": now_iso,
            "operator": _bounded(operator or "owner", PRINT_OPERATOR_MAX_CHARS),
            "role": _bounded(operator_role, 32),
            "status": "SENDING",
            "error_code": None,
            "error": None,
            "provider_task_id": None,
            "route": dict(initial.get("route") or {}),
        }
        meta["manual_reprint_count"] = int(meta.get("manual_reprint_count") or 0) + 1
        meta["manual_reprints"] = (list(meta.get("manual_reprints") or []) + [event])[-MANUAL_REPRINT_HISTORY_LIMIT:]
        # Legacy DTO fields remain additive, while initial status/task/attempts stay immutable.
        meta["manual_reprint"] = True
        meta["manual_reprint_by"] = event["operator"]
        meta["manual_reprint_at"] = now_iso
        meta["manual_reprint_role"] = event["role"]
        _set_print_meta(locked, meta)
        await db.commit()
        try:
            task_id = await _execute_provider_with_frozen_route(locked, db, initial)
            final_status, error_code, error = "SUCCESS", None, None
        except Exception as exc:
            final_status = "UNKNOWN" if _is_unknown_print_exception(exc) else "FAILED"
            error_code = str(getattr(exc, "code", None) or str(exc) or type(exc).__name__)
            error = str(exc)
            task_id = None
        final_result = await db.execute(
            select(Order)
            .where(Order.id == order.id, Order.tenant_id == tenant_id)
            .with_for_update()
        )
        final_order = final_result.scalar_one_or_none()
        if final_order:
            await db.refresh(final_order)
            final_meta = _get_print_meta(final_order)
            _record_manual_reprint_result(
                final_meta,
                attempt_id=attempt_id,
                status=final_status,
                error_code=error_code,
                error=error,
                provider_task_id=task_id,
            )
            _set_print_meta(final_order, final_meta)
            await db.commit()
        return {
            "success": final_status == "SUCCESS",
            "status": final_status.lower(),
            "code": error_code,
            "provider_task_id": task_id,
            "manual_reprint": True,
        }

    claimed_order, claim = await _claim_initial_print_attempt(
        int(order.id), tenant_id, db, reason=reason
    )
    if not claimed_order:
        return claim
    initial = _initial_print_meta(_get_print_meta(claimed_order))
    attempt_no = initial.get("attempts")
    printer_identifier = (initial.get("route") or {}).get("printer_id") if isinstance(initial.get("route"), dict) else None
    logger.info(
        "PRINT_TRIGGERED order_id=%s printer_id=%s attempt=%s reason=%s",
        order.id, printer_identifier, attempt_no, reason,
    )
    try:
        task_id = await _execute_provider_with_frozen_route(claimed_order, db, initial)
        logger.info(
            "PRINT_SUCCEEDED order_id=%s printer_id=%s attempt=%s provider_task_id=%s",
            order.id, printer_identifier, attempt_no, task_id,
        )
        return await _persist_initial_print_result(
            db,
            order_id=int(order.id),
            tenant_id=tenant_id,
            status="SUCCESS",
            provider_task_id=task_id,
        )
    except Exception as exc:
        status = "UNKNOWN" if _is_unknown_print_exception(exc) else "FAILED"
        error_code = str(getattr(exc, "code", None) or str(exc) or type(exc).__name__)
        logger.warning(
            "PRINT_FAILED order_id=%s printer_id=%s attempt=%s result=%s error_category=%s",
            order.id, printer_identifier, attempt_no, status, error_code,
        )
        return await _persist_initial_print_result(
            db,
            order_id=int(order.id),
            tenant_id=tenant_id,
            status=status,
            error_code=error_code,
            error=str(exc),
        )


async def reconcile_print_orders(
    db: AsyncSession,
    orders,
    *,
    trigger: str = "reconcile",
    pickup_settings: dict | None = None,
) -> int:
    """Best-effort print recovery for a bounded batch of orders. Returns print call count."""
    from app.services.pickup_no_service import load_pickup_settings, should_defer_kitchen_print

    if not orders:
        return 0

    batch = list(orders)[:PRINT_RECONCILE_BATCH_LIMIT]
    now = datetime.now(timezone.utc)
    settings_by_tenant: dict[str, dict] = {}
    attempted = 0

    for order in batch:
        if getattr(order, "status", None) not in _AUTO_RECONCILE_STATUSES:
            continue

        tenant_id = str(getattr(order, "tenant_id", "") or "")
        if pickup_settings is not None:
            settings = pickup_settings
        else:
            if tenant_id not in settings_by_tenant:
                settings_by_tenant[tenant_id] = await load_pickup_settings(db, tenant_id)
            settings = settings_by_tenant[tenant_id]

        defer = should_defer_kitchen_print(order, settings)
        eligibility = evaluate_print_eligibility(order, defer_kitchen_print=defer, manual=False)
        if eligibility.get("code") in (
            "ALREADY_SUCCESS",
            "WAITING_PICKUP_NO",
            "NOT_YET_PAYABLE",
            "NOT_PRINTABLE",
        ):
            continue

        meta = _get_print_meta(order)
        db_print_status = str(getattr(order, "print_status", "") or "").upper()
        meta_status = meta.get("status")

        # Result-unknown must never auto-retry (risk of duplicate tickets).
        if db_print_status == "UNKNOWN" or meta_status == "unknown":
            continue

        attempts = int(meta.get("attempts") or 0)
        is_failed = db_print_status == "FAILED" or meta_status == "failed"

        if is_failed:
            if attempts >= MAX_PRINT_RETRY_ATTEMPTS:
                continue
            last_at = _parse_dt(meta.get("last_attempt_at")) or _parse_dt(meta.get("failed_at"))
            if last_at and (now - last_at).total_seconds() < PRINT_RETRY_COOLDOWN_SECONDS:
                continue
            await _print_paid_order_ticket(order, db, reason=trigger)
            attempted += 1
            continue

        # Never successfully printed: first attempt after grace window.
        if attempts == 0 and not is_failed:
            eligible_at = _eligible_at_for_reconcile(order)
            if eligible_at and (now - eligible_at).total_seconds() < PRINT_RECONCILE_GRACE_SECONDS:
                continue
            await _print_paid_order_ticket(order, db, reason=trigger)
            attempted += 1

    return attempted


async def _quarantine_stale_sending(
    db: AsyncSession,
    *,
    order_id: int,
    tenant_id: str,
    allow_provider_call: bool,
) -> bool:
    if allow_provider_call:
        raise ValueError("stale SENDING quarantine must never call provider")
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id, Order.tenant_id == tenant_id)
        .with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        return False
    await db.refresh(order)
    meta = _get_print_meta(order)
    initial = _initial_print_meta(meta)
    if str(initial.get("status") or "").upper() != "SENDING":
        return False
    last_at = _parse_dt(initial.get("last_attempt_at"))
    if last_at and (datetime.now(timezone.utc) - last_at).total_seconds() < PRINT_SENDING_STALE_SECONDS:
        return False
    initial.update({
        "status": "UNKNOWN",
        "last_error_code": "STALE_SENDING",
        "last_error": "provider outcome unknown after interrupted sending claim",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })
    _mark_order_print_state(order, "UNKNOWN")
    _sync_legacy_initial_fields(meta)
    _set_print_meta(order, meta)
    await db.commit()
    return True


async def recover_pending_print_orders_once(db: AsyncSession | None = None) -> int:
    """Startup/interval recovery with eligibility filtering before the batch limit."""
    if db is None:
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as recovery_db:
            return await recover_pending_print_orders_once(recovery_db)

    now = datetime.utcnow()
    pending_cutoff = now - timedelta(seconds=PRINT_RECONCILE_GRACE_SECONDS)
    failed_cutoff = now - timedelta(seconds=PRINT_RETRY_COOLDOWN_SECONDS)
    sending_cutoff = now - timedelta(seconds=PRINT_SENDING_STALE_SECONDS)
    query = (
        select(Order)
        .where(
            Order.print_status.in_(["PENDING", "FAILED", "SENDING"]),
            Order.status.in_(["pending", "preparing", "done", "settled"]),
            or_(
                Order.payment_mode.in_(["postpay", "table_account"]),
                and_(Order.payment_mode == "prepay", Order.payment_status == "paid"),
            ),
            or_(
                and_(Order.print_status == "PENDING", Order.updated_at <= pending_cutoff),
                and_(Order.print_status == "FAILED", Order.updated_at <= failed_cutoff),
                and_(Order.print_status == "SENDING", Order.updated_at <= sending_cutoff),
            ),
        )
        .order_by(Order.updated_at.asc(), Order.id.asc())
        .limit(PRINT_RECONCILE_BATCH_LIMIT)
    )
    result = await db.execute(query)
    candidates = list(result.scalars().all())
    handled = 0
    for order in candidates:
        status = str(getattr(order, "print_status", "") or "").upper()
        logger.info(
            "PRINT_RECOVERY_ATTEMPT order_id=%s printer_id=%s attempt=%s reason=startup_recovery prior_status=%s",
            order.id, None, None, status,
        )
        if status == "SENDING":
            # STALE_SENDING: SENDING becomes UNKNOWN; provider is deliberately not called.
            if await _quarantine_stale_sending(
                db,
                order_id=int(order.id),
                tenant_id=str(order.tenant_id),
                allow_provider_call=False,
            ):
                handled += 1
            continue
        result_data = await _print_paid_order_ticket(order, db, reason="startup_recovery")
        if (
            result_data.get("skipped")
            and result_data.get("code") == "WAITING_PICKUP_NO"
            and status == "PENDING"
        ):
            await _park_waiting_pickup_print_intent(
                db,
                order_id=int(order.id),
                tenant_id=str(order.tenant_id),
            )
        if not result_data.get("skipped"):
            handled += 1
    return handled


async def print_recovery_loop() -> None:
    while True:
        try:
            await recover_pending_print_orders_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[PRINT_RECOVERY_LOOP_FAILED] error=%s", exc)
        await asyncio.sleep(PRINT_RECOVERY_INTERVAL_SECONDS)


# asyncio.create_task() 返回的 Task 如果没有任何地方存着强引用，理论上可能在下一次
# 事件循环切换时被垃圾回收掉、任务莫名其妙就没跑完——这是 asyncio 官方文档专门强调过的
# 坑（"Save a reference to the result of this function"）。对于打印这种失败了也不会有人
# 立刻发现的后台任务，这个坑一旦踩中会很难查，所以这里维护一个模块级的引用集合，任务
# 跑完自动从集合里摘掉。
_background_print_tasks: set[asyncio.Task[None]] = set()


def _spawn_background_print_task(coro: Coroutine[Any, Any, Any]) -> None:
    task = asyncio.create_task(coro)
    _background_print_tasks.add(task)
    task.add_done_callback(_background_print_tasks.discard)


async def _print_paid_order_ticket_background(
    order_id: int,
    tenant_id: str,
    *,
    reason: str,
    bind: Any = None,
) -> None:
    """给顾客下单请求用的"不等打印机"版本。第三方云打印 API（飞鹅云/快麦）慢一点，
    顾客提交订单这个动作就跟着慢——打印本来就是"尽力而为、失败可恢复"的旁路副作用
    （见 _print_paid_order_ticket 里已有的说明和失败重试机制），没道理让它卡在顾客
    的请求-响应周期里。

    必须用独立的 DB session，不能复用调用方传进来的那个：调用方的请求早就返回了，
    它的 session 这时候可能已经关闭；而且这个函数是在调用方 commit 之后才被调度的
    （见 create_order 里的调用位置），这里重新按 order_id 查一次，保证读到的是已经
    落库的最新状态，不会因为事务可见性问题误判成"订单还不存在/还没付款"。

    session 工厂放函数体内 import（而不是模块顶部）：这个模块的打印失败恢复测试
    （test_print_failure_recovery_contracts.py）用一个手搭的 sys.modules 假环境加载
    这个文件，只桩了 app.core.database.get_db，模块顶部多 import 一个新符号会让那些
    测试在 import 这一步就直接炸掉——跟文件里其它服务依赖（Tenant/TenantConfig 等）
    延迟到函数体内 import 是同一个理由，不是我随手加的风格不一致。
    """
    if bind is None:
        from app.core.database import AsyncSessionLocal as session_factory
    else:
        session_factory = async_sessionmaker(bind=bind, expire_on_commit=False)

    async with session_factory() as bg_db:
        try:
            TenantContext.set_tenant_id(tenant_id)
            order_result = await bg_db.execute(
                select(Order).where(Order.id == order_id, Order.tenant_id == tenant_id)
            )
            order = order_result.scalar_one_or_none()
            if not order:
                return
            await _print_paid_order_ticket(order, bg_db, reason=reason, _fresh_session=True)
            await bg_db.commit()
        except Exception as exc:
            logger.warning(
                "[PRINT_BACKGROUND_TASK_FAILED] order_id=%s reason=%s error=%s",
                order_id, reason, exc,
            )
