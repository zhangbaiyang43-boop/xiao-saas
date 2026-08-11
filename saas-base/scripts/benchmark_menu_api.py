"""Reproducible application benchmark for GET /api/v1/menu/items.

This harness uses the production ASGI route/middleware with an isolated in-memory
SQLite database. Results describe application scaling only; they are not evidence
about production MySQL, its network, pool, optimizer, or storage latency.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import math
import statistics
import time
from collections.abc import Sequence
from typing import Any

from starlette.requests import Request


PERCENTILES = (50, 75, 90, 95, 99)
DATASETS = ((30, 5), (100, 10), (500, 20))


def percentile(values: Sequence[float], percentage: int) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("at least one sample is required")
    position = (len(ordered) - 1) * (percentage / 100)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize(values: Sequence[float]) -> dict[str, float]:
    samples = [float(value) for value in values]
    if not samples:
        raise ValueError("at least one sample is required")
    result = {f"p{p}": round(percentile(samples, p), 3) for p in PERCENTILES}
    result["max"] = round(max(samples), 3)
    result["avg"] = round(statistics.fmean(samples), 3)
    return result


def build_dataset(item_count: int, category_count: int) -> dict[str, Any]:
    categories = [f"Category {index + 1}" for index in range(category_count)]
    items = []
    specs = {}
    for index in range(item_count):
        item_id = index + 1
        items.append(
            {
                "id": item_id,
                "name": f"Benchmark Dish {item_id:04d}",
                "description": f"Freshly prepared benchmark menu item {item_id}",
                "price": f"{8 + (index % 80) * 0.5:.2f}",
                "category": categories[index % category_count],
                "emoji": "🍜",
                "available": True,
                "sort_order": index,
                "image": f"https://cdn.example.invalid/menu/{item_id}.webp",
                "sales_count": index % 200,
                "tags": "popular,fresh" if index % 4 == 0 else None,
                "original_price": None,
                "stock": None if index % 5 else 20,
            }
        )
        # 34% of dishes have specs. Each has 2-3 groups and 2-3 options.
        if index % 3 == 0:
            groups = []
            for group_index in range(2 + (index % 2)):
                groups.append(
                    {
                        "name": f"Choice {group_index + 1}",
                        "options": [
                            {"name": f"Option {option + 1}", "price": option}
                            for option in range(2 + ((index + group_index) % 2))
                        ],
                    }
                )
            specs[str(item_id)] = groups
    return {"items": items, "specs": specs}


def build_menu_response(
    item_count: int,
    category_count: int,
    *,
    text_multiplier: int = 1,
):
    """Build the same public object shape returned by ``list_menu_items``."""
    from app.core.response import success_response

    dataset = build_dataset(item_count, category_count)
    repeated_description = max(1, text_multiplier)
    serialized_items = []
    for item in dataset["items"]:
        raw_tags = item["tags"] or ""
        spec_groups = dataset["specs"].get(str(item["id"]), [])
        serialized_items.append(
            {
                "id": str(item["id"]),
                "name": item["name"],
                "description": item["description"] * repeated_description,
                "price": float(item["price"]),
                "category": item["category"],
                "emoji": item["emoji"],
                "available": item["available"],
                "sort_order": item["sort_order"],
                "image": item["image"],
                "sales_count": item["sales_count"],
                "tags": [tag.strip() for tag in raw_tags.split(",") if tag.strip()],
                "original_price": None,
                "stock": item["stock"],
                "sold_out": item["stock"] is not None and item["stock"] <= 0,
                "spec_groups": spec_groups,
                "has_options": bool(spec_groups),
            }
        )
    return success_response(
        data={
            "items": serialized_items,
            "version": "2026-08-11T12:30:00",
        }
    )


async def render_production_response(response_object):
    """Reproduce FastAPI 0.109's observed no-response-field response path."""
    from fastapi.routing import serialize_response
    from starlette.responses import JSONResponse

    content = await serialize_response(field=None, response_content=response_object)
    return JSONResponse(content)


def render_model_dump_then_json_response(response_object):
    """Candidate A: Pydantic JSON-mode conversion plus the current renderer."""
    from starlette.responses import JSONResponse

    return JSONResponse(response_object.model_dump(mode="json"))


def render_model_dump_json(response_object):
    """Candidate B: Pydantic-core JSON bytes in a standard Starlette response."""
    from starlette.responses import Response

    return Response(
        content=response_object.model_dump_json(),
        media_type="application/json",
    )


