"""Phase R3: staff assisted add — permission, audit, prepay gate, domain reuse."""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime
from unittest.mock import patch

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.orders import OrderCreate, OrderItemIn, create_order
from app.core.merchant_auth import staff_route_allowed
from app.core.permissions import (
    PERM_ORDER_ASSISTED_ADD,
    ROLE_FRONTDESK,
    ROLE_KITCHEN,
    ROLE_OWNER,
    ROLE_WAITER,
    has_permission,
)
from app.models.base import Base
from app.models.dining import DiningSession
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.merchant_account import MerchantAccount
from app.models.merchant_account_trusted_device import MerchantAccountTrustedDevice  # noqa: F401
from app.models.merchant_account_wechat_binding import MerchantAccountWechatBinding  # noqa: F401
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.services.dining_session_service import DiningSessionService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT = "tenant-r3-a"
FAKE_HASH = "test-password-hash"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_request(*, role: str, account_id: int | None, tenant_id: str = TENANT):
    req = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/orders",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    req.state.token_type = "merchant"
    req.state.tenant_id = tenant_id
    req.state.role = role
    req.state.account_id = account_id
    req.state.customer_id = None
    return req


class PhaseR3PermissionTest(unittest.TestCase):
    def test_r3_assisted_add_matrix(self):
        self.assertTrue(has_permission(ROLE_OWNER, PERM_ORDER_ASSISTED_ADD))
        self.assertTrue(has_permission(ROLE_FRONTDESK, PERM_ORDER_ASSISTED_ADD))
        self.assertTrue(has_permission(ROLE_WAITER, PERM_ORDER_ASSISTED_ADD))
        self.assertFalse(has_permission(ROLE_KITCHEN, PERM_ORDER_ASSISTED_ADD))

    def test_r3_routes(self):
        self.assertTrue(staff_route_allowed("POST", "/api/v1/orders", ROLE_WAITER))
        self.assertTrue(staff_route_allowed("POST", "/api/v1/orders", ROLE_FRONTDESK))
        self.assertFalse(staff_route_allowed("POST", "/api/v1/orders", ROLE_KITCHEN))
        self.assertTrue(staff_route_allowed("GET", "/api/v1/menu/items", ROLE_WAITER))
        self.assertTrue(staff_route_allowed("GET", "/api/v1/dining-sessions/active", ROLE_FRONTDESK))
        self.assertFalse(staff_route_allowed("GET", "/api/v1/dining-sessions/active", ROLE_KITCHEN))


