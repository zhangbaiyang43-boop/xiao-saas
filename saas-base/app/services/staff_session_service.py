"""Staff auth session orchestration (JWT + trusted device). Provider-agnostic.

Upstream (password / legacy OA / MP handoff) must already prove the MerchantAccount
is allowed to receive a session. This service does not verify passwords or WeChat.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.permissions import STAFF_ROLES, parse_staff_role, permission_list
from app.core.security import create_access_token
from app.models.merchant_account import MerchantAccount
from app.models.merchant_account_trusted_device import MerchantAccountTrustedDevice
from app.models.tenant import Tenant
from app.services.staff_trusted_device_service import (
    StaffTrustedDeviceService,
    encode_device_credential,
)


def _staff_jwt(account: MerchantAccount) -> str:
    minutes = max(15, int(settings.STAFF_ACCESS_TOKEN_MINUTES or 120))
    return create_access_token(
        account.tenant_id,
        expires_delta=timedelta(minutes=minutes),
        role=account.role,
        account_id=int(account.id),
    )


def _session_payload(account: MerchantAccount, tenant: Tenant | None, *, auth_method: str) -> dict:
    role = parse_staff_role(account.role)
    if role not in STAFF_ROLES:
        raise ValueError("invalid_staff_role")
    return {
        "tenant_id": account.tenant_id,
        "tenant_name": tenant.name if tenant else None,
        "name": account.name,
        "phone": None,
        "token": _staff_jwt(account),
        "token_type": "bearer",
        "role": role,
        "account_id": str(account.id),
        "username": account.username,
        "permissions": permission_list(role),
        "home_path": "/waiter" if role == "waiter" else "/kitchen",
        "auth_method": auth_method,
        "device_trusted": True,
    }


class StaffSessionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.devices = StaffTrustedDeviceService(db)

    async def _get_tenant(self, tenant_id: str) -> Tenant | None:
        result = await self.db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
        return result.scalar_one_or_none()

    async def issue_session_for_account(
        self,
        account: MerchantAccount,
        *,
        auth_method: str,
        user_agent: str | None = None,
        tenant: Tenant | None = None,
        existing_device_id: str | None = None,
        existing_secret: str | None = None,
    ) -> dict[str, Any]:
        """Issue JWT + trusted device. Prefer rotate existing device when same account.

        If cookie belongs to a different account, create a new device (cookie replaced).
        """
        if existing_device_id and existing_secret:
            row = (
                await self.db.execute(
                    select(MerchantAccountTrustedDevice).where(
                        MerchantAccountTrustedDevice.device_id == existing_device_id
                    )
                )
            ).scalar_one_or_none()
            if row and int(row.merchant_account_id) == int(account.id):
                refreshed = await self.refresh_device(
                    device_id=existing_device_id, secret=existing_secret, user_agent=user_agent
                )
                if refreshed.get("ok"):
                    refreshed["auth_method"] = auth_method
                    return refreshed
        return await self._issue_with_device(
            account, auth_method=auth_method, user_agent=user_agent, tenant=tenant
        )

    async def refresh_device(
        self, *, device_id: str, secret: str, user_agent: str | None = None
    ) -> dict[str, Any]:
        account, new_secret, err = await self.devices.authenticate_and_rotate(
            device_id=device_id, secret=secret
        )
        if err or not account or not new_secret:
            msg = {
                "device_invalid": "设备登录已失效，请重新登录",
                "device_expired": "可信设备已过期，请重新登录",
                "account_disabled": "账号已停用",
            }.get(err or "", "设备登录已失效，请重新登录")
            return {"ok": False, "code": err or "device_invalid", "msg": msg}

        role = parse_staff_role(account.role)
        if role not in STAFF_ROLES:
            return {"ok": False, "code": "role_invalid", "msg": "账号角色无效"}

        tenant = await self._get_tenant(account.tenant_id)
        if not tenant or not tenant.status:
            return {"ok": False, "code": "tenant_disabled", "msg": "商家已停用"}

        data = _session_payload(account, tenant, auth_method="staff_device")
        data["device_credential"] = encode_device_credential(device_id, new_secret)
        data["device_id"] = device_id
        data["ok"] = True
        return data

    async def _issue_with_device(
        self,
        account: MerchantAccount,
        *,
        auth_method: str,
        user_agent: str | None = None,
        tenant: Tenant | None = None,
    ) -> dict[str, Any]:
        role = parse_staff_role(account.role)
        if role not in STAFF_ROLES:
            return {"ok": False, "code": "role_invalid", "msg": "账号角色无效"}
        if tenant is None:
            tenant = await self._get_tenant(account.tenant_id)
        if not tenant or not tenant.status:
            return {"ok": False, "code": "tenant_disabled", "msg": "商家已停用"}

        device, raw_secret = await self.devices.create_device(
            tenant_id=account.tenant_id,
            account_id=int(account.id),
            user_agent=user_agent,
        )
        data = _session_payload(account, tenant, auth_method=auth_method)
        data["device_credential"] = encode_device_credential(device.device_id, raw_secret)
        data["device_id"] = device.device_id
        data["ok"] = True
        return data
