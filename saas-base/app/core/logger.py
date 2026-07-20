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