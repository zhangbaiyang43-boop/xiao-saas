"""Phase R2: Waiter order.serve + WAITING_TO_SERVE workbench contracts."""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.merchant_auth import staff_route_allowed
from app.core.permissions import (
    ROLE_FRONTDESK,
    ROLE_KITCHEN,
    ROLE_OWNER,
    ROLE_WAITER,
    has_permission,
)
from app.core.security import create_access_token
from app.models.base import Base
from app.models.merchant_account import MerchantAccount
from app.models.merchant_account_trusted_device import MerchantAccountTrustedDevice  # noqa: F401
from app.models.merchant_account_wechat_binding import MerchantAccountWechatBinding  # noqa: F401
from app.models.order import Order, OrderItem  # noqa: F401
from app.models.tenant import Tenant
from app.services.order_lifecycle_service import OrderLifecycleService
from app.services.workbench_sync_service import is_order_visible_in_workbench, is_waiting_to_serve
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT = "tenant-r2-a"
TENANT_B = "tenant-r2-b"
FAKE_HASH = "test-password-hash-not-used-for-verify"


class PhaseR2ServeUnitTest(unittest.TestCase):
    def test_r2_permissions(self):
        self.assertTrue(has_permission(ROLE_WAITER, "order.serve"))
        self.assertFalse(has_permission(ROLE_FRONTDESK, "order.serve"))
        self.assertFalse(has_permission(ROLE_KITCHEN, "order.serve"))
        self.assertTrue(has_permission(ROLE_OWNER, "order.serve"))
        self.assertTrue(staff_route_allowed("POST", "/api/v1/orders/1/serve", ROLE_WAITER))
        self.assertFalse(staff_route_allowed("POST", "/api/v1/orders/1/serve", ROLE_FRONTDESK))
        self.assertFalse(staff_route_allowed("POST", "/api/v1/orders/1/serve", ROLE_KITCHEN))
        self.assertTrue(staff_route_allowed("GET", "/api/v1/orders/workbench/recent-served-by-me", ROLE_WAITER))
        self.assertFalse(staff_route_allowed("GET", "/api/v1/orders/workbench/recent-served-by-me", ROLE_FRONTDESK))
        self.assertFalse(staff_route_allowed("GET", "/api/v1/orders/workbench/recent-served-by-me", ROLE_KITCHEN))

    def test_r2_visibility(self):
        self.assertFalse(is_waiting_to_serve(SimpleNamespace(status="pending", served_at=None)))
        self.assertFalse(is_waiting_to_serve(SimpleNamespace(status="preparing", served_at=None)))
        self.assertTrue(is_waiting_to_serve(SimpleNamespace(status="done", served_at=None)))
        self.assertFalse(is_waiting_to_serve(SimpleNamespace(status="done", served_at=datetime.utcnow())))
        self.assertTrue(is_order_visible_in_workbench(SimpleNamespace(status="done", served_at=None), "waiter"))
        self.assertFalse(is_order_visible_in_workbench(SimpleNamespace(status="pending", served_at=None), "waiter"))


