"""P1-01: logged-in member order list. Does not change GET /orders/my."""
from __future__ import annotations

import asyncio
import inspect
import unittest
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.member import list_member_orders
from app.api.v1.orders import get_my_order
from app.models.base import Base
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "p1-01-member-orders-a"
TENANT_B = "p1-01-member-orders-b"
CUSTOMER_A = 101
CUSTOMER_B = 202


def make_customer_request(tenant_id=TENANT_A, customer_id=CUSTOMER_A):
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/member/orders",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    if tenant_id is not None:
        request.state.tenant_id = tenant_id
    if customer_id is not None:
        request.state.customer_id = customer_id
    return request


class P1MemberOrderListTest(unittest.IsolatedAsyncioTestCase):
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

    async def _make_order(self, *, tenant_id, customer_id, created_at, qty=1, **overrides):
        values = dict(
            tenant_id=tenant_id,
            customer_id=customer_id,
            table_no="A1",
            status="pending",
            payment_status="paid",
            payment_mode="prepay",
            total=28.0,
            pickup_no="07",
            created_at=created_at,
        )
        values.update(overrides)
        order = Order(**values)
        self.db.add(order)
        await self.db.flush()
        self.db.add(
            OrderItem(id=generate_snowflake_id(), order_id=order.id, name="番茄炒蛋", price=18.0, qty=qty)
        )
        await self.db.commit()
        await self.db.refresh(order)
        return order

    def test_orders_my_contract_still_requires_order_id(self):
        params = inspect.signature(get_my_order).parameters
        self.assertIn("order_id", params)
        self.assertEqual(params["order_id"].kind, inspect.Parameter.POSITIONAL_OR_KEYWORD)

    async def test_unauthenticated_is_401(self):
        result = await list_member_orders(make_customer_request(None, None), skip=0, limit=20, db=self.db)
        self.assertEqual(result.code, 401)

    async def test_lists_only_own_tenant_and_customer_orders(self):
        newer = datetime.utcnow()
        older = newer - timedelta(hours=1)
        mine_new = await self._make_order(tenant_id=TENANT_A, customer_id=CUSTOMER_A, created_at=newer, qty=2)
        mine_old = await self._make_order(tenant_id=TENANT_A, customer_id=CUSTOMER_A, created_at=older, qty=1)
        await self._make_order(tenant_id=TENANT_A, customer_id=CUSTOMER_B, created_at=newer)
        await self._make_order(tenant_id=TENANT_B, customer_id=CUSTOMER_A, created_at=newer)
        await self._make_order(tenant_id=TENANT_A, customer_id=None, created_at=newer)

        result = await list_member_orders(make_customer_request(), skip=0, limit=20, db=self.db)
        self.assertEqual(result.code, 200, result.msg)
        page = result.data
        ids = [row["order_id"] for row in page["items"]]
        self.assertEqual(ids, [str(mine_new.id), str(mine_old.id)])
        self.assertEqual(page["total"], 2)
        self.assertNotIn("items", page["items"][0])
        self.assertEqual(page["items"][0]["dish_count"], 2)
        self.assertEqual(page["items"][0]["status_text"], "等待接单")
        self.assertEqual(page["items"][0]["pickup_no"], "07")
        self.assertIn("refund_required", page["items"][0])
        self.assertFalse(page["items"][0]["refund_required"])

    async def test_pagination(self):
        base = datetime.utcnow()
        created = []
        for index in range(3):
            created.append(
                await self._make_order(
                    tenant_id=TENANT_A,
                    customer_id=CUSTOMER_A,
                    created_at=base + timedelta(minutes=index),
                )
            )
        first = await list_member_orders(make_customer_request(), skip=0, limit=2, db=self.db)
        second = await list_member_orders(make_customer_request(), skip=2, limit=2, db=self.db)
        self.assertEqual(first.data["total"], 3)
        self.assertEqual(len(first.data["items"]), 2)
        self.assertEqual(len(second.data["items"]), 1)
        self.assertEqual(first.data["items"][0]["order_id"], str(created[2].id))
        self.assertEqual(second.data["items"][0]["order_id"], str(created[0].id))
