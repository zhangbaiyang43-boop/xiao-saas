import json
import logging
import os
import traceback
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

from app.core.request_context import RequestContext
from app.core.tenant_context import TenantContext

_RESERVED_RECORD_KEYS = set(logging.makeLogRecord({}).__dict__.keys()) | {
    "asctime",
    "message",
    "msg",
    "args",
    "exc_text",
    "stack_info",
}

_BLOCKED_EXTRA_KEYS = {
    "authorization",
    "cookie",
    "password",
    "token",
    "access_token",
    "refresh_token",
    "paysign",
    "pay_sign",
    "noncestr",
    "nonce_str",
    "private_key",
    "api_key",
    "apiv3_key",
    "secret",
    "session_key",
    "openid",
    "code",
    "otp",
    "verification_code",
    "headers",
    "payload",
    "body",
    "raw_body",
}

_COUPON_EVENT_BY_TO_STATUS = {
    "LOCKED": "COUPON_LOCKED",
    "USED": "COUPON_REDEEMED",
    "UNUSED": "COUPON_RELEASED",
}

_LOGGING_CONFIGURED = False


def _json_safe(value, depth: int = 0):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if depth >= 4:
        return str(value)[:200]
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, depth + 1) for item in value[:50]]
    if isinstance(value, dict):
        return {str(key): _json_safe(val, depth + 1) for key, val in list(value.items())[:50]}
    try:
        return str(value)[:500]
    except Exception:
        return "<unserializable>"


class JsonFormatter(logging.Formatter):
    def format(self, record):
        try:
            request_id = (
                getattr(record, "request_id", None)
                or RequestContext.get_request_id()
                or "unknown"
            )
            tenant_id = (
                getattr(record, "tenant_id", None)
                or TenantContext.get_current_tenant_id()
                or "unknown"
            )
            log_record = {
                "timestamp": datetime.utcnow().isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "event": getattr(record, "event", None),
                "message": record.getMessage(),
                "request_id": request_id,
                "tenant_id": tenant_id,
            }
            for key, value in record.__dict__.items():
                if key in log_record or key in _RESERVED_RECORD_KEYS:
                    continue
                if key.startswith("_") or str(key).lower() in _BLOCKED_EXTRA_KEYS:
                    continue
                log_record[key] = _json_safe(value)
            if record.exc_info:
                log_record["traceback"] = "".join(traceback.format_exception(*record.exc_info))
                if not log_record.get("error_type") and record.exc_info[0] is not None:
                    log_record["error_type"] = record.exc_info[0].__name__
            compact = {key: value for key, value in log_record.items() if value is not None}
            return json.dumps(compact, ensure_ascii=False, separators=(",", ":"), default=str)
        except Exception:
            return json.dumps(
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "level": "ERROR",
                    "event": "LOG_FORMAT_FAILED",
                    "message": "log_format_failed",
                },
                separators=(",", ":"),
            )


def _build_handlers():
    formatter = JsonFormatter()
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    log_file = "logs/app.log"
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    return console_handler, file_handler


def _ensure_ops_alert_filter(target: logging.Logger) -> None:
    try:
        from app.core.ops_alert import OpsAlertFilter
    except Exception:
        return
    for handler in target.handlers:
        if any(isinstance(item, OpsAlertFilter) for item in handler.filters):
            continue
        handler.addFilter(OpsAlertFilter())


def _attach_handlers(target: logging.Logger, handlers) -> None:
    target.setLevel(logging.INFO)
    target.handlers.clear()
    for handler in handlers:
        target.addHandler(handler)
    target.propagate = False
    _ensure_ops_alert_filter(target)


def setup_logger():
    """JSON handlers on both `saas-member` and parent `app`.

    Named `saas-member` stays the importable application logger. Module loggers
    (`logging.getLogger(__name__)` under `app.*`) propagate to `app` and share
    the same handlers. Both have propagate=False so records are not also
    emitted by the root/uvicorn formatter.
    """
    global _LOGGING_CONFIGURED
    named = logging.getLogger("saas-member")
    app_logger = logging.getLogger("app")
    if _LOGGING_CONFIGURED and named.handlers and app_logger.handlers:
        _ensure_ops_alert_filter(named)
        _ensure_ops_alert_filter(app_logger)
        return named

    handlers = _build_handlers()
    _attach_handlers(named, handlers)
    _attach_handlers(app_logger, handlers)
    _LOGGING_CONFIGURED = True
    _ensure_ops_alert_filter(named)
    _ensure_ops_alert_filter(app_logger)
    return named


logger = setup_logger()


def mask_phone(phone) -> str:
    """138****5678-style unrecoverable display -- last 4 digits only."""
    p = str(phone or "").strip()
    if len(p) < 4:
        return "***"
    return "***" + p[-4:]


def mask_wechat_identity(value) -> str:
    """Short, bounded diagnostic form of an openid/unionid -- never the full
    value. Enough to eyeball-correlate two log lines about the same identity
    without the value itself being reconstructable or reusable."""
    v = str(value or "").strip()
    if not v:
        return ""
    return f"{v[:6]}...(len={len(v)})"


def safe_log(log_fn, *args, **kwargs) -> None:
    try:
        log_fn(*args, **kwargs)
    except Exception:
        pass


def log_event(level: str, event: str, **fields) -> None:
    extra = {"event": event}
    extra.update(fields)
    log_fn = getattr(logger, level, logger.info)
    safe_log(log_fn, event, extra=extra)


def log_order_status_changed(
    *,
    order_id,
    old_status,
    new_status,
    tenant_id=None,
    actor=None,
    source=None,
    reason=None,
) -> None:
    if old_status == new_status:
        return
    log_event(
        "info",
        "ORDER_STATUS_CHANGED",
        order_id=order_id,
        tenant_id=tenant_id,
        old_status=old_status,
        new_status=new_status,
        actor=actor,
        source=source,
        reason=reason,
    )


def log_coupon_transition(
    *,
    coupon_id,
    from_status,
    to_status,
    tenant_id=None,
    member_id=None,
    order_id=None,
    reason=None,
) -> None:
    event = _COUPON_EVENT_BY_TO_STATUS.get(to_status)
    if not event:
        return
    log_event(
        "info",
        event,
        coupon_id=coupon_id,
        tenant_id=tenant_id,
        member_id=member_id,
        order_id=order_id,
        from_status=from_status,
        to_status=to_status,
        reason=reason,
    )