class PhaseR3AssistedAddServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.waiter_id = generate_snowflake_id()
        self.frontdesk_id = generate_snowflake_id()
        self.session_id = generate_snowflake_id()
        self.parent_order_id = generate_snowflake_id()
        self.dish_id = generate_snowflake_id()
        async with self.SessionLocal() as db:
            db.add_all(
                [
                    Tenant(
                        tenant_id=TENANT,
                        name="R3店",
                        password_hash="x",
                        phone="13900005555",
                        status=True,
                        is_open=True,
                        payment_mode="postpay",
                    ),
                    MerchantAccount(
                        id=self.waiter_id,
                        tenant_id=TENANT,
                        name="服务员A",
                        username="wa3",
                        password_hash=FAKE_HASH,
                        role="waiter",
                        status="active",
                    ),
                    MerchantAccount(
                        id=self.frontdesk_id,
                        tenant_id=TENANT,
                        name="前台A",
                        username="fd3",
                        password_hash=FAKE_HASH,
                        role="frontdesk",
                        status="active",
                    ),
                    DiningSession(
                        id=self.session_id,
                        tenant_id=TENANT,
                        table_no="12",
                        status="OPEN",
                        active_key=f"{TENANT}:12",
                        pickup_no="07",
                        started_at=datetime.utcnow(),
                        last_activity_at=datetime.utcnow(),
                    ),
                    Order(
                        id=self.parent_order_id,
                        tenant_id=TENANT,
                        dining_session_id=self.session_id,
                        table_no="12",
                        total=30,
                        status="pending",
                        payment_status="unpaid",
                        payment_mode="postpay",
                        order_type="INITIAL",
                        source="miniprogram",
                        pickup_no="07",
                    ),
                    MenuItem(
                        id=self.dish_id,
                        tenant_id=TENANT,
                        name="炒青菜",
                        price="12.00",
                        available=True,
                        category="热菜",
                    ),
                    # P0-01: this suite is about staff-assisted add-on permissions/
                    # idempotency, not table validity -- register both tables it
                    # uses. "99" (test_r3_no_open_session) intentionally has no
                    # OPEN session but must still be a *registered* table, so that
                    # test keeps exercising "no open session" rather than tripping
                    # the new table-authority check first.
                    EntranceCode(
                        id=generate_snowflake_id(),
                        tenant_id=TENANT, name="12", scene="E00000000112",
                        table_no="12", entry_type="table", status=1,
                    ),
                    EntranceCode(
                        id=generate_snowflake_id(),
                        tenant_id=TENANT, name="99", scene="E00000000199",
                        table_no="99", entry_type="table", status=1,
                    ),
                ]
            )
            await db.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    def _body(self, *, request_id=None, price=12.0, table="12", session_id=None):
        return OrderCreate(
            shop=TENANT,
            table=table,
            dining_session_id=session_id if session_id is not None else self.session_id,
            items=[OrderItemIn(dish_id=self.dish_id, name="炒青菜", price=price, qty=1)],
            total=price,
            request_id=request_id,
        )

    async def test_r3_waiter_assisted_add_audit(self):
        async with self.SessionLocal() as db:
            req = make_request(role="waiter", account_id=self.waiter_id)
            with patch("app.api.v1.orders._spawn_background_print_task"):
                res = await create_order(self._body(request_id="r3-wa-1"), req, db)
            self.assertEqual(res.code, 200)
            result = await db.execute(
                select(Order).where(Order.client_request_id == "r3-wa-1")
            )
            order = result.scalar_one()
            self.assertEqual(order.source, "staff")
            self.assertEqual(order.created_by_account_id, self.waiter_id)
            self.assertEqual(order.created_by_role, "waiter")
            self.assertEqual(order.status, "pending")
            self.assertEqual(order.payment_status, "unpaid")
            self.assertEqual(order.dining_session_id, self.session_id)
            self.assertEqual(order.order_type, "ADD_ON")
            self.assertEqual(order.parent_order_id, self.parent_order_id)

    async def test_r3_role_snapshot_survives_role_change(self):
        async with self.SessionLocal() as db:
            req = make_request(role="waiter", account_id=self.waiter_id)
            with patch("app.api.v1.orders._spawn_background_print_task"):
                res = await create_order(self._body(request_id="r3-snap-1"), req, db)
            self.assertEqual(res.code, 200)
            account = (
                await db.execute(select(MerchantAccount).where(MerchantAccount.id == self.waiter_id))
            ).scalar_one()
            account.role = "frontdesk"
            await db.commit()
            order = (
                await db.execute(select(Order).where(Order.client_request_id == "r3-snap-1"))
            ).scalar_one()
            self.assertEqual(order.created_by_role, "waiter")

    async def test_r3_price_from_backend(self):
        async with self.SessionLocal() as db:
            req = make_request(role="frontdesk", account_id=self.frontdesk_id)
            with patch("app.api.v1.orders._spawn_background_print_task"):
                res = await create_order(self._body(request_id="r3-price", price=0.01), req, db)
            self.assertEqual(res.code, 200)
            order = (
                await db.execute(select(Order).where(Order.client_request_id == "r3-price"))
            ).scalar_one()
            self.assertEqual(float(order.total), 12.0)

    async def test_r3_idempotency(self):
        async with self.SessionLocal() as db:
            req = make_request(role="waiter", account_id=self.waiter_id)
            with patch("app.api.v1.orders._spawn_background_print_task"):
                r1 = await create_order(self._body(request_id="r3-idem"), req, db)
                r2 = await create_order(self._body(request_id="r3-idem"), req, db)
            self.assertEqual(r1.code, 200)
            self.assertEqual(r2.code, 200)
            count = (
                await db.execute(
                    select(func.count()).select_from(Order).where(Order.client_request_id == "r3-idem")
                )
            ).scalar_one()
            self.assertEqual(count, 1)

    async def test_r3_no_open_session(self):
        async with self.SessionLocal() as db:
            req = make_request(role="waiter", account_id=self.waiter_id)
            body = self._body(request_id="r3-empty", table="99", session_id=None)
            body.dining_session_id = None
            res = await create_order(body, req, db)
            self.assertEqual(res.code, 400)
            self.assertIn("没有进行中", res.msg or "")

    async def test_r3_prepay_creates_staff_assisted_pending_payment_order(self):
        async with self.SessionLocal() as db:
            tenant = (await db.execute(select(Tenant).where(Tenant.tenant_id == TENANT))).scalar_one()
            tenant.payment_mode = "prepay"
            await db.commit()
            req = make_request(role="waiter", account_id=self.waiter_id)
            with patch("app.api.v1.orders._spawn_background_print_task") as spawn_print:
                res = await create_order(self._body(request_id="r3-prepay"), req, db)
            self.assertEqual(res.code, 200)
            order = (
                await db.execute(select(Order).where(Order.client_request_id == "r3-prepay"))
            ).scalar_one()
            self.assertEqual(order.source, "staff_assisted")
            self.assertEqual(order.status, "pending_payment")
            self.assertEqual(order.payment_status, "unpaid")
            self.assertIsNone(order.customer_id)
            self.assertIsNone(order.participant_id)
            self.assertEqual(order.created_by_account_id, self.waiter_id)
            self.assertEqual(order.created_by_role, "waiter")
            spawn_print.assert_not_called()

    async def test_r3_list_active_sessions(self):
        async with self.SessionLocal() as db:
            rows = await DiningSessionService(db).list_active_sessions_for_staff(TENANT)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["table_no"], "12")
            self.assertEqual(rows[0]["pickup_no"], "07")


if __name__ == "__main__":
    unittest.main()