class PhaseR2ServeServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.waiter_id = generate_snowflake_id()
        self.waiter_b_id = generate_snowflake_id()
        self.order_id = generate_snowflake_id()
        async with self.SessionLocal() as db:
            db.add_all(
                [
                    Tenant(
                        tenant_id=TENANT,
                        name="R2店",
                        password_hash="x",
                        phone="13900004444",
                        status=True,
                        is_open=True,
                    ),
                    MerchantAccount(
                        id=self.waiter_id,
                        tenant_id=TENANT,
                        name="服务员A",
                        username="wa",
                        password_hash=FAKE_HASH,
                        role="waiter",
                        status="active",
                    ),
                    MerchantAccount(
                        id=self.waiter_b_id,
                        tenant_id=TENANT,
                        name="服务员B",
                        username="wb",
                        password_hash=FAKE_HASH,
                        role="waiter",
                        status="active",
                    ),
                    Order(
                        id=self.order_id,
                        tenant_id=TENANT,
                        table_no="A1",
                        total=20,
                        status="done",
                        payment_status="unpaid",
                        payment_mode="postpay",
                        print_status="FAILED",
                        pickup_no=None,
                    ),
                ]
            )
            await db.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_r2_05_06_state_gate(self):
        async with self.SessionLocal() as db:
            from sqlalchemy import select

            order = (
                await db.execute(select(Order).where(Order.id == self.order_id))
            ).scalar_one()
            order.status = "pending"
            await db.commit()
            svc = OrderLifecycleService(db)
            svc.set_tenant_id(TENANT)
            r = await svc.serve_order(self.order_id, account_id=self.waiter_id, role="waiter")
            self.assertEqual(r.code, 409)

            order.status = "preparing"
            await db.commit()
            r = await svc.serve_order(self.order_id, account_id=self.waiter_id, role="waiter")
            self.assertEqual(r.code, 409)

    async def test_r2_07_16_serve_idempotent_audit(self):
        async with self.SessionLocal() as db:
            from sqlalchemy import select

            svc = OrderLifecycleService(db)
            svc.set_tenant_id(TENANT)
            with patch(
                "app.services.order_lifecycle_service._print_paid_order_ticket",
                new_callable=AsyncMock,
                create=True,
            ):
                r1 = await svc.serve_order(self.order_id, account_id=self.waiter_id, role="waiter")
            self.assertEqual(r1.code, 200)
            self.assertFalse(r1.data.get("idempotent"))
            order = (
                await db.execute(select(Order).where(Order.id == self.order_id))
            ).scalar_one()
            self.assertEqual(order.status, "done")
            self.assertIsNotNone(order.served_at)
            self.assertEqual(int(order.served_by_account_id), self.waiter_id)
            self.assertEqual(order.served_by_role, "waiter")
            first_served_at = order.served_at

            r2 = await svc.serve_order(self.order_id, account_id=self.waiter_b_id, role="waiter")
            self.assertEqual(r2.code, 200)
            self.assertTrue(r2.data.get("idempotent"))
            await db.refresh(order)
            self.assertEqual(int(order.served_by_account_id), self.waiter_id)
            self.assertEqual(order.served_at, first_served_at)

    async def test_r2_09_11_payment_print_pickup_independent(self):
        async with self.SessionLocal() as db:
            from sqlalchemy import select

            order = (
                await db.execute(select(Order).where(Order.id == self.order_id))
            ).scalar_one()
            self.assertEqual(order.payment_status, "unpaid")
            self.assertEqual(order.print_status, "FAILED")
            self.assertIsNone(order.pickup_no)
            svc = OrderLifecycleService(db)
            svc.set_tenant_id(TENANT)
            r = await svc.serve_order(self.order_id, account_id=self.waiter_id, role="waiter")
            self.assertEqual(r.code, 200)
            await db.refresh(order)
            self.assertEqual(order.payment_status, "unpaid")
            self.assertEqual(order.print_status, "FAILED")
            self.assertEqual(order.status, "done")

    async def test_r2_kitchen_complete_does_not_auto_serve(self):
        async with self.SessionLocal() as db:
            oid = generate_snowflake_id()
            db.add(
                Order(
                    id=oid,
                    tenant_id=TENANT,
                    table_no="B1",
                    total=10,
                    status="preparing",
                    payment_status="paid",
                    payment_mode="prepay",
                )
            )
            await db.commit()
            svc = OrderLifecycleService(db)
            svc.set_tenant_id(TENANT)
            from app.api.v1.orders import OrderStatusUpdate

            r = await svc.update_order_status(oid, OrderStatusUpdate(status="done"))
            self.assertEqual(r.code, 200)
            from sqlalchemy import select

            order = (await db.execute(select(Order).where(Order.id == oid))).scalar_one()
            self.assertEqual(order.status, "done")
            self.assertIsNone(order.served_at)
            self.assertTrue(is_waiting_to_serve(order))


