"""Mini-program staff bind scenes (short opaque scene for getwxacodeunlimit).

WeChat scene max length is 32. Use 128-bit hex (32 chars).
Production: Redis fail-closed (shared with staff_bind_token_service rules).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any, Optional

from app.config import settings
from app.core.logger import logger
from app.services.staff_bind_token_service import (
    StaffAuthStoreUnavailable,
    _delete,
    _get,
    _put,
)

MP_BIND_PREFIX = "staff_mp_bind:"
MP_BIND_ACCOUNT_PREFIX = "staff_mp_bind_account:"
MP_BIND_STATUS_PREFIX = "staff_mp_bind_status:"


def _hash_scene(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _ttl() -> int:
    return max(60, int(settings.STAFF_MP_BIND_TTL_SECONDS or settings.STAFF_WECHAT_BIND_TTL_SECONDS or 300))


def new_bind_scene() -> str:
    """128-bit secure random, hex-encoded → exactly 32 chars (WeChat scene limit)."""
    return secrets.token_hex(16)


async def invalidate_account_mp_bind(account_id: int) -> None:
    meta = await _get(f"{MP_BIND_ACCOUNT_PREFIX}{int(account_id)}")
    if meta and meta.get("scene_hash"):
        await _delete(f"{MP_BIND_PREFIX}{meta['scene_hash']}")
    await _delete(f"{MP_BIND_ACCOUNT_PREFIX}{int(account_id)}")


async def create_mp_bind_session(
    *,
    tenant_id: str,
    account_id: int,
    created_by_owner: str,
) -> dict[str, Any]:
    """Create single-active bind scene for account; previous scene invalidated."""
    await invalidate_account_mp_bind(account_id)

    scene = new_bind_scene()
    scene_hash = _hash_scene(scene)
    ttl = _ttl()
    expires_at = datetime.utcnow() + timedelta(seconds=ttl)
    payload = {
        "tenant_id": tenant_id,
        "account_id": int(account_id),
        "created_by_owner": created_by_owner,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    try:
        await _put(f"{MP_BIND_PREFIX}{scene_hash}", payload, ttl)
        await _put(f"{MP_BIND_ACCOUNT_PREFIX}{int(account_id)}", {"scene_hash": scene_hash}, ttl)
    except StaffAuthStoreUnavailable:
        raise
    logger.info(
        "staff_mp_bind_session_created account_id=%s tenant_id=%s",
        account_id,
        tenant_id,
    )
    return {
        "scene": scene,
        "session_id": scene_hash[:16],
        "expires_at": expires_at.isoformat() + "Z",
        "expires_in": ttl,
    }


async def peek_mp_bind_scene(scene: str) -> Optional[dict]:
    raw = (scene or "").strip()
    if not raw or len(raw) < 16 or len(raw) > 32:
        return None
    data = await _get(f"{MP_BIND_PREFIX}{_hash_scene(raw)}")
    if not data or data.get("status") != "pending":
        return None
    return data


async def consume_mp_bind_scene(scene: str) -> Optional[dict]:
    raw = (scene or "").strip()
    if not raw or len(raw) < 16 or len(raw) > 32:
        return None
    scene_hash = _hash_scene(raw)
    key = f"{MP_BIND_PREFIX}{scene_hash}"
    data = await _get(key)
    if not data or data.get("status") != "pending":
        return None
    await _delete(key)
    account_id = data.get("account_id")
    if account_id is not None:
        meta = await _get(f"{MP_BIND_ACCOUNT_PREFIX}{int(account_id)}")
        if meta and meta.get("scene_hash") == scene_hash:
            await _delete(f"{MP_BIND_ACCOUNT_PREFIX}{int(account_id)}")
        try:
            await _put(
                f"{MP_BIND_STATUS_PREFIX}{int(account_id)}",
                {"status": "bound", "at": datetime.utcnow().isoformat()},
                120,
            )
        except StaffAuthStoreUnavailable:
            pass
    return data


async def get_mp_bind_status_for_account(account_id: int) -> str:
    """pending | bound | expired"""
    status = await _get(f"{MP_BIND_STATUS_PREFIX}{int(account_id)}")
    if status and status.get("status") == "bound":
        return "bound"
    meta = await _get(f"{MP_BIND_ACCOUNT_PREFIX}{int(account_id)}")
    if meta and meta.get("scene_hash"):
        data = await _get(f"{MP_BIND_PREFIX}{meta['scene_hash']}")
        if data and data.get("status") == "pending":
            return "pending"
    return "expired"
