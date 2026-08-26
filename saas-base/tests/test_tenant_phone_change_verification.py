"""联系电话改绑验证码校验：PUT /api/v1/tenant/profile 之前允许在已登录状态下
直接把 phone 改成任意值且不做任何校验——phone 同时是登录凭证，这意味着手滑
改错这个字段会把商户直接踢出自己的账号，且没有任何验证挡在中间。

这里验证新增的门槛：只有当提交的 phone 真的和当前值不同时，才需要一个发到
新手机号、CHANGE_PHONE 用途的验证码；手机号没变的普通资料编辑（改名字/地址/
logo）完全不受影响，照旧直接保存。
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1 import tenant as tenant_module
from app.core.tenant_context import TenantContext
from app.models.base import Base
from app.models.tenant import Tenant
from app.schemas.tenant import TenantPhoneCodeRequest, UpdateTenantProfileRequest
from app.services import tencent_sms_service as sms_module
from app.services.tencent_sms_service import SmsPurpose, TencentSmsService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_ID = "tenant-phone-change-001"
ORIGINAL_PHONE = "13800001111"
NEW_PHONE = "13900002222"
VALID_CODE = "135790"


def make_request(path: str = "/api/v1/tenant/profile") -> Request:
    return Request(
        {
            "type": "http",
            "method": "PUT",
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


class TenantPhoneChangeVerificationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.db.add(
            Tenant(
                tenant_id=TENANT_ID,
                name="老王川菜馆",
                phone=ORIGINAL_PHONE,
                password_hash="x",
                status=True,
                is_open=True,
            )
        )
        await self.db.commit()
        TenantContext.set_tenant_id(TENANT_ID)

    async def asyncTearDown(self):
        TenantContext.clear()
        sms_module._memory_cache.clear()
        await self.db.close()
        await self.engine.dispose()

    async def _current_phone(self) -> str | None:
        result = await self.db.execute(select(Tenant).where(Tenant.tenant_id == TENANT_ID))
        return result.scalar_one().phone

    async def _store_valid_change_code(self, phone: str = NEW_PHONE, code: str = VALID_CODE) -> None:
        await TencentSmsService().store_login_code(phone, code, purpose=SmsPurpose.CHANGE_PHONE)

    # -- 1. phone 没变的普通编辑：不受影响，照旧直接保存 -----------------------

    async def test_editing_other_fields_without_touching_phone_needs_no_code(self):
        data = UpdateTenantProfileRequest(name="老王川菜馆(总店)")
        res = await tenant_module.update_profile(data, db=self.db)
        self.assertEqual(res.code, 200, res.msg)
        self.assertEqual(await self._current_phone(), ORIGINAL_PHONE)

    async def test_resubmitting_the_same_phone_needs_no_code(self):
        data = UpdateTenantProfileRequest(phone=ORIGINAL_PHONE, address="人民路1号")
        res = await tenant_module.update_profile(data, db=self.db)
        self.assertEqual(res.code, 200, res.msg)
        self.assertEqual(await self._current_phone(), ORIGINAL_PHONE)

    # -- 2. phone 变了但验证码缺失/错误：拒绝，且数据库里的手机号不能被改动 ----

    async def test_changing_phone_without_a_code_is_rejected(self):
        data = UpdateTenantProfileRequest(phone=NEW_PHONE)
        res = await tenant_module.update_profile(data, db=self.db)
        self.assertNotEqual(res.code, 200)
        self.assertEqual(await self._current_phone(), ORIGINAL_PHONE)

    async def test_changing_phone_with_wrong_code_is_rejected(self):
        await self._store_valid_change_code()
        data = UpdateTenantProfileRequest(phone=NEW_PHONE, phone_code="000000")
        res = await tenant_module.update_profile(data, db=self.db)
        self.assertNotEqual(res.code, 200)
        self.assertEqual(await self._current_phone(), ORIGINAL_PHONE)

    async def test_changing_phone_with_a_code_sent_for_a_different_purpose_is_rejected(self):
        # A LOGIN-purpose code for that same new number must not double as a
        # CHANGE_PHONE code -- that's exactly the cross-purpose replay
        # SmsPurpose exists to block.
        await TencentSmsService().store_login_code(NEW_PHONE, VALID_CODE, purpose=SmsPurpose.LOGIN)
        data = UpdateTenantProfileRequest(phone=NEW_PHONE, phone_code=VALID_CODE)
        res = await tenant_module.update_profile(data, db=self.db)
        self.assertNotEqual(res.code, 200)
        self.assertEqual(await self._current_phone(), ORIGINAL_PHONE)

    # -- 3. phone 变了且验证码正确：更新成功 -----------------------------------

    async def test_changing_phone_with_the_correct_code_succeeds(self):
        await self._store_valid_change_code()
        data = UpdateTenantProfileRequest(phone=NEW_PHONE, phone_code=VALID_CODE)
        res = await tenant_module.update_profile(data, db=self.db)
        self.assertEqual(res.code, 200, res.msg)
        self.assertEqual(await self._current_phone(), NEW_PHONE)

    async def test_correct_code_is_single_use_and_cannot_be_replayed(self):
        await self._store_valid_change_code()
        data = UpdateTenantProfileRequest(phone=NEW_PHONE, phone_code=VALID_CODE)
        first = await tenant_module.update_profile(data, db=self.db)
        self.assertEqual(first.code, 200, first.msg)

        # Change it back, reusing the exact same (already-consumed) code.
        data_back = UpdateTenantProfileRequest(phone=ORIGINAL_PHONE, phone_code=VALID_CODE)
        second = await tenant_module.update_profile(data_back, db=self.db)
        self.assertNotEqual(second.code, 200)
        self.assertEqual(await self._current_phone(), NEW_PHONE)

    # -- 4. 发验证码接口：给新手机号发送，走 CHANGE_PHONE 用途 -----------------

    @patch("app.api.v1.tenant.TencentSmsService.request_login_code")
    async def test_send_phone_code_endpoint_uses_change_phone_purpose(self, mock_send):
        mock_send.return_value = (True, "验证码已发送", {"retry_after": 60})
        data = TenantPhoneCodeRequest(phone=NEW_PHONE)

        res = await tenant_module.send_change_phone_code(make_request("/api/v1/tenant/profile/phone-code"), data, db=self.db)

        self.assertEqual(res.code, 200, res.msg)
        mock_send.assert_awaited_once_with(NEW_PHONE, purpose=SmsPurpose.CHANGE_PHONE)


if __name__ == "__main__":
    unittest.main()