class PhaseR2ServeHttpTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.waiter_id = generate_snowflake_id()
        self.waiter_b_id = generate_snowflake_id()
        self.frontdesk_id = generate_snowflake_id()
        self.kitchen_id = generate_snowflake_id()
        self.order_id = generate_snowflake_id()
        self.recent_old_id = generate_snowflake_id()
        self.recent_new_id = generate_snowflake_id()
        self.other_waiter_order_id = generate_snowflake_id()
        self.auto_served_order_id = generate_snowflake_id()
        self.tenant_b_order_id = generate_snowflake_id()
        now = datetime.utcnow()
        async with self.SessionLocal() as db:
            db.add_all(
                [
                    Tenant(
                        tenant_id=TENANT,
                        name="R2 HTTP",
                        password_hash="x",
                        phone="13900005555",
                        status=True,
                        is_open=True,
                    ),
                    Tenant(
                        tenant_id=TENANT_B,
                        name="R2 HTTP B",
                        password_hash="x",
                        phone="13900006666",
                        status=True,
                        is_open=True,
                    ),
                    MerchantAccount(
                        id=self.waiter_id,
                        tenant_id=TENANT,
                        name="W",
                        username="w2",
                        password_hash=FAKE_HASH,
                        role="waiter",
                        status="active",
                    ),
                    MerchantAccount(
                        id=self.waiter_b_id,
                        tenant_id=TENANT,
                        name="WB",
                        username="wb2",
                        password_hash=FAKE_HASH,
                        role="waiter",
                        status="active",
                    ),
                    MerchantAccount(
                        id=self.frontdesk_id,
                        tenant_id=TENANT,
                        name="F",
                        username="f2",
                        password_hash=FAKE_HASH,
                        role="frontdesk",
                        status="active",
                    ),
                    MerchantAccount(
                        id=self.kitchen_id,
                        tenant_id=TENANT,
                        name="K",
                        username="k2",
                        password_hash=FAKE_HASH,
                        role="kitchen",
                        status="active",
                    ),
                    Order(
                        id=self.order_id,
                        tenant_id=TENANT,
                        table_no="T9",
                        total=18,
                        status="done",
                        payment_status="unpaid",
                        payment_mode="table_account",
                        print_status="UNKNOWN",
                    ),
                    Order(
                        id=self.recent_old_id,
                        tenant_id=TENANT,
                        table_no="01",
                        total=18,
                        status="done",
                        payment_status="unpaid",
                        payment_mode="table_account",
                        pickup_no="01",
                        served_at=now - timedelta(minutes=5),
                        served_by_account_id=self.waiter_id,
                        served_by_role="waiter",
                    ),
                    Order(
                        id=self.recent_new_id,
                        tenant_id=TENANT,
                        table_no="30",
                        total=26,
                        status="done",
                        payment_status="unpaid",
                        payment_mode="table_account",
                        pickup_no="30",
                        served_at=now,
                        served_by_account_id=self.waiter_id,
                        served_by_role="waiter",
                    ),
                    Order(
                        id=self.other_waiter_order_id,
                        tenant_id=TENANT,
                        table_no="02",
                        total=12,
                        status="done",
                        payment_status="unpaid",
                        payment_mode="table_account",
                        pickup_no="02",
                        served_at=now - timedelta(minutes=1),
                        served_by_account_id=self.waiter_b_id,
                        served_by_role="waiter",
                    ),
                    Order(
                        id=self.auto_served_order_id,
                        tenant_id=TENANT,
                        table_no="03",
                        total=12,
                        status="done",
                        payment_status="unpaid",
                        payment_mode="table_account",
                        pickup_no="03",
                        served_at=now - timedelta(minutes=2),
                        served_by_account_id=None,
                        served_by_role=None,
                    ),
                    Order(
                        id=self.tenant_b_order_id,
                        tenant_id=TENANT_B,
                        table_no="99",
                        total=12,
                        status="done",
                        payment_status="unpaid",
                        payment_mode="table_account",
                        pickup_no="99",
                        served_at=now - timedelta(minutes=3),
                        served_by_account_id=self.waiter_id,
                        served_by_role="waiter",
                    ),
                    OrderItem(
                        id=generate_snowflake_id(),
                        order_id=self.recent_old_id,
                        name="牛肉汤",
                        price=18,
                        qty=1,
                    ),
                    OrderItem(
                        id=generate_snowflake_id(),
                        order_id=self.recent_new_id,
                        name="牛肉汤",
                        price=18,
                        qty=1,
                    ),
                    OrderItem(
                        id=generate_snowflake_id(),
                        order_id=self.recent_new_id,
                        name="烧饼",
                        price=4,
                        qty=2,
                    ),
                    OrderItem(
                        id=generate_snowflake_id(),
                        order_id=self.other_waiter_order_id,
                        name="羊肉汤",
                        price=12,
                        qty=1,
                    ),
                ]
            )
            await db.commit()

        from app.main import app

        self.app = app
        self._session_patch = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._session_patch.start()
        self._cache_get = patch(
            "app.core.cache_helper.get_cache", new_callable=AsyncMock, return_value=None
        )
        self._cache_set = patch(
            "app.core.cache_helper.set_cache", new_callable=AsyncMock, return_value=None
        )
        self._cache_get.start()
        self._cache_set.start()
        import httpx

        transport = httpx.ASGITransport(app=self.app)
        self.client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        self._session_patch.stop()
        self._cache_get.stop()
        self._cache_set.stop()
        await self.engine.dispose()

    def _auth(self, role: str, account_id: int) -> dict:
        token = create_access_token(TENANT, role=role, account_id=account_id)
        return {"Authorization": f"Bearer {token}"}

    async def test_r2_http_role_gates(self):
        r = await self.client.post(
            f"/api/v1/orders/{self.order_id}/serve",
            headers=self._auth("frontdesk", self.frontdesk_id),
        )
        self.assertEqual(r.status_code, 403)
        r = await self.client.post(
            f"/api/v1/orders/{self.order_id}/serve",
            headers=self._auth("kitchen", self.kitchen_id),
        )
        self.assertEqual(r.status_code, 403)
        r = await self.client.post(
            f"/api/v1/orders/{self.order_id}/serve",
            headers=self._auth("waiter", self.waiter_id),
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body.get("code"), 200)

    async def test_r2_waiter_workbench_only_unserved_done(self):
        h = self._auth("waiter", self.waiter_id)
        r = await self.client.get("/api/v1/orders/workbench", headers=h)
        self.assertEqual(r.status_code, 200)
        rows = r.json().get("data") or []
        ids = {str(x.get("id")) for x in rows}
        self.assertIn(str(self.order_id), ids)

    async def test_p0_waiter_recent_served_by_me_filters_account_tenant_and_auto_served(self):
        h = self._auth("waiter", self.waiter_id)
        r = await self.client.get("/api/v1/orders/workbench/recent-served-by-me", headers=h)
        self.assertEqual(r.status_code, 200)
        rows = r.json().get("data") or []
        ids = [str(x.get("order_id")) for x in rows]
        self.assertEqual(ids[:2], [str(self.recent_new_id), str(self.recent_old_id)])
        self.assertNotIn(str(self.other_waiter_order_id), ids)
        self.assertNotIn(str(self.auto_served_order_id), ids)
        self.assertNotIn(str(self.tenant_b_order_id), ids)
        first = rows[0]
        self.assertEqual(first["table_no"], "30")
        self.assertEqual(first["pickup_no"], "30")
        self.assertEqual(first["items"][0], {"name": "牛肉汤", "qty": 1})
        self.assertEqual(first["items"][1], {"name": "烧饼", "qty": 2})
        for forbidden in ("total", "payment_status", "phone", "customer_id", "coupon_id", "openid"):
            self.assertNotIn(forbidden, first)

    async def test_p0_waiter_recent_served_by_me_limit_latest_first(self):
        h = self._auth("waiter", self.waiter_id)
        r = await self.client.get("/api/v1/orders/workbench/recent-served-by-me?limit=1", headers=h)
        self.assertEqual(r.status_code, 200)
        rows = r.json().get("data") or []
        self.assertEqual([str(x.get("order_id")) for x in rows], [str(self.recent_new_id)])


if __name__ == "__main__":
    unittest.main()
