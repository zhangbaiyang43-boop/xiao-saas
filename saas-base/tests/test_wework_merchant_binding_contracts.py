import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException
import jwt

from app.config import settings
from app.api.v1 import wework
from app.api.v1.super_admin import _verify_super_token
from app.middleware.auth_middleware import WHITELIST, WHITELIST_PREFIXES
from app.models.merchant_wecom_binding import MerchantWecomBinding, MerchantWecomBindingToken
from app.services.tencent_sms_service import SmsPurpose
from app.services.wework_binding_service import (
    BINDING_CODE_PUBLIC_MESSAGE,
    CODE_PUBLIC_COOLDOWN_SECONDS,
    CODE_PUBLIC_MAX_REQUESTS,
    TOKEN_TTL_MINUTES,
    WeworkBindingService,
)


SERVICE_SOURCE = inspect.getsource(WeworkBindingService)
API_SOURCE = inspect.getsource(wework)


class _ScalarResult:
    def __init__(self, item):
        self.item = item

    def scalar_one_or_none(self):
        return self.item


class _FakeSession:
    def __init__(self, *items):
        self.items = list(items)
        self.added = []
        self.commit_count = 0
        self.rollback_count = 0
        self.refresh_count = 0

    async def execute(self, _query):
        item = self.items.pop(0) if self.items else None
        return _ScalarResult(item)

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1

    async def refresh(self, _item):
        self.refresh_count += 1


class _FakeSms:
    ttl = 300
    interval = 60

    def __init__(self, result=(True, "验证码已发送", {"expires_in": 300, "retry_after": 60})):
        self.result = result
        self.calls = []
        self.verify_calls = []

    async def request_login_code(self, phone, purpose=SmsPurpose.LOGIN):
        self.calls.append((phone, purpose))
        return self.result

    async def verify_login_code(self, phone, code, purpose=SmsPurpose.LOGIN):
        self.verify_calls.append((phone, code, purpose))
        return code == "123456"


