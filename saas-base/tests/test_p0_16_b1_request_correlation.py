"""P0-16 Phase B1 -- T02 (create-order client_request_id logging) and T03
(X-Request-ID response propagation).

Phase A confirmed client_request_id -- the P0-04/P0-15 business idempotency
key -- was never logged anywhere in the backend, and the HTTP-level request_id
minted by LoggingMiddleware never left the server (no response header).
"""

import asyncio
import unittest
from datetime import datetime
from unittest.mock import patch

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from app.models.base import Base
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.api.v1.orders import create_order, OrderCreate, OrderItemIn
from app.middleware.logging_middleware import LoggingMiddleware
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_request():
    return Request(
        {
            "type": "http", "method": "POST", "path": "/api/v1/orders",
            "headers": [], "query_string": b"", "server": ("testserver", 80),
            "scheme": "http", "client": ("testclient", 50000),
        }
    )


class CreateOrderCorrelationLoggingTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(tenant_id=TENANT_A, name="Restaurant A", password_hash="x", status=True, is_open=True, payment_mode="postpay")
        self.dish = MenuItem(tenant_id=TENANT_A, name="宫保鸡丁", price="28.00", available=True)
        self.db.add_all([self.tenant, self.dish])
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _body(self, request_id):
        return OrderCreate(
            shop=TENANT_A, table="", items=[OrderItemIn(dish_id=self.dish.id, name="宫保鸡丁", price=28, qty=1)],
            total=28, request_id=request_id,
        )

    async def test_order_created_log_contains_client_request_id_and_order_id(self):
        with patch("app.api.v1.orders.logger") as mock_logger:
            result = await create_order(self._body("K-CREATED-1"), make_request(), db=self.db)
        self.assertEqual(result.code, 200)

        all_calls = [str(c) for c in mock_logger.info.call_args_list + mock_logger.warning.call_args_list]
        matching = [c for c in all_calls if "ORDER_CREATED" in c]
        self.assertTrue(matching, f"no ORDER_CREATED log emitted; calls were: {all_calls}")
        combined = " ".join(matching)
        self.assertIn("K-CREATED-1", combined)
        self.assertIn(str(result.data["order_id"]), combined)
        self.assertIn(TENANT_A, combined)
        # must never log the raw items payload
        self.assertNotIn("宫保鸡丁", combined)

    async def test_idempotent_replay_log_is_distinguishable_from_fresh_create(self):
        with patch("app.api.v1.orders.logger") as mock_logger:
            first = await create_order(self._body("K-REPLAY-1"), make_request(), db=self.db)
            second = await create_order(self._body("K-REPLAY-1"), make_request(), db=self.db)
        self.assertEqual(first.data["order_id"], second.data["order_id"])

        all_calls = [str(c) for c in mock_logger.info.call_args_list + mock_logger.warning.call_args_list]
        replay_calls = [c for c in all_calls if "ORDER_IDEMPOTENT_REPLAY" in c]
        self.assertTrue(replay_calls, f"no ORDER_IDEMPOTENT_REPLAY log emitted; calls were: {all_calls}")
        self.assertIn("K-REPLAY-1", " ".join(replay_calls))

    async def test_fingerprint_conflict_log_identifies_the_request(self):
        with patch("app.api.v1.orders.logger") as mock_logger:
            await create_order(self._body("K-CONFLICT-1"), make_request(), db=self.db)
            conflict_body = OrderCreate(
                shop=TENANT_A, table="",
                items=[OrderItemIn(dish_id=self.dish.id, name="宫保鸡丁", price=28, qty=2)],
                total=56, request_id="K-CONFLICT-1",
            )
            conflict_result = await create_order(conflict_body, make_request(), db=self.db)
        self.assertEqual(conflict_result.code, 409)

        all_calls = [str(c) for c in mock_logger.info.call_args_list + mock_logger.warning.call_args_list]
        conflict_calls = [c for c in all_calls if "ORDER_FINGERPRINT_CONFLICT" in c]
        self.assertTrue(conflict_calls, f"no ORDER_FINGERPRINT_CONFLICT log emitted; calls were: {all_calls}")
        self.assertIn("K-CONFLICT-1", " ".join(conflict_calls))

    async def test_no_participant_token_or_phone_ever_logged_in_correlation_lines(self):
        with patch("app.api.v1.orders.logger") as mock_logger:
            await create_order(self._body("K-SAFE-1"), make_request(), db=self.db)
        all_calls = " ".join(str(c) for c in mock_logger.info.call_args_list + mock_logger.warning.call_args_list)
        self.assertNotIn("participant_token", all_calls.lower())


class XRequestIdHeaderTest(unittest.IsolatedAsyncioTestCase):
    """T03: the request_id LoggingMiddleware already mints on request.state must
    reach the client via a response header -- currently it never leaves the
    server, so a customer's error screenshot has nothing to correlate against
    the backend's own logs."""

    def _make_request(self):
        return Request(
            {
                "type": "http", "method": "GET", "path": "/api/v1/orders/1",
                "headers": [], "query_string": b"", "server": ("testserver", 80),
                "scheme": "http", "client": ("testclient", 50000),
            }
        )

    async def test_success_response_carries_x_request_id(self):
        request = self._make_request()

        async def call_next(_req):
            return Response("ok", status_code=200)

        response = await LoggingMiddleware(lambda scope, receive, send: None).dispatch(request, call_next)

        self.assertIn("X-Request-ID", response.headers)
        self.assertEqual(response.headers["X-Request-ID"], request.state.request_id)

    async def test_business_error_response_still_carries_x_request_id(self):
        # error_response()-style bodies return HTTP 200 with a business error
        # code in the JSON body -- the header must still be present.
        request = self._make_request()

        async def call_next(_req):
            return JSONResponse({"code": 400, "msg": "缺少shop参数"}, status_code=200)

        response = await LoggingMiddleware(lambda scope, receive, send: None).dispatch(request, call_next)

        self.assertIn("X-Request-ID", response.headers)
        self.assertEqual(response.headers["X-Request-ID"], request.state.request_id)

    async def test_exception_response_still_carries_x_request_id(self):
        # A raised HTTPException/validation error is turned into a Response by
        # FastAPI's own exception handlers *before* call_next returns to this
        # middleware -- so the normal (non-except) path below still applies.
        request = self._make_request()

        async def call_next(_req):
            return JSONResponse({"code": 500, "msg": "服务器内部错误"}, status_code=500)

        response = await LoggingMiddleware(lambda scope, receive, send: None).dispatch(request, call_next)

        self.assertIn("X-Request-ID", response.headers)
        self.assertEqual(response.headers["X-Request-ID"], request.state.request_id)

    async def test_x_process_time_ms_header_is_unaffected(self):
        request = self._make_request()

        async def call_next(_req):
            return Response("ok", status_code=200)

        response = await LoggingMiddleware(lambda scope, receive, send: None).dispatch(request, call_next)

        self.assertIn("X-Process-Time-Ms", response.headers)


if __name__ == "__main__":
    unittest.main()
