"""Phase 02 — Activation Home facts endpoint.

GET /api/v1/tenant/activation-status is pure read-only facts for the
frontend's Activation Home to render -- no persisted onboarding/progress
state, no step numbers, no onboarding_completed-style field that could trap
an existing tenant under a false default. `activated` is exactly
`has_orders`; `has_dishes` only counts AVAILABLE dishes (an off-shelf dish
can't actually be ordered); `has_entrance_codes` only counts active
TABLE-channel codes (a channel/staff-share code doesn't let a customer reach
the ordering flow).
"""

from __future__ import annotations

import asyncio
import unittest

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.tenant import get_activation_status
from app.core.tenant_context import TenantContext
from app.models.base import Base
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import Order
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
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


@event.listens_for(EntranceCode, "before_insert")
def _assign_entrance_code_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Order, "before_insert")
def _assign_order_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


TENANT_A = "tenant-activation-a"


class TenantActivationStatusTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add(Tenant(tenant_id=TENANT_A, name="T", password_hash="x", status=True))
        await self.db.commit()

    async def asyncTearDown(self):
        TenantContext.clear()
        await self.db.close()
        await self.engine.dispose()

    async def _call(self):
        TenantContext.set_tenant_id(TENANT_A)
        try:
            res = await get_activation_status(db=self.db)
        finally:
            TenantContext.clear()
        return res

    async def test_zero_data_tenant_is_fully_unactivated(self):
        res = await self._call()
        self.assertEqual(res.code, 200)
        self.assertEqual(
            res.data,
            {
                "has_dishes": False,
                "has_entrance_codes": False,
                "has_orders": False,
                "activated": False,
                "dish_count": 0,
                "entrance_code_count": 0,
                "order_count": 0,
            },
        )

    async def test_unavailable_dish_does_not_count_as_has_dishes(self):
        self.db.add(MenuItem(tenant_id=TENANT_A, name="下架菜", price=10, available=False))
        await self.db.commit()
        res = await self._call()
        self.assertFalse(res.data["has_dishes"])
        self.assertEqual(res.data["dish_count"], 0)

    async def test_available_dish_counts_as_has_dishes(self):
        self.db.add(MenuItem(tenant_id=TENANT_A, name="宫保鸡丁", price=28, available=True))
        await self.db.commit()
        res = await self._call()
        self.assertTrue(res.data["has_dishes"])
        self.assertEqual(res.data["dish_count"], 1)

    async def test_non_table_entrance_code_does_not_count(self):
        self.db.add(
            EntranceCode(tenant_id=TENANT_A, name="渠道码", channel="CHANNEL", scene="s1", entry_type="staff_share", status=1)
        )
        await self.db.commit()
        res = await self._call()
        self.assertFalse(res.data["has_entrance_codes"])

    async def test_inactive_table_entrance_code_does_not_count(self):
        self.db.add(
            EntranceCode(tenant_id=TENANT_A, name="1号桌", channel="STORE", scene="s2", entry_type="table", status=0)
        )
        await self.db.commit()
        res = await self._call()
        self.assertFalse(res.data["has_entrance_codes"])

    async def test_active_table_entrance_code_counts(self):
        self.db.add(
            EntranceCode(tenant_id=TENANT_A, name="1号桌", channel="STORE", scene="s3", entry_type="table", status=1)
        )
        await self.db.commit()
        res = await self._call()
        self.assertTrue(res.data["has_entrance_codes"])
        self.assertEqual(res.data["entrance_code_count"], 1)

    async def test_order_marks_activated_regardless_of_dish_or_code_state(self):
        # activated == has_orders, independent of the other two facts --
        # an order could exist even if the dish/code that produced it was
        # since deleted/disabled.
        self.db.add(Order(tenant_id=TENANT_A, status="pending", total=10))
        await self.db.commit()
        res = await self._call()
        self.assertTrue(res.data["has_orders"])
        self.assertTrue(res.data["activated"])
        self.assertEqual(res.data["order_count"], 1)

    async def test_dishes_and_codes_without_orders_is_not_activated(self):
        self.db.add(MenuItem(tenant_id=TENANT_A, name="宫保鸡丁", price=28, available=True))
        self.db.add(
            EntranceCode(tenant_id=TENANT_A, name="1号桌", channel="STORE", scene="s4", entry_type="table", status=1)
        )
        await self.db.commit()
        res = await self._call()
        self.assertTrue(res.data["has_dishes"])
        self.assertTrue(res.data["has_entrance_codes"])
        self.assertFalse(res.data["has_orders"])
        self.assertFalse(res.data["activated"])

    async def test_no_persisted_onboarding_step_fields_in_response(self):
        # Contract guard (Phase 02 §10): backend returns only facts, never
        # step/progress/wizard-shaped fields -- the frontend decides how to
        # present them.
        res = await self._call()
        for forbidden in ("onboarding_step", "wizard_step", "progress_percent"):
            self.assertNotIn(forbidden, res.data)


if __name__ == "__main__":
    unittest.main()
