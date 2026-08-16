import logging
import json
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from app.core.tenant_context import TenantContext
import traceback

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "tenant_id": TenantContext.get_current_tenant_id() or "unknown",
            "request_id": getattr(record, "request_id", "unknown"),
            "message": record.getMessage()
        }
        
        if record.exc_info:
            log_record["exception"] = traceback.format_exc()
        
        return json.dumps(log_record)

def setup_logger():
    logger = logging.getLogger("saas-member")
    logger.setLevel(logging.INFO)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(JsonFormatter())
    
    log_file = "logs/app.log"
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(JsonFormatter())
    
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logger()


# P0-16 Phase B1: small, pure PII-mask helpers. Deliberately NOT a redaction
# framework -- just the two shapes this codebase's confirmed leak sites need
# (phone, WeChat openid/unionid). Never raises on None/short/malformed input,
# since these are called directly inside f-strings at logger call sites.
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


# P0-16 Phase B1: telemetry must never change a business result (Section 27/83
# of the B1 brief). Python's logging module already isolates a malformed
# *argument* internally (Handler.handleError swallows formatting failures),
# but if the logging call itself is mocked/replaced to raise outright (e.g. a
# genuinely broken handler), that would otherwise propagate straight into the
# caller. This wraps exactly that case, best-effort, with no DB/transaction
# coupling of any kind.
def safe_log(log_fn, *args, **kwargs) -> None:
    try:
        log_fn(*args, **kwargs)
    except Exception:
        pass