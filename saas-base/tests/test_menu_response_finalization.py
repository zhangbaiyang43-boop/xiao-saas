import asyncio
import json
import unittest
from datetime import datetime
from decimal import Decimal

from app.core.response import RespVo
from scripts.benchmark_menu_api import (
    DATASETS,
    build_menu_response,
    gzip_diagnostic,
    render_model_dump_json,
    render_model_dump_then_json_response,
    render_production_response,
    run_candidate_api_benchmark,
    run_finalization_benchmark,
)


if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class MenuResponseFinalizationContractTest(unittest.IsolatedAsyncioTestCase):
    def test_menu_route_uses_the_observed_no_response_field_pipeline(self):
        from app.main import app

        route = next(
            route
            for route in app.routes
            if getattr(route, "path", None) == "/api/v1/menu/items"
            and "GET" in getattr(route, "methods", set())
        )

        self.assertIsNone(route.response_model)
        self.assertIsNone(route.response_field)

    async def test_candidates_preserve_json_semantics_and_http_contract(self):
        response = RespVo(
            code=200,
            msg="成功",
            data={
                "items": [
                    {
                        "id": "101",
                        "name": "宫保鸡丁",
                        "description": None,
                        "price": Decimal("18.25"),
                        "category": "热菜",
                        "emoji": "🍽️",
                        "available": True,
                        "sort_order": 1,
                        "image": "https://example.invalid/宫保鸡丁.webp",
                        "sales_count": 7,
                        "tags": ["招牌", "微辣"],
                        "original_price": Decimal("20.50"),
                        "stock": 0,
                        "sold_out": True,
                        "spec_groups": [
                            {
                                "name": "份量",
                                "options": [
                                    {"name": "大份", "price": Decimal("3.50")},
                                ],
                            }
                        ],
                        "has_options": True,
                    }
                ],
                "version": datetime(2026, 8, 11, 12, 30, 0),
            },
        )

        current = await render_production_response(response)
        candidates = (
            render_model_dump_then_json_response(response),
            render_model_dump_json(response),
        )

        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.media_type, "application/json")
        for candidate in candidates:
            self.assertEqual(candidate.status_code, current.status_code)
            self.assertEqual(candidate.media_type, current.media_type)
            self.assertEqual(json.loads(candidate.body), json.loads(current.body))
            self.assertEqual(
                candidate.headers["content-type"],
                current.headers["content-type"],
            )
            self.assertEqual(
                candidate.headers["content-length"],
                str(len(candidate.body)),
            )

    def test_benchmark_payload_matches_menu_response_contract(self):
        response = build_menu_response(30, 5)
        body = response.model_dump(mode="json")

        self.assertEqual(set(body), {"code", "msg", "data"})
        self.assertEqual(set(body["data"]), {"items", "version"})
        self.assertEqual(len(body["data"]["items"]), 30)
        first = body["data"]["items"][0]
        self.assertEqual(first["id"], "1")
        self.assertIsInstance(first["price"], float)
        self.assertIn("spec_groups", first)
        self.assertIn("stock", first)
        self.assertIn("image", first)

    async def test_finalization_report_has_all_accounting_stages_and_candidates(self):
        report = await run_finalization_benchmark(samples=2, warmup=0)

        self.assertEqual([row["items"] for row in report["results"]], [30, 100, 500])
        self.assertEqual(tuple((row["items"], row["categories"]) for row in report["results"]), DATASETS)
        for row in report["results"]:
            self.assertEqual(
                set(row["metrics"]),
                {
                    "response_model_ms",
                    "json_render_ms",
                    "middleware_asgi_ms",
                    "current_finalization_ms",
                    "candidate_model_dump_json_response_ms",
                    "candidate_model_dump_json_ms",
                },
            )
            for summary in row["metrics"].values():
                self.assertEqual(
                    set(summary),
                    {"p50", "p75", "p90", "p95", "p99", "max", "avg"},
                )
            self.assertGreater(row["payload_bytes"], 0)
            self.assertGreaterEqual(row["gzip"]["raw_bytes"], row["gzip"]["gzip_bytes"])
        self.assertEqual(report["byte_scaling_probe"]["items"], 100)
        self.assertGreater(
            report["byte_scaling_probe"]["expanded_payload_bytes"],
            report["byte_scaling_probe"]["baseline_payload_bytes"],
        )

    async def test_candidate_api_benchmark_compares_same_route_contract(self):
        report = await run_candidate_api_benchmark(samples=1, warmup=0)

        self.assertEqual(
            set(report["modes"]),
            {"current", "model_dump_json_response", "model_dump_json"},
        )
        for mode in report["modes"].values():
            self.assertEqual([row["items"] for row in mode], [30, 100, 500])
            for row in mode:
                self.assertEqual(row["status_code"], 200)
                self.assertEqual(row["content_type"], "application/json")
                self.assertEqual(row["item_count"], row["items"])
                self.assertIn("server_total_ms", row["metrics"])
                self.assertIn("handler_total_ms", row["metrics"])

    def test_gzip_diagnostic_reports_size_ratio_and_cpu(self):
        payload = b'{"data":"' + (b"menu-item," * 1000) + b'"}'

        result = gzip_diagnostic(payload, samples=3)

        self.assertEqual(result["raw_bytes"], len(payload))
        self.assertLess(result["gzip_bytes"], result["raw_bytes"])
        self.assertGreater(result["compression_ratio"], 0)
        self.assertLess(result["compression_ratio"], 1)
        self.assertGreaterEqual(result["compression_cpu_ms"]["p50"], 0)


if __name__ == "__main__":
    unittest.main()