def _super_token(token_type="super_admin"):
    return jwt.encode(
        {"sub": "contract", "type": token_type, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def _event(**overrides):
    data = {
        "id": 9001,
        "tenant_id": "callback-scope-only",
        "external_userid": "wm_external_001",
        "userid": "wecom_staff_001",
        "change_type": "add_external_contact",
        "event_type": "change_external_contact",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _token(**overrides):
    data = {
        "status": "ACTIVE",
        "used_at": None,
        "expires_at": datetime.utcnow() + timedelta(minutes=10),
        "external_userid": "wm_external_001",
        "wecom_user_id": "wecom_staff_001",
        "last_code_requested_at": None,
        "code_request_count": 0,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _tenant(**overrides):
    data = {"tenant_id": "tenant_001", "name": "开心门店", "phone": "13800000000", "status": True}
    data.update(overrides)
    return SimpleNamespace(**data)


class WeworkMerchantBindingContractsTest(unittest.TestCase):
    def test_binding_models_keep_active_uniqueness_at_db_layer(self):
        constraints = {item.name for item in MerchantWecomBinding.__table__.constraints}

        self.assertIn("ux_merchant_wecom_active_tenant", constraints)
        self.assertIn("ux_merchant_wecom_active_external_userid", constraints)
        self.assertIn("active_tenant_id_key", MerchantWecomBinding.__table__.columns)
        self.assertIn("active_external_userid_key", MerchantWecomBinding.__table__.columns)

    def test_token_model_hashes_token_at_rest(self):
        columns = MerchantWecomBindingToken.__table__.columns
        constraints = {item.name for item in MerchantWecomBindingToken.__table__.constraints}

        self.assertIn("token_hash", columns)
        self.assertNotIn("token", columns)
        self.assertIn("ux_merchant_wecom_token_hash", constraints)
        self.assertIn("hashlib.sha256", SERVICE_SOURCE)

    def test_token_is_opaque_single_use_and_ttl_bounded(self):
        self.assertGreaterEqual(len(WeworkBindingService.new_raw_token()), 32)
        self.assertGreaterEqual(TOKEN_TTL_MINUTES, 10)
        self.assertLessEqual(TOKEN_TTL_MINUTES, 30)
        self.assertIn("secrets.token_urlsafe(32)", SERVICE_SOURCE)
        self.assertIn("token.used_at = now", SERVICE_SOURCE)
        self.assertIn("TOKEN_USED", SERVICE_SOURCE)
        self.assertIn("TOKEN_EXPIRED", SERVICE_SOURCE)

    def test_token_create_uses_event_id_not_arbitrary_external_userid(self):
        self.assertIn("wework_event_log_id", API_SOURCE)
        self.assertIn("source_event_id=payload.wework_event_log_id", API_SOURCE)
        self.assertNotIn("external_userid: str", inspect.getsource(wework.BindingTokenRequest))
        self.assertIn("WeworkEventLog", SERVICE_SOURCE)
        self.assertIn("EVENT_IDENTITY_MISSING", SERVICE_SOURCE)
        self.assertIn("EVENT_NOT_BINDABLE", SERVICE_SOURCE)

    def test_token_create_requires_route_level_super_admin(self):
        source = inspect.getsource(wework.create_binding_token)
        # wework.router is APIRouter(prefix="/api/v1/wework"), so each route.path
        # is already prefix-composed at registration -- match the canonical final
        # path, the same one asserted against WHITELIST below.
        route = next(item for item in wework.router.routes if item.path == "/api/v1/wework/bindings/tokens")

        self.assertIn("/api/v1/wework/bindings/tokens", WHITELIST)
        self.assertIn("_verify_super_token", API_SOURCE)
        self.assertIs(wework._verify_super_token, _verify_super_token)
        self.assertIn("Depends(_require_wework_super_token)", source)
        self.assertIn("HTTPException(status_code=401", API_SOURCE)
        self.assertTrue(any(dependency.call is wework._require_wework_super_token for dependency in route.dependant.dependencies))
        self.assertNotIn("ROLE_OWNER", API_SOURCE)
        self.assertNotIn("_require_owner", API_SOURCE)

    def test_super_admin_token_contract_rejects_anonymous_and_merchant_token(self):
        with self.assertRaises(HTTPException) as missing_header:
            wework._require_wework_super_token(None)
        self.assertEqual(missing_header.exception.status_code, 401)

        with self.assertRaises(HTTPException) as merchant_token:
            wework._require_wework_super_token(_super_token("merchant"))
        self.assertEqual(merchant_token.exception.status_code, 401)

        with self.assertRaises(HTTPException) as staff_token:
            wework._require_wework_super_token(_super_token("staff"))
        self.assertEqual(staff_token.exception.status_code, 401)

        self.assertEqual(wework._require_wework_super_token(_super_token("super_admin")), "contract")

    def test_public_code_and_confirm_are_exactly_whitelisted(self):
        self.assertIn("/api/v1/wework/bindings/code", WHITELIST)
        self.assertIn("/api/v1/wework/bindings/confirm", WHITELIST)
        self.assertFalse(any("/api/v1/wework/bindings" in prefix for prefix in WHITELIST_PREFIXES))
        self.assertNotIn("/api/v1/wework", WHITELIST)

    def test_binding_endpoints_keep_slowapi_request_signature_contract(self):
        for endpoint in (wework.create_binding_token, wework.send_binding_code, wework.confirm_binding):
            self.assertIn("request", inspect.signature(endpoint).parameters)

    def test_binding_code_validates_token_before_sending_sms(self):
        send_source = inspect.getsource(WeworkBindingService.send_binding_code)

        self.assertLess(send_source.index("_valid_token"), send_source.index("request_login_code"))
        self.assertIn("purpose=SmsPurpose.WECOM_BINDING", send_source)
        self.assertIn("lock=True", send_source)

    def test_binding_code_public_response_is_phone_existence_opaque(self):
        send_source = inspect.getsource(WeworkBindingService.send_binding_code)

        self.assertEqual(BINDING_CODE_PUBLIC_MESSAGE, "如果该手机号可用于绑定，验证码将发送")
        self.assertGreaterEqual(CODE_PUBLIC_COOLDOWN_SECONDS, 60)
        self.assertGreaterEqual(CODE_PUBLIC_MAX_REQUESTS, 5)
        self.assertEqual(send_source.count("return True, BINDING_CODE_PUBLIC_MESSAGE"), 3)
        self.assertIn("if not tenant or not tenant.status", send_source)
        self.assertIn("await sms.request_login_code", send_source)
        self.assertNotIn("return await TencentSmsService().request_login_code", send_source)

    def test_binding_code_consumes_token_throttle_before_phone_lookup(self):
        send_source = inspect.getsource(WeworkBindingService.send_binding_code)

        self.assertLess(send_source.index("token.last_code_requested_at = now"), send_source.index("_tenant_by_phone"))
        self.assertLess(send_source.index("token.code_request_count"), send_source.index("_tenant_by_phone"))
        self.assertIn("await self.db.commit()", send_source)

    def test_non_existing_phone_does_not_send_sms_provider_call(self):
        send_source = inspect.getsource(WeworkBindingService.send_binding_code)
        missing_phone_branch = send_source[
            send_source.index("if not tenant or not tenant.status"):
            send_source.index("await sms.request_login_code")
        ]

        self.assertNotIn("request_login_code", missing_phone_branch)

    async def _send_code_result(self, *, tenant, sms=None, token=None):
        sms = sms or _FakeSms()
        token = token or _token()
        db = _FakeSession(token, tenant)
        with patch.object(
            __import__("app.services.wework_binding_service", fromlist=["TencentSmsService"]),
            "TencentSmsService",
            return_value=sms,
        ):
            result = await WeworkBindingService(db).send_binding_code(
                binding_token="opaque-binding-token",
                phone="13800000000",
            )
        return result, db, sms, token

    def test_existing_and_non_existing_phone_public_code_responses_are_equivalent(self):
        async def run_case():
            existing, _, _, _ = await self._send_code_result(tenant=_tenant())
            missing, _, _, _ = await self._send_code_result(tenant=None)

            self.assertEqual(existing[0], missing[0])
            self.assertEqual(existing[1], missing[1])
            self.assertEqual(set(existing[2].keys()), set(missing[2].keys()))
            self.assertEqual(existing[1], BINDING_CODE_PUBLIC_MESSAGE)

        __import__("asyncio").run(run_case())

    def test_provider_cooldown_public_response_stays_generic(self):
        async def run_case():
            provider_cooldown = _FakeSms((False, "请求过于频繁", {"error_code": "TOO_FREQUENT", "retry_after": 60}))
            result, _, sms, _ = await self._send_code_result(tenant=_tenant(), sms=provider_cooldown)

            self.assertEqual(result[0], True)
            self.assertEqual(result[1], BINDING_CODE_PUBLIC_MESSAGE)
            self.assertEqual(set(result[2].keys()), {"expires_in", "retry_after"})
            self.assertEqual(sms.calls, [("13800000000", SmsPurpose.WECOM_BINDING)])

        __import__("asyncio").run(run_case())

    def test_non_existing_phone_consumes_token_throttle_without_sms_provider_call(self):
        async def run_case():
            token = _token()
            result, db, sms, token = await self._send_code_result(tenant=None, token=token)

            self.assertEqual(result[1], BINDING_CODE_PUBLIC_MESSAGE)
            self.assertEqual(token.code_request_count, 1)
            self.assertIsNotNone(token.last_code_requested_at)
            self.assertEqual(db.commit_count, 1)
            self.assertEqual(sms.calls, [])

        __import__("asyncio").run(run_case())

    def test_existing_phone_consumes_token_throttle_before_sms_provider_call(self):
        async def run_case():
            token = _token()
            result, db, sms, token = await self._send_code_result(tenant=_tenant(), token=token)

            self.assertEqual(result[1], BINDING_CODE_PUBLIC_MESSAGE)
            self.assertEqual(token.code_request_count, 1)
            self.assertIsNotNone(token.last_code_requested_at)
            self.assertEqual(db.commit_count, 1)
            self.assertEqual(sms.calls, [("13800000000", SmsPurpose.WECOM_BINDING)])

        __import__("asyncio").run(run_case())

    def test_token_level_rapid_repeat_returns_generic_without_provider_side_effect(self):
        async def run_case():
            token = _token(last_code_requested_at=datetime.utcnow(), code_request_count=1)
            result, db, sms, token = await self._send_code_result(tenant=_tenant(), token=token)

            self.assertEqual(result[0], True)
            self.assertEqual(result[1], BINDING_CODE_PUBLIC_MESSAGE)
            self.assertEqual(token.code_request_count, 1)
            self.assertEqual(db.commit_count, 0)
            self.assertEqual(sms.calls, [])

        __import__("asyncio").run(run_case())

    def test_binding_confirm_uses_same_otp_purpose(self):
        confirm_source = inspect.getsource(WeworkBindingService.confirm_binding)

        self.assertEqual(SmsPurpose.WECOM_BINDING, "wecom_binding")
        self.assertIn("purpose=SmsPurpose.WECOM_BINDING", confirm_source)

    def test_confirm_does_not_accept_tenant_or_external_identity_from_client(self):
        fields = set(wework.BindingConfirmRequest.model_fields.keys())

        self.assertEqual(fields, {"binding_token", "phone", "otp_code"})
        self.assertNotIn("tenant_id", fields)
        self.assertNotIn("external_userid", fields)
        self.assertNotIn("wecom_user_id", fields)

    def test_tenant_source_is_owner_phone_not_callback_tenant(self):
        confirm_source = inspect.getsource(WeworkBindingService.confirm_binding)

        self.assertIn("_tenant_by_phone(normalized_phone)", confirm_source)
        self.assertNotIn("token.tenant_id", confirm_source)
        self.assertNotIn("event.tenant_id", confirm_source)

    def test_token_create_does_not_authorize_with_callback_tenant(self):
        create_source = inspect.getsource(WeworkBindingService.create_binding_token)

        self.assertIn("_trusted_event(source_event_id)", create_source)
        self.assertNotIn("actor_tenant_id", create_source)
        self.assertNotIn("request.state.tenant_id", create_source)
        self.assertNotIn("event.tenant_id !=", create_source)

    def test_token_source_event_validation_behavior(self):
        async def run_case():
            with self.assertRaisesRegex(Exception, "企业微信事件不存在"):
                await WeworkBindingService(_FakeSession(None)).create_binding_token(source_event_id=404)

            with self.assertRaisesRegex(Exception, "企业微信事件缺少客户身份"):
                await WeworkBindingService(_FakeSession(_event(external_userid=None))).create_binding_token(source_event_id=1)

            with self.assertRaisesRegex(Exception, "该企业微信事件不能用于商户绑定"):
                await WeworkBindingService(_FakeSession(_event(change_type="del_external_contact"))).create_binding_token(source_event_id=1)

            db = _FakeSession(_event(), None)
            issue = await WeworkBindingService(db).create_binding_token(source_event_id=1)
            self.assertGreaterEqual(len(issue.token), 32)
            self.assertEqual(db.commit_count, 1)
            self.assertEqual(len(db.added), 1)
            self.assertEqual(db.added[0].external_userid, "wm_external_001")

        __import__("asyncio").run(run_case())

    def test_conflict_cases_are_explicit(self):
        self.assertIn("EXTERNAL_USERID_CONFLICT", SERVICE_SOURCE)
        self.assertIn("TENANT_BINDING_CONFLICT", SERVICE_SOURCE)
        self.assertIn("ALREADY_BOUND", SERVICE_SOURCE)
        self.assertIn("BINDING_CONFLICT", SERVICE_SOURCE)

    def test_invalid_otp_does_not_consume_token(self):
        invalid_otp_pos = SERVICE_SOURCE.index("INVALID_OTP")
        first_used_at_pos = SERVICE_SOURCE.index("token.used_at = now")

        self.assertLess(invalid_otp_pos, first_used_at_pos)

    def test_binding_and_token_consumption_share_one_commit(self):
        confirm_source = inspect.getsource(WeworkBindingService.confirm_binding)

        self.assertIn("self.db.add(binding)", confirm_source)
        self.assertIn("token.used_at = now", confirm_source)
        self.assertIn("await self.db.commit()", confirm_source)
        self.assertLess(confirm_source.index("self.db.add(binding)"), confirm_source.rindex("await self.db.commit()"))
        self.assertLess(confirm_source.index("token.used_at = now"), confirm_source.rindex("await self.db.commit()"))


if __name__ == "__main__":
    unittest.main()
