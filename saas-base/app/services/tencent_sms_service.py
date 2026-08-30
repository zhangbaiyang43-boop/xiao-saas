import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.config import settings
from app.core.cache_helper import delete_cache, get_cache, set_cache
from app.core.logger import logger

_memory_cache: dict[str, tuple[float, Any]] = {}


class SmsPurpose:
    """Binds a one-time code to the flow it was issued for, so a code sent
    for one purpose cannot be replayed to complete a different one (e.g. a
    LOGIN code cannot be used to REGISTER). Threaded through the cache-key
    and hash functions below -- each purpose gets its own cooldown/code
    namespace, entirely independent of the others (the daily send *budget*
    is deliberately NOT purpose-scoped -- see _daily_key). Deliberately just
    a few string constants, not a project-wide enum: add a new one here only
    when a new phone-verification flow actually needs it."""

    LOGIN = "login"
    REGISTER = "register"
    CHANGE_PHONE = "change_phone"
    WECOM_BINDING = "wecom_binding"


class SmsErrorCode:
    """Stable, client-facing business codes for a failed send_login_code
    request. These -- never Tencent's own Message string -- are what
    reaches the API response's data.error_code and, from there, the
    frontend. Minimal taxonomy on purpose: only what request_login_code can
    actually and reliably distinguish today."""

    TOO_FREQUENT = "SMS_TOO_FREQUENT"
    DAILY_LIMIT = "SMS_DAILY_LIMIT"
    PROVIDER_REJECTED = "SMS_PROVIDER_REJECTED"
    PROVIDER_UNAVAILABLE = "SMS_PROVIDER_UNAVAILABLE"


# Canonical, server-authored Chinese copy per SmsErrorCode -- the only text
# a client ever sees for a failed send, regardless of what Tencent's own
# Message field said.
_ERROR_CODE_MESSAGES = {
    SmsErrorCode.TOO_FREQUENT: "验证码获取过于频繁，请稍后再试",
    SmsErrorCode.DAILY_LIMIT: "今日验证码获取次数已达上限，请明日再试",
    SmsErrorCode.PROVIDER_REJECTED: "验证码发送失败，请稍后再试或联系服务商",
    SmsErrorCode.PROVIDER_UNAVAILABLE: "短信服务暂时不可用，请稍后再试",
}

# Tencent's own machine-readable per-number daily cap rejection code -- the
# ONLY provider code allowed to map to SmsErrorCode.DAILY_LIMIT and to
# saturate our local daily counter (see request_login_code). Matched
# exactly against SendStatusSet[0].Code, never against the human-readable
# Message string, so a Tencent wording change can never silently break this.
_PROVIDER_DAILY_LIMIT_CODE = "LimitExceeded.PhoneNumberDailyLimit"
# Tencent's other LimitExceeded.* codes (e.g. the 30-second/1-hour windows)
# are frequency-shaped, not a hard daily cutoff -- classified as
# TOO_FREQUENT rather than DAILY_LIMIT.
_PROVIDER_RATE_LIMIT_PREFIX = "LimitExceeded."


def _classify_provider_code(provider_code: str | None) -> str:
    """provider_code is None only for the network/timeout/exception path
    (see _send_login_code_with_status) -- that's a transport failure, not a
    rejection, so it maps to PROVIDER_UNAVAILABLE rather than REJECTED."""
    if provider_code is None:
        return SmsErrorCode.PROVIDER_UNAVAILABLE
    if provider_code == _PROVIDER_DAILY_LIMIT_CODE:
        return SmsErrorCode.DAILY_LIMIT
    if provider_code.startswith(_PROVIDER_RATE_LIMIT_PREFIX):
        return SmsErrorCode.TOO_FREQUENT
    return SmsErrorCode.PROVIDER_REJECTED


@dataclass
class SmsSendStatus:
    """Structured result of one provider send attempt -- ok plus enough of
    the provider's own machine-readable response to classify a failure
    without ever needing to string-match provider_message."""

    ok: bool
    provider_code: str | None
    provider_message: str


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


