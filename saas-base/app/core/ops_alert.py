"""P0 ops alerts: event sidecar, fail-open, in-process cooldown.

Never imported by payment/print business logic. A logging Filter observes
candidate events after they are already logged. Webhook failures must not
propagate into request handlers.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

CANDIDATE_EVENTS = frozenset(
    {
        "WXPAY_CALLBACK_ORDER_NOT_FOUND",
        "UNHANDLED_EXCEPTION",
        "PRINT_FAILED",
    }
)

_SELF_EVENTS = frozenset(
    {
        "OPS_ALERT_TRIGGERED",
        "OPS_ALERT_SENT",
        "OPS_ALERT_SUPPRESSED",
        "OPS_ALERT_FAILED",
    }
)

_CORE_MENU_PATHS = frozenset({"/api/v1/menu/items", "/api/v1/shop/info"})

WXPAY_COOLDOWN_SECONDS = 10 * 60
EXCEPTION_COOLDOWN_SECONDS = 10 * 60
PRINT_WINDOW_SECONDS = 10 * 60
PRINT_THRESHOLD = 3
PRINT_COOLDOWN_SECONDS = 15 * 60
MAX_FINGERPRINTS = 256
MAX_INFLIGHT = 8
STATE_TTL_SECONDS = 30 * 60
WEBHOOK_TIMEOUT_SECONDS = 2.5

_lock = threading.Lock()
_state: dict[str, "_Bucket"] = {}
_inflight: set[asyncio.Task] = set()


@dataclass
class _Bucket:
    count: int = 0
    last_seen: float = 0.0
    last_sent: float | None = None
    fail_times: deque[float] = field(default_factory=deque)
    last_order_id: Any = None
    last_out_trade_no: Any = None
    last_request_id: Any = None
    last_printer_id: Any = None


def _webhook_url() -> str:
    try:
        from app.config import settings

        return str(getattr(settings, "OPS_ALERT_WEBHOOK_URL", "") or "").strip()
    except Exception:
        return ""


def reset_ops_alert_state() -> None:
    with _lock:
        _state.clear()
        _inflight.clear()


def is_core_exception_path(method: str | None, path: str | None) -> bool:
    path = str(path or "")
    method = str(method or "").upper()
    if path in _CORE_MENU_PATHS:
        return True
    if method != "POST":
        return False
    if path == "/api/v1/orders" or path == "/api/v1/orders/wxpay-notify":
        return True
    prefix = "/api/v1/orders/"
    if path.startswith(prefix) and path.endswith("/pay"):
        rest = path[len(prefix) : -len("/pay")]
        return bool(rest) and "/" not in rest
    return False


def _stack_top(exc_info) -> str:
    if not exc_info or not exc_info[2]:
        return ""
    try:
        frames = traceback.extract_tb(exc_info[2])
    except Exception:
        return ""
    for frame in reversed(frames):
        filename = str(frame.filename or "").replace("\\", "/")
        marker = "/app/"
        idx = filename.rfind(marker)
        if idx == -1:
            continue
        rel = filename[idx + 1 :]
        return f"{rel}:{frame.lineno}"
    if frames:
        last = frames[-1]
        return f"{last.name}:{last.lineno}"
    return ""


def _field(value: Any, max_len: int = 128) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() in ("unknown", "none"):
        return ""
    return text[:max_len]


def _purge_locked(now: float) -> None:
    expired = [key for key, bucket in _state.items() if now - bucket.last_seen > STATE_TTL_SECONDS]
    for key in expired:
        _state.pop(key, None)
    if len(_state) <= MAX_FINGERPRINTS:
        return
    overflow = sorted(_state.items(), key=lambda item: item[1].last_seen)
    for key, _bucket in overflow[: max(0, len(_state) - MAX_FINGERPRINTS)]:
        _state.pop(key, None)


def _log_ops(event: str, **fields: Any) -> None:
    if event in CANDIDATE_EVENTS:
        return
    extra = {"event": event}
    extra.update(fields)
    try:
        logging.getLogger("saas-member").info(event, extra=extra)
    except Exception:
        pass


def _enqueue_send(text: str) -> None:
    if not _webhook_url():
        return
    if len(_inflight) >= MAX_INFLIGHT:
        _log_ops("OPS_ALERT_FAILED", reason="inflight_cap")
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _log_ops("OPS_ALERT_FAILED", reason="no_event_loop")
        return
    task = loop.create_task(_send_async(text))
    _inflight.add(task)

    def _done(done: asyncio.Task) -> None:
        _inflight.discard(done)
        try:
            exc = done.exception()
        except asyncio.CancelledError:
            return
        except Exception:
            _log_ops("OPS_ALERT_FAILED", reason="callback_error")
            return
        if exc is not None:
            _log_ops("OPS_ALERT_FAILED", reason=type(exc).__name__)

    task.add_done_callback(_done)


async def _send_async(text: str) -> None:
    url = _webhook_url()
    if not url:
        return
    try:
        import httpx

        payload = {"msgtype": "text", "text": {"content": text[:1800]}}
        timeout = httpx.Timeout(WEBHOOK_TIMEOUT_SECONDS, connect=1.5)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            try:
                body = response.json()
            except Exception:
                _log_ops("OPS_ALERT_FAILED", reason="wecom_invalid_json")
                return
            if int((body or {}).get("errcode", -1) or -1) != 0:
                _log_ops("OPS_ALERT_FAILED", reason="wecom_rejected")
                return
        _log_ops("OPS_ALERT_SENT")
    except Exception as exc:
        _log_ops("OPS_ALERT_FAILED", reason=type(exc).__name__)


def _format_wxpay(fields: dict[str, Any], count: int) -> str:
    lines = [
        "[P0] 微信支付订单无法匹配",
        f"时间：{_field(fields.get('timestamp')) or datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"tenant：{_field(fields.get('tenant_id')) or '-'}",
        f"out_trade_no：{_field(fields.get('out_trade_no') or fields.get('order_id')) or '-'}",
        f"request_id：{_field(fields.get('request_id')) or '-'}",
        f"event：WXPAY_CALLBACK_ORDER_NOT_FOUND",
        f"reason：{_field(fields.get('reason')) or 'ORDER_NOT_FOUND'}",
    ]
    if _field(fields.get("transaction_id")):
        lines.append(f"transaction_id：{_field(fields.get('transaction_id'))}")
    if count > 1:
        lines.append(f"count：{count}")
    return "\n".join(lines)


def _format_exception(fields: dict[str, Any], fingerprint: str, count: int) -> str:
    lines = [
        "[P0] 核心接口异常",
        f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"tenant：{_field(fields.get('tenant_id')) or '-'}",
        f"path：{_field(fields.get('path'), 200) or '-'}",
        f"error_type：{_field(fields.get('error_type')) or '-'}",
        f"request_id：{_field(fields.get('request_id')) or '-'}",
        f"fingerprint：{fingerprint[:160]}",
        f"count：{count}",
    ]
    stack_top = _field(fields.get("stack_top"), 200)
    if stack_top:
        lines.append(f"stack：{stack_top}")
    return "\n".join(lines)


def _format_print(fields: dict[str, Any], count: int) -> str:
    return "\n".join(
        [
            "[P0] 开心点单异常",
            "类型：厨房连续打印失败",
            f"商户：{_field(fields.get('tenant_id')) or '-'}",
            f"打印机：{_field(fields.get('printer_id')) or '-'}",
            f"10分钟失败：{count}",
            f"最近订单：{_field(fields.get('order_id')) or '-'}",
            f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ]
    )


def observe_ops_event(
    event: str,
    *,
    tenant_id=None,
    order_id=None,
    request_id=None,
    printer_id=None,
    path=None,
    method=None,
    error_type=None,
    reason=None,
    out_trade_no=None,
    transaction_id=None,
    trade_state=None,
    stack_top=None,
    exc_info=None,
) -> str:
    """Return sent / suppressed / pending / ignored / disabled. Never raises."""
    try:
        return _observe_impl(
            event,
            tenant_id=tenant_id,
            order_id=order_id,
            request_id=request_id,
            printer_id=printer_id,
            path=path,
            method=method,
            error_type=error_type,
            reason=reason,
            out_trade_no=out_trade_no,
            transaction_id=transaction_id,
            trade_state=trade_state,
            stack_top=stack_top or _stack_top(exc_info),
        )
    except Exception:
        try:
            _log_ops("OPS_ALERT_FAILED", reason="observe_error")
        except Exception:
            pass
        return "failed"


def _observe_impl(event: str, **fields: Any) -> str:
    if event in _SELF_EVENTS or event not in CANDIDATE_EVENTS:
        return "ignored"
    if event == "UNHANDLED_EXCEPTION" and not is_core_exception_path(fields.get("method"), fields.get("path")):
        return "ignored"
    if not _webhook_url():
        return "disabled"

    tenant = _field(fields.get("tenant_id")) or "unknown"
    if event == "WXPAY_CALLBACK_ORDER_NOT_FOUND":
        fingerprint = f"wxpay.order_not_found|{tenant}"
        cooldown = WXPAY_COOLDOWN_SECONDS
        kind = "wxpay"
    elif event == "UNHANDLED_EXCEPTION":
        path = _field(fields.get("path"), 200) or "-"
        error_type = _field(fields.get("error_type")) or "-"
        stack_top = _field(fields.get("stack_top"), 200)
        fingerprint = f"exception|{path}|{error_type}|{stack_top}"
        cooldown = EXCEPTION_COOLDOWN_SECONDS
        kind = "exception"
    else:
        printer = _field(fields.get("printer_id")) or "unknown"
        fingerprint = f"print.fail|{tenant}|{printer}"
        cooldown = PRINT_COOLDOWN_SECONDS
        kind = "print"

    now = time.monotonic()
    with _lock:
        _purge_locked(now)
        bucket = _state.get(fingerprint)
        if bucket is None:
            bucket = _Bucket()
            _state[fingerprint] = bucket
        bucket.count += 1
        bucket.last_seen = now
        bucket.last_order_id = fields.get("order_id") or bucket.last_order_id
        bucket.last_out_trade_no = fields.get("out_trade_no") or fields.get("order_id") or bucket.last_out_trade_no
        bucket.last_request_id = fields.get("request_id") or bucket.last_request_id
        bucket.last_printer_id = fields.get("printer_id") or bucket.last_printer_id
        send_now = False
        if kind == "print":
            bucket.fail_times.append(now)
            while bucket.fail_times and now - bucket.fail_times[0] > PRINT_WINDOW_SECONDS:
                bucket.fail_times.popleft()
            window_n = len(bucket.fail_times)
            cooled = bucket.last_sent is None or (now - bucket.last_sent) >= cooldown
            if window_n >= PRINT_THRESHOLD and cooled:
                send_now = True
                bucket.last_sent = now
            result_count = window_n
        else:
            result_count = bucket.count
            if bucket.last_sent is None:
                send_now = True
                bucket.last_sent = now
            elif now - bucket.last_sent < cooldown:
                send_now = False
            else:
                send_now = True
                bucket.last_sent = now
        count_snapshot = result_count
        fingerprint_snapshot = fingerprint
        latest_order = bucket.last_order_id
        latest_out_trade_no = bucket.last_out_trade_no
        latest_request_id = bucket.last_request_id
        latest_printer = bucket.last_printer_id

    if not send_now:
        _log_ops("OPS_ALERT_SUPPRESSED", fingerprint=fingerprint_snapshot, count=count_snapshot)
        return "pending" if kind == "print" and count_snapshot < PRINT_THRESHOLD else "suppressed"

    payload_fields = {
        "tenant_id": fields.get("tenant_id"),
        "order_id": latest_order,
        "out_trade_no": latest_out_trade_no,
        "request_id": latest_request_id,
        "path": fields.get("path"),
        "error_type": fields.get("error_type"),
        "printer_id": latest_printer,
        "reason": fields.get("reason"),
        "transaction_id": fields.get("transaction_id"),
        "stack_top": fields.get("stack_top"),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if kind == "wxpay":
        text = _format_wxpay(payload_fields, count_snapshot)
    elif kind == "exception":
        text = _format_exception(payload_fields, fingerprint_snapshot, count_snapshot)
    else:
        text = _format_print(payload_fields, count_snapshot)
    _log_ops("OPS_ALERT_TRIGGERED", fingerprint=fingerprint_snapshot, count=count_snapshot)
    _enqueue_send(text)
    return "sent"


def observe_from_record(record: logging.LogRecord) -> str:
    event = getattr(record, "event", None)
    if event in _SELF_EVENTS or event not in CANDIDATE_EVENTS:
        return "ignored"
    tenant_id = getattr(record, "tenant_id", None)
    if not tenant_id:
        try:
            from app.core.tenant_context import TenantContext

            tenant_id = TenantContext.get_current_tenant_id()
        except Exception:
            tenant_id = None
    request_id = getattr(record, "request_id", None)
    if not request_id:
        try:
            from app.core.request_context import RequestContext

            request_id = RequestContext.get_request_id()
        except Exception:
            request_id = None
    return observe_ops_event(
        str(event),
        tenant_id=tenant_id,
        order_id=getattr(record, "order_id", None),
        request_id=request_id,
        printer_id=getattr(record, "printer_id", None),
        path=getattr(record, "path", None),
        method=getattr(record, "method", None),
        error_type=getattr(record, "error_type", None),
        reason=getattr(record, "reason", None),
        out_trade_no=getattr(record, "out_trade_no", None),
        transaction_id=getattr(record, "transaction_id", None),
        trade_state=getattr(record, "trade_state", None),
        exc_info=getattr(record, "exc_info", None),
    )


class OpsAlertFilter(logging.Filter):
    """Handler-level filter: never drops records; observes candidate events once."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if getattr(record, "_ops_alert_seen", False):
                return True
            try:
                record._ops_alert_seen = True  # type: ignore[attr-defined]
            except Exception:
                pass
            event = getattr(record, "event", None)
            if event not in CANDIDATE_EVENTS:
                return True
            observe_from_record(record)
        except Exception:
            try:
                _log_ops("OPS_ALERT_FAILED", reason="filter_error")
            except Exception:
                pass
        return True
