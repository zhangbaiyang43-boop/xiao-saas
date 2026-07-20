import base64
import hashlib
import hmac
import json
import random
import time
from datetime import datetime
from typing import Any

from app.config import settings
from app.core.logger import logger
from app.core.redis_client import redis_client


class AntiFraudService:
    DYNAMIC_PREFIX = "DVC1"
    # Excludes O, 0, I, 1, L to avoid visual confusion
    VERIFY_CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

    @staticmethod
    def generate_short_verify_code(length: int = 6) -> str:
        return "".join(random.choices(AntiFraudService.VERIFY_CODE_CHARS, k=length))

    @staticmethod
    def _b64encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode().rstrip("=")

    @staticmethod
    def _b64decode(data: str) -> bytes:
        padding = "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(data + padding)

    @staticmethod
    def _sign(payload_part: str) -> str:
        digest = hmac.new(
            settings.JWT_SECRET_KEY.encode(),
            payload_part.encode(),
            hashlib.sha256,
        ).digest()
        return AntiFraudService._b64encode(digest)

    @staticmethod
    def build_dynamic_verify_code(
        tenant_id: str,
        coupon_id: int,
        customer_id: int,
        coupon_code: str,
        ttl_seconds: int | None = None,
        now: int | None = None,
    ) -> str:
        now_ts = int(now or time.time())
        ttl = int(ttl_seconds or settings.VERIFY_CODE_TTL_SECONDS)
        payload = {
            "tenant_id": str(tenant_id),
            "coupon_id": int(coupon_id),
            "customer_id": int(customer_id),
            "coupon_code": str(coupon_code).strip().upper(),
            "exp": now_ts + ttl,
            "iat": now_ts,
        }
        payload_part = AntiFraudService._b64encode(
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        )
        return f"{AntiFraudService.DYNAMIC_PREFIX}.{payload_part}.{AntiFraudService._sign(payload_part)}"

    @staticmethod
    def is_dynamic_verify_code(code: str) -> bool:
        return str(code or "").startswith(f"{AntiFraudService.DYNAMIC_PREFIX}.")

    @staticmethod
    def parse_dynamic_verify_code(code: str, now: int | None = None) -> dict[str, Any]:
        parts = str(code or "").strip().split(".")
        if len(parts) != 3 or parts[0] != AntiFraudService.DYNAMIC_PREFIX:
            raise ValueError("不是动态核销码")

        payload_part, signature = parts[1], parts[2]
        expected = AntiFraudService._sign(payload_part)
        if not hmac.compare_digest(signature, expected):
            raise ValueError("核销码签名无效")

        payload = json.loads(AntiFraudService._b64decode(payload_part).decode())
        now_ts = int(now or time.time())
        if now_ts > int(payload.get("exp") or 0):
            raise ValueError("核销码已过期")
        return payload

    @staticmethod
    def today_key() -> str:
        return datetime.utcnow().strftime("%Y%m%d")

    @staticmethod
    async def _incr_with_ttl(key: str, ttl_seconds: int) -> int:
        value = await redis_client.incr(key)
        if int(value) == 1:
            await redis_client.expire(key, ttl_seconds)
        return int(value)

    @staticmethod
    async def allow_counter(key: str, limit: int, ttl_seconds: int, risk_type: str, detail: dict | None = None) -> bool:
        if not settings.REDIS_ENABLED:
            return True
        try:
            count = await AntiFraudService._incr_with_ttl(key, ttl_seconds)
            if count > int(limit):
                await AntiFraudService.log_risk(risk_type, {**(detail or {}), "key": key, "count": count, "limit": limit})
                return False
            return True
        except Exception as exc:
            logger.error(f"anti fraud counter failed: {exc}")
            return True

    @staticmethod
    async def allow_daily_issue(tenant_id: str, customer_id: int) -> bool:
        key = f"antifraud:issue:{tenant_id}:{customer_id}:{AntiFraudService.today_key()}"
        return await AntiFraudService.allow_counter(
            key,
            settings.DAILY_COUPON_ISSUE_LIMIT,
            86400,
            "daily_issue_limit",
            {"tenant_id": tenant_id, "customer_id": str(customer_id)},
        )

    @staticmethod
    async def allow_daily_verify(tenant_id: str, customer_id: int) -> bool:
        key = f"antifraud:verify:{tenant_id}:{customer_id}:{AntiFraudService.today_key()}"
        return await AntiFraudService.allow_counter(
            key,
            settings.DAILY_COUPON_VERIFY_LIMIT,
            86400,
            "daily_verify_limit",
            {"tenant_id": tenant_id, "customer_id": str(customer_id)},
        )

    @staticmethod
    async def allow_frequency(scope: str, identity: str, detail: dict | None = None) -> bool:
        if not identity:
            return True
        key = f"antifraud:freq:{scope}:{identity}"
        return await AntiFraudService.allow_counter(
            key,
            settings.DEVICE_FREQUENCY_LIMIT,
            settings.DEVICE_FREQUENCY_WINDOW_SECONDS,
            "high_frequency",
            detail,
        )

    @staticmethod
    async def log_risk(risk_type: str, detail: dict | None = None) -> None:
        payload = {
            "risk_type": risk_type,
            "detail": detail or {},
            "created_at": datetime.utcnow().isoformat(),
        }
        logger.warning(f"anti fraud risk: {payload}")
        if not settings.REDIS_ENABLED:
            return
        try:
            await redis_client.lpush("antifraud:risk_logs", json.dumps(payload, ensure_ascii=False))
            await redis_client.ltrim("antifraud:risk_logs", 0, 999)
        except Exception as exc:
            logger.error(f"anti fraud risk log failed: {exc}")
