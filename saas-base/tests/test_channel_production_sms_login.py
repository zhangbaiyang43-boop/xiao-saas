from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import jwt
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.core.database import get_db
from app.main import app
from app.models.base import Base
from app.services import channel_auth_code_service as channel_codes
from app.services import tencent_sms_service as merchant_sms
from app.services.channel_auth_code_service import ChannelAuthCodeService
from app.services.channel_partner_service import (
    PARTNER_STATUS_ACTIVE,
    PARTNER_STATUS_DISABLED,
    PARTNER_STATUS_SUSPENDED,
    ChannelPartnerService,
)
from app.services.tencent_sms_service import TencentSmsService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class ChannelProductionSmsLoginTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_env = settings.APP_ENV
        self.original_redis_enabled = settings.REDIS_ENABLED
        self.original_daily_limit = settings.SMS_CODE_DAILY_LIMIT
        self.original_max_attempts = settings.SMS_CODE_MAX_ATTEMPTS
        settings.APP_ENV = "production"
        settings.REDIS_ENABLED = False
        settings.SMS_CODE_DAILY_LIMIT = 2
        settings.SMS_CODE_MAX_ATTEMPTS = 3
        channel_codes._memory_cache.clear()
        merchant_sms._memory_cache.clear()

        self.engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        async def override_get_db():
            yield self.db

        app.dependency_overrides[get_db] = override_get_db
        transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.db.close()
        await self.engine.dispose()
        channel_codes._memory_cache.clear()
        merchant_sms._memory_cache.clear()
        settings.APP_ENV = self.original_env
        settings.REDIS_ENABLED = self.original_redis_enabled
        settings.SMS_CODE_DAILY_LIMIT = self.original_daily_limit
        settings.SMS_CODE_MAX_ATTEMPTS = self.original_max_attempts

    async def _partner(self, mobile: str = "13900000001", status: str = PARTNER_STATUS_ACTIVE):
        return await ChannelPartnerService(self.db).create_partner(
            partner_code=f"CP{mobile[-4:]}",
            name="Channel",
            mobile=mobile,
            partner_type="OTHER",
            status=status,
        )

    async def _request_code(self, mobile: str):
        return await self.client.post("/api/v1/channel/auth/request-code", json={"mobile": mobile})

    async def _login(self, mobile: str, code: str):
        return await self.client.post("/api/v1/channel/auth/login", json={"mobile": mobile, "code": code})

    async def _channel_cache_state(self, mobile: str) -> tuple[object, object, int]:
        service = ChannelAuthCodeService()
        mobile_key = channel_codes.normalize_mobile(mobile)
        code = await channel_codes._cache_get(service._code_key(mobile_key))
        cooldown = await channel_codes._cache_get(service._cooldown_key(mobile_key))
        daily = int(await channel_codes._cache_get(service._daily_key(mobile_key)) or 0)
        return code, cooldown, daily

    def _assert_no_debug_code(self, response: httpx.Response) -> None:
        payload = response.json().get("data")
        if isinstance(payload, dict):
            self.assertNotIn("debug_code", payload)

    async def test_production_config_complete_provider_success_stores_channel_otp(self):
        await self._partner()
        with (
            patch.object(TencentSmsService, "is_configured", return_value=True),
            patch.object(TencentSmsService, "send_login_code", new=AsyncMock(return_value=(True, "sent"))) as send,
            patch("app.services.channel_auth_code_service.generate_login_code", return_value="123456"),
        ):
            response = await self._request_code("13900000001")

        self.assertEqual(response.json()["code"], 200)
        self.assertEqual(send.await_count, 1)
        send.assert_awaited_once_with("13900000001", "123456")
        data = response.json()["data"]
        self.assertIn("expires_in", data)
        self.assertIn("retry_after", data)
        self.assertNotIn("debug_code", data)
        code, cooldown, daily = await self._channel_cache_state("13900000001")
        self.assertIsInstance(code, dict)
        self.assertTrue(cooldown)
        self.assertEqual(daily, 1)

    async def test_production_config_missing_fails_closed_without_cache_side_effects(self):
        await self._partner()
        with (
            patch.object(TencentSmsService, "is_configured", return_value=False),
            patch.object(TencentSmsService, "send_login_code", new=AsyncMock()) as send,
        ):
            response = await self._request_code("13900000001")

        self.assertEqual(response.json()["code"], 400)
        self.assertEqual(response.json()["msg"], "短信服务暂不可用，请联系平台管理员")
        self._assert_no_debug_code(response)
        self.assertEqual(send.await_count, 0)
        self.assertEqual(await self._channel_cache_state("13900000001"), (None, None, 0))

    async def test_provider_failure_does_not_store_otp_or_consume_cooldown_or_daily(self):
        await self._partner()
        with (
            patch.object(TencentSmsService, "is_configured", return_value=True),
            patch.object(TencentSmsService, "send_login_code", new=AsyncMock(return_value=(False, "provider detail"))) as send,
        ):
            response = await self._request_code("13900000001")

        self.assertEqual(response.json()["code"], 400)
        self.assertEqual(response.json()["msg"], "验证码发送失败，请稍后再试")
        self._assert_no_debug_code(response)
        self.assertEqual(send.await_count, 1)
        self.assertEqual(await self._channel_cache_state("13900000001"), (None, None, 0))

    async def test_provider_success_then_login_returns_channel_partner_jwt(self):
        partner = await self._partner()
        with (
            patch.object(TencentSmsService, "is_configured", return_value=True),
            patch.object(TencentSmsService, "send_login_code", new=AsyncMock(return_value=(True, "sent"))),
            patch("app.services.channel_auth_code_service.generate_login_code", return_value="246810"),
        ):
            await self._request_code("13900000001")

        response = await self._login("13900000001", "246810")

        self.assertEqual(response.json()["code"], 200)
        token = response.json()["data"]["token"]
        decoded = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        self.assertEqual(decoded["type"], "channel_partner")
        self.assertEqual(decoded["partner_id"], str(partner.id))

    async def test_channel_otp_is_single_use(self):
        await self._partner()
        await ChannelAuthCodeService().store_login_code("13900000001", "135790")

        first = await self._login("13900000001", "135790")
        second = await self._login("13900000001", "135790")

        self.assertEqual(first.json()["code"], 200)
        self.assertEqual(second.json()["code"], 400)

    async def test_wrong_code_max_attempts_deletes_otp(self):
        await self._partner()
        await ChannelAuthCodeService().store_login_code("13900000001", "999999")

        for _ in range(settings.SMS_CODE_MAX_ATTEMPTS):
            failed = await self._login("13900000001", "000000")
            self.assertEqual(failed.json()["code"], 400)
        correct_after_limit = await self._login("13900000001", "999999")

        self.assertEqual(correct_after_limit.json()["code"], 400)

    async def test_ttl_expired_otp_cannot_login(self):
        await self._partner()
        service = ChannelAuthCodeService()
        await service.store_login_code("13900000001", "123123")
        key = service._code_key("13900000001")
        record = await channel_codes._cache_get(key)
        record["expires_at"] = int(channel_codes._now() - 1)
        await channel_codes._cache_set(key, record, 1)

        response = await self._login("13900000001", "123123")

        self.assertEqual(response.json()["code"], 400)

    async def test_cooldown_blocks_second_provider_send(self):
        await self._partner()
        with (
            patch.object(TencentSmsService, "is_configured", return_value=True),
            patch.object(TencentSmsService, "send_login_code", new=AsyncMock(return_value=(True, "sent"))) as send,
        ):
            first = await self._request_code("13900000001")
            second = await self._request_code("13900000001")

        self.assertEqual(first.json()["code"], 200)
        self.assertEqual(second.json()["code"], 400)
        self.assertIn("频繁", second.json()["msg"])
        self._assert_no_debug_code(second)
        self.assertEqual(send.await_count, 1)

    async def test_daily_limit_blocks_provider_send(self):
        await self._partner()
        service = ChannelAuthCodeService()
        await channel_codes._cache_set(service._daily_key("13900000001"), settings.SMS_CODE_DAILY_LIMIT, 86400)
        with (
            patch.object(TencentSmsService, "is_configured", return_value=True),
            patch.object(TencentSmsService, "send_login_code", new=AsyncMock()) as send,
        ):
            response = await self._request_code("13900000001")

        self.assertEqual(response.json()["code"], 400)
        self.assertIn("上限", response.json()["msg"])
        self._assert_no_debug_code(response)
        self.assertEqual(send.await_count, 0)

    async def test_disabled_partner_cannot_request_code(self):
        await self._partner(status=PARTNER_STATUS_DISABLED)
        with patch.object(TencentSmsService, "send_login_code", new=AsyncMock()) as send:
            response = await self._request_code("13900000001")

        self.assertEqual(response.json()["code"], 403)
        self.assertEqual(send.await_count, 0)

    async def test_suspended_partner_can_request_code_and_login(self):
        await self._partner(status=PARTNER_STATUS_SUSPENDED)
        with (
            patch.object(TencentSmsService, "is_configured", return_value=True),
            patch.object(TencentSmsService, "send_login_code", new=AsyncMock(return_value=(True, "sent"))),
            patch("app.services.channel_auth_code_service.generate_login_code", return_value="555666"),
        ):
            code_response = await self._request_code("13900000001")
        login_response = await self._login("13900000001", "555666")

        self.assertEqual(code_response.json()["code"], 200)
        self.assertEqual(login_response.json()["code"], 200)

    async def test_invalid_mobile_never_calls_provider(self):
        for index, mobile in enumerate(["123", "abcdefghijk", "23800138000"], start=1):
            if mobile != "abcdefghijk":
                await ChannelPartnerService(self.db).create_partner(
                    partner_code=f"INVALID{index}",
                    name="Invalid",
                    mobile=mobile,
                    partner_type="OTHER",
                    status=PARTNER_STATUS_ACTIVE,
                )
            with (
                patch.object(TencentSmsService, "is_configured", return_value=True),
                patch.object(TencentSmsService, "send_login_code", new=AsyncMock()) as send,
            ):
                response = await self._request_code(mobile)
            self.assertIn(response.json()["code"], {400, 404})
            self._assert_no_debug_code(response)
            self.assertEqual(send.await_count, 0)

    async def test_channel_and_merchant_otp_namespaces_are_isolated(self):
        phone = "13900000001"
        await ChannelAuthCodeService().store_login_code(phone, "111111")
        await TencentSmsService().store_login_code(phone, "222222")

        self.assertFalse(await ChannelAuthCodeService().verify_login_code(phone, "222222"))
        self.assertFalse(await TencentSmsService().verify_login_code(phone, "111111"))
        self.assertTrue(await ChannelAuthCodeService().verify_login_code(phone, "111111"))
        self.assertTrue(await TencentSmsService().verify_login_code(phone, "222222"))

    async def test_provider_success_happens_before_channel_otp_store(self):
        await self._partner()
        calls = []

        async def fake_send(_service, _phone, _code):
            calls.append("send")
            return True, "sent"

        async def fake_store(_service, _mobile, _code):
            calls.append("store")

        with (
            patch.object(TencentSmsService, "is_configured", return_value=True),
            patch.object(TencentSmsService, "send_login_code", new=fake_send),
            patch.object(ChannelAuthCodeService, "store_login_code", new=fake_store),
        ):
            response = await self._request_code("13900000001")

        self.assertEqual(response.json()["code"], 200)
        self.assertEqual(calls, ["send", "store"])

    async def test_tencent_rejection_log_is_sanitized(self):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "Response": {
                        "RequestId": "req-123",
                        "SendStatusSet": [
                            {
                                "Code": "FailedOperation.TemplateIncorrect",
                                "Message": "template parameter mismatch",
                                "PhoneNumber": "+8613900000001",
                            }
                        ],
                    }
                }

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                return FakeResponse()

        with (
            patch("app.services.tencent_sms_service.httpx.AsyncClient", new=FakeClient),
            patch("app.services.tencent_sms_service.logger.error") as log_error,
        ):
            ok, msg = await TencentSmsService().send_login_code("13900000001", "123456")

        self.assertFalse(ok)
        self.assertEqual(msg, "template parameter mismatch")
        logged = " ".join(str(item) for item in log_error.call_args.args)
        self.assertIn("FailedOperation.TemplateIncorrect", logged)
        self.assertIn("req-123", logged)
        self.assertIn("139****0001", logged)
        self.assertNotIn("123456", logged)
        self.assertNotIn("13900000001", logged)
        self.assertNotIn("template parameter mismatch", logged)

    async def test_concurrent_same_mobile_request_sends_provider_once(self):
        await self._partner()

        with (
            patch.object(TencentSmsService, "is_configured", return_value=True),
            patch.object(TencentSmsService, "send_login_code", new=AsyncMock(return_value=(True, "sent"))) as send,
        ):
            first, second = await asyncio.gather(
                self._request_code("13900000001"),
                self._request_code("13900000001"),
            )

        codes = sorted([first.json()["code"], second.json()["code"]])
        self.assertEqual(codes, [200, 400])
        self.assertEqual(send.await_count, 1)


if __name__ == "__main__":
    unittest.main()
