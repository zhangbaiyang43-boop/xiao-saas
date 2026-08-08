"""Staff WeChat bind + login orchestration (Authentication only)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.logger import logger
from app.core.merchant_auth import invalidate_account_auth_cache
from app.core.permissions import STAFF_ROLES, parse_staff_role, permission_list
from app.core.security import create_access_token
from app.models.merchant_account import MerchantAccount
from app.models.merchant_account_wechat_binding import MerchantAccountWechatBinding
from app.models.tenant import Tenant
from app.services import staff_bind_token_service as bind_tokens
from app.services.staff_trusted_device_service import (
    StaffTrustedDeviceService,
    encode_device_credential,
)
from app.services.staff_wechat_provider import WechatIdentity, get_staff_wechat_provider
from app.utils.id_generator import generate_snowflake_id


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


class StaffWechatAuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.devices = StaffTrustedDeviceService(db)

    async def _get_tenant(self, tenant_id: str) -> Tenant | None:
        result = await self.db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
        return result.scalar_one_or_none()

    async def _get_account(self, tenant_id: str, account_id: int) -> MerchantAccount | None:
        result = await self.db.execute(
            select(MerchantAccount).where(
                MerchantAccount.id == int(account_id),
                MerchantAccount.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_active_binding_for_account(
        self, *, tenant_id: str, account_id: int, app_id: str | None = None
    ) -> MerchantAccountWechatBinding | None:
        q = select(MerchantAccountWechatBinding).where(
            MerchantAccountWechatBinding.tenant_id == tenant_id,
            MerchantAccountWechatBinding.merchant_account_id == int(account_id),
            MerchantAccountWechatBinding.revoked_at.is_(None),
        )
        if app_id:
            q = q.where(MerchantAccountWechatBinding.wechat_app_id == app_id)
        result = await self.db.execute(q.order_by(MerchantAccountWechatBinding.bound_at.desc()))
        return result.scalars().first()

    async def list_active_accounts_for_openid(
        self, *, app_id: str, openid: str
    ) -> list[tuple[MerchantAccount, Tenant]]:
        result = await self.db.execute(
            select(MerchantAccountWechatBinding).where(
                MerchantAccountWechatBinding.wechat_app_id == app_id,
                MerchantAccountWechatBinding.openid == openid,
                MerchantAccountWechatBinding.revoked_at.is_(None),
            )
        )
        bindings = result.scalars().all()
        out: list[tuple[MerchantAccount, Tenant]] = []
        for b in bindings:
            acc = await self._get_account(b.tenant_id, int(b.merchant_account_id))
            if not acc or acc.status != "active":
                continue
            if parse_staff_role(acc.role) not in STAFF_ROLES:
                continue
            tenant = await self._get_tenant(acc.tenant_id)
            if not tenant or not tenant.status:
                continue
            out.append((acc, tenant))
        return out

    async def is_wechat_bound(self, *, tenant_id: str, account_id: int) -> bool:
        row = await self.get_active_binding_for_account(tenant_id=tenant_id, account_id=account_id)
        return row is not None

    async def unbind_wechat(self, *, tenant_id: str, account_id: int) -> dict:
        result = await self.db.execute(
            select(MerchantAccountWechatBinding).where(
                MerchantAccountWechatBinding.tenant_id == tenant_id,
                MerchantAccountWechatBinding.merchant_account_id == int(account_id),
                MerchantAccountWechatBinding.revoked_at.is_(None),
            )
        )
        rows = result.scalars().all()
        now = datetime.utcnow()
        for row in rows:
            row.revoked_at = now
        await self.db.commit()
        revoked_devices = await self.devices.revoke_all(tenant_id=tenant_id, account_id=account_id)
        await invalidate_account_auth_cache(int(account_id))
        logger.info(
            "staff_wechat_unbound account_id=%s tenant_id=%s devices=%s",
            account_id,
            tenant_id,
            revoked_devices,
        )
        return {"wechat_bound": False, "trusted_devices_revoked": revoked_devices}

    async def preview_bind(self, *, bind_token: str) -> dict[str, Any]:
        data = await bind_tokens.peek_bind_token(bind_token)
        if not data:
            return {"ok": False, "code": "bind_token_invalid", "msg": "绑定码已失效，请让老板重新生成"}
        account = await self._get_account(data["tenant_id"], int(data["account_id"]))
        if not account or account.status != "active":
            return {"ok": False, "code": "account_invalid", "msg": "员工账号不可用"}
        if parse_staff_role(account.role) not in STAFF_ROLES:
            return {"ok": False, "code": "role_invalid", "msg": "该账号不支持微信绑定"}
        existing = await self.get_active_binding_for_account(
            tenant_id=account.tenant_id, account_id=int(account.id)
        )
        if existing:
            return {
                "ok": False,
                "code": "already_bound",
                "msg": "该员工已绑定微信，请老板先解除绑定",
            }
        tenant = await self._get_tenant(account.tenant_id)
        return {
            "ok": True,
            "shop_name": tenant.name if tenant else "门店",
            "staff_name": account.name,
            "role": account.role,
            "role_label": "服务员" if account.role == "waiter" else "后厨",
        }

    async def confirm_bind(
        self,
        *,
        bind_token: str,
        identity: WechatIdentity,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        # Re-validate before consume.
        peek = await bind_tokens.peek_bind_token(bind_token)
        if not peek:
            return {"ok": False, "code": "bind_token_invalid", "msg": "绑定码已失效，请让老板重新生成"}

        account = await self._get_account(peek["tenant_id"], int(peek["account_id"]))
        if not account or account.status != "active":
            return {"ok": False, "code": "account_invalid", "msg": "员工账号不可用"}
        if account.tenant_id != peek["tenant_id"]:
            return {"ok": False, "code": "tenant_mismatch", "msg": "绑定失败"}
        role = parse_staff_role(account.role)
        if role not in STAFF_ROLES:
            return {"ok": False, "code": "role_invalid", "msg": "该账号不支持微信绑定"}

        existing = await self.get_active_binding_for_account(
            tenant_id=account.tenant_id, account_id=int(account.id), app_id=identity.app_id
        )
        if existing:
            if existing.openid == identity.openid:
                # Idempotent re-bind same wechat → refresh device.
                consumed = await bind_tokens.consume_bind_token(bind_token)
                if not consumed:
                    return {"ok": False, "code": "bind_token_invalid", "msg": "绑定码已失效，请让老板重新生成"}
                return await self._issue_with_device(account, auth_method="staff_wechat", user_agent=user_agent)
            return {
                "ok": False,
                "code": "already_bound",
                "msg": "该员工已绑定微信，请老板先解除绑定",
            }

        consumed = await bind_tokens.consume_bind_token(bind_token)
        if not consumed:
            return {"ok": False, "code": "bind_token_invalid", "msg": "绑定码已失效，请让老板重新生成"}

        binding = MerchantAccountWechatBinding(
            id=generate_snowflake_id(),
            tenant_id=account.tenant_id,
            merchant_account_id=int(account.id),
            wechat_app_id=identity.app_id,
            openid=identity.openid,
            unionid=identity.unionid,
            bound_at=datetime.utcnow(),
            revoked_at=None,
        )
        self.db.add(binding)
        await self.db.commit()
        logger.info(
            "staff_wechat_bound account_id=%s tenant_id=%s",
            account.id,
            account.tenant_id,
        )
        return await self._issue_with_device(account, auth_method="staff_wechat", user_agent=user_agent)

    async def login_with_identity(
        self,
        *,
        identity: WechatIdentity,
        account_id: int | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        matches = await self.list_active_accounts_for_openid(
            app_id=identity.app_id, openid=identity.openid
        )
        if not matches:
            return {"ok": False, "code": "not_bound", "msg": "该微信尚未绑定员工，请先扫码绑定"}

        if account_id is not None:
            chosen = [(a, t) for a, t in matches if int(a.id) == int(account_id)]
            if not chosen:
                return {"ok": False, "code": "account_not_found", "msg": "未找到可登录的员工身份"}
            account, tenant = chosen[0]
            return await self._issue_with_device(
                account, auth_method="staff_wechat", user_agent=user_agent, tenant=tenant
            )

        if len(matches) > 1:
            return {
                "ok": False,
                "code": "multiple_accounts",
                "msg": "请选择工作门店",
                "accounts": [
                    {
                        "account_id": str(a.id),
                        "shop_name": t.name,
                        "staff_name": a.name,
                        "role": a.role,
                        "role_label": "服务员" if a.role == "waiter" else "后厨",
                    }
                    for a, t in matches
                ],
            }

        account, tenant = matches[0]
        return await self._issue_with_device(
            account, auth_method="staff_wechat", user_agent=user_agent, tenant=tenant
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


def resolve_identity_from_provider_code(code: str):
    return get_staff_wechat_provider().exchange_code(code)
