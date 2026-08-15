"""P0-12 finding 03: pickup_no_enabled is the merchant's server-side authority
over whether a CUSTOMER-supplied pickup number can create/claim an active
table-pager lease. Before this fix, an ordinary (non-staff) customer request
could include `pickup_no` directly in the create-order body and have it
applied/leased completely unconditionally when pickup_settings["enabled"] was
False -- only a narrow prepay-unpaid carve-out ever consulted the enabled flag
at all. This is reachable via the same public POST /orders endpoint every
customer order goes through -- no staff/merchant token required.

RED-first: run against the pre-fix code, confirmed the customer-supplied value
WAS honored while disabled (Order.pickup_no ended up set, an active
PickupNoAssignment lease was created). Now fixed: an ordinary customer's
explicit pickup_no is ignored (treated the same as not having sent the field
at all) whenever the feature is disabled; a staff-assisted order's explicit
value is still honored regardless (a separate, authenticated-principal-derived
business need, per the P0-12 audit's product framing), and everything is
unchanged when the feature is enabled.
"""

import asyncio
import unittest
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.dining import DiningParticipant, DiningSession
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.pickup_no_assignment import PickupNoAssignment
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.api.v1.orders import create_order, OrderCreate, OrderItemIn
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT = "tenant-p0-12-pickup"
TABLE = "T11"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_customer_request(customer_id=None):
    req = Request(
        {
            "type": "http", "method": "POST", "path": "/api/v1/orders",
            "headers": [], "query_string": b"",
            "server": ("testserver", 80), "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    req.state.customer_id = customer_id
    req.state.token_type = None  # ordinary customer -- no merchant token
    return req


def make_staff_request(tenant_id=TENANT, role="owner", account_id=1):
    req = Request(
        {
            "type": "http", "method": "POST", "path": "/api/v1/orders",
            "headers": [], "query_string": b"",
            "server": ("testserver", 80), "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    req.state.customer_id = None
    req.state.tenant_id = tenant_id
    req.state.token_type = "merchant"
    req.state.role = role
    req.state.account_id = account_id
    return req


class PickupDisabledCustomerAuthorityTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.db.add(Tenant(
            tenant_id=TENANT, name="Test Restaurant", password_hash="x",
            status=True, is_open=True, payment_mode="postpay",
        ))
        self.config = TenantConfig(tenant_id=TENANT, business_info={"is_open": True, "pickup_no_enabled": False})
        self.db.add(self.config)
        self.dish = MenuItem(tenant_id=TENANT, name="米饭", price="8.00", available=True)
        self.db.add(self.dish)
        self.db.add(EntranceCode(
            id=generate_snowflake_id(),
            tenant_id=TENANT, name=TABLE, scene=f"E{TENANT}",
            table_no=TABLE, entry_type="table", status=1,
        ))
        await self.db.flush()

        now = datetime.utcnow()
        self.session = DiningSession(
            tenant_id=TENANT, table_no=TABLE, status="OPEN",
            active_key=f"{TENANT}:{TABLE}", started_at=now, last_activity_at=now,
        )
        self.db.add(self.session)
        await self.db.flush()
        self.participant = DiningParticipant(
            tenant_id=TENANT, session_id=self.session.id,
            customer_id=7001, joined_at=now, last_active_at=now,
        )
        self.db.add(self.participant)
        await self.db.flush()
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _customer_body(self, *, request_id, pickup_no=None):
        return OrderCreate(
            shop=TENANT, table=TABLE, dining_session_id=self.session.id,
            items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=8.0, qty=1)],
            total=8.0, request_id=request_id, pickup_no=pickup_no,
        )

    async def _assignment_count(self):
        result = await self.db.execute(select(PickupNoAssignment).where(PickupNoAssignment.tenant_id == TENANT))
        return len(result.scalars().all())

    # ---- RED scenario: ordinary customer, feature disabled, explicit pickup_no ----
    async def test_disabled_customer_explicit_pickup_no_is_ignored(self):
        result = await create_order(
            self._customer_body(request_id="R-PICKUP-1", pickup_no="18"),
            make_customer_request(customer_id=7001), db=self.db,
        )
        self.assertEqual(result.code, 200, result.msg)

        order = await self.db.get(Order, int(result.data["order_id"]))
        self.assertIsNone(order.pickup_no)
        await self.db.refresh(self.session)
        self.assertIsNone(self.session.pickup_no)
        self.assertEqual(await self._assignment_count(), 0)

    # ---- Control: staff-assisted explicit pickup_no still honored while disabled ----
    async def test_disabled_staff_assisted_explicit_pickup_no_still_honored(self):
        result = await create_order(
            OrderCreate(
                shop=TENANT, table=TABLE,
                items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=8.0, qty=1)],
                total=8.0, request_id="R-PICKUP-STAFF", pickup_no="19",
            ),
            make_staff_request(), db=self.db,
        )
        self.assertEqual(result.code, 200, result.msg)

        order = await self.db.get(Order, int(result.data["order_id"]))
        self.assertEqual(order.pickup_no, "19")
        self.assertEqual(await self._assignment_count(), 1)

    # ---- Control: enabled feature still honors an ordinary customer's explicit value ----
    async def test_enabled_customer_explicit_pickup_no_still_honored(self):
        await self.db.refresh(self.config)
        self.config.business_info = {"is_open": True, "pickup_no_enabled": True}
        await self.db.commit()

        result = await create_order(
            self._customer_body(request_id="R-PICKUP-2", pickup_no="20"),
            make_customer_request(customer_id=7001), db=self.db,
        )
        self.assertEqual(result.code, 200, result.msg)

        order = await self.db.get(Order, int(result.data["order_id"]))
        self.assertEqual(order.pickup_no, "20")
        self.assertEqual(await self._assignment_count(), 1)

    # ---- Control: disabled + no explicit value -> unaffected, order still created ----
    async def test_disabled_no_explicit_value_order_still_created_normally(self):
        result = await create_order(
            self._customer_body(request_id="R-PICKUP-3", pickup_no=None),
            make_customer_request(customer_id=7001), db=self.db,
        )
        self.assertEqual(result.code, 200, result.msg)
        order = await self.db.get(Order, int(result.data["order_id"]))
        self.assertIsNone(order.pickup_no)


if __name__ == "__main__":
    unittest.main()
