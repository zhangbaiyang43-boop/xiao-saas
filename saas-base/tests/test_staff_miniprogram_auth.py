"""Staff mini-program identity + handoff Authentication tests."""

from __future__ import annotations

import asyncio
import unittest

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.permissions import permission_list
from app.core.security import verify_token
from app.models.base import Base
from app.models.merchant_account import MerchantAccount
from app.models.merchant_account_trusted_device import MerchantAccountTrustedDevice  # noqa: F401
from app.models.merchant_account_wechat_binding import MerchantAccountWechatBinding  # noqa: F401
from app.models.tenant import Tenant
from app.services import staff_handoff_service as handoff_svc
from app.services import staff_mp_bind_session_service as mp_bind
from app.services.staff_miniprogram_provider import (
    MockMiniProgramIdentityProvider,
    STAFF_MP_TEST_SCAN_PREFIX,
    build_staff_mp_test_scan_payload,
)
from app.services.staff_wechat_auth_service import StaffWechatAuthService
from app.services.staff_wechat_provider import WechatIdentity as WId
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-mp-a"
TENANT_B = "tenant-mp-b"
APP_ID = "mock_miniapp"


class StaffMiniprogramAuthTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from app.services import staff_bind_token_service as bind_tokens

        bind_tokens._MEMORY.clear()
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

        self.waiter_id = generate_snowflake_id()
        self.kitchen_id = generate_snowflake_id()
        self.waiter_b_id = generate_snowflake_id()

        async with self.SessionLocal() as db:
            db.add_all(
                [
                    Tenant(
                        tenant_id=TENANT_A,
                        name="老王川菜馆",
                        password_hash="x",
                        phone="13800001111",
                        status=True,
                        is_open=True,
                    ),
                    Tenant(
                        tenant_id=TENANT_B,
                        name="老李烧烤",
                        password_hash="x",
                        phone="13800002222",
                        status=True,
                        is_open=True,
                    ),
                    MerchantAccount(
                        id=self.waiter_id,
                        tenant_id=TENANT_A,
                        name="张白杨",
                        username=None,
                        password_hash=None,
                        role="waiter",
                        status="active",
                    ),
                    MerchantAccount(
                        id=self.kitchen_id,
                        tenant_id=TENANT_A,
                        name="小李",
                        username=None,
                        password_hash=None,
                        role="kitchen",
                        status="active",
                    ),
                    MerchantAccount(
                        id=self.waiter_b_id,
                        tenant_id=TENANT_B,
                        name="张白杨",
                        username=None,
                        password_hash=None,
                        role="kitchen",
                        status="active",
                    ),
                ]
            )
            await db.commit()

    async def test_mp_bind_scene_single_use_and_length(self):
        session = await mp_bind.create_mp_bind_session(
            tenant_id=TENANT_A, account_id=self.waiter_id, created_by_owner=TENANT_A
        )
        scene = session["scene"]
        self.assertEqual(len(scene), 32)
        self.assertIsNotNone(await mp_bind.peek_mp_bind_scene(scene))

        session2 = await mp_bind.create_mp_bind_session(
            tenant_id=TENANT_A, account_id=self.waiter_id, created_by_owner=TENANT_A
        )
        self.assertIsNone(await mp_bind.peek_mp_bind_scene(scene))
        self.assertIsNotNone(await mp_bind.peek_mp_bind_scene(session2["scene"]))

        consumed = await mp_bind.consume_mp_bind_scene(session2["scene"])
        self.assertEqual(int(consumed["account_id"]), self.waiter_id)
        self.assertIsNone(await mp_bind.consume_mp_bind_scene(session2["scene"]))

    async def test_bind_and_handoff_flow(self):
        async with self.SessionLocal() as db:
            svc = StaffWechatAuthService(db)
            session = await mp_bind.create_mp_bind_session(
                tenant_id=TENANT_A, account_id=self.waiter_id, created_by_owner=TENANT_A
            )
            identity = WId(app_id=APP_ID, openid="openid_waiter_a")
            peek = await mp_bind.peek_mp_bind_scene(session["scene"])
            bound = await svc.bind_wechat_identity(
                tenant_id=peek["tenant_id"],
                account_id=int(peek["account_id"]),
                identity=identity,
            )
            self.assertTrue(bound["ok"])
            await mp_bind.consume_mp_bind_scene(session["scene"])

            handoff = await handoff_svc.create_handoff(
                tenant_id=TENANT_A,
                account_id=self.waiter_id,
                wechat_app_id=APP_ID,
                openid="openid_waiter_a",
            )
            payload = await handoff_svc.consume_handoff(handoff["handoff_token"])
            self.assertEqual(int(payload["account_id"]), self.waiter_id)
            self.assertIsNone(await handoff_svc.consume_handoff(handoff["handoff_token"]))

            issued = await svc.issue_session_for_account(
                bound["account"], auth_method="staff_mp_handoff"
            )
            self.assertTrue(issued["ok"])
            self.assertEqual(issued["role"], "waiter")
            self.assertEqual(set(issued["permissions"]), set(permission_list("waiter")))
            self.assertIn("device_credential", issued)
            tok = verify_token(issued["token"])
            self.assertEqual(tok["account_id"], self.waiter_id)
            self.assertNotEqual(tok.get("role"), "owner")

    async def test_already_bound_other_openid_rejected(self):
        async with self.SessionLocal() as db:
            svc = StaffWechatAuthService(db)
            await svc.bind_wechat_identity(
                tenant_id=TENANT_A,
                account_id=self.waiter_id,
                identity=WId(app_id=APP_ID, openid="openid_1"),
            )
            again = await svc.bind_wechat_identity(
                tenant_id=TENANT_A,
                account_id=self.waiter_id,
                identity=WId(app_id=APP_ID, openid="openid_2"),
            )
            self.assertFalse(again["ok"])
            self.assertEqual(again["code"], "already_bound")

    async def test_idempotent_same_openid(self):
        async with self.SessionLocal() as db:
            svc = StaffWechatAuthService(db)
            first = await svc.bind_wechat_identity(
                tenant_id=TENANT_A,
                account_id=self.waiter_id,
                identity=WId(app_id=APP_ID, openid="openid_same"),
            )
            second = await svc.bind_wechat_identity(
                tenant_id=TENANT_A,
                account_id=self.waiter_id,
                identity=WId(app_id=APP_ID, openid="openid_same"),
            )
            self.assertTrue(first["ok"])
            self.assertTrue(second["ok"])
            self.assertTrue(second.get("idempotent"))

    async def test_role_change_reflected_on_handoff(self):
        async with self.SessionLocal() as db:
            svc = StaffWechatAuthService(db)
            await svc.bind_wechat_identity(
                tenant_id=TENANT_A,
                account_id=self.waiter_id,
                identity=WId(app_id=APP_ID, openid="openid_role"),
            )
            acc = await svc._get_account(TENANT_A, self.waiter_id)
            acc.role = "kitchen"
            await db.commit()
            await db.refresh(acc)
            issued = await svc.issue_session_for_account(acc, auth_method="staff_mp_handoff")
            self.assertEqual(issued["role"], "kitchen")
            self.assertEqual(set(issued["permissions"]), set(permission_list("kitchen")))

    async def test_disabled_account_login_lookup_empty(self):
        async with self.SessionLocal() as db:
            svc = StaffWechatAuthService(db)
            await svc.bind_wechat_identity(
                tenant_id=TENANT_A,
                account_id=self.waiter_id,
                identity=WId(app_id=APP_ID, openid="openid_dis"),
            )
            acc = await svc._get_account(TENANT_A, self.waiter_id)
            acc.status = "disabled"
            await db.commit()
            matches = await svc.list_active_accounts_for_openid(app_id=APP_ID, openid="openid_dis")
            self.assertEqual(matches, [])

    async def test_multi_store_requires_select(self):
        async with self.SessionLocal() as db:
            svc = StaffWechatAuthService(db)
            identity = WId(app_id=APP_ID, openid="openid_multi")
            await svc.bind_wechat_identity(
                tenant_id=TENANT_A, account_id=self.waiter_id, identity=identity
            )
            await svc.bind_wechat_identity(
                tenant_id=TENANT_B, account_id=self.waiter_b_id, identity=identity
            )
            matches = await svc.list_active_accounts_for_openid(
                app_id=APP_ID, openid="openid_multi"
            )
            self.assertEqual(len(matches), 2)
            login = await svc.login_with_identity(identity=identity)
            self.assertEqual(login["code"], "multiple_accounts")

    async def test_mock_provider_code(self):
        provider = MockMiniProgramIdentityProvider(app_id=APP_ID)
        identity = await provider.exchange_code("mock:openid_x:union_y")
        self.assertEqual(identity.openid, "openid_x")
        self.assertEqual(identity.unionid, "union_y")
        self.assertEqual(identity.app_id, APP_ID)

    async def test_wrong_tenant_cannot_bind_via_scene_payload(self):
        async with self.SessionLocal() as db:
            svc = StaffWechatAuthService(db)
            # Scene for tenant A account; attempt bind with mismatched tenant_id rejected.
            result = await svc.bind_wechat_identity(
                tenant_id=TENANT_B,
                account_id=self.waiter_id,
                identity=WId(app_id=APP_ID, openid="x"),
            )
            self.assertFalse(result["ok"])


