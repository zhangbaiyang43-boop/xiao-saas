"""One-time staff WeChat bind tokens / OAuth state.

Production: Redis only (fail closed). Process-local memory is for
dev/test only — bind tokens and OAuth state need single-use TTL and
cross-worker consistency, which memory cannot provide.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi.encoders import jsonable_encoder

from app.config import settings
from app.core.logger import logger
from app.core.redis_client import redis_client

BIND_PREFIX = "staff_bind:"
BIND_ACCOUNT_PREFIX = "staff_bind_account:"
OAUTH_STATE_PREFIX = "staff_oauth_state:"
OAUTH_SESSION_PREFIX = "staff_oauth_session:"

# Dev/test only. Never used when memory_store_allowed() is False.
_MEMORY: dict[str, tuple[Any, float]] = {}

STAFF_AUTH_STORE_UNAVAILABLE_MSG = "员工微信绑定服务暂不可用，请稍后重试"


class StaffAuthStoreUnavailable(Exception):
    """Redis unavailable in an environment that forbids memory fallback."""

    def __init__(self, msg: str = STAFF_AUTH_STORE_UNAVAILABLE_MSG):
        super().__init__(msg)
        self.msg = msg


def memory_store_allowed() -> bool:
    """Memory fallback only for non-production (or explicit flag)."""
    if settings.STAFF_WECHAT_ALLOW_MEMORY_STORE:
        return True
    env = (settings.APP_ENV or "").strip().lower()
    if env in ("production", "prod"):
        return False
    return True


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _bind_ttl() -> int:
    return max(60, int(settings.STAFF_WECHAT_BIND_TTL_SECONDS or 300))


def _full_key(key: str) -> str:
    return f"{settings.CACHE_PREFIX}{key}"


def _mem_set(key: str, value: Any, ttl: int) -> None:
    _MEMORY[key] = (value, time.time() + ttl)


def _mem_get(key: str) -> Any | None:
    item = _MEMORY.get(key)
    if not item:
        return None
    value, exp = item
    if time.time() > exp:
        _MEMORY.pop(key, None)
        return None
    return value


def _mem_del(key: str) -> None:
    _MEMORY.pop(key, None)


async def _redis_set(key: str, value: Any, ttl: int) -> bool:
    if not settings.REDIS_ENABLED:
        return False
    try:
        serialized = json.dumps(jsonable_encoder(value), ensure_ascii=False)
        await redis_client.setex(_full_key(key), ttl, serialized)
        return True
    except Exception as exc:
        logger.warning("staff_auth_redis_write_failed key_type=%s", key.split(":")[0])
        logger.debug("staff_auth_redis_write_error: %s", type(exc).__name__)
        return False


async def _redis_get(key: str) -> Any | None:
    if not settings.REDIS_ENABLED:
        return None
    try:
        raw = await redis_client.get(_full_key(key))
    except Exception as exc:
        logger.warning("staff_auth_redis_read_failed key_type=%s", key.split(":")[0])
        logger.debug("staff_auth_redis_read_error: %s", type(exc).__name__)
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


async def _redis_delete(key: str) -> None:
    if not settings.REDIS_ENABLED:
        return
    try:
        await redis_client.delete(_full_key(key))
    except Exception:
        pass


async def _put(key: str, value: Any, ttl: int) -> None:
    redis_ok = await _redis_set(key, value, ttl)
    if redis_ok:
        return
    if memory_store_allowed():
        _mem_set(key, value, ttl)
        return
    raise StaffAuthStoreUnavailable()


async def _get(key: str) -> Any | None:
    cached = await _redis_get(key)
    if cached is not None:
        return cached
    if memory_store_allowed():
        return _mem_get(key)
    return None


async def _delete(key: str) -> None:
    await _redis_delete(key)
    if memory_store_allowed():
        _mem_del(key)


async def create_bind_token(
    *,
    tenant_id: str,
    account_id: int,
    created_by_owner: str,
) -> dict[str, Any]:
    """Create a single active bind token for account; invalidate previous."""
    await invalidate_account_bind_token(account_id)

    raw = secrets.token_urlsafe(32)  # ~256 bit
    token_hash = _hash_token(raw)
    ttl = _bind_ttl()
    expires_at = datetime.utcnow() + timedelta(seconds=ttl)
    payload = {
        "tenant_id": tenant_id,
        "account_id": int(account_id),
        "created_by_owner": created_by_owner,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    await _put(f"{BIND_PREFIX}{token_hash}", payload, ttl)
    await _put(f"{BIND_ACCOUNT_PREFIX}{int(account_id)}", {"token_hash": token_hash}, ttl)

    base = (settings.PUBLIC_BASE_URL or settings.H5_ORDER_BASE_URL or "").rstrip("/")
    binding_url = f"{base}/staff-bind?t={raw}"
    logger.info(
        "staff_bind_token_created account_id=%s tenant_id=%s",
        account_id,
        tenant_id,
    )
    return {
        "binding_url": binding_url,
        "expires_at": expires_at.isoformat() + "Z",
        "expires_in": ttl,
    }


async def invalidate_account_bind_token(account_id: int) -> None:
    meta = await _get(f"{BIND_ACCOUNT_PREFIX}{int(account_id)}")
    if meta and meta.get("token_hash"):
        await _delete(f"{BIND_PREFIX}{meta['token_hash']}")
    await _delete(f"{BIND_ACCOUNT_PREFIX}{int(account_id)}")


async def peek_bind_token(raw_token: str) -> Optional[dict]:
    if not raw_token or len(raw_token) < 16:
        return None
    data = await _get(f"{BIND_PREFIX}{_hash_token(raw_token)}")
    if not data or data.get("status") != "pending":
        return None
    return data


async def consume_bind_token(raw_token: str) -> Optional[dict]:
    """Single-use consume. Returns payload or None if invalid/used/expired."""
    if not raw_token or len(raw_token) < 16:
        return None
    token_hash = _hash_token(raw_token)
    key = f"{BIND_PREFIX}{token_hash}"
    data = await _get(key)
    if not data or data.get("status") != "pending":
        return None
    await _delete(key)
    account_id = data.get("account_id")
    if account_id is not None:
        meta = await _get(f"{BIND_ACCOUNT_PREFIX}{int(account_id)}")
        if meta and meta.get("token_hash") == token_hash:
            await _delete(f"{BIND_ACCOUNT_PREFIX}{int(account_id)}")
        try:
            await _put(
                f"staff_bind_status:{int(account_id)}",
                {"status": "bound", "at": datetime.utcnow().isoformat()},
                120,
            )
        except StaffAuthStoreUnavailable:
            # Binding already consumed; status poll may miss — acceptable.
            pass
    return data


async def get_bind_status_for_account(account_id: int) -> str:
    """pending | bound | expired — for owner QR polling only."""
    status = await _get(f"staff_bind_status:{int(account_id)}")
    if status and status.get("status") == "bound":
        return "bound"
    meta = await _get(f"{BIND_ACCOUNT_PREFIX}{int(account_id)}")
    if meta and meta.get("token_hash"):
        data = await _get(f"{BIND_PREFIX}{meta['token_hash']}")
        if data and data.get("status") == "pending":
            return "pending"
    return "expired"


async def create_oauth_state(payload: dict, ttl: int = 300) -> str:
    state = secrets.token_urlsafe(24)
    await _put(f"{OAUTH_STATE_PREFIX}{state}", payload, ttl)
    return state


async def consume_oauth_state(state: str) -> Optional[dict]:
    if not state:
        return None
    key = f"{OAUTH_STATE_PREFIX}{state}"
    data = await _get(key)
    if not data:
        return None
    await _delete(key)
    return data


async def create_oauth_session(payload: dict, ttl: int = 300) -> str:
    sid = secrets.token_urlsafe(24)
    await _put(f"{OAUTH_SESSION_PREFIX}{sid}", payload, ttl)
    return sid


async def get_oauth_session(sid: str) -> Optional[dict]:
    if not sid:
        return None
    return await _get(f"{OAUTH_SESSION_PREFIX}{sid}")


async def delete_oauth_session(sid: str) -> None:
    if sid:
        await _delete(f"{OAUTH_SESSION_PREFIX}{sid}")