def gzip_diagnostic(payload: bytes, samples: int = 100) -> dict[str, Any]:
    timings = []
    compressed = b""
    for _ in range(samples):
        started_at = time.perf_counter()
        compressed = gzip.compress(payload)
        timings.append((time.perf_counter() - started_at) * 1000)
    return {
        "raw_bytes": len(payload),
        "gzip_bytes": len(compressed),
        "compression_ratio": round(len(compressed) / len(payload), 4),
        "compression_cpu_ms": summarize(timings),
    }


def _build_residual_app(payload: bytes):
    """Benchmark-only app with the production middleware order and ready bytes."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.responses import Response

    from app.config import settings
    from app.middleware.auth_middleware import AuthMiddleware
    from app.middleware.logging_middleware import LoggingMiddleware
    from app.middleware.tenant_middleware import TenantMiddleware

    benchmark_app = FastAPI()

    @benchmark_app.get("/api/v1/menu/items")
    async def ready_payload():
        return Response(content=payload, media_type="application/json")

    benchmark_app.add_middleware(AuthMiddleware)
    benchmark_app.add_middleware(TenantMiddleware)
    benchmark_app.add_middleware(LoggingMiddleware)
    benchmark_app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip()
            for origin in settings.CORS_ORIGINS.split(",")
            if origin.strip()
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
        expose_headers=["X-Process-Time-Ms", "X-Workbench-Cursor"],
    )
    return benchmark_app


async def _middleware_asgi_samples(payload: bytes, samples: int, warmup: int) -> list[float]:
    import httpx

    benchmark_app = _build_residual_app(payload)
    transport = httpx.ASGITransport(app=benchmark_app)
    timings = []
    async with httpx.AsyncClient(transport=transport, base_url="http://benchmark") as client:
        for _ in range(warmup):
            response = await client.get("/api/v1/menu/items")
            response.raise_for_status()
        for _ in range(samples):
            response = await client.get("/api/v1/menu/items")
            response.raise_for_status()
            if response.content != payload:
                raise RuntimeError("middleware residual payload mismatch")
            timings.append(float(response.headers["x-process-time-ms"]))
    return timings


async def _measure_finalization_dataset(
    item_count: int,
    category_count: int,
    samples: int,
    warmup: int,
) -> dict[str, Any]:
    from fastapi.routing import serialize_response
    from starlette.responses import JSONResponse

    response_object = build_menu_response(item_count, category_count)

    async def current_response_model_phase():
        return await serialize_response(field=None, response_content=response_object)

    for _ in range(warmup):
        serialized = await current_response_model_phase()
        JSONResponse(serialized)
        render_model_dump_then_json_response(response_object)
        render_model_dump_json(response_object)

    response_model_samples = []
    json_render_samples = []
    current_samples = []
    candidate_a_samples = []
    candidate_b_samples = []
    serialized = await current_response_model_phase()
    for _ in range(samples):
        started_at = time.perf_counter()
        await current_response_model_phase()
        response_model_samples.append((time.perf_counter() - started_at) * 1000)

        started_at = time.perf_counter()
        JSONResponse(serialized)
        json_render_samples.append((time.perf_counter() - started_at) * 1000)

        started_at = time.perf_counter()
        await render_production_response(response_object)
        current_samples.append((time.perf_counter() - started_at) * 1000)

        started_at = time.perf_counter()
        render_model_dump_then_json_response(response_object)
        candidate_a_samples.append((time.perf_counter() - started_at) * 1000)

        started_at = time.perf_counter()
        render_model_dump_json(response_object)
        candidate_b_samples.append((time.perf_counter() - started_at) * 1000)

    current_response = await render_production_response(response_object)
    middleware_samples = await _middleware_asgi_samples(
        current_response.body,
        samples=samples,
        warmup=warmup,
    )
    return {
        "items": item_count,
        "categories": category_count,
        "payload_bytes": len(current_response.body),
        "metrics": {
            "response_model_ms": summarize(response_model_samples),
            "json_render_ms": summarize(json_render_samples),
            "middleware_asgi_ms": summarize(middleware_samples),
            "current_finalization_ms": summarize(current_samples),
            "candidate_model_dump_json_response_ms": summarize(candidate_a_samples),
            "candidate_model_dump_json_ms": summarize(candidate_b_samples),
        },
        "gzip": gzip_diagnostic(current_response.body, samples=samples),
    }


async def run_finalization_benchmark(samples: int = 100, warmup: int = 10) -> dict[str, Any]:
    results = [
        await _measure_finalization_dataset(item_count, category_count, samples, warmup)
        for item_count, category_count in DATASETS
    ]

    async def measure_text_variant(text_multiplier: int) -> dict[str, float]:
        from fastapi.routing import serialize_response
        from starlette.responses import JSONResponse

        response_object = build_menu_response(100, 10, text_multiplier=text_multiplier)
        model_samples = []
        render_samples = []
        serialized = await serialize_response(field=None, response_content=response_object)
        for _ in range(samples):
            started_at = time.perf_counter()
            await serialize_response(field=None, response_content=response_object)
            model_samples.append((time.perf_counter() - started_at) * 1000)
            started_at = time.perf_counter()
            rendered = JSONResponse(serialized)
            render_samples.append((time.perf_counter() - started_at) * 1000)
        return {
            "payload_bytes": len(rendered.body),
            "response_model_p50_ms": percentile(model_samples, 50),
            "json_render_p50_ms": percentile(render_samples, 50),
        }

    baseline_text = await measure_text_variant(1)
    expanded_text = await measure_text_variant(8)
    return {
        "pipeline": {
            "fastapi": "0.109.0",
            "pydantic": "2.6.1",
            "starlette": "0.35.1",
            "response_field": None,
            "response_model_phase": "APPROXIMATE: serialize_response(field=None) / jsonable_encoder",
            "json_renderer": "starlette.responses.JSONResponse",
            "middleware_stack": ["CORSMiddleware", "LoggingMiddleware", "TenantMiddleware", "AuthMiddleware"],
        },
        "samples_per_dataset": samples,
        "warmup_per_dataset": warmup,
        "results": results,
        "byte_scaling_probe": {
            "items": 100,
            "baseline_payload_bytes": baseline_text["payload_bytes"],
            "expanded_payload_bytes": expanded_text["payload_bytes"],
            "baseline_response_model_p50_ms": round(baseline_text["response_model_p50_ms"], 3),
            "expanded_response_model_p50_ms": round(expanded_text["response_model_p50_ms"], 3),
            "baseline_json_render_p50_ms": round(baseline_text["json_render_p50_ms"], 3),
            "expanded_json_render_p50_ms": round(expanded_text["json_render_p50_ms"], 3),
        },
    }


def _build_candidate_api_app(session_factory, mode: str):
    from fastapi import Depends, FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from app.api.v1.menu import _list_menu_items
    from app.config import settings
    from app.middleware.auth_middleware import AuthMiddleware
    from app.middleware.logging_middleware import LoggingMiddleware
    from app.middleware.tenant_middleware import TenantMiddleware

    candidate_app = FastAPI()

    async def benchmark_db():
        async with session_factory() as session:
            yield session

    @candidate_app.get("/api/v1/menu/items")
    async def benchmark_menu(request: Request, shop: str, db=Depends(benchmark_db)):
        raw_response = await _list_menu_items(
            request,
            shop,
            db,
            finalize_json=False,
        )
        if mode == "current":
            return raw_response
        if mode == "model_dump_json_response":
            return render_model_dump_then_json_response(raw_response)
        if mode == "model_dump_json":
            return render_model_dump_json(raw_response)
        raise RuntimeError(f"unknown candidate mode: {mode}")

    candidate_app.add_middleware(AuthMiddleware)
    candidate_app.add_middleware(TenantMiddleware)
    candidate_app.add_middleware(LoggingMiddleware)
    candidate_app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip()
            for origin in settings.CORS_ORIGINS.split(",")
            if origin.strip()
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
        expose_headers=["X-Process-Time-Ms", "X-Workbench-Cursor"],
    )
    return candidate_app


async def run_candidate_api_benchmark(samples: int = 100, warmup: int = 10) -> dict[str, Any]:
    """Compare candidates through the same route logic, DB, and middleware stack."""
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.models.base import Base
    from app.models.menu_item import MenuItem
    from app.models.tenant import Tenant
    from app.models.tenant_config import TenantConfig

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[Tenant.__table__, MenuItem.__table__, TenantConfig.__table__],
            )
        )
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    modes = {}
    try:
        for mode in ("current", "model_dump_json_response", "model_dump_json"):
            app = _build_candidate_api_app(session_factory, mode)
            capture = DiagnosticsCapture(app)
            transport = httpx.ASGITransport(app=capture)
            mode_results = []
            async with httpx.AsyncClient(transport=transport, base_url="http://benchmark") as client:
                for item_count, category_count in DATASETS:
                    tenant_id = await seed_dataset(session_factory, item_count, category_count)
                    url = f"/api/v1/menu/items?shop={tenant_id}"
                    for _ in range(warmup):
                        response = await client.get(url)
                        response.raise_for_status()
                    server_samples = []
                    handler_samples = []
                    payload_samples = []
                    body = None
                    for _ in range(samples):
                        response = await client.get(url)
                        response.raise_for_status()
                        body = response.json()
                        diagnostics = capture.last["diagnostics"]
                        server_samples.append(capture.last["server_total_ms"])
                        handler_samples.append(float(diagnostics["handler_total_ms"]))
                        payload_samples.append(float(len(response.content)))
                    if body["code"] != 200 or len(body["data"]["items"]) != item_count:
                        raise RuntimeError("candidate API response contract mismatch")
                    mode_results.append(
                        {
                            "items": item_count,
                            "categories": category_count,
                            "status_code": response.status_code,
                            "content_type": response.headers["content-type"],
                            "item_count": len(body["data"]["items"]),
                            "metrics": {
                                "server_total_ms": summarize(server_samples),
                                "handler_total_ms": summarize(handler_samples),
                                "payload_bytes": summarize(payload_samples),
                            },
                        }
                    )
            modes[mode] = mode_results
    finally:
        await engine.dispose()
    return {
        "environment": "same menu handler + isolated SQLite + production middleware order",
        "samples_per_dataset": samples,
        "warmup_per_dataset": warmup,
        "modes": modes,
    }


class DiagnosticsCapture:
    """Benchmark-only ASGI wrapper; production middleware remains untouched."""

    def __init__(self, app):
        self.app = app
        self.last: dict[str, Any] = {}

    async def __call__(self, scope, receive, send):
        response_headers: dict[str, str] = {}

        async def capture_send(message):
            if message["type"] == "http.response.start":
                response_headers.update(
                    (key.decode("latin-1").lower(), value.decode("latin-1"))
                    for key, value in message.get("headers", [])
                )
            await send(message)

        await self.app(scope, receive, capture_send)
        state = scope.get("state") or {}
        self.last = {
            "diagnostics": dict(state.get("menu_diagnostics") or {}),
            "server_total_ms": float(response_headers["x-process-time-ms"]),
        }


async def seed_dataset(session_factory, item_count: int, category_count: int) -> str:
    from sqlalchemy import delete

    from app.models.menu_item import MenuItem
    from app.models.tenant import Tenant
    from app.models.tenant_config import TenantConfig

    dataset = build_dataset(item_count, category_count)
    tenant_id = f"menu-benchmark-{item_count}"
    async with session_factory() as session:
        await session.execute(delete(TenantConfig))
        await session.execute(delete(MenuItem))
        await session.execute(delete(Tenant))
        session.add(
            Tenant(
                id=10_000 + item_count,
                tenant_id=tenant_id,
                name=f"Benchmark Restaurant {item_count}",
                password_hash="benchmark-only",
                status=True,
            )
        )
        session.add_all(
            MenuItem(tenant_id=tenant_id, **item)
            for item in dataset["items"]
        )
        session.add(
            TenantConfig(
                id=20_000 + item_count,
                tenant_id=tenant_id,
                business_info={"menu_item_specs": dataset["specs"]},
            )
        )
        await session.commit()
    return tenant_id


def diagnostics_overhead_microbenchmark(
    item_count: int,
    category_count: int,
    iterations: int = 1000,
) -> dict[str, float]:
    serialized_items = []
    dataset = build_dataset(item_count, category_count)
    for item in dataset["items"]:
        serialized_items.append(
            {
                "category": item["category"],
                "spec_groups": dataset["specs"].get(str(item["id"]), []),
            }
        )

    off_samples = []
    on_samples = []
    for _ in range(iterations):
        started = time.perf_counter()
        len(serialized_items)
        off_samples.append((time.perf_counter() - started) * 1000)

        started = time.perf_counter()
        len(serialized_items)
        len({item["category"] for item in serialized_items if item["category"] is not None})
        sum(len(item["spec_groups"]) for item in serialized_items)
        sum(
            len(group.get("options") or [])
            for item in serialized_items
            for group in item["spec_groups"]
            if isinstance(group, dict)
        )
        time.perf_counter()
        on_samples.append((time.perf_counter() - started) * 1000)

    off_p50 = percentile(off_samples, 50)
    on_p50 = percentile(on_samples, 50)
    return {
        "off_p50_ms": round(off_p50, 6),
        "on_p50_ms": round(on_p50, 6),
        "delta_p50_ms": round(max(0.0, on_p50 - off_p50), 6),
    }


async def explain_sqlite(session_factory, tenant_id: str) -> list[str]:
    from sqlalchemy import text

    statement = text(
        "EXPLAIN QUERY PLAN SELECT * FROM menu_items "
        "WHERE tenant_id = :tenant_id AND available = 1 "
        "ORDER BY sort_order, id"
    )
    async with session_factory() as session:
        result = await session.execute(statement, {"tenant_id": tenant_id})
        return [str(row[-1]) for row in result.all()]


async def run_benchmark(requests: int, warmup: int) -> dict[str, Any]:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.database import get_db
    from app.main import app
    from app.models.base import Base
    from app.models.menu_item import MenuItem
    from app.models.tenant import Tenant
    from app.models.tenant_config import TenantConfig

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[Tenant.__table__, MenuItem.__table__, TenantConfig.__table__],
            )
        )
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def benchmark_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = benchmark_db
    capture = DiagnosticsCapture(app)
    transport = httpx.ASGITransport(app=capture)
    results = []
    explain = []
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://benchmark") as client:
            for item_count, category_count in DATASETS:
                tenant_id = await seed_dataset(session_factory, item_count, category_count)
                url = f"/api/v1/menu/items?shop={tenant_id}"
                for _ in range(warmup):
                    response = await client.get(url)
                    response.raise_for_status()

                samples: dict[str, list[float]] = {
                    "client_total_ms": [],
                    "server_total_ms": [],
                    "handler_total_ms": [],
                    "tenant_query_ms": [],
                    "menu_query_ms": [],
                    "config_query_ms": [],
                    "mapping_ms": [],
                    "serialization_prepare_ms": [],
                    "payload_bytes": [],
                }
                for _ in range(requests):
                    started_at = time.perf_counter()
                    response = await client.get(url)
                    client_total_ms = (time.perf_counter() - started_at) * 1000
                    response.raise_for_status()
                    body = response.json()
                    if body["code"] != 200 or len(body["data"]["items"]) != item_count:
                        raise RuntimeError("benchmark response contract mismatch")
                    diagnostics = capture.last["diagnostics"]
                    samples["client_total_ms"].append(client_total_ms)
                    samples["server_total_ms"].append(capture.last["server_total_ms"])
                    for metric in (
                        "handler_total_ms",
                        "tenant_query_ms",
                        "menu_query_ms",
                        "config_query_ms",
                        "mapping_ms",
                        "serialization_prepare_ms",
                    ):
                        samples[metric].append(float(diagnostics[metric]))
                    samples["payload_bytes"].append(float(len(response.content)))

                metrics = {name: summarize(values) for name, values in samples.items()}
                overhead = diagnostics_overhead_microbenchmark(item_count, category_count)
                overhead["percent_of_handler_p50"] = round(
                    overhead["delta_p50_ms"] / metrics["handler_total_ms"]["p50"] * 100,
                    3,
                )
                results.append(
                    {
                        "items": item_count,
                        "categories": category_count,
                        "spec_dishes": len(build_dataset(item_count, category_count)["specs"]),
                        "requests": requests,
                        "metrics": metrics,
                        "diagnostics_overhead": overhead,
                    }
                )
                if item_count == DATASETS[-1][0]:
                    explain = await explain_sqlite(session_factory, tenant_id)
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()

    return {
        "environment": "production ASGI route/middleware + isolated in-memory SQLite",
        "evidence_scope": "APPLICATION BENCHMARK; NOT PRODUCTION MYSQL REPRESENTATIVE",
        "cold_start": "NOT MEASURED",
        "warmup_requests_per_dataset": warmup,
        "results": results,
        "sqlite_explain_query_plan": explain,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument(
        "--mode",
        choices=("application", "finalization", "candidates", "all"),
        default="application",
    )
    args = parser.parse_args()
    if args.requests <= 0 or args.warmup < 0:
        parser.error("--requests must be positive and --warmup cannot be negative")
    if args.mode == "application":
        report = asyncio.run(run_benchmark(args.requests, args.warmup))
    elif args.mode == "finalization":
        report = asyncio.run(run_finalization_benchmark(args.requests, args.warmup))
    elif args.mode == "candidates":
        report = asyncio.run(run_candidate_api_benchmark(args.requests, args.warmup))
    else:
        async def run_all():
            return {
                "application": await run_benchmark(args.requests, args.warmup),
                "finalization": await run_finalization_benchmark(args.requests, args.warmup),
                "candidates": await run_candidate_api_benchmark(args.requests, args.warmup),
            }

        report = asyncio.run(run_all())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
