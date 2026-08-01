import asyncio
import unittest
from datetime import datetime, timedelta

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.config import settings
from app.models.base import Base
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.models.menu_item import MenuItem
from app.models.order import OrderItem
from app.models.tenant import Tenant
from app.api.v1.orders import create_order, OrderCreate, OrderItemIn
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_request(customer_id):
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
    req.state.customer_id = customer_id
    return req


class CouponTenantSecurityTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._original_redis_enabled = settings.REDIS_ENABLED
        settings.REDIS_ENABLED = False

        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant_a = Tenant(tenant_id=TENANT_A, name="Restaurant A", password_hash="x", status=True, is_open=True, payment_mode="postpay")
        self.tenant_b = Tenant(tenant_id=TENANT_B, name="Restaurant B", password_hash="x", status=True, is_open=True, payment_mode="postpay")
        self.db.add_all([self.tenant_a, self.tenant_b])
        await self.db.flush()

        self.dish_a = MenuItem(tenant_id=TENANT_A, name="Dish A", price="50.00", available=True)
        self.dish_b = MenuItem(tenant_id=TENANT_B, name="Dish B", price="50.00", available=True)
        self.db.add_all([self.dish_a, self.dish_b])
        await self.db.flush()

        self.customer_a1 = Customer(tenant_id=TENANT_A, openid="a1")
        self.customer_b1 = Customer(tenant_id=TENANT_B, openid="b1")
        self.db.add_all([self.customer_a1, self.customer_b1])
        await self.db.flush()

        now = datetime.utcnow()
        self.template_a = CouponTemplate(
            tenant_id=TENANT_A, name="A Coupon", type="FIXED", value=10, min_amount=0,
            total_stock=100, used_stock=0, start_time=now - timedelta(days=1), end_time=now + timedelta(days=30), status=1,
        )
        self.template_b = CouponTemplate(
            tenant_id=TENANT_B, name="B Coupon", type="FIXED", value=10, min_amount=0,
            total_stock=100, used_stock=0, start_time=now - timedelta(days=1), end_time=now + timedelta(days=30), status=1,
        )
        self.db.add_all([self.template_a, self.template_b])
        await self.db.flush()

        # CA1: customer A1's own coupon, template belongs to tenant A
        self.coupon_a1 = Coupon(
            tenant_id=TENANT_A, template_id=self.template_a.id, customer_id=self.customer_a1.id,
            code="CODEA1", verify_code="AAA111", status="UNUSED", expire_time=now + timedelta(days=30),
        )
        # CB1: customer B1's coupon, template belongs to tenant B
        self.coupon_b1 = Coupon(
            tenant_id=TENANT_B, template_id=self.template_b.id, customer_id=self.customer_b1.id,
            code="CODEB1", verify_code="BBB111", status="UNUSED", expire_time=now + timedelta(days=30),
        )
        self.db.add_all([self.coupon_a1, self.coupon_b1])
        await self.db.commit()

    async def asyncTearDown(self):
        settings.REDIS_ENABLED = self._original_redis_enabled
        await self.db.close()
        await self.engine.dispose()

    def _order_body(self, shop, dish, coupon_id=None):
        return OrderCreate(
            shop=shop, table="A1",
            items=[OrderItemIn(dish_id=dish.id, name=dish.name, price=float(dish.price), qty=1)],
            total=float(dish.price), coupon_id=coupon_id,
        )

    async def test_customer_can_use_their_own_coupon(self):
        result = await create_order(
            self._order_body(TENANT_A, self.dish_a, self.coupon_a1.id), make_request(self.customer_a1.id), db=self.db,
        )
        self.assertEqual(result.code, 200)
        self.assertIsNotNone(result.data["discount_amount"])
        await self.db.refresh(self.coupon_a1)
        self.assertEqual(self.coupon_a1.status, "LOCKED")

    async def test_customer_cannot_use_a_coupon_from_another_tenant(self):
        # A1 orders at tenant A, but tries to use a coupon that belongs to tenant B
        result = await create_order(
            self._order_body(TENANT_A, self.dish_a, self.coupon_b1.id), make_request(self.customer_a1.id), db=self.db,
        )
        self.assertEqual(result.code, 400)
        await self.db.refresh(self.coupon_b1)
        self.assertEqual(self.coupon_b1.status, "UNUSED")  # untouched

    async def test_customer_cannot_use_another_customers_coupon(self):
        # B1 tries to order at tenant A using A1's own coupon
        result = await create_order(
            self._order_body(TENANT_A, self.dish_a, self.coupon_a1.id), make_request(self.customer_b1.id), db=self.db,
        )
        self.assertEqual(result.code, 400)
        await self.db.refresh(self.coupon_a1)
        self.assertEqual(self.coupon_a1.status, "UNUSED")  # untouched

    async def test_used_coupon_cannot_be_locked_again(self):
        first = await create_order(
            self._order_body(TENANT_A, self.dish_a, self.coupon_a1.id), make_request(self.customer_a1.id), db=self.db,
        )
        self.assertEqual(first.code, 200)

        # Same coupon, second (independent) order-creation attempt — the coupon is
        # already LOCKED by the first order, so this must be rejected, proving the
        # `.with_for_update()` + `status == "UNUSED"` filter in create_order actually
        # prevents the same coupon from being locked onto two different orders.
        second = await create_order(
            self._order_body(TENANT_A, self.dish_a, self.coupon_a1.id), make_request(self.customer_a1.id), db=self.db,
        )
        self.assertEqual(second.code, 400)

    async def test_expired_coupon_is_rejected(self):
        self.coupon_a1.expire_time = datetime.utcnow() - timedelta(days=1)
        await self.db.commit()

        result = await create_order(
            self._order_body(TENANT_A, self.dish_a, self.coupon_a1.id), make_request(self.customer_a1.id), db=self.db,
        )
        self.assertEqual(result.code, 400)

    async def test_revoked_coupon_is_rejected(self):
        self.coupon_a1.status = "REVOKED"
        await self.db.commit()

        result = await create_order(
            self._order_body(TENANT_A, self.dish_a, self.coupon_a1.id), make_request(self.customer_a1.id), db=self.db,
        )
        self.assertEqual(result.code, 400)


if __name__ == "__main__":
    unittest.main()
