import asyncio
import inspect
import json
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request
from starlette.responses import Response

from app.api.v1.orders import router, wxpay_notify
from app.core import ops_alert
from app.middleware.auth_middleware import AuthMiddleware, _is_order_wxpay_notify_path
from app.models.base import Base
from app.models.order import Order
from app.models.tenant import Tenant
from app.services.order_payment_service import (
    OrderPaymentService,
    _build_order_wxpay_notify_url,
)


if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


def make_request(tenant_id: str) -> Request:
    async def _body():
        return b"{}"

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": f"/api/v1/orders/wxpay-notify/{tenant_id}",
            "path_params": {"tenant_id": tenant_id},
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "https",
            "client": ("testclient", 50000),
        }
    )
    request.body = _body
    return request


def response_body(response: Response):
    if not response.body:
        return None
    return json.loads(response.body)


class _FakeWxPayService:
    resource = None
    reason = "OK"
    constructed_with = []

    def __init__(self, tenant):
        self.enabled = True
        self.last_verify_reason = self.reason
        self.constructed_with.append(tenant)

    def verify_notify(self, _headers, _raw_body):
        self.last_verify_reason = self.reason
        return self.resource


class WxpayCallbackRouteContractTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.Session()
        self.tenant_a = Tenant(
            tenant_id=TENANT_A,
            name="Tenant A",
            password_hash="x",
            status=True,
            is_open=True,
            payment_mode="prepay",
            wx_pay_enabled=True,
            wx_mchid="same-mchid",
            wx_api_key_v3="encrypted-key",
            wx_cert_serial="serial",
            wx_private_key="encrypted-private-key",
        )
        self.tenant_b = Tenant(
            tenant_id=TENANT_B,
            name="Tenant B",
            password_hash="x",
            status=True,
            is_open=True,
            payment_mode="prepay",
            wx_pay_enabled=True,
            wx_mchid="same-mchid",
            wx_api_key_v3="encrypted-key",
            wx_cert_serial="serial",
            wx_private_key="encrypted-private-key",
        )
        self.db.add_all([self.tenant_a, self.tenant_b])
        await self.db.commit()
        _FakeWxPayService.constructed_with = []

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def make_order(self, tenant_id=TENANT_A, **overrides):
        values = {
            "tenant_id": tenant_id,
            "total": "28.00",
            "status": "pending_payment",
            "payment_status": "unpaid",
            "payment_mode": "prepay",
        }
        values.update(overrides)
        order = Order(**values)
        self.db.add(order)
        await self.db.commit()
        return order

    @staticmethod
    def resource(order, **overrides):
        value = {
            "out_trade_no": str(order.id),
            "trade_state": "SUCCESS",
            "transaction_id": f"wx-routing-{order.id}",
            "amount": {"total": 2800, "payer_total": 2800, "currency": "CNY"},
        }
        value.update(overrides)
        return value

    async def notify(self, tenant_id, resource, *, reason="OK"):
        _FakeWxPayService.resource = resource
        _FakeWxPayService.reason = reason

        async def mark_paid(_service, order, *, payment_method):
            order.payment_status = "paid"
            order.payment_method = payment_method
            order.status = "pending"
            return None, None

        with (
            patch("app.services.wxpay_service.WxPayService", _FakeWxPayService),
            patch.object(OrderPaymentService, "_on_payment_success", mark_paid),
            patch.object(
                OrderPaymentService,
                "_run_post_commit_payment_effects",
                new_callable=AsyncMock,
            ) as post_commit,
        ):
            response = await wxpay_notify(tenant_id, make_request(tenant_id), db=self.db)
        return response, post_commit

    async def test_dynamic_route_replaces_legacy_route(self):
        route_paths = {getattr(route, "path", "") for route in router.routes}
        self.assertIn("/orders/wxpay-notify/{tenant_id}", route_paths)
        self.assertNotIn("/orders/wxpay-notify", route_paths)

    async def test_notify_url_strips_trailing_slash_and_path_encodes_tenant(self):
        with patch(
            "app.services.order_payment_service.settings.H5_ORDER_BASE_URL",
            "https://saas.example.com/",
        ):
            self.assertEqual(
                _build_order_wxpay_notify_url("tenant/a b?"),
                "https://saas.example.com/api/v1/orders/wxpay-notify/tenant%2Fa%20b%3F",
            )

    async def test_notify_url_rejects_non_https_base(self):
        with patch(
            "app.services.order_payment_service.settings.H5_ORDER_BASE_URL",
            "http://saas.example.com",
        ):
            with self.assertRaisesRegex(RuntimeError, "HTTPS"):
                _build_order_wxpay_notify_url(TENANT_A)

    async def test_dynamic_callback_is_explicitly_anonymous_without_legacy_match(self):
        self.assertTrue(_is_order_wxpay_notify_path(f"/api/v1/orders/wxpay-notify/{TENANT_A}"))
        self.assertFalse(_is_order_wxpay_notify_path("/api/v1/orders/wxpay-notify"))
        self.assertFalse(_is_order_wxpay_notify_path(f"/api/v1/orders/wxpay-notify/{TENANT_A}/extra"))

        middleware = AuthMiddleware(app=None)
        called = AsyncMock(return_value=Response(status_code=204))
        response = await middleware.dispatch(make_request(TENANT_A), called)
        self.assertEqual(response.status_code, 204)
        called.assert_awaited_once()

    async def test_ops_alert_recognizes_only_dynamic_callback_path(self):
        self.assertTrue(
            ops_alert.is_core_exception_path(
                "POST", f"/api/v1/orders/wxpay-notify/{TENANT_A}"
            )
        )
        self.assertFalse(
            ops_alert.is_core_exception_path("POST", "/api/v1/orders/wxpay-notify")
        )

    async def test_tenant_a_and_tenant_b_routes_only_mutate_their_own_orders(self):
        for tenant_id in (TENANT_A, TENANT_B):
            with self.subTest(tenant_id=tenant_id):
                order = await self.make_order(tenant_id)
                response, post_commit = await self.notify(tenant_id, self.resource(order))
                self.assertEqual(response.status_code, 204)
                self.assertIsNone(response_body(response))
                await self.db.refresh(order)
                self.assertEqual(order.payment_status, "paid")
                post_commit.assert_awaited_once()

    async def test_shared_credentials_wrong_route_is_404_without_fallback_or_mutation(self):
        order_b = await self.make_order(TENANT_B)
        response, post_commit = await self.notify(TENANT_A, self.resource(order_b))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response_body(response)["code"], "FAIL")
        await self.db.refresh(order_b)
        self.assertEqual(order_b.payment_status, "unpaid")
        self.assertIsNone(order_b.wx_transaction_id)
        post_commit.assert_not_awaited()
        self.assertEqual(len(_FakeWxPayService.constructed_with), 1)

    async def test_unknown_tenant_is_404_without_constructing_provider(self):
        order = await self.make_order()
        response, post_commit = await self.notify("missing-tenant", self.resource(order))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response_body(response)["code"], "FAIL")
        self.assertEqual(_FakeWxPayService.constructed_with, [])
        post_commit.assert_not_awaited()

    async def test_signature_and_decrypt_failures_are_400(self):
        for reason in ("SIGNATURE_VERIFY_FAILED", "DECRYPT_FAILED"):
            with self.subTest(reason=reason):
                response, post_commit = await self.notify(TENANT_A, None, reason=reason)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response_body(response)["code"], "FAIL")
                post_commit.assert_not_awaited()

    async def test_invalid_out_trade_no_and_unknown_order_are_4xx(self):
        invalid, _ = await self.notify(
            TENANT_A,
            {
                "out_trade_no": "not-an-order-id",
                "trade_state": "SUCCESS",
                "transaction_id": "wx-invalid-order",
                "amount": {"total": 2800, "currency": "CNY"},
            },
        )
        self.assertEqual(invalid.status_code, 400)

        unknown, _ = await self.notify(
            TENANT_A,
            {
                "out_trade_no": "999999999999999999",
                "trade_state": "SUCCESS",
                "transaction_id": "wx-unknown-order",
                "amount": {"total": 2800, "currency": "CNY"},
            },
        )
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(response_body(unknown)["code"], "FAIL")

    async def test_payment_fact_failures_are_422_and_zero_mutation(self):
        mutations = (
            lambda fact: fact.update(trade_state="NOTPAY"),
            lambda fact: fact.pop("amount"),
            lambda fact: fact["amount"].update(total=1),
            lambda fact: fact["amount"].update(currency="USD"),
            lambda fact: fact.pop("transaction_id"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                order = await self.make_order()
                fact = self.resource(order)
                mutate(fact)
                response, post_commit = await self.notify(TENANT_A, fact)
                self.assertEqual(response.status_code, 422)
                await self.db.refresh(order)
                self.assertEqual(order.payment_status, "unpaid")
                self.assertIsNone(order.wx_transaction_id)
                post_commit.assert_not_awaited()

    async def test_transaction_id_reuse_is_409(self):
        first = await self.make_order()
        second = await self.make_order()
        transaction_id = "wx-shared-routing-transaction"
        first_response, _ = await self.notify(
            TENANT_A, self.resource(first, transaction_id=transaction_id)
        )
        second_response, second_post_commit = await self.notify(
            TENANT_A, self.resource(second, transaction_id=transaction_id)
        )
        self.assertEqual(first_response.status_code, 204)
        self.assertEqual(second_response.status_code, 409)
        await self.db.refresh(second)
        self.assertEqual(second.payment_status, "unpaid")
        self.assertIsNone(second.wx_transaction_id)
        second_post_commit.assert_not_awaited()

    async def test_exact_replay_is_204_and_runs_post_commit_once(self):
        order = await self.make_order()
        fact = self.resource(order)
        first, first_post_commit = await self.notify(TENANT_A, fact)
        replay, replay_post_commit = await self.notify(TENANT_A, fact)
        self.assertEqual(first.status_code, 204)
        self.assertEqual(replay.status_code, 204)
        first_post_commit.assert_awaited_once()
        replay_post_commit.assert_not_awaited()

    async def test_paused_tenant_valid_inflight_callback_is_processed(self):
        self.tenant_a.wx_pay_enabled = False
        await self.db.commit()
        order = await self.make_order()
        response, _ = await self.notify(TENANT_A, self.resource(order))
        self.assertEqual(response.status_code, 204)
        await self.db.refresh(order)
        self.assertEqual(order.payment_status, "paid")
        self.assertTrue(_FakeWxPayService.constructed_with[0].wx_pay_enabled)
        await self.db.refresh(self.tenant_a)
        self.assertFalse(self.tenant_a.wx_pay_enabled)

    async def test_postpay_and_table_account_callbacks_are_rejected(self):
        for mode in ("postpay", "table_account"):
            with self.subTest(mode=mode):
                order = await self.make_order(payment_mode=mode)
                response, post_commit = await self.notify(TENANT_A, self.resource(order))
                self.assertEqual(response.status_code, 422)
                await self.db.refresh(order)
                self.assertEqual(order.payment_status, "unpaid")
                self.assertIsNone(order.wx_transaction_id)
                post_commit.assert_not_awaited()

    async def test_internal_failure_rolls_back_and_returns_500(self):
        order = await self.make_order()
        order_id = order.id
        _FakeWxPayService.resource = self.resource(order)
        _FakeWxPayService.reason = "OK"

        async def fail_after_claim(_service, _order, *, payment_method):
            raise RuntimeError("database effect failed")

        with (
            patch("app.services.wxpay_service.WxPayService", _FakeWxPayService),
            patch.object(OrderPaymentService, "_on_payment_success", fail_after_claim),
        ):
            response = await wxpay_notify(TENANT_A, make_request(TENANT_A), db=self.db)

        self.assertEqual(response.status_code, 500)
        current = await self.db.get(Order, order_id)
        await self.db.refresh(current)
        self.assertEqual(current.payment_status, "unpaid")
        self.assertIsNone(current.wx_transaction_id)

    async def test_service_source_has_no_tenant_scan_or_query_hint(self):
        source = inspect.getsource(OrderPaymentService.wxpay_notify)
        self.assertNotIn("request.query_params", source)
        self.assertNotIn("scalars().all()", source)
        self.assertNotIn("for t in tenants", source)
        self.assertNotIn("Tenant.wx_pay_enabled == True", source)


if __name__ == "__main__":
    unittest.main()