class StaffMpTestScanPayloadTest(unittest.TestCase):
    """TEMP_STAFF_SCAN_TEST — 正式小程序上线后删除。"""

    def test_payload_format_reuses_scene(self):
        scene = "0123456789abcdef0123456789abcdef"
        payload = build_staff_mp_test_scan_payload(scene)
        self.assertTrue(payload.startswith(STAFF_MP_TEST_SCAN_PREFIX))
        self.assertEqual(payload[len(STAFF_MP_TEST_SCAN_PREFIX) :], scene)


class AppImportMiniprogramRoutesTest(unittest.TestCase):
    def test_routes_registered(self):
        from app.main import app

        paths = {getattr(r, "path", None) for r in app.routes}
        self.assertIn("/api/v1/staff/miniprogram/bind/confirm", paths)
        self.assertIn("/api/v1/login/staff/handoff", paths)
        self.assertIn("/api/v1/merchant-accounts/{account_id}/miniprogram-bind-session", paths)
        self.assertIn("/api/v1/staff/miniprogram/status", paths)


class StaffMpAuthMiddlewareWhitelistTest(unittest.TestCase):
    """First-time bind/login must be anonymous; other /api/v1/staff/* stay protected."""

    PUBLIC_PATHS = (
        "/api/v1/staff/miniprogram/status",
        "/api/v1/staff/miniprogram/bind/preview",
        "/api/v1/staff/miniprogram/bind/confirm",
        "/api/v1/staff/miniprogram/login",
        "/api/v1/staff/miniprogram/login/select",
        "/api/v1/login/staff/handoff",
    )

    def test_exact_whitelist_entries(self):
        from app.middleware.auth_middleware import WHITELIST

        for path in self.PUBLIC_PATHS:
            self.assertIn(path, WHITELIST)
        # Must not open all staff APIs
        self.assertNotIn("/api/v1/staff", WHITELIST)
        self.assertNotIn("/api/v1/orders/workbench", WHITELIST)

    def test_anonymous_bind_preview_passes_middleware(self):
        import json

        from starlette.requests import Request

        from app.middleware.auth_middleware import AuthMiddleware

        middleware = AuthMiddleware(app=None)
        called = {"ok": False}

        async def call_next(request):
            called["ok"] = True
            return json.dumps({"ok": True})

        def make_req(path):
            return Request(
                {
                    "type": "http",
                    "method": "POST",
                    "path": path,
                    "headers": [],
                    "query_string": b"",
                    "server": ("testserver", 80),
                    "scheme": "http",
                    "client": ("testclient", 50000),
                }
            )

        for path in self.PUBLIC_PATHS:
            called["ok"] = False
            result = asyncio.run(middleware.dispatch(make_req(path), call_next))
            self.assertTrue(called["ok"], path)
            self.assertEqual(result, json.dumps({"ok": True}))

        # Non-optional merchant path still 401 without JWT (orders/* is optional-auth).
        called["ok"] = False
        blocked = asyncio.run(middleware.dispatch(make_req("/api/v1/merchant-accounts"), call_next))
        self.assertFalse(called["ok"])
        self.assertEqual(blocked.status_code, 401)
        body = json.loads(blocked.body.decode("utf-8"))
        self.assertEqual(body["code"], 401)


if __name__ == "__main__":
    unittest.main()
