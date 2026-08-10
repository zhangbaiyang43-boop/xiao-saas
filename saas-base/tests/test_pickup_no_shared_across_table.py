import asyncio
import unittest
from datetime import datetime

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.dining import DiningSession
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.api.v1.orders import OrderCreate, OrderItemIn, create_order, update_order_pickup_no, OrderPickupNoUpdate
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_staff_request():
    request = Request(
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
    request.state.tenant_id = TENANT_A
    request.state.token_type = "merchant"
    # get_request_principal() requires role=="owner" for an account_id-less merchant
    # request (see app/middleware/auth_middleware.py:127-142, which is what a real
    # request gets from AuthMiddleware) -- this fixture predates that check.
    request.state.role = "owner"
    request.state.account_id = None
    return request


class PickupNoSharedAcrossTableTest(unittest.IsolatedAsyncioTestCase):
    """The physical pickup tag is handed out once per table sitting, not once per order --
    a table gets multiple orders over a meal (add-ons) but only ever holds one tag. Storing
    pickup_no only on Order would force staff to retype the same number on every add-on
    (see the admin-h5 screenshot that prompted this fix). It must live on the shared
    DiningSession and be inherited by every order under it."""

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(
            tenant_id=TENANT_A, name="Test Restaurant", password_hash="x",
            status=True, is_open=True, payment_mode="postpay",
        )
        self.db.add(self.tenant)
        self.dish = MenuItem(tenant_id=TENANT_A, name="Kung Pao Chicken", price="28.00", available=True)
        self.db.add(self.dish)
        await self.db.flush()
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _staff_order_body(self, pickup_no=None):
        return OrderCreate(
            shop=TENANT_A, table="A20",
            items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=28.0, qty=1)],
            total=28.0,
            pickup_no=pickup_no,
        )

    async def test_add_on_order_inherits_pickup_no_set_on_the_first_order(self):
        first_resp = await create_order(self._staff_order_body(pickup_no="07"), make_staff_request(), self.db)
        self.assertEqual(first_resp.data["pickup_no"], "07")

        add_on_resp = await create_order(self._staff_order_body(pickup_no=None), make_staff_request(), self.db)
        self.assertEqual(add_on_resp.data["pickup_no"], "07")

        session = (await self.db.execute(select(DiningSession).where(DiningSession.tenant_id == TENANT_A))).scalar_one()
        self.assertEqual(session.pickup_no, "07")

    async def test_registering_pickup_no_on_one_order_cascades_to_every_order_at_the_table(self):
        first_resp = await create_order(self._staff_order_body(), make_staff_request(), self.db)
        second_resp = await create_order(self._staff_order_body(), make_staff_request(), self.db)
        self.assertIsNone(first_resp.data["pickup_no"])
        self.assertIsNone(second_resp.data["pickup_no"])

        result = await update_order_pickup_no(
            first_resp.data["id"], OrderPickupNoUpdate(pickup_no="12"), make_staff_request(), self.db
        )
        self.assertEqual(sorted(result.data["order_ids"]), sorted([first_resp.data["id"], second_resp.data["id"]]))

        orders = (await self.db.execute(select(Order).where(Order.tenant_id == TENANT_A))).scalars().all()
        self.assertEqual({o.pickup_no for o in orders}, {"12"})

        session = (await self.db.execute(select(DiningSession).where(DiningSession.tenant_id == TENANT_A))).scalar_one()
        self.assertEqual(session.pickup_no, "12")


if __name__ == "__main__":
    unittest.main()
