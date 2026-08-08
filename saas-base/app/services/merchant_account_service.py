from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.merchant_auth import (
    check_staff_password,
    hash_staff_password,
    invalidate_account_auth_cache,
)
from app.core.permissions import ROLE_KITCHEN, ROLE_WAITER, STAFF_ROLES
from app.core.response import error_response, success_response
from app.models.merchant_account import MerchantAccount
from app.utils.id_generator import generate_snowflake_id

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


def serialize_account(account: MerchantAccount) -> dict:
    return {
        "id": str(account.id),
        "tenant_id": account.tenant_id,
        "name": account.name,
        "username": account.username,
        "role": account.role,
        "status": account.status,
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
        return success_response(data=[serialize_account(a) for a in rows])

    async def get_by_username(self, tenant_id: str, username: str) -> MerchantAccount | None:
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
        username: str,
        password: str,
        role: str,
    ):
        name = (name or "").strip()
        username = (username or "").strip().lower()
        role = (role or "").strip().lower()
        password = password or ""

        if not name or len(name) > 64:
            return error_response(code=400, msg="请填写员工姓名")
        if not _USERNAME_RE.match(username):
            return error_response(code=400, msg="登录账号需为3-32位字母数字或下划线")
        if role not in STAFF_ROLES:
            return error_response(code=400, msg="岗位仅支持服务员或后厨")
        if len(password) < 6 or len(password) > 64:
            return error_response(code=400, msg="密码长度需为6-64位")

        existing = await self.get_by_username(tenant_id, username)
        if existing:
            return error_response(code=400, msg="该登录账号已存在")

        account = MerchantAccount(
            id=generate_snowflake_id(),
            tenant_id=tenant_id,
            name=name,
            username=username,
            password_hash=hash_staff_password(password),
            role=role,
            status="active",
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return success_response(data=serialize_account(account), msg="员工已创建")

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

        if status is not None:
            status = status.strip().lower()
            if status not in ("active", "disabled"):
                return error_response(code=400, msg="状态无效")
            account.status = status

        await self.db.commit()
        await self.db.refresh(account)
        await invalidate_account_auth_cache(account.id)
        return success_response(data=serialize_account(account), msg="已保存")

    async def reset_password(self, *, tenant_id: str, account_id: int, password: str):
        account = await self.get_by_id(tenant_id, account_id)
        if not account:
            return error_response(code=404, msg="员工不存在")
        password = password or ""
        if len(password) < 6 or len(password) > 64:
            return error_response(code=400, msg="密码长度需为6-64位")
        account.password_hash = hash_staff_password(password)
        await self.db.commit()
        await invalidate_account_auth_cache(account.id)
        return success_response(msg="密码已重置")

    async def authenticate(self, *, tenant_id: str, username: str, password: str):
        account = await self.get_by_username(tenant_id, username)
        if not account:
            return None, "账号或密码错误"
        if account.status != "active":
            return None, "账号已停用"
        if not check_staff_password(password, account.password_hash):
            return None, "账号或密码错误"
        return account, None
