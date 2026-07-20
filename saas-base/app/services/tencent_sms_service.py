import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime
from typing import Any

import httpx

from app.config import settings
from app.core.cache_helper import delete_cache, get_cache, set_cache
from app.core.logger import logger

_memory_cache: dict[str, tuple[float, Any]] = {}
_HOST = "sms.tencentcloudapi.com"
_SERVICE = "sms"
_VERSION = "2021-01-11"
_ACTION = "SendSms"
_ALGORITHM = "TC3-HMAC-SHA256"


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


def hash_login_code(phone: str, code: str) -> str:
    secret = settings.JWT_SECRET_KEY.encode("utf-8")
    payload = f"merchant-login:{phone}:{code}".encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def generate_login_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


class TencentSmsService:
    def __init__(self) -> None:
        self.ttl = settings.SMS_CODE_TTL_SECONDS
        self.interval = settings.SMS_CODE_SEND_INTERVAL_SECONDS
        self.daily_limit = settings.SMS_CODE_DAILY_LIMIT
        self.max_attempts = settings.SMS_CODE_MAX_ATTEMPTS

    def _code_key(self, phone: str) -> str:
        return f"sms:merchant-login:code:{phone}"

    def _cooldown_key(self, phone: str) -> str:
        return f"sms:merchant-login:cooldown:{phone}"

    def _daily_key(self, phone: str) -> str:
        day = datetime.utcnow().strftime("%Y%m%d")
        return f"sms:merchant-login:daily:{day}:{phone}"

    def is_configured(self) -> bool:
        return all([
            settings.TENCENTCLOUD_SECRET_ID,
            settings.TENCENTCLOUD_SECRET_KEY,
            settings.TENCENT_SMS_APP_ID,
            settings.TENCENT_SMS_SIGN_NAME,
            settings.TENCENT_SMS_LOGIN_TEMPLATE_ID,
        ])

    async def request_login_code(self, phone: str) -> tuple[bool, str, dict]:
        cooldown = await _cache_get(self._cooldown_key(phone))
        if cooldown:
            return False, "验证码发送过于频繁，请稍后再试", {"retry_after": self.interval}

        sent_count = int(await _cache_get(self._daily_key(phone)) or 0)
        if sent_count >= self.daily_limit:
            return False, "今日验证码发送次数已达上限，请明天再试", {}

        if not self.is_configured():
            logger.error("Tencent SMS config missing for merchant login code")
            return False, "短信服务未配置，请联系服务商：15936889988", {}

        code = generate_login_code()
        ok, message = await self.send_login_code(phone, code)
        if not ok:
            return False, message, {}

        await self.store_login_code(phone, code)
        await _cache_set(self._cooldown_key(phone), True, self.interval)
        await _cache_set(self._daily_key(phone), sent_count + 1, 86400)
        return True, "验证码已发送", {"expires_in": self.ttl, "retry_after": self.interval}

    async def store_login_code(self, phone: str, code: str) -> None:
        record = {
            "hash": hash_login_code(phone, code),
            "expires_at": int(_now() + self.ttl),
            "attempts": 0,
        }
        await _cache_set(self._code_key(phone), record, self.ttl)

    async def verify_login_code(self, phone: str, code: str) -> bool:
        record = await _cache_get(self._code_key(phone))
        if not isinstance(record, dict):
            return False

        if int(record.get("expires_at") or 0) <= int(_now()):
            await _cache_delete(self._code_key(phone))
            return False

        attempts = int(record.get("attempts") or 0)
        if attempts >= self.max_attempts:
            await _cache_delete(self._code_key(phone))
            return False

        expected = str(record.get("hash") or "")
        actual = hash_login_code(phone, (code or "").strip())
        if hmac.compare_digest(expected, actual):
            await _cache_delete(self._code_key(phone))
            return True

        record["attempts"] = attempts + 1
        remaining_ttl = max(int(record.get("expires_at") or 0) - int(_now()), 1)
        await _cache_set(self._code_key(phone), record, remaining_ttl)
        return False

    async def send_login_code(self, phone: str, code: str) -> tuple[bool, str]:
        payload = {
            "PhoneNumberSet": [f"+86{phone}"],
            "SmsSdkAppId": settings.TENCENT_SMS_APP_ID,
            "SignName": settings.TENCENT_SMS_SIGN_NAME,
            "TemplateId": settings.TENCENT_SMS_LOGIN_TEMPLATE_ID,
            "TemplateParamSet": [code],
        }
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        timestamp = int(time.time())
        headers = self._build_headers(body, timestamp)

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post(f"https://{_HOST}", content=body.encode("utf-8"), headers=headers)
                response.raise_for_status()
                result = response.json()
        except Exception as exc:
            logger.error(f"Tencent SMS send failed: {exc}")
            return False, "验证码发送失败，请稍后再试"

        status_set = (result.get("Response") or {}).get("SendStatusSet") or []
        first_status = status_set[0] if status_set else {}
        code_value = first_status.get("Code")
        if code_value == "Ok":
            return True, "验证码已发送"

        logger.error(f"Tencent SMS rejected login code: {result}")
        return False, first_status.get("Message") or "验证码发送失败，请稍后再试"

    def _build_headers(self, body: str, timestamp: int) -> dict[str, str]:
        date = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")
        canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{_HOST}\nx-tc-action:{_ACTION.lower()}\n"
        signed_headers = "content-type;host;x-tc-action"
        canonical_request = "\n".join([
            "POST",
            "/",
            "",
            canonical_headers,
            signed_headers,
            _sha256_hex(body),
        ])
        credential_scope = f"{date}/{_SERVICE}/tc3_request"
        string_to_sign = "\n".join([
            _ALGORITHM,
            str(timestamp),
            credential_scope,
            _sha256_hex(canonical_request),
        ])
        secret_date = _sign(("TC3" + settings.TENCENTCLOUD_SECRET_KEY).encode("utf-8"), date)
        secret_service = _sign(secret_date, _SERVICE)
        secret_signing = _sign(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            f"{_ALGORITHM} Credential={settings.TENCENTCLOUD_SECRET_ID}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return {
            "Authorization": authorization,
            "Content-Type": "application/json; charset=utf-8",
            "Host": _HOST,
            "X-TC-Action": _ACTION,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": _VERSION,
            "X-TC-Region": settings.TENCENT_SMS_REGION,
        }