"""Behavioral coverage for the merchant SMS stable error contract
(Phase: P1 SMS Stable Error Contract + Auth Redirect Semantics).

Exercises TencentSmsService.request_login_code() directly -- the layer
responsible for classifying a failed send into a stable error_code and a
server-authored Chinese message, never Tencent's own raw Message string.
Unit-level (no app/db wiring needed): mirrors the FakeResponse/FakeClient
pattern already used by
saas-base/tests/test_channel_production_sms_login.py::test_tencent_rejection_log_is_sanitized
for exercising the real HTTP-call code path without a network dependency.
"""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from app.config import settings
from app.services import tencent_sms_service as merchant_sms
from app.services.tencent_sms_service import SmsErrorCode, SmsPurpose, TencentSmsService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _fake_client(status_set):
    """Builds a fake httpx.AsyncClient whose .post() resolves to a Tencent
    SendSms response carrying the given SendStatusSet -- same fake shape as
    test_tencent_rejection_log_is_sanitized, reused here so both tests stay
    aligned with the real response shape."""

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"Response": {"RequestId": "req-contract-test", "SendStatusSet": status_set}}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            return FakeResponse()

    return FakeClient


class MerchantSmsErrorContractTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_daily_limit = settings.SMS_CODE_DAILY_LIMIT
        self.original_interval = settings.SMS_CODE_SEND_INTERVAL_SECONDS
        self.original_redis_enabled = settings.REDIS_ENABLED
        settings.SMS_CODE_DAILY_LIMIT = 2
        settings.SMS_CODE_SEND_INTERVAL_SECONDS = 60
        settings.REDIS_ENABLED = False
        merchant_sms._memory_cache.clear()

    async def asyncTearDown(self):
        merchant_sms._memory_cache.clear()
        settings.SMS_CODE_DAILY_LIMIT = self.original_daily_limit
        settings.SMS_CODE_SEND_INTERVAL_SECONDS = self.original_interval
        settings.REDIS_ENABLED = self.original_redis_enabled

    # ------------------------------------------------------------------
    # 1. Provider machine code = real per-number daily limit.
    # ------------------------------------------------------------------
    async def test_provider_daily_limit_code_maps_to_stable_error(self):
        status_set = [{
            "Code": "LimitExceeded.PhoneNumberDailyLimit",
            "Message": "the number of sms messages sent from a single mobile number every day exceeds the upper limit",
            "PhoneNumber": "+8613900000002",
        }]
        with (
            patch.object(TencentSmsService, "is_configured", return_value=True),
            patch("app.services.tencent_sms_service.httpx.AsyncClient", new=_fake_client(status_set)),
        ):
            ok, msg, payload = await TencentSmsService().request_login_code("13900000002")

        self.assertFalse(ok)
        self.assertEqual(payload.get("error_code"), SmsErrorCode.DAILY_LIMIT)
        self.assertEqual(msg, "今日验证码获取次数已达上限，请明日再试")
        self.assertNotIn("upper limit", msg)
        self.assertNotIn("upper limit", str(payload))

    async def test_provider_daily_limit_saturates_local_counter(self):
        # Only the FIRST call is allowed to reach the (fake) provider --
        # the second call must be rejected by our own local daily counter
        # alone, proving the short-circuit in request_login_code actually
        # writes the counter to daily_limit rather than leaving it at
        # whatever count it was before the provider's rejection.
        status_set = [{
            "Code": "LimitExceeded.PhoneNumberDailyLimit",
            "Message": "upper limit",
            "PhoneNumber": "+8613900000003",
        }]
        call_count = {"n": 0}
        FakeClient = _fake_client(status_set)

        class CountingClient(FakeClient):
            async def post(self, *args, **kwargs):
                call_count["n"] += 1
                return await super().post(*args, **kwargs)

        with (
            patch.object(TencentSmsService, "is_configured", return_value=True),
            patch("app.services.tencent_sms_service.httpx.AsyncClient", new=CountingClient),
        ):
            ok1, _msg1, payload1 = await TencentSmsService().request_login_code("13900000003")
            ok2, msg2, payload2 = await TencentSmsService().request_login_code("13900000003")

        self.assertFalse(ok1)
        self.assertFalse(ok2)
        self.assertEqual(payload1.get("error_code"), SmsErrorCode.DAILY_LIMIT)
        self.assertEqual(payload2.get("error_code"), SmsErrorCode.DAILY_LIMIT)
        self.assertEqual(msg2, "今日验证码获取次数已达上限，请明日再试")
        self.assertEqual(call_count["n"], 1, "second call must short-circuit locally, never reach the provider again")

    # ------------------------------------------------------------------
    # 2. Unknown / unmapped provider rejection code.
    # ------------------------------------------------------------------
    async def test_unknown_provider_rejection_maps_to_generic_stable_error(self):
        status_set = [{
            "Code": "FailedOperation.TemplateIncorrectOrUnapproved",
            "Message": "template not approved by carrier -- internal provider detail",
            "PhoneNumber": "+8613900000004",
        }]
        with (
            patch.object(TencentSmsService, "is_configured", return_value=True),
            patch("app.services.tencent_sms_service.httpx.AsyncClient", new=_fake_client(status_set)),
        ):
            ok, msg, payload = await TencentSmsService().request_login_code("13900000004")

        self.assertFalse(ok)
        self.assertEqual(payload.get("error_code"), SmsErrorCode.PROVIDER_REJECTED)
        self.assertEqual(msg, "验证码发送失败，请稍后再试或联系服务商")
        self.assertNotIn("template not approved", msg)
        self.assertNotIn("internal provider detail", msg)
        self.assertNotIn("template not approved", str(payload))

    async def test_unknown_provider_rejection_does_not_saturate_daily_counter(self):
        # An unrecognized rejection must NOT silently burn the local daily
        # budget -- only the unambiguous provider daily-limit code may do
        # that (see test_provider_daily_limit_saturates_local_counter).
        status_set = [{
            "Code": "FailedOperation.SomethingElse",
            "Message": "irrelevant",
            "PhoneNumber": "+8613900000005",
        }]
        with (
            patch.object(TencentSmsService, "is_configured", return_value=True),
            patch("app.services.tencent_sms_service.httpx.AsyncClient", new=_fake_client(status_set)),
        ):
            await TencentSmsService().request_login_code("13900000005")

        service = TencentSmsService()
        daily_key = service._daily_key("13900000005", SmsPurpose.LOGIN)
        stored = merchant_sms._memory_get(daily_key)
        self.assertIsNone(stored, "an unrecognized rejection must not write to the daily counter at all")

    # ------------------------------------------------------------------
    # 3. Provider network / transport failure (no HTTP response at all).
    # ------------------------------------------------------------------
    async def test_provider_network_failure_maps_to_provider_unavailable(self):
        class RaisingClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                raise TimeoutError("connection timed out")

        with (
            patch.object(TencentSmsService, "is_configured", return_value=True),
            patch("app.services.tencent_sms_service.httpx.AsyncClient", new=RaisingClient),
        ):
            ok, msg, payload = await TencentSmsService().request_login_code("13900000006")

        self.assertFalse(ok)
        self.assertEqual(payload.get("error_code"), SmsErrorCode.PROVIDER_UNAVAILABLE)
        self.assertEqual(msg, "短信服务暂时不可用，请稍后再试")
        self.assertNotIn("timed out", msg)

    async def test_missing_provider_config_maps_to_provider_unavailable(self):
        with patch.object(TencentSmsService, "is_configured", return_value=False):
            ok, msg, payload = await TencentSmsService().request_login_code("13900000007")

        self.assertFalse(ok)
        self.assertEqual(payload.get("error_code"), SmsErrorCode.PROVIDER_UNAVAILABLE)
        self.assertEqual(msg, "短信服务暂时不可用，请稍后再试")

    # ------------------------------------------------------------------
    # 4. Local cooldown ("too frequent").
    # ------------------------------------------------------------------
    async def test_local_cooldown_maps_to_too_frequent_with_retry_after(self):
        settings.SMS_CODE_SEND_INTERVAL_SECONDS = 45
        service = TencentSmsService()
        await merchant_sms._cache_set(service._cooldown_key("13900000008", SmsPurpose.LOGIN), True, 45)

        ok, msg, payload = await service.request_login_code("13900000008")

        self.assertFalse(ok)
        self.assertEqual(payload.get("error_code"), SmsErrorCode.TOO_FREQUENT)
        self.assertEqual(payload.get("retry_after"), 45)
        self.assertEqual(msg, "验证码获取过于频繁，请稍后再试")

    # ------------------------------------------------------------------
    # 5. Unified daily counter across purposes; code storage stays isolated.
    # ------------------------------------------------------------------
    async def test_daily_budget_is_unified_across_login_and_register_purposes(self):
        phone = "13900000009"
        service = TencentSmsService()

        # Directly seed the count that a successful REGISTER send would
        # have left behind (avoids a real provider call for this part).
        await merchant_sms._cache_set(service._daily_key(phone, SmsPurpose.REGISTER), 2, 86400)

        # settings.SMS_CODE_DAILY_LIMIT == 2 (asyncSetUp) -- a LOGIN request
        # for the SAME phone must see the budget as already exhausted,
        # because the two purposes must share one daily key.
        ok, msg, payload = await service.request_login_code(phone, purpose=SmsPurpose.LOGIN)

        self.assertFalse(ok)
        self.assertEqual(payload.get("error_code"), SmsErrorCode.DAILY_LIMIT)
        self.assertEqual(msg, "今日验证码获取次数已达上限，请明日再试")
        # The two purposes must resolve to the exact same cache key.
        self.assertEqual(
            service._daily_key(phone, SmsPurpose.LOGIN),
            service._daily_key(phone, SmsPurpose.REGISTER),
        )

    async def test_code_storage_remains_purpose_isolated_despite_unified_daily_budget(self):
        phone = "13900000010"
        service = TencentSmsService()
        await service.store_login_code(phone, "111111", purpose=SmsPurpose.LOGIN)
        await service.store_login_code(phone, "222222", purpose=SmsPurpose.REGISTER)

        # A login code must not verify against the register purpose, and
        # vice versa -- unifying the daily *budget* must not merge the
        # one-time-code namespaces themselves.
        self.assertFalse(await service.verify_login_code(phone, "222222", purpose=SmsPurpose.LOGIN))
        self.assertFalse(await service.verify_login_code(phone, "111111", purpose=SmsPurpose.REGISTER))
        self.assertTrue(await service.verify_login_code(phone, "111111", purpose=SmsPurpose.LOGIN))
        self.assertTrue(await service.verify_login_code(phone, "222222", purpose=SmsPurpose.REGISTER))


if __name__ == "__main__":
    unittest.main()
