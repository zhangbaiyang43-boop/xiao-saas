"""P0-12 finding 01: an exact idempotent retry of an ALREADY-CREATED order must
win over the merchant's own temporary open/close admission toggle
(TenantConfig.business_info["is_open"]) -- a store that closes between the
original success and a lost-response retry must not strand that legitimate
order by rejecting the retry outright. Platform-level suspension (Tenant.status)
is a *different* authority and must NOT be weakened -- a suspended tenant is
denied even on an exact retry.

RED-first: the tests below were run against the pre-fix code (which checked
is_open BEFORE the replay lookup) and failed exactly where expected; they now
pass against the fix (replay lookup moved before the is_open check, tenant.status
left untouched before it).

Matrix:
  B01 store open -> R1 -> O1; store closes; same R1/same owner -> O1 replay
  B02 store closed -> new R2 -> DENY
  B03 store reopens -> new R2 -> ALLOW
  B04 config failure does not burn the key (first attempt while closed never
      creates an Order; store reopens; same request_id retry succeeds)
  T01 Tenant.status=false + new request -> DENY
  T02 Tenant.status=false + existing request_id retry -> DENY (not replayed --
      platform suspension is never bypassed by idempotency)
  Controls: P0-11 cross-owner deny and P0-04 fingerprint-mismatch conflict both
  still hold even while the store is closed.
"""

import asyncio
import unittest
from datetime import datetime

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.order import Order, OrderItem
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.api.v1.orders import create_order, OrderCreate, OrderItemIn
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT = "tenant-p0-12-store"
TABLE = "T09"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_request(customer_id=None):
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


class StoreCloseReplayAuthorityTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(
            tenant_id=TENANT, name="Test Restaurant", password_hash="x",
            status=True, is_open=True, payment_mode="postpay",
        )
        self.db.add(self.tenant)
        self.config = TenantConfig(tenant_id=TENANT, business_info={"is_open": True})
        self.db.add(self.config)
        self.dish = MenuItem(tenant_id=TENANT, name="米饭", price="8.00", available=True)
        self.db.add(self.dish)
        self.db.add(EntranceCode(
            id=generate_snowflake_id(),
            tenant_id=TENANT, name=TABLE, scene=f"E{TENANT}",
            table_no=TABLE, entry_type="table", status=1,
        ))
        await self.db.flush()
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _body(self, *, request_id, table=TABLE):
        return OrderCreate(
            shop=TENANT, table=table,
            items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=8.0, qty=1)],
            total=8.0, request_id=request_id,
        )

    async def _close_store(self):
        await self.db.refresh(self.config)
        self.config.business_info = {"is_open": False}
        await self.db.commit()

    async def _reopen_store(self):
        await self.db.refresh(self.config)
        self.config.business_info = {"is_open": True}
        await self.db.commit()

    async def _order_count(self):
        result = await self.db.execute(select(func.count()).select_from(Order))
        return int(result.scalar() or 0)

    # ---- B01: exact retry after store closes replays the existing order ----
    async def test_b01_exact_retry_after_store_closes_replays_existing_order(self):
        first = await create_order(self._body(request_id="R-B01"), make_request(customer_id=6001), db=self.db)
        self.assertEqual(first.code, 200, first.msg)

        await self._close_store()

        retry = await create_order(self._body(request_id="R-B01"), make_request(customer_id=6001), db=self.db)
        self.assertEqual(retry.code, 200, retry.msg)
        self.assertEqual(retry.data["order_id"], first.data["order_id"])
        self.assertEqual(await self._order_count(), 1)

    # ---- B02: store closed, genuinely new request -> DENY ----
    async def test_b02_store_closed_new_request_denied(self):
        await self._close_store()
        result = await create_order(self._body(request_id="R-B02"), make_request(customer_id=6002), db=self.db)
        self.assertEqual(result.code, 400)
        self.assertEqual(await self._order_count(), 0)

    # ---- B03: store reopens, new request -> ALLOW ----
    async def test_b03_store_reopen_new_request_allowed(self):
        await self._close_store()
        await self._reopen_store()
        result = await create_order(self._body(request_id="R-B03"), make_request(customer_id=6003), db=self.db)
        self.assertEqual(result.code, 200, result.msg)
        self.assertEqual(await self._order_count(), 1)

    # ---- B04: a precondition-failure never burns the idempotency key ----
    async def test_b04_config_failure_does_not_burn_request_id(self):
        await self._close_store()
        first_attempt = await create_order(self._body(request_id="R-B04"), make_request(customer_id=6004), db=self.db)
        self.assertEqual(first_attempt.code, 400)
        self.assertEqual(await self._order_count(), 0)

        await self._reopen_store()
        retry = await create_order(self._body(request_id="R-B04"), make_request(customer_id=6004), db=self.db)
        self.assertEqual(retry.code, 200, retry.msg)
        self.assertEqual(await self._order_count(), 1)

    # ---- T01: platform suspension denies a new request ----
    async def test_t01_platform_suspended_new_request_denied(self):
        await self.db.refresh(self.tenant)
        self.tenant.status = False
        await self.db.commit()

        result = await create_order(self._body(request_id="R-T01"), make_request(customer_id=6005), db=self.db)
        self.assertEqual(result.code, 403)
        self.assertEqual(await self._order_count(), 0)

    # ---- T02: platform suspension is NEVER bypassed by an idempotent retry ----
    async def test_t02_platform_suspended_existing_request_id_still_denied(self):
        first = await create_order(self._body(request_id="R-T02"), make_request(customer_id=6006), db=self.db)
        self.assertEqual(first.code, 200, first.msg)

        await self.db.refresh(self.tenant)
        self.tenant.status = False
        await self.db.commit()

        retry = await create_order(self._body(request_id="R-T02"), make_request(customer_id=6006), db=self.db)
        self.assertEqual(retry.code, 403)
        self.assertEqual(await self._order_count(), 1)  # still just O1, no replay, no new order

    # ---- Control: P0-11 cross-owner deny still holds while the store is closed ----
    async def test_control_cross_owner_denied_even_when_store_closed(self):
        h_result = await create_order(self._body(request_id="R-CTRL1"), make_request(customer_id=6007), db=self.db)
        self.assertEqual(h_result.code, 200, h_result.msg)

        await self._close_store()

        w_result = await create_order(self._body(request_id="R-CTRL1"), make_request(customer_id=6008), db=self.db)
        self.assertEqual(w_result.code, 409)
        self.assertEqual(w_result.data["code"], "IDEMPOTENCY_CONFLICT")
        self.assertNotIn("existing_order_id", w_result.data)
        self.assertEqual(await self._order_count(), 1)

    # ---- Control: P0-04 fingerprint mismatch still 409s, not an unconditional replay ----
    async def test_control_fingerprint_mismatch_still_conflicts_when_store_closed(self):
        dish2 = MenuItem(tenant_id=TENANT, name="面条", price="18.00", available=True)
        self.db.add(dish2)
        await self.db.commit()

        first = await create_order(self._body(request_id="R-CTRL2"), make_request(customer_id=6009), db=self.db)
        self.assertEqual(first.code, 200, first.msg)

        await self._close_store()

        different_payload = OrderCreate(
            shop=TENANT, table=TABLE,
            items=[OrderItemIn(dish_id=dish2.id, name=dish2.name, price=18.0, qty=1)],
            total=18.0, request_id="R-CTRL2",
        )
        retry = await create_order(different_payload, make_request(customer_id=6009), db=self.db)
        self.assertEqual(retry.code, 409)
        self.assertEqual(retry.data["code"], "IDEMPOTENCY_CONFLICT")
        self.assertEqual(retry.data["existing_order_id"], first.data["order_id"])
        self.assertEqual(await self._order_count(), 1)


if __name__ == "__main__":
    unittest.main()
