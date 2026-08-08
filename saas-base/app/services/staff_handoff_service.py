"""One-time H5 handoff tokens (miniapp identity → admin-h5 trusted device + JWT).

Handoff is NOT a JWT / device secret / permission token.
Production: Redis fail-closed.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any, Optional

from app.config import settings
from app.core.logger import logger
from app.services.staff_bind_token_service import StaffAuthStoreUnavailable, _delete, _get, _put

HANDOFF_PREFIX = "staff_handoff:"


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _ttl() -> int:
    return max(15, int(settings.STAFF_HANDOFF_TTL_SECONDS or 60))


async def create_handoff(
    *,
    tenant_id: str,
    account_id: int,
    wechat_app_id: str,
    openid: str,
) -> dict[str, Any]:
    raw = secrets.token_urlsafe(32)  # 256-bit
    token_hash = _hash_token(raw)
    ttl = _ttl()
    expires_at = datetime.utcnow() + timedelta(seconds=ttl)
    # Store openid hash only — never persist raw openid in Redis value for logs/leak surface.
    openid_ref = hashlib.sha256(f"{wechat_app_id}:{openid}".encode("utf-8")).hexdigest()[:24]
    payload = {
        "tenant_id": tenant_id,
        "account_id": int(account_id),
        "wechat_app_id": wechat_app_id,
        "openid_ref": openid_ref,
        "purpose": "staff_h5_login",
        "created_at": datetime.utcnow().isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    await _put(f"{HANDOFF_PREFIX}{token_hash}", payload, ttl)
    logger.info(
        "staff_handoff_created account_id=%s tenant_id=%s",
        account_id,
        tenant_id,
    )
    return {
        "handoff_token": raw,
        "expires_at": expires_at.isoformat() + "Z",
        "expires_in": ttl,
    }


async def consume_handoff(raw_token: str) -> Optional[dict]:
    raw = (raw_token or "").strip()
    if not raw or len(raw) < 16:
        return None
    key = f"{HANDOFF_PREFIX}{_hash_token(raw)}"
    data = await _get(key)
    if not data or data.get("purpose") != "staff_h5_login":
        return None
    await _delete(key)
    return data
