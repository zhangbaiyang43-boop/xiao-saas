"""Reproducible application benchmark for GET /api/v1/menu/items.

This harness uses the production ASGI route/middleware with an isolated in-memory
SQLite database. Results describe application scaling only; they are not evidence
about production MySQL, its network, pool, optimizer, or storage latency.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import time
from collections.abc import Sequence
from typing import Any


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
    args = parser.parse_args()
    if args.requests <= 0 or args.warmup < 0:
        parser.error("--requests must be positive and --warmup cannot be negative")
    report = asyncio.run(run_benchmark(args.requests, args.warmup))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