def hash_login_code(phone: str, code: str, purpose: str = SmsPurpose.LOGIN) -> str:
    secret = settings.JWT_SECRET_KEY.encode("utf-8")
    payload = f"merchant-{purpose}:{phone}:{code}".encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def generate_login_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def mask_phone(phone: str) -> str:
    value = str(phone or "")
    if len(value) == 11:
        return f"{value[:3]}****{value[-4:]}"
    if len(value) > 3:
        return f"{value[:3]}****"
    return "****"


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

    def _code_key(self, phone: str, purpose: str = SmsPurpose.LOGIN) -> str:
        return f"sms:merchant-{purpose}:code:{phone}"

    def _cooldown_key(self, phone: str, purpose: str = SmsPurpose.LOGIN) -> str:
        return f"sms:merchant-{purpose}:cooldown:{phone}"

    def _daily_key(self, phone: str, purpose: str = SmsPurpose.LOGIN) -> str:
        # Deliberately NOT purpose-scoped: Tencent's real per-number daily
        # cap is a single shared budget for the phone number regardless of
        # which of our flows (login vs register) asked for the code, so our
        # own counter must track the same shared budget or it can never
        # pre-empt the provider's real limit (a user could exhaust the
        # per-purpose budget on register, then still have "10 more" on
        # login against a number Tencent has already fully throttled).
        # `purpose` stays a parameter for call-site compatibility with
        # _code_key/_cooldown_key, just unused here.
        del purpose
        day = datetime.utcnow().strftime("%Y%m%d")
        return f"sms:merchant:daily:{day}:{phone}"

    def is_configured(self) -> bool:
        return all([
            settings.TENCENTCLOUD_SECRET_ID,
            settings.TENCENTCLOUD_SECRET_KEY,
            settings.TENCENT_SMS_APP_ID,
            settings.TENCENT_SMS_SIGN_NAME,
            settings.TENCENT_SMS_LOGIN_TEMPLATE_ID,
        ])

    async def request_login_code(self, phone: str, purpose: str = SmsPurpose.LOGIN) -> tuple[bool, str, dict]:
        cooldown = await _cache_get(self._cooldown_key(phone, purpose))
        if cooldown:
            return (
                False,
                _ERROR_CODE_MESSAGES[SmsErrorCode.TOO_FREQUENT],
                {"error_code": SmsErrorCode.TOO_FREQUENT, "retry_after": self.interval},
            )

        daily_key = self._daily_key(phone, purpose)
        sent_count = int(await _cache_get(daily_key) or 0)
        if sent_count >= self.daily_limit:
            return (
                False,
                _ERROR_CODE_MESSAGES[SmsErrorCode.DAILY_LIMIT],
                {"error_code": SmsErrorCode.DAILY_LIMIT},
            )

        if not self.is_configured():
            logger.error("Tencent SMS config missing for merchant login code")
            return (
                False,
                _ERROR_CODE_MESSAGES[SmsErrorCode.PROVIDER_UNAVAILABLE],
                {"error_code": SmsErrorCode.PROVIDER_UNAVAILABLE},
            )

        code = generate_login_code()
        status = await self._send_login_code_with_status(phone, code)
        if not status.ok:
            error_code = _classify_provider_code(status.provider_code)
            if error_code == SmsErrorCode.DAILY_LIMIT:
                # Tencent's own machine-readable per-number daily cap fired
                # -- saturate our local counter so the very next click is
                # rejected by our own cheap cache check instead of paying
                # for another round trip to Tencent for a result we already
                # know. Only for this exact, unambiguous provider code --
                # never for PROVIDER_REJECTED (an unrecognized rejection
                # must not silently exhaust a budget that may not actually
                # be spent).
                await _cache_set(daily_key, self.daily_limit, 86400)
            return False, _ERROR_CODE_MESSAGES[error_code], {"error_code": error_code}

        await self.store_login_code(phone, code, purpose)
        await _cache_set(self._cooldown_key(phone, purpose), True, self.interval)
        await _cache_set(daily_key, sent_count + 1, 86400)
        return True, "验证码已发送", {"expires_in": self.ttl, "retry_after": self.interval}

    async def store_login_code(self, phone: str, code: str, purpose: str = SmsPurpose.LOGIN) -> None:
        record = {
            "hash": hash_login_code(phone, code, purpose),
            "expires_at": int(_now() + self.ttl),
            "attempts": 0,
        }
        await _cache_set(self._code_key(phone, purpose), record, self.ttl)

    async def verify_login_code(self, phone: str, code: str, purpose: str = SmsPurpose.LOGIN) -> bool:
        record = await _cache_get(self._code_key(phone, purpose))
        if not isinstance(record, dict):
            return False

        if int(record.get("expires_at") or 0) <= int(_now()):
            await _cache_delete(self._code_key(phone, purpose))
            return False

        attempts = int(record.get("attempts") or 0)
        if attempts >= self.max_attempts:
            await _cache_delete(self._code_key(phone, purpose))
            return False

        expected = str(record.get("hash") or "")
        actual = hash_login_code(phone, (code or "").strip(), purpose)
        if hmac.compare_digest(expected, actual):
            await _cache_delete(self._code_key(phone, purpose))
            return True

        record["attempts"] = attempts + 1
        remaining_ttl = max(int(record.get("expires_at") or 0) - int(_now()), 1)
        await _cache_set(self._code_key(phone, purpose), record, remaining_ttl)
        return False

    async def send_login_code(self, phone: str, code: str) -> tuple[bool, str]:
        """Backward-compatible wrapper: (ok, provider_message) exactly as
        before -- the channel-partner flow and its tests
        (test_tencent_rejection_log_is_sanitized) call this directly and
        depend on the raw provider message being returned unclassified at
        this layer for their own diagnostic/logging purposes. Classification
        for the merchant login/register UI happens one layer up, in
        request_login_code, via _send_login_code_with_status."""
        status = await self._send_login_code_with_status(phone, code)
        return status.ok, status.provider_message

    async def _send_login_code_with_status(self, phone: str, code: str) -> SmsSendStatus:
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
            return SmsSendStatus(ok=False, provider_code=None, provider_message="验证码发送失败，请稍后再试")

        status_set = (result.get("Response") or {}).get("SendStatusSet") or []
        first_status = status_set[0] if status_set else {}
        code_value = first_status.get("Code")
        if code_value == "Ok":
            return SmsSendStatus(ok=True, provider_code=code_value, provider_message="验证码已发送")

        response_payload = result.get("Response") or {}
        request_id = response_payload.get("RequestId") or ""
        logger.error(
            "Tencent SMS rejected: provider=tencent code=%s request_id=%s phone=%s",
            code_value,
            request_id,
            mask_phone(phone),
        )
        return SmsSendStatus(
            ok=False,
            provider_code=code_value,
            provider_message=first_status.get("Message") or "验证码发送失败，请稍后再试",
        )

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
