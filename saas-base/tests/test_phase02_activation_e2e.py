"""Phase 02 — Merchant Signup + Activation, closed-loop proof.

This exercises the real, unmocked API functions across the full chain the
Phase 02 audit's FIRST_ORDER_SUCCESS target describes:

    register (MerchantProvisioningService, SELF_REGISTER)
        -> add a dish (MenuItem, available)
        -> generate a table entrance code
        -> customer submits an order for that table (create_order)
        -> merchant's activation-status facts flip to activated

Deliberately in-process rather than through a live HTTP/browser session (see
Phase 02 report §38 for why: a real WeChat Pay JSAPI scan is not something
this environment can automate), but every call here is the real router/
service function -- create_order is the actual production order-creation
path, not a stub -- against a real (in-memory) database. The one thing NOT
exercised end-to-end is entrance-code QR *image* generation, which calls out
to the WeChat API (app/services/entrance_code_service.py::_generate_code_image)
and is unrelated to this phase's payment_mode change -- the EntranceCode row
itself (the thing table_registry_active() actually checks) is inserted
directly, exactly mirroring the existing convention in
tests/test_order_creation_idempotency.py.

The specific claim under test: a SELF_REGISTER-sourced tenant (payment_mode=
table_account, Phase 02's P0-01 fix) can complete a real order with ZERO
WeChat Pay configuration -- need_payment must be False and payment_mode must
never be "prepay" for this tenant.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.orders import OrderCreate, OrderItemIn, create_order
from app.api.v1.tenant import get_activation_status
from app.core.tenant_context import TenantContext
from app.models.base import Base
from app.models.dining import DiningParticipant, DiningSession
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import OrderItem
from app.models.subscription import Plan, Subscription
from app.services.merchant_provisioning_service import MerchantProvisioningService, ProvisioningSource
from app.services.tencent_sms_service import SmsPurpose, TencentSmsService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@event.listens_for(Plan, "before_insert")
def _assign_plan_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Subscription, "before_insert")
def _assign_subscription_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(MenuItem, "before_insert")
def _assign_menu_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_request(path="/api/v1/orders"):
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


class Phase02ActivationClosedLoopTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

    async def asyncTearDown(self):
        TenantContext.clear()
        await self.db.close()
        await self.engine.dispose()

    async def test_register_to_first_order_closed_loop_with_zero_wxpay_config(self):
        phone = "13600000001"

        # ---- Step 0: register (real OTP flow) ------------------------------
        await TencentSmsService().store_login_code(phone, "888888", purpose=SmsPurpose.REGISTER)
        self.assertTrue(
            await TencentSmsService().verify_login_code(phone, "888888", purpose=SmsPurpose.REGISTER)
        )
        result = await MerchantProvisioningService(self.db).provision_merchant(
            name="老王川菜馆", phone=phone, source=ProvisioningSource.SELF_REGISTER
        )
        tenant = result.tenant
        self.assertIsNotNone(result.subscription, "self-registration must grant a trial")
        # P0-01 fix: zero-config payment mode, never the WeChat-Pay-dependent default.
        self.assertEqual(tenant.payment_mode, "table_account")

        # ---- Activation-status before any dish/table/order: fully unactivated
        TenantContext.set_tenant_id(tenant.tenant_id)
        status_before = await get_activation_status(db=self.db)
        TenantContext.clear()
        self.assertFalse(status_before.data["activated"])
        self.assertFalse(status_before.data["has_dishes"])
        self.assertFalse(status_before.data["has_entrance_codes"])

        # ---- Step 1: add a dish (name + price only, per the Phase 02 audit's
        # confirmed minimum-fields finding) --------------------------------
        dish = MenuItem(tenant_id=tenant.tenant_id, name="宫保鸡丁", price=28, available=True)
        self.db.add(dish)
        await self.db.commit()
        await self.db.refresh(dish)

        # ---- Step 2: generate a table entrance code ------------------------
        # (QR *image* generation calls the WeChat API and is out of scope for
        # this test -- see module docstring. The row table_registry_active()
        # actually checks is what's inserted here.)
        self.db.add(
            EntranceCode(
                id=generate_snowflake_id(),
                tenant_id=tenant.tenant_id,
                name="A1号桌",
                channel="STORE",
                scene=f"E2E_{tenant.tenant_id[:8]}",
                table_no="A1",
                entry_type="table",
                status=1,
            )
        )
        await self.db.commit()

        TenantContext.set_tenant_id(tenant.tenant_id)
        status_mid = await get_activation_status(db=self.db)
        TenantContext.clear()
        self.assertTrue(status_mid.data["has_dishes"])
        self.assertTrue(status_mid.data["has_entrance_codes"])
        self.assertFalse(status_mid.data["activated"], "no order yet")

        # ---- Step 3: customer scans and submits a real order ----------------
        # table_account is session-based (multiple diners can share one
        # table's bill), so a real customer scan first opens a DiningSession
        # + DiningParticipant -- exactly what entrance_codes.py's resolve
        # flow creates. That part of the chain is unrelated to this phase's
        # payment_mode change, so it's set up directly here rather than
        # re-driving the WeChat-API-dependent QR resolve endpoint.
        now = datetime.utcnow()
        session = DiningSession(
            tenant_id=tenant.tenant_id, table_no="A1", status="OPEN",
            started_at=now, last_activity_at=now,
        )
        self.db.add(session)
        await self.db.flush()
        self.db.add(
            DiningParticipant(
                tenant_id=tenant.tenant_id, session_id=session.id,
                client_id="e2e-client-1", joined_at=now, last_active_at=now,
            )
        )
        await self.db.commit()

        order_body = OrderCreate(
            shop=tenant.tenant_id,
            table="A1",
            dining_session_id=session.id,
            client_id="e2e-client-1",
            items=[OrderItemIn(dish_id=dish.id, name=dish.name, price=28.0, qty=1)],
            total=28.0,
            request_id="e2e-first-order-1",
        )
        order_res = await create_order(order_body, make_request(), db=self.db)
        self.assertEqual(order_res.code, 200, order_res.msg)
        # The whole point of the P0-01 fix: this tenant never configured a
        # single WeChat Pay credential, and the order still doesn't need one.
        self.assertEqual(order_res.data["payment_mode"], "table_account")
        self.assertFalse(order_res.data["need_payment"])

        # ---- Step 4: merchant's admin sees the order -------------------------
        order_result = await self.db.execute(
            select(OrderItem).where(OrderItem.order_id == order_res.data["order_id"])
        )
        self.assertEqual(len(order_result.scalars().all()), 1)

        # ---- Step 5: activation-status flips to activated ---------------------
        TenantContext.set_tenant_id(tenant.tenant_id)
        status_after = await get_activation_status(db=self.db)
        TenantContext.clear()
        self.assertTrue(status_after.data["activated"])
        self.assertTrue(status_after.data["has_orders"])
        self.assertEqual(status_after.data["order_count"], 1)


if __name__ == "__main__":
    unittest.main()
