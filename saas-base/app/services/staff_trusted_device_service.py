"""Trusted device credentials for staff auto-login (opaque secret, hashed in DB)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.logger import logger
from app.core.merchant_auth import invalidate_account_auth_cache
from app.models.merchant_account import MerchantAccount
from app.models.merchant_account_trusted_device import MerchantAccountTrustedDevice
from app.utils.id_generator import generate_snowflake_id


def _hash_secret(secret: str) -> str:
    # HMAC with JWT secret as pepper so DB dump alone is not enough.
    pepper = (settings.JWT_SECRET_KEY or "").encode("utf-8")
    return hmac.new(pepper, secret.encode("utf-8"), hashlib.sha256).hexdigest()


def _device_ttl_days() -> int:
    return max(1, int(settings.STAFF_TRUST_DEVICE_DAYS or 30))


def summarize_user_agent(ua: str | None) -> tuple[str | None, str | None]:
    """Return (device_name, ua_summary) for display only — never for auth."""
    raw = (ua or "").strip()
    if not raw:
        return None, None
    summary = raw[:120]
    lower = raw.lower()
    if "iphone" in lower or "ios" in lower:
        name = "微信 · iPhone"
    elif "android" in lower:
        name = "微信 · Android"
    elif "windows" in lower:
        name = "微信 · Windows"
    elif "mac" in lower:
        name = "微信 · Mac"
    else:
        name = "微信 · 设备"
    return name, summary


class StaffTrustedDeviceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_device(
        self,
        *,
        tenant_id: str,
        account_id: int,
        user_agent: str | None = None,
    ) -> tuple[MerchantAccountTrustedDevice, str]:
        """Returns (row, raw_secret). Raw secret is shown once to client only."""
        raw_secret = secrets.token_urlsafe(32)
        device_id = secrets.token_urlsafe(16)
        name, ua_summary = summarize_user_agent(user_agent)
        now = datetime.utcnow()
        row = MerchantAccountTrustedDevice(
            id=generate_snowflake_id(),
            tenant_id=tenant_id,
            merchant_account_id=int(account_id),
            device_id=device_id,
            device_secret_hash=_hash_secret(raw_secret),
            device_name=name,
            user_agent_summary=ua_summary,
            last_used_at=now,
            expires_at=now + timedelta(days=_device_ttl_days()),
            revoked_at=None,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        logger.info(
            "trusted_device_created account_id=%s tenant_id=%s",
            account_id,
            tenant_id,
        )
        return row, raw_secret

    async def count_active(self, *, tenant_id: str, account_id: int) -> int:
        now = datetime.utcnow()
        result = await self.db.execute(
            select(MerchantAccountTrustedDevice).where(
                MerchantAccountTrustedDevice.tenant_id == tenant_id,
                MerchantAccountTrustedDevice.merchant_account_id == int(account_id),
                MerchantAccountTrustedDevice.revoked_at.is_(None),
                MerchantAccountTrustedDevice.expires_at > now,
            )
        )
        return len(result.scalars().all())

    async def revoke_all(self, *, tenant_id: str, account_id: int) -> int:
        now = datetime.utcnow()
        result = await self.db.execute(
            select(MerchantAccountTrustedDevice).where(
                MerchantAccountTrustedDevice.tenant_id == tenant_id,
                MerchantAccountTrustedDevice.merchant_account_id == int(account_id),
                MerchantAccountTrustedDevice.revoked_at.is_(None),
            )
        )
        rows = result.scalars().all()
        for row in rows:
            row.revoked_at = now
        await self.db.commit()
        await invalidate_account_auth_cache(int(account_id))
        logger.info(
            "trusted_devices_revoked_all account_id=%s tenant_id=%s count=%s",
            account_id,
            tenant_id,
            len(rows),
        )
        return len(rows)

    async def revoke_device(
        self, *, tenant_id: str, account_id: int, device_id: str
    ) -> bool:
        result = await self.db.execute(
            select(MerchantAccountTrustedDevice).where(
                MerchantAccountTrustedDevice.tenant_id == tenant_id,
                MerchantAccountTrustedDevice.merchant_account_id == int(account_id),
                MerchantAccountTrustedDevice.device_id == device_id,
                MerchantAccountTrustedDevice.revoked_at.is_(None),
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            return False
        row.revoked_at = datetime.utcnow()
        await self.db.commit()
        await invalidate_account_auth_cache(int(account_id))
        logger.info(
            "trusted_device_revoked account_id=%s tenant_id=%s",
            account_id,
            tenant_id,
        )
        return True

    async def authenticate_and_rotate(
        self, *, device_id: str, secret: str
    ) -> tuple[Optional[MerchantAccount], Optional[str], Optional[str]]:
        """Validate device; on success rotate secret.

        Returns (account, new_raw_secret, error_code).
        """
        result = await self.db.execute(
            select(MerchantAccountTrustedDevice).where(
                MerchantAccountTrustedDevice.device_id == device_id,
            )
        )
        device = result.scalar_one_or_none()
        if not device or device.revoked_at is not None:
            return None, None, "device_invalid"
        if device.expires_at <= datetime.utcnow():
            return None, None, "device_expired"
        if not hmac.compare_digest(device.device_secret_hash, _hash_secret(secret)):
            return None, None, "device_invalid"

        acc_result = await self.db.execute(
            select(MerchantAccount).where(
                MerchantAccount.id == int(device.merchant_account_id),
                MerchantAccount.tenant_id == device.tenant_id,
            )
        )
        account = acc_result.scalar_one_or_none()
        if not account or account.status != "active":
            return None, None, "account_disabled"

        # Rotate secret.
        new_secret = secrets.token_urlsafe(32)
        device.device_secret_hash = _hash_secret(new_secret)
        device.last_used_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(account)
        logger.info(
            "trusted_device_refreshed account_id=%s tenant_id=%s",
            account.id,
            account.tenant_id,
        )
        return account, new_secret, None


def encode_device_credential(device_id: str, secret: str) -> str:
    return f"{device_id}.{secret}"


def decode_device_credential(raw: str | None) -> tuple[Optional[str], Optional[str]]:
    if not raw or "." not in raw:
        return None, None
    device_id, secret = raw.split(".", 1)
    if not device_id or not secret:
        return None, None
    return device_id, secret
