"""P0-13 findings 03/05: direct application-level proof that coupon locking is
atomic (not a check-then-set race), that a create_order failure never leaves a
coupon stuck LOCKED with no owning order, and that single-use is enforced
across sequential attempts. True sub-millisecond concurrent-transaction proof
is deferred to MySQL (see MYSQL_COUPON_LOCK_CONCURRENCY=PENDING_RELEASE_GATE in
the P0-13 report) -- this file proves the application contract and the DB-level
mechanism the contract depends on, consistent with the same SQLite limitation
already documented for P0-10/P0-11 (asyncio.gather against a shared in-memory
SQLite connection corrupts AsyncSession state; it isn't a real MySQL/InnoDB
constraint, just a driver limitation of the test harness).
"""

import asyncio
import unittest
from datetime import datetime, timedelta

from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.entrance_code import EntranceCode
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


TENANT = "p0-13-lock-tenant"
TABLE = "T21"


def make_request(customer_id):
    req = Request(
        {
            "type": "http", "method": "POST", "path": "/api/v1/orders",
            "headers": [], "query_string": b"",
            "server": ("testserver", 80), "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    req.state.customer_id = customer_id
    return req


class CouponLockConcurrencyAndAtomicityTest(unittest.IsolatedAsyncioTestCase):
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
        self.dish = MenuItem(tenant_id=TENANT, name="宫保鸡丁", price="100.00", available=True, stock=5)
        self.db.add(self.dish)
        self.db.add(EntranceCode(
            id=generate_snowflake_id(),
            tenant_id=TENANT, name=TABLE, scene=f"E{TENANT}",
            table_no=TABLE, entry_type="table", status=1,
        ))
        self.template = CouponTemplate(
            tenant_id=TENANT, name="20 off", type="FIXED", value="20.00",
            min_amount="0.00", total_stock=100, used_stock=1,
            start_time=datetime.utcnow() - timedelta(days=1),
            end_time=datetime.utcnow() + timedelta(days=30), status=1,
        )
        self.db.add(self.template)
        await self.db.flush()
        self.coupon = Coupon(
            tenant_id=TENANT, template_id=self.template.id, customer_id=8001,
            code=f"CODE-{generate_snowflake_id()}", status="UNUSED",
            expire_time=datetime.utcnow() + timedelta(days=1),
        )
        self.db.add(self.coupon)
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _body(self, *, request_id, coupon_id=None, table=TABLE):
        return OrderCreate(
            shop=TENANT, table=table,
            items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=100.0, qty=1)],
            total=100.0, coupon_id=coupon_id, request_id=request_id,
        )

    # ---- Q1: lock is a single atomic SELECT ... FOR UPDATE, not check-then-set ----
    def test_lock_query_is_select_for_update_not_check_then_set(self):
        import inspect
        from app.api.v1 import orders as orders_module
        source = inspect.getsource(orders_module._apply_create_order_coupon)
        self.assertIn(".with_for_update()", source)
        self.assertIn('Coupon.status == "UNUSED"', source)
        # the lock predicate and the row-lock clause must be part of the same
        # SELECT statement (both appear before any UPDATE-only statement) --
        # a plain regression pin that the query shape hasn't regressed into a
        # separate SELECT-then-UPDATE pair.
        select_idx = source.index("select(Coupon)")
        for_update_idx = source.index(".with_for_update()")
        status_idx = source.index('Coupon.status == "UNUSED"')
        self.assertTrue(select_idx < status_idx < for_update_idx)

    # ---- Sequential single-use: second attempt on an already-locked coupon is denied ----
    async def test_two_orders_sequential_single_use(self):
        first = await create_order(self._body(request_id="R-SEQ-1", coupon_id=self.coupon.id), make_request(8001), db=self.db)
        self.assertEqual(first.code, 200, first.msg)
        self.assertEqual(first.data["discount_amount"], 20.0)

        second = await create_order(self._body(request_id="R-SEQ-2", coupon_id=self.coupon.id), make_request(8001), db=self.db)
        self.assertEqual(second.code, 400)
        self.assertEqual(second.msg, "优惠券不可用或已失效")
        self.assertNotIn("discount_amount", second.data or {})

        result = await self.db.execute(select(Order).where(Order.tenant_id == TENANT))
        orders = result.scalars().all()
        self.assertEqual(len(orders), 1)  # only the first order was created

    # ---- Logical two-device race: winner locks, loser's re-read denies (proves the WHERE-filter re-check) ----
    async def test_logical_two_device_race_only_one_winner(self):
        # Simulates the outcome InnoDB's row lock guarantees on production: the
        # first transaction to commit its LOCKED write is the only one whose
        # SELECT ... WHERE status='UNUSED' ... FOR UPDATE can ever have matched.
        winner = await create_order(self._body(request_id="R-RACE-WIN", coupon_id=self.coupon.id), make_request(8001), db=self.db)
        self.assertEqual(winner.code, 200, winner.msg)

        loser = await create_order(self._body(request_id="R-RACE-LOSE", coupon_id=self.coupon.id), make_request(8001), db=self.db)
        self.assertEqual(loser.code, 400)

        await self.db.refresh(self.coupon)
        self.assertEqual(self.coupon.status, "LOCKED")
        result = await self.db.execute(select(Order).where(Order.tenant_id == TENANT))
        self.assertEqual(len(result.scalars().all()), 1)

    # ---- Create-failure atomicity: coupon lock must not survive a transaction that never commits ----
    async def test_transaction_rollback_discards_coupon_lock(self):
        # Directly exercises the atomicity guarantee create_order depends on:
        # in production, every request gets its own session (app/core/database.py
        # get_db), and a request that returns an error response WITHOUT calling
        # db.commit() has its entire pending transaction discarded when that
        # session is torn down at request end. This reproduces exactly that --
        # lock the coupon (mirroring what _apply_create_order_coupon does),
        # then roll back without ever committing, exactly as would happen if
        # something failed further down the same request (menu/table/stock/
        # persist) before reaching the final commit.
        from app.api.v1.orders import _apply_create_order_coupon, OrderCreate as _OC

        body = self._body(request_id="R-ROLLBACK", coupon_id=self.coupon.id)
        early_response, applied_coupon_id, discount = await _apply_create_order_coupon(
            body, customer_id=8001, tenant_id=TENANT, real_total=100.0, db=self.db,
        )
        self.assertIsNone(early_response)
        self.assertEqual(applied_coupon_id, self.coupon.id)
        self.assertEqual(float(discount), 20.0)
        self.assertEqual(self.coupon.status, "LOCKED")  # locked in-memory, same identity-mapped object

        await self.db.flush()  # lands the UPDATE in the still-open (uncommitted) transaction

        await self.db.rollback()  # simulates the session being torn down without a commit

        await self.db.refresh(self.coupon)
        self.assertEqual(self.coupon.status, "UNUSED")  # no ghost lock survives

    # ---- Stock failure occurs before coupon is ever touched ----
    async def test_stock_failure_before_coupon_lock_leaves_coupon_untouched(self):
        self.dish.stock = 0
        await self.db.commit()

        result = await create_order(self._body(request_id="R-STOCK-FAIL", coupon_id=self.coupon.id), make_request(8001), db=self.db)
        self.assertEqual(result.code, 400)
        await self.db.refresh(self.coupon)
        self.assertEqual(self.coupon.status, "UNUSED")

    # ---- Table/session failure occurs before coupon is ever touched ----
    async def test_invalid_table_before_coupon_lock_leaves_coupon_untouched(self):
        result = await create_order(
            self._body(request_id="R-TABLE-FAIL", coupon_id=self.coupon.id, table="NONEXISTENT-TABLE"),
            make_request(8001), db=self.db,
        )
        self.assertEqual(result.code, 400)
        await self.db.refresh(self.coupon)
        self.assertEqual(self.coupon.status, "UNUSED")


if __name__ == "__main__":
    unittest.main()
