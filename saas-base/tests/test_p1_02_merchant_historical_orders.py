"""P1-02: merchant historical list_orders date window + forced pagination."""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.orders import list_orders
from app.models.base import Base
from app.models.order import Order
from app.models.tenant import Tenant
from app.services.order_lifecycle_service import resolve_merchant_list_date

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "p1-02-hist-a"
TENANT_B = "p1-02-hist-b"


def make_owner_request(tenant_id=TENANT_A):
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/orders",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    request.state.tenant_id = tenant_id
    request.state.token_type = "merchant"
    request.state.role = "owner"
    request.state.account_id = None
    return request


class P1MerchantHistoricalOrdersTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        for tid in (TENANT_A, TENANT_B):
            self.db.add(
                Tenant(
                    tenant_id=tid,
                    name=f"Shop {tid}",
                    password_hash="x",
                    status=True,
                    is_open=True,
                    payment_mode="prepay",
                )
            )
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_order(self, *, tenant_id, created_at, status="settled"):
        order = Order(
            tenant_id=tenant_id,
            table_no="A1",
            status=status,
            payment_status="paid",
            payment_mode="prepay",
            total=28.0,
            created_at=created_at,
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    def test_invalid_date_str_is_none(self):
        self.assertIsNone(resolve_merchant_list_date("last7"))
        self.assertIsNone(resolve_merchant_list_date("2026-13-01"))
        self.assertIsNone(resolve_merchant_list_date("todayx"))

    def test_today_and_empty_are_live(self):
        live_empty = resolve_merchant_list_date(None)
        live_today = resolve_merchant_list_date("today")
        self.assertEqual(live_empty[0], "live")
        self.assertEqual(live_today[0], "live")
        self.assertEqual(live_empty[1:], live_today[1:])

    async def test_invalid_date_returns_400_not_unscoped(self):
        result = await list_orders(make_owner_request(), date_str="last7", db=self.db)
        self.assertEqual(result.code, 400)

    async def test_yesterday_excludes_other_days_and_other_tenant(self):
        mode, start, end = resolve_merchant_list_date("yesterday")
        self.assertEqual(mode, "day")
        in_window = start + timedelta(hours=2)
        other_day = start - timedelta(hours=2)
        await self._make_order(tenant_id=TENANT_A, created_at=in_window)
        await self._make_order(tenant_id=TENANT_A, created_at=other_day)
        await self._make_order(tenant_id=TENANT_B, created_at=in_window)

        result = await list_orders(make_owner_request(), date_str="yesterday", db=self.db)
        self.assertEqual(result.code, 200, result.msg)
        page = result.data
        self.assertIn("items", page)
        self.assertEqual(page["total"], 1)
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(page["page"], 1)

    async def test_iso_date_window(self):
        await self._make_order(tenant_id=TENANT_A, created_at=datetime(2026, 8, 20, 12, 0, 0))
        await self._make_order(tenant_id=TENANT_A, created_at=datetime(2026, 8, 19, 12, 0, 0))
        await self._make_order(tenant_id=TENANT_A, created_at=datetime(2026, 8, 21, 12, 0, 0))
        result = await list_orders(make_owner_request(), date_str="2026-08-20", db=self.db)
        self.assertEqual(result.code, 200)
        self.assertEqual(result.data["total"], 1)
        created = result.data["items"][0]["created_at"]
        self.assertTrue(created.startswith("2026-08-20") or "2026-08-20" in created or created.startswith("2026-08-19T16"))

    async def test_historical_forces_pagination(self):
        start = resolve_merchant_list_date("yesterday")[1]
        for i in range(3):
            await self._make_order(tenant_id=TENANT_A, created_at=start + timedelta(minutes=i))
        result = await list_orders(
            make_owner_request(), date_str="yesterday", page=1, page_size=2, db=self.db
        )
        self.assertEqual(result.data["total"], 3)
        self.assertEqual(len(result.data["items"]), 2)

    async def test_pagination_twenty_per_page(self):
        start = resolve_merchant_list_date("2026-08-20")[1]
        for i in range(105):
            self.db.add(
                Order(
                    tenant_id=TENANT_A,
                    table_no="A1",
                    status="settled",
                    payment_status="paid",
                    payment_mode="prepay",
                    total=10.0,
                    created_at=start + timedelta(minutes=i),
                )
            )
        await self.db.commit()
        first = await list_orders(
            make_owner_request(), date_str="2026-08-20", page=1, page_size=20, db=self.db
        )
        second = await list_orders(
            make_owner_request(), date_str="2026-08-20", page=2, page_size=20, db=self.db
        )
        self.assertEqual(first.data["total"], 105)
        self.assertEqual(len(first.data["items"]), 20)
        self.assertEqual(len(second.data["items"]), 20)
        self.assertNotEqual(first.data["items"][0]["id"], second.data["items"][0]["id"])

    async def test_page_size_capped_at_100(self):
        start = resolve_merchant_list_date("2026-08-20")[1]
        for i in range(12):
            self.db.add(
                Order(
                    tenant_id=TENANT_A,
                    table_no="A1",
                    status="settled",
                    payment_status="paid",
                    payment_mode="prepay",
                    total=10.0,
                    created_at=start + timedelta(minutes=i),
                )
            )
        await self.db.commit()
        result = await list_orders(
            make_owner_request(), date_str="2026-08-20", page=1, page_size=200, db=self.db
        )
        self.assertEqual(result.data["page_size"], 100)
        self.assertEqual(len(result.data["items"]), 12)
