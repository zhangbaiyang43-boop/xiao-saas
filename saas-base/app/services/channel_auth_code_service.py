import asyncio
import hashlib
import hmac
import re
import secrets
import time
from collections import defaultdict
from datetime import datetime
from typing import Any

from app.config import settings
from app.core.cache_helper import delete_cache, get_cache, set_cache
from app.services.channel_partner_service import normalize_mobile
from app.services.tencent_sms_service import TencentSmsService

SMS_CONFIG_UNAVAILABLE_MSG = "短信服务暂不可用，请联系平台管理员"
SMS_PROVIDER_FAILURE_MSG = "验证码发送失败，请稍后再试"
INVALID_MOBILE_MSG = "请输入正确的手机号"

_memory_cache: dict[str, tuple[float, Any]] = {}
_code_locks = defaultdict(asyncio.Lock)
_send_locks = defaultdict(asyncio.Lock)


def _now() -> float:
    return time.time()


def _memory_get(key: str) -> Any:
    item = _memory_cache.get(key)
    if not item:
        return None
    expires_at, value = item
    if expires_at <= _now():
        _memory_cache.pop(key, None)
        return None
    return value


def _memory_set(key: str, value: Any, ttl: int) -> None:
    _memory_cache[key] = (_now() + max(ttl, 1), value)


def _memory_delete(key: str) -> None:
    _memory_cache.pop(key, None)


async def _cache_get(key: str) -> Any:
    cached = await get_cache(key)
    if cached is not None:
        return cached
    return _memory_get(key)


async def _cache_set(key: str, value: Any, ttl: int) -> None:
    _memory_set(key, value, ttl)
    await set_cache(key, value, ttl)


async def _cache_delete(key: str) -> None:
    _memory_delete(key)
    await delete_cache(key)


def hash_channel_login_code(mobile_normalized: str, code: str) -> str:
    secret = settings.JWT_SECRET_KEY.encode("utf-8")
    payload = f"channel-login:{mobile_normalized}:{code}".encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def generate_login_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def is_valid_mainland_mobile(mobile_normalized: str) -> bool:
    return bool(re.fullmatch(r"1\d{10}", mobile_normalized or ""))


class ChannelAuthCodeService:
    def __init__(self) -> None:
        self.ttl = settings.SMS_CODE_TTL_SECONDS
        self.interval = settings.SMS_CODE_SEND_INTERVAL_SECONDS
        self.daily_limit = settings.SMS_CODE_DAILY_LIMIT
        self.max_attempts = settings.SMS_CODE_MAX_ATTEMPTS

    def _code_key(self, mobile_normalized: str) -> str:
        return f"sms:channel-login:code:{mobile_normalized}"

    def _cooldown_key(self, mobile_normalized: str) -> str:
        return f"sms:channel-login:cooldown:{mobile_normalized}"

    def _daily_key(self, mobile_normalized: str) -> str:
        day = datetime.utcnow().strftime("%Y%m%d")
        return f"sms:channel-login:daily:{day}:{mobile_normalized}"

    def _fake_provider_enabled(self) -> bool:
        return (settings.APP_ENV or "").strip().lower() != "production"

    async def request_login_code(self, mobile: str) -> tuple[bool, str, dict]:
        mobile_normalized = normalize_mobile(mobile)
        if not mobile_normalized:
            return False, "mobile required", {}
        if not is_valid_mainland_mobile(mobile_normalized):
            return False, INVALID_MOBILE_MSG, {}

        async with _send_locks[mobile_normalized]:
            cooldown = await _cache_get(self._cooldown_key(mobile_normalized))
            if cooldown:
                return False, "验证码发送过于频繁，请稍后再试", {"retry_after": self.interval}
            sent_count = int(await _cache_get(self._daily_key(mobile_normalized)) or 0)
            if sent_count >= self.daily_limit:
                return False, "今日验证码发送次数已达上限，请明天再试", {}

            code = generate_login_code()
            if not self._fake_provider_enabled():
                sms = TencentSmsService()
                if not sms.is_configured():
                    return False, SMS_CONFIG_UNAVAILABLE_MSG, {}
                ok, _provider_message = await sms.send_login_code(mobile_normalized, code)
                if not ok:
                    return False, SMS_PROVIDER_FAILURE_MSG, {}
                await self.store_login_code(mobile_normalized, code)
                await _cache_set(self._cooldown_key(mobile_normalized), True, self.interval)
                await _cache_set(self._daily_key(mobile_normalized), sent_count + 1, 86400)
                return True, "验证码已发送", {"expires_in": self.ttl, "retry_after": self.interval}

            await self.store_login_code(mobile_normalized, code)
            await _cache_set(self._cooldown_key(mobile_normalized), True, self.interval)
            await _cache_set(self._daily_key(mobile_normalized), sent_count + 1, 86400)
            return True, "验证码已发送", {"expires_in": self.ttl, "retry_after": self.interval, "debug_code": code}

    async def store_login_code(self, mobile_normalized: str, code: str) -> None:
        mobile_key = normalize_mobile(mobile_normalized)
        record = {
            "hash": hash_channel_login_code(mobile_key, (code or "").strip()),
            "expires_at": int(_now() + self.ttl),
            "attempts": 0,
        }
        await _cache_set(self._code_key(mobile_key), record, self.ttl)

    async def verify_login_code(self, mobile_normalized: str, code: str) -> bool:
        mobile_key = normalize_mobile(mobile_normalized)
        async with _code_locks[mobile_key]:
            key = self._code_key(mobile_key)
            record = await _cache_get(key)
            if not isinstance(record, dict):
                return False
            if int(record.get("expires_at") or 0) <= int(_now()):
                await _cache_delete(key)
                return False
            attempts = int(record.get("attempts") or 0)
            if attempts >= self.max_attempts:
                await _cache_delete(key)
                return False
            expected = str(record.get("hash") or "")
            actual = hash_channel_login_code(mobile_key, (code or "").strip())
            if hmac.compare_digest(expected, actual):
                await _cache_delete(key)
                return True
            record["attempts"] = attempts + 1
            remaining_ttl = max(int(record.get("expires_at") or 0) - int(_now()), 1)
            await _cache_set(key, record, remaining_ttl)
            return False
