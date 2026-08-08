from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.merchant_auth import (
    check_staff_password,
    hash_staff_password,
    invalidate_account_auth_cache,
    validate_staff_password,
)
from app.core.permissions import STAFF_ROLES
from app.core.response import error_response, success_response
from app.models.merchant_account import MerchantAccount
from app.services.staff_trusted_device_service import StaffTrustedDeviceService
from app.services.staff_wechat_auth_service import StaffWechatAuthService
from app.utils.id_generator import generate_snowflake_id

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


async def serialize_account(db: AsyncSession, account: MerchantAccount) -> dict:
    wechat = StaffWechatAuthService(db)
    devices = StaffTrustedDeviceService(db)
    bound = await wechat.is_wechat_bound(tenant_id=account.tenant_id, account_id=int(account.id))
    device_count = await devices.count_active(tenant_id=account.tenant_id, account_id=int(account.id))
    return {
        "id": str(account.id),
        "tenant_id": account.tenant_id,
        "name": account.name,
        "username": account.username,
        "has_password": bool(account.username and account.password_hash),
        "role": account.role,
        "status": account.status,
        "wechat_bound": bound,
        "trusted_device_count": device_count,
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "updated_at": account.updated_at.isoformat() if account.updated_at else None,
    }


class MerchantAccountService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_accounts(self, tenant_id: str):
        result = await self.db.execute(
            select(MerchantAccount)
            .where(MerchantAccount.tenant_id == tenant_id)
            .order_by(MerchantAccount.created_at.desc())
        )
        rows = result.scalars().all()
        data = [await serialize_account(self.db, a) for a in rows]
        return success_response(data=data)

    async def get_by_username(self, tenant_id: str, username: str) -> MerchantAccount | None:
        if not username:
            return None
        result = await self.db.execute(
            select(MerchantAccount).where(
                MerchantAccount.tenant_id == tenant_id,
                MerchantAccount.username == username.strip().lower(),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, tenant_id: str, account_id: int) -> MerchantAccount | None:
        result = await self.db.execute(
            select(MerchantAccount).where(
                MerchantAccount.id == int(account_id),
                MerchantAccount.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_account(
        self,
        *,
        tenant_id: str,
        name: str,
        role: str,
        username: str | None = None,
        password: str | None = None,
    ):
        name = (name or "").strip()
        role = (role or "").strip().lower()
        username = (username or "").strip().lower() or None
        password = password if password else None

        if not name or len(name) > 64:
            return error_response(code=400, msg="请填写员工姓名")
        if role not in STAFF_ROLES:
            return error_response(code=400, msg="岗位仅支持服务员或后厨")

        password_hash = None
        if username or password:
            if not username or not _USERNAME_RE.match(username):
                return error_response(code=400, msg="登录账号需为3-32位字母数字或下划线")
            pw_err = validate_staff_password(password)
            if pw_err:
                return error_response(code=400, msg=pw_err)
            existing = await self.get_by_username(tenant_id, username)
            if existing:
                return error_response(code=400, msg="该登录账号已存在")
            password_hash = hash_staff_password(password)

        account = MerchantAccount(
            id=generate_snowflake_id(),
            tenant_id=tenant_id,
            name=name,
            username=username,
            password_hash=password_hash,
            role=role,
            status="active",
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return success_response(data=await serialize_account(self.db, account), msg="员工已创建")

    async def update_account(
        self,
        *,
        tenant_id: str,
        account_id: int,
        name: str | None = None,
        role: str | None = None,
        status: str | None = None,
    ):
        account = await self.get_by_id(tenant_id, account_id)
        if not account:
            return error_response(code=404, msg="员工不存在")

        if name is not None:
            name = name.strip()
            if not name or len(name) > 64:
                return error_response(code=400, msg="请填写员工姓名")
            account.name = name

        if role is not None:
            role = role.strip().lower()
            if role not in STAFF_ROLES:
                return error_response(code=400, msg="岗位仅支持服务员或后厨")
            account.role = role

        disabling = False
        if status is not None:
            status = status.strip().lower()
            if status not in ("active", "disabled"):
                return error_response(code=400, msg="状态无效")
            if account.status != "disabled" and status == "disabled":
                disabling = True
            account.status = status

        await self.db.commit()
        await self.db.refresh(account)
        await invalidate_account_auth_cache(account.id)

        if disabling:
            await StaffTrustedDeviceService(self.db).revoke_all(
                tenant_id=tenant_id, account_id=int(account.id)
            )

        return success_response(data=await serialize_account(self.db, account), msg="已保存")

    async def reset_password(self, *, tenant_id: str, account_id: int, password: str):
        account = await self.get_by_id(tenant_id, account_id)
        if not account:
            return error_response(code=404, msg="员工不存在")
        if not account.username:
            return error_response(code=400, msg="请先设置登录账号")
        pw_err = validate_staff_password(password)
        if pw_err:
            return error_response(code=400, msg=pw_err)
        account.password_hash = hash_staff_password(password)
        await self.db.commit()
        await invalidate_account_auth_cache(account.id)
        return success_response(msg="密码已设置")

    async def set_backup_login(
        self,
        *,
        tenant_id: str,
        account_id: int,
        username: str,
        password: str,
    ):
        account = await self.get_by_id(tenant_id, account_id)
        if not account:
            return error_response(code=404, msg="员工不存在")
        username = (username or "").strip().lower()
        if not _USERNAME_RE.match(username):
            return error_response(code=400, msg="登录账号需为3-32位字母数字或下划线")
        pw_err = validate_staff_password(password)
        if pw_err:
            return error_response(code=400, msg=pw_err)
        existing = await self.get_by_username(tenant_id, username)
        if existing and int(existing.id) != int(account.id):
            return error_response(code=400, msg="该登录账号已存在")
        account.username = username
        account.password_hash = hash_staff_password(password)
        await self.db.commit()
        await self.db.refresh(account)
        await invalidate_account_auth_cache(account.id)
        return success_response(data=await serialize_account(self.db, account), msg="登录账号已设置")

    async def authenticate(self, *, tenant_id: str, username: str, password: str):
        account = await self.get_by_username(tenant_id, username)
        if not account:
            return None, "账号或密码错误"
        if account.status != "active":
            return None, "账号已停用"
        if not account.username or not account.password_hash:
            return None, "账号或密码错误"
        if not check_staff_password(password, account.password_hash):
            return None, "账号或密码错误"
        return account, None
