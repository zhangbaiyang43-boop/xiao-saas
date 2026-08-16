"""P0-14: server final amount authority -- cross-tenant dish rejection and
coupon discount VALUE correctness.

Phase A audit found MONEY-12 (cross-tenant product IDs cannot influence
another tenant's order amount) and part of MONEY-04 (coupon discount is a
server computation) already PROVEN by direct code reading, but:
  - MONEY-12 only had a static source-text test asserting the tenant filter
    string appears in the query (test_order_amount_security_contracts.py:39)
    -- no test ever submitted a real cross-tenant dish_id through create_order.
  - P0-13's coupon tests set discount_amount as a DB fixture precondition and
    P0-02/coupon-tenant tests only assert a discount is non-None -- no test
    asserts the discount VALUE matches the expected server derivation from
    CouponTemplate.value for a concrete FIXED or PERCENT case.
This file closes both gaps with genuine runtime contracts. It does not
re-litigate P0-13's coupon lifecycle (locking/status transitions) or P0-02's
tampered-price/qty tests -- those are already covered elsewhere.
"""

import asyncio
import unittest
from datetime import datetime, timedelta

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.api.v1.orders import create_order, OrderCreate, OrderItemIn
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


def make_request():
    return Request(
        {
            "type": "http", "method": "POST", "path": "/api/v1/orders",
            "headers": [], "query_string": b"", "server": ("testserver", 80),
            "scheme": "http", "client": ("testclient", 50000),
        }
    )


def make_customer_request(customer_id):
    req = make_request()
    req.state.customer_id = customer_id
    return req


class CrossTenantDishOrderCreationTest(unittest.IsolatedAsyncioTestCase):
    """A07: tenant B submitting tenant A's dish_id cannot create an order,
    let alone one priced from tenant A's menu."""

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant_a = Tenant(tenant_id=TENANT_A, name="Restaurant A", password_hash="x", status=True, is_open=True, payment_mode="postpay")
        self.tenant_b = Tenant(tenant_id=TENANT_B, name="Restaurant B", password_hash="x", status=True, is_open=True, payment_mode="postpay")
        self.db.add_all([self.tenant_a, self.tenant_b])
        await self.db.flush()

        # Tenant A's dish is deliberately cheap-looking is irrelevant here --
        # the point is tenant B must never be able to reach it at all.
        self.dish_a = MenuItem(tenant_id=TENANT_A, name="Dish A", price="28.00", available=True)
        self.db.add(self.dish_a)
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _order_count(self):
        return len((await self.db.execute(select(Order))).scalars().all())

    async def test_A07_cross_tenant_dish_id_is_rejected_not_priced(self):
        body = OrderCreate(
            shop=TENANT_B, table="",
            items=[OrderItemIn(dish_id=self.dish_a.id, name="Dish A", price=28.00, qty=1)],
            total=28.00,
        )
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 400)
        self.assertIn("菜品不存在", result.msg or "")
        self.assertEqual(await self._order_count(), 0)


class CouponDiscountValueAuthorityTest(unittest.IsolatedAsyncioTestCase):
    """A08/A09: the discount amount actually applied matches the server-side
    derivation from CouponTemplate.value/type -- not just "some non-None
    discount landed", and not any client-suppliable value (OrderCreate has no
    discount_amount/coupon_amount field at all, confirmed statically by
    test_order_amount_security_contracts.py:test_client_total_discount_and_
    pay_amount_are_not_part_of_order_create_schema -- not duplicated here)."""

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(tenant_id=TENANT_A, name="Restaurant A", password_hash="x", status=True, is_open=True, payment_mode="postpay")
        self.customer = Customer(tenant_id=TENANT_A, openid="wx-openid-1")
        self.db.add_all([self.tenant, self.customer])
        await self.db.flush()

        # Priced at exactly 100.00 so the expected discount arithmetic is
        # trivial to state and verify by inspection.
        self.dish = MenuItem(tenant_id=TENANT_A, name="Set Meal", price="100.00", available=True)
        self.db.add(self.dish)

        now = datetime.utcnow()
        # cap_discount_amount's MAX_DISCOUNT_RATIO is 20% of order_total (see
        # app/core/platform_rules.py) -- both templates below are chosen well
        # under that 20.00 ceiling so this proves the raw value formula itself,
        # not the P0-13 cap (already covered elsewhere).
        self.template_fixed = CouponTemplate(
            tenant_id=TENANT_A, name="Fixed 15", type="FIXED", value=15, min_amount=0,
            total_stock=100, used_stock=0, start_time=now - timedelta(days=1), end_time=now + timedelta(days=30), status=1,
        )
        self.template_percent = CouponTemplate(
            tenant_id=TENANT_A, name="Percent 10", type="PERCENT", value=10, min_amount=0,
            total_stock=100, used_stock=0, start_time=now - timedelta(days=1), end_time=now + timedelta(days=30), status=1,
        )
        self.db.add_all([self.template_fixed, self.template_percent])
        await self.db.flush()

        self.coupon_fixed = Coupon(
            tenant_id=TENANT_A, template_id=self.template_fixed.id, customer_id=self.customer.id,
            code="FIXED15", verify_code="AAA111", status="UNUSED", expire_time=now + timedelta(days=30),
        )
        self.coupon_percent = Coupon(
            tenant_id=TENANT_A, template_id=self.template_percent.id, customer_id=self.customer.id,
            code="PCT10", verify_code="BBB111", status="UNUSED", expire_time=now + timedelta(days=30),
        )
        self.db.add_all([self.coupon_fixed, self.coupon_percent])
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _order_body(self, coupon_id):
        return OrderCreate(
            shop=TENANT_A, table="",
            items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=100.00, qty=1)],
            total=100.00, coupon_id=coupon_id,
        )

    async def test_A08_fixed_coupon_discount_matches_server_computed_value(self):
        result = await create_order(self._order_body(self.coupon_fixed.id), make_customer_request(self.customer.id), db=self.db)
        self.assertEqual(result.code, 200)
        self.assertEqual(result.data["discount_amount"], 15.0)
        self.assertEqual(result.data["total"], 85.0)

    async def test_A09_percent_coupon_discount_matches_server_computed_value(self):
        result = await create_order(self._order_body(self.coupon_percent.id), make_customer_request(self.customer.id), db=self.db)
        self.assertEqual(result.code, 200)
        # PERCENT: real_total(100) * value(10) / 100 = 10.00
        self.assertEqual(result.data["discount_amount"], 10.0)
        self.assertEqual(result.data["total"], 90.0)


if __name__ == "__main__":
    unittest.main()
