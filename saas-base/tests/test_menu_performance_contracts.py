import asyncio
import json
import unittest
from unittest.mock import patch

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.api.v1.menu import list_menu_items
from app.middleware.logging_middleware import LoggingMiddleware
from app.models.base import Base
from app.models.menu_item import MenuItem
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig


if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


TENANT_ID = "menu-perf-tenant"
EXPECTED_ITEM_FIELDS = {
    "id",
    "name",
    "description",
    "price",
    "category",
    "emoji",
    "available",
    "sort_order",
    "image",
    "sales_count",
    "tags",
    "original_price",
    "stock",
    "sold_out",
    "spec_groups",
    "has_options",
}

# The slow-menu warning's `extra=` must stay a lightweight correlation record.
# Heavy per-request diagnostics belong only in the structured JSON message; these
# keys must never be copied into `extra`.
SLOW_LOG_DETAIL_KEYS_NOT_ALLOWED_IN_EXTRA = frozenset({
    "tenant_query_ms",
    "handler_total_ms",
    "menu_query_ms",
    "config_query_ms",
    "mapping_ms",
    "serialization_prepare_ms",
    "payload_bytes",
    "menu_item_count",
    "category_count",
    "spec_group_count",
    "spec_option_count",
    "cache_state",
})
# PII / credential / payment identifiers must never appear in `extra` (nor in the
# message, but `extra` is what an unstructured log sink surfaces verbatim).
SLOW_LOG_SENSITIVE_KEYS_NOT_ALLOWED_IN_EXTRA = frozenset({
    "openid",
    "unionid",
    "authorization",
    "access_token",
    "refresh_token",
    "phone",
    "mobile",
    "password",
    "cookie",
    "request_body",
    "raw_body",
    "session_token",
    "participant_token",
    "dining_session_token",
    "out_trade_no",
    "transaction_id",
})


def make_request() -> Request:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/menu/items",
            "headers": [],
            "query_string": f"shop={TENANT_ID}".encode(),
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    request.state.request_id = "menu-perf-request"
    return request


class MenuPerformanceContractTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    tables=[Tenant.__table__, MenuItem.__table__, TenantConfig.__table__],
                )
            )
        self.SessionLocal = sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self.db = self.SessionLocal()
        self.db.add(
            Tenant(
                tenant_id=TENANT_ID,
                name="Performance Restaurant",
                password_hash="x",
                status=True,
            )
        )
        items = [
            MenuItem(
                id=101,
                tenant_id=TENANT_ID,
                name="Noodles",
                price="18.00",
                category="Staples",
                available=True,
                stock=8,
                image="https://example.invalid/noodles.webp",
            ),
            MenuItem(
                id=102,
                tenant_id=TENANT_ID,
                name="Tea",
                price="6.00",
                category="Drinks",
                available=True,
                stock=None,
            ),
        ]
        self.db.add_all(items)
        self.db.add(
            TenantConfig(
                tenant_id=TENANT_ID,
                business_info={
                    "menu_item_specs": {
                        "101": [
                            {
                                "name": "Size",
                                "options": [
                                    {"name": "Regular", "price": 0},
                                    {"name": "Large", "price": 3},
                                ],
                            }
                        ]
                    }
                },
            )
        )
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_customer_menu_keeps_response_contract_and_records_diagnostics(self):
        request = make_request()
        statements = []

        @event.listens_for(self.engine.sync_engine, "before_cursor_execute")
        def count_statement(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        response = await list_menu_items(request, shop=TENANT_ID, db=self.db)

        body = json.loads(response.body)
        self.assertEqual(body["code"], 200)
        self.assertEqual(set(body["data"]), {"items", "version"})
        self.assertEqual(len(body["data"]["items"]), 2)
        self.assertEqual(set(body["data"]["items"][0]), EXPECTED_ITEM_FIELDS)
        self.assertEqual(len(statements), 3)

        diagnostics = request.state.menu_diagnostics
        for field in (
            "tenant_query_ms",
            "menu_query_ms",
            "config_query_ms",
            "mapping_ms",
            "serialization_prepare_ms",
            "handler_total_ms",
        ):
            self.assertIsInstance(diagnostics[field], float)
            self.assertGreaterEqual(diagnostics[field], 0)
        self.assertGreaterEqual(
            diagnostics["handler_total_ms"],
            diagnostics["tenant_query_ms"]
            + diagnostics["menu_query_ms"]
            + diagnostics["config_query_ms"]
            + diagnostics["mapping_ms"]
            + diagnostics["serialization_prepare_ms"],
        )
        self.assertEqual(diagnostics["menu_item_count"], 2)
        self.assertEqual(diagnostics["category_count"], 2)
        self.assertEqual(diagnostics["spec_group_count"], 1)
        self.assertEqual(diagnostics["spec_option_count"], 2)
        self.assertEqual(diagnostics["cache_state"], "none")
        self.assertEqual(diagnostics["request_id"], "menu-perf-request")
        self.assertEqual(diagnostics["tenant_id"], TENANT_ID)

    async def test_customer_menu_success_is_finalized_without_losing_diagnostics(self):
        request = make_request()

        response = await list_menu_items(request, shop=TENANT_ID, db=self.db)

        self.assertIsInstance(response, Response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/json")
        body = json.loads(response.body)
        self.assertEqual(body["code"], 200)
        self.assertEqual(body["msg"], "ok")
        self.assertEqual(len(body["data"]["items"]), 2)
        self.assertEqual(set(body["data"]["items"][0]), EXPECTED_ITEM_FIELDS)
        self.assertEqual(request.state.menu_diagnostics["request_id"], "menu-perf-request")
        self.assertEqual(request.state.menu_diagnostics["menu_item_count"], 2)

    async def test_finalized_menu_keeps_slow_log_payload_and_request_correlation(self):
        request = make_request()
        finalized = await list_menu_items(request, shop=TENANT_ID, db=self.db)

        async def call_next(current_request):
            self.assertIs(current_request, request)
            return finalized

        with patch("app.middleware.logging_middleware.time.time", side_effect=[10.0, 10.6]):
            with patch("app.middleware.logging_middleware.logger.warning") as warning:
                response = await LoggingMiddleware(lambda scope, receive, send: None).dispatch(
                    request,
                    call_next,
                )

        diagnostics = request.state.menu_diagnostics
        self.assertEqual(response.headers["X-Process-Time-Ms"], "600.0")
        self.assertEqual(diagnostics["payload_bytes"], len(finalized.body))
        self.assertEqual(diagnostics["request_id"], "menu-perf-request")
        detailed = [
            json.loads(call.args[0])
            for call in warning.call_args_list
            if call.args and call.args[0].startswith("{")
        ]
        self.assertEqual(detailed[0]["event"], "SLOW_MENU_API")

    async def test_menu_error_path_keeps_framework_response_contract(self):
        request = make_request()

        response = await list_menu_items(request, shop=None, db=self.db)

        self.assertEqual(response.code, 400)
        self.assertEqual(response.msg, "缺少shop参数")
        self.assertIsNone(response.data)

    async def test_fast_request_does_not_emit_detailed_slow_log(self):
        from app.middleware.logging_middleware import _log_slow_menu_api

        with patch("app.middleware.logging_middleware.logger.warning") as warning:
            _log_slow_menu_api({"server_total_ms": 499.999})
            warning.assert_not_called()

    async def test_slow_log_is_structured_thresholded_and_private(self):
        from app.middleware.logging_middleware import _log_slow_menu_api

        base = {
            "request_id": "request-123",
            "tenant_id": TENANT_ID,
            "server_total_ms": 700.0,
            "handler_total_ms": 700.0,
            "tenant_query_ms": 100.0,
            "menu_query_ms": 400.0,
            "config_query_ms": 50.0,
            "mapping_ms": 30.0,
            "serialization_prepare_ms": 2.0,
            "payload_bytes": 4096,
            "menu_item_count": 100,
            "category_count": 10,
            "spec_group_count": 20,
            "spec_option_count": 50,
            "cache_state": "none",
            "status_code": 200,
        }

        with patch("app.middleware.logging_middleware.logger.warning") as warning:
            _log_slow_menu_api(base)
            warning.assert_called_once()
            message, = warning.call_args.args
            logged = json.loads(message)
            self.assertEqual(logged, {"event": "SLOW_MENU_API", **base})
            fields = warning.call_args.kwargs["extra"]
            # Contract: `extra` carries the request correlation id and the event
            # classification with their exact values -- but is NOT pinned to an
            # exact key set, so a future safe correlation field (trace_id,
            # span_id, ...) can be added without breaking this. What it must
            # NOT contain is heavy diagnostics or any PII/credential key.
            self.assertEqual(fields.get("request_id"), "request-123")
            self.assertEqual(fields.get("event"), "SLOW_MENU_API")
            for detail_key in SLOW_LOG_DETAIL_KEYS_NOT_ALLOWED_IN_EXTRA:
                self.assertNotIn(detail_key, fields)
            for sensitive_key in SLOW_LOG_SENSITIVE_KEYS_NOT_ALLOWED_IN_EXTRA:
                self.assertNotIn(sensitive_key, fields)
            for forbidden in ("authorization", "openid", "phone", "password", "items"):
                self.assertNotIn(forbidden, logged)

        with patch("app.middleware.logging_middleware.logger.warning") as warning:
            _log_slow_menu_api({**base, "server_total_ms": 1200.0})
            logged = json.loads(warning.call_args.args[0])
            self.assertEqual(logged["event"], "VERY_SLOW_MENU_API")

    async def test_logging_middleware_adds_server_total_and_payload_before_slow_log(self):
        request = make_request()
        diagnostics = {
            "request_id": "menu-perf-request",
            "tenant_id": TENANT_ID,
            "server_total_ms": None,
            "handler_total_ms": 20.0,
            "tenant_query_ms": 3.0,
            "menu_query_ms": 8.0,
            "config_query_ms": 2.0,
            "mapping_ms": 4.0,
            "serialization_prepare_ms": 1.0,
            "payload_bytes": None,
            "menu_item_count": 30,
            "category_count": 5,
            "spec_group_count": 10,
            "spec_option_count": 25,
            "cache_state": "none",
            "status_code": 200,
        }

        async def call_next(current_request):
            current_request.state.menu_diagnostics = diagnostics
            return JSONResponse({"code": 200, "msg": "ok", "data": {"items": []}})

        with patch("app.middleware.logging_middleware.time.time", side_effect=[10.0, 10.6]):
            with patch("app.middleware.logging_middleware.logger.warning") as warning:
                response = await LoggingMiddleware(lambda scope, receive, send: None).dispatch(
                    request,
                    call_next,
                )

        self.assertEqual(response.headers["X-Process-Time-Ms"], "600.0")
        self.assertEqual(diagnostics["server_total_ms"], 600.0)
        self.assertEqual(diagnostics["payload_bytes"], int(response.headers["content-length"]))
        detailed = [
            json.loads(call.args[0])
            for call in warning.call_args_list
            if call.args and call.args[0].startswith("{")
        ]
        self.assertEqual(detailed[0]["event"], "SLOW_MENU_API")


class MenuBenchmarkContractTest(unittest.TestCase):
    def test_summary_contains_required_long_tail_percentiles(self):
        from scripts.benchmark_menu_api import summarize

        summary = summarize([1.0, 2.0, 3.0, 4.0, 100.0])

        self.assertEqual(
            set(summary),
            {"p50", "p75", "p90", "p95", "p99", "max", "avg"},
        )
        self.assertEqual(summary["p50"], 3.0)
        self.assertEqual(summary["max"], 100.0)
        self.assertEqual(summary["avg"], 22.0)
        self.assertGreaterEqual(summary["p99"], summary["p95"])
        self.assertGreaterEqual(summary["p95"], summary["p90"])

    def test_dataset_shape_is_deterministic_and_realistic(self):
        from scripts.benchmark_menu_api import build_dataset

        first = build_dataset(100, 10)
        second = build_dataset(100, 10)

        self.assertEqual(first, second)
        self.assertEqual(len(first["items"]), 100)
        self.assertEqual(len({item["category"] for item in first["items"]}), 10)
        self.assertGreaterEqual(len(first["specs"]), 20)
        self.assertLessEqual(len(first["specs"]), 40)
        for groups in first["specs"].values():
            self.assertIn(len(groups), (2, 3))
            for group in groups:
                self.assertIn(len(group["options"]), (2, 3))


if __name__ == "__main__":
    unittest.main()
