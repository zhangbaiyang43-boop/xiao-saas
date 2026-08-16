"""P0-11 Phase B acceptance: same physical table, multiple people scanning in
(nearly) simultaneously, sharing one DiningSession but keeping independent
carts/orders/authority. Covers the Phase A RED plan (R01, R03-R09) not already
exercised by test_p0_11_idempotency_owner_isolation.py's R13 matrix, plus the
5-participant / 20-order acceptance matrices (sections 50-52 of the P0-11
Phase B spec).

Findings closed by this file:
  P0-11-02 same-table simultaneous first-scan coverage gap
  P0-11-03 multi-customer table_account settlement coverage gap
"""

import asyncio
import unittest
from datetime import datetime

from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.config import settings
from app.models.base import Base
from app.models.dining import DiningParticipant, DiningSession
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.api.v1.orders import create_order, settle_table, OrderCreate, OrderItemIn, MockPayBody
from app.services.dining_session_service import DiningSessionService, hash_participant_token
from app.services.order_lifecycle_service import OrderLifecycleService
from app.services.order_payment_service import OrderPaymentService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT = "tenant-p0-11-accept"
TABLE = "T08"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_request(customer_id=None, tenant_id=None, token_type=None):
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
    req.state.tenant_id = tenant_id
    req.state.token_type = token_type
    return req


from types import SimpleNamespace


class FakeRequest:
    def __init__(self, **state):
        self.state = SimpleNamespace(**state)


def make_merchant_request(tenant_id=TENANT):
    return FakeRequest(tenant_id=tenant_id, token_type="merchant", role="owner", account_id=None)


class P0_11AcceptanceBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.db.add(Tenant(
            tenant_id=TENANT, name="Test Restaurant", password_hash="x",
            status=True, is_open=True, payment_mode="table_account",
        ))
        await self.db.flush()
        self.db.add(EntranceCode(
            id=generate_snowflake_id(),
            tenant_id=TENANT, name=TABLE, scene=f"E{TENANT}",
            table_no=TABLE, entry_type="table", status=1,
        ))
        self.dish_gongbao = MenuItem(tenant_id=TENANT, name="宫保鸡丁", price="30.00", available=True)
        self.dish_yuxiang = MenuItem(tenant_id=TENANT, name="鱼香肉丝", price="40.00", available=True)
        self.dish_rice = MenuItem(tenant_id=TENANT, name="米饭", price="5.00", available=True)
        self.db.add_all([self.dish_gongbao, self.dish_yuxiang, self.dish_rice])
        await self.db.flush()
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _open_session(self):
        now = datetime.utcnow()
        session = DiningSession(
            tenant_id=TENANT, table_no=TABLE, status="OPEN",
            active_key=f"{TENANT}:{TABLE}", started_at=now, last_activity_at=now,
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def _join(self, session, *, customer_id):
        now = datetime.utcnow()
        participant = DiningParticipant(
            tenant_id=TENANT, session_id=session.id,
            customer_id=customer_id, joined_at=now, last_active_at=now,
        )
        self.db.add(participant)
        await self.db.flush()
        return participant

    def _body(self, session, dish, *, request_id, qty=1, coupon_id=None):
        return OrderCreate(
            shop=TENANT, table=TABLE, dining_session_id=session.id,
            items=[OrderItemIn(dish_id=dish.id, name=dish.name, price=float(dish.price), qty=qty)],
            total=float(dish.price) * qty, request_id=request_id, coupon_id=coupon_id,
        )

    async def _order_count(self):
        result = await self.db.execute(select(func.count()).select_from(Order))
        return int(result.scalar() or 0)


# ---- R01: same-table simultaneous first scan -> exactly one OPEN session ----
class SimultaneousFirstScanTest(P0_11AcceptanceBase):
    """True sub-millisecond concurrent transactions can't be proven against
    in-process SQLite (same limitation documented in
    test_dining_session_append_order_locking.py / test_coupon_redis_fallback_
    idempotency.py -- two AsyncSession objects sharing one aiosqlite connection
    corrupt each other's cursor/transaction state under asyncio.gather, which
    isn't a real MySQL/InnoDB constraint, just a SQLite/aiosqlite driver
    limitation). What IS verified here, sequentially, is the application
    contract _get_or_create_open_session depends on: (a) two different diners
    resolving against an empty table converge on the exact same session, and
    (b) the DB-level unique constraint on active_key that its IntegrityError
    handler catches genuinely exists and rejects a second OPEN session for the
    same table. See MYSQL_MULTI_PARTICIPANT_RACE=PENDING_RELEASE_GATE in the
    P0-11 report for the real-concurrency proof this defers to.
    """

    async def test_h_and_w_sequential_first_scan_converge_on_one_session(self):
        svc = DiningSessionService(self.db)
        result_h = await svc.resolve_session(TENANT, TABLE, customer_id=6001)
        await self.db.commit()
        result_w = await svc.resolve_session(TENANT, TABLE, customer_id=6002)
        await self.db.commit()

        self.assertEqual(result_h["dining_session_id"], result_w["dining_session_id"])

        open_sessions = await self.db.execute(
            select(DiningSession).where(
                DiningSession.tenant_id == TENANT,
                DiningSession.table_no == TABLE,
                DiningSession.status == "OPEN",
            )
        )
        self.assertEqual(len(open_sessions.scalars().all()), 1)

        participants = await self.db.execute(
            select(DiningParticipant).where(DiningParticipant.session_id == int(result_h["dining_session_id"]))
        )
        customer_ids = sorted(p.customer_id for p in participants.scalars().all())
        self.assertEqual(customer_ids, [6001, 6002])

    async def test_active_key_unique_constraint_backstops_the_race(self):
        # This is the exact backstop _get_or_create_open_session's `except
        # IntegrityError` branch relies on: proves the constraint that would
        # fire if two truly-concurrent inserts ever raced past the row lock
        # actually exists at the schema level, not just in application logic.
        now = datetime.utcnow()
        first = DiningSession(
            tenant_id=TENANT, table_no=TABLE, status="OPEN",
            active_key=f"{TENANT}:{TABLE}", started_at=now, last_activity_at=now,
        )
        self.db.add(first)
        await self.db.flush()

        second = DiningSession(
            tenant_id=TENANT, table_no=TABLE, status="OPEN",
            active_key=f"{TENANT}:{TABLE}", started_at=now, last_activity_at=now,
        )
        self.db.add(second)
        with self.assertRaises(IntegrityError):
            await self.db.flush()


# ---- R03/R04: identical payload, distinct legitimate request ids -> 2 orders, no item cross-leak ----
class IdenticalPayloadDistinctOrdersTest(P0_11AcceptanceBase):
    async def test_h_w_same_dish_same_qty_different_request_ids_yields_two_orders(self):
        session = await self._open_session()
        await self._join(session, customer_id=7001)
        await self._join(session, customer_id=7002)

        h_result = await create_order(
            self._body(session, self.dish_rice, request_id="H-RICE-1"),
            make_request(customer_id=7001), db=self.db,
        )
        w_result = await create_order(
            self._body(session, self.dish_rice, request_id="W-RICE-1"),
            make_request(customer_id=7002), db=self.db,
        )
        self.assertEqual(h_result.code, 200, h_result.msg)
        self.assertEqual(w_result.code, 200, w_result.msg)
        self.assertNotEqual(h_result.data["order_id"], w_result.data["order_id"])
        self.assertEqual(await self._order_count(), 2)

    async def test_h_w_different_dishes_never_cross_contaminate_items(self):
        session = await self._open_session()
        await self._join(session, customer_id=7011)
        await self._join(session, customer_id=7012)

        h_result = await create_order(
            self._body(session, self.dish_gongbao, request_id="H-ITEM-1"),
            make_request(customer_id=7011), db=self.db,
        )
        w_result = await create_order(
            self._body(session, self.dish_yuxiang, qty=2, request_id="W-ITEM-1"),
            make_request(customer_id=7012), db=self.db,
        )
        self.assertEqual(h_result.code, 200)
        self.assertEqual(w_result.code, 200)

        h_items = await self.db.execute(select(OrderItem).where(OrderItem.order_id == int(h_result.data["order_id"])))
        w_items = await self.db.execute(select(OrderItem).where(OrderItem.order_id == int(w_result.data["order_id"])))
        h_names = [i.name for i in h_items.scalars().all()]
        w_names = [i.name for i in w_items.scalars().all()]
        self.assertEqual(h_names, ["宫保鸡丁"])
        self.assertEqual(w_names, ["鱼香肉丝"])


# ---- R06/R07: ordinary cross-participant cancel/pay authority ----
class CrossParticipantAuthorityTest(P0_11AcceptanceBase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.session = await self._open_session()
        await self._join(self.session, customer_id=8001)
        await self._join(self.session, customer_id=8002)
        h_result = await create_order(
            self._body(self.session, self.dish_gongbao, request_id="H-AUTH-1"),
            make_request(customer_id=8001), db=self.db,
        )
        self.assertEqual(h_result.code, 200, h_result.msg)
        self.h1_id = int(h_result.data["order_id"])

    async def test_h_cannot_cancel_w_order(self):
        # H1 was created postpay-shaped (pending, not pending_payment) since tenant
        # default is table_account; force it into a cancellable pending_payment
        # state isn't needed here -- cancel_order's ownership check runs before
        # any status check, so a wrong-owner attempt is denied regardless.
        result = await OrderLifecycleService(self.db).cancel_order(
            self.h1_id, customer_id=8002, participant_token=None,
        )
        self.assertEqual(result.code, 403)
        order = await self.db.get(Order, self.h1_id)
        self.assertNotEqual(order.status, "cancelled")

    async def test_w_cannot_pay_h_order(self):
        # mock_pay_order only proceeds past its own status guard for
        # pending_payment orders (the prepay shape) -- the default tenant here
        # is table_account (asyncSetUp), so H1 is "pending", not
        # "pending_payment". Build a dedicated prepay-shaped order directly so
        # the flow actually reaches the ownership check this test targets.
        prepay_order = Order(
            tenant_id=TENANT, dining_session_id=self.session.id, table_no=TABLE,
            customer_id=8001, total="30.00", status="pending_payment",
            payment_status="unpaid", payment_mode="prepay", source="miniprogram",
        )
        self.db.add(prepay_order)
        await self.db.commit()
        await self.db.refresh(prepay_order)

        settings.ALLOW_MOCK_MONEY_ENDPOINTS = True
        try:
            result = await OrderPaymentService(self.db).mock_pay_order(
                str(prepay_order.id),
                MockPayBody(participant_token=None),
                make_request(customer_id=8002, tenant_id=TENANT),
            )
        finally:
            settings.ALLOW_MOCK_MONEY_ENDPOINTS = False
        self.assertEqual(result.code, 403)
        await self.db.refresh(prepay_order)
        self.assertNotEqual(prepay_order.payment_status, "paid")

    async def test_h_can_query_own_order_w_cannot(self):
        own = await OrderLifecycleService(self.db).get_my_order(
            self.h1_id, customer_id=8001, participant_token=None,
        )
        self.assertEqual(own.code, 200, own.msg)
        other = await OrderLifecycleService(self.db).get_my_order(
            self.h1_id, customer_id=8002, participant_token=None,
        )
        self.assertEqual(other.code, 403)


# ---- R08/R11: multi-customer + staff table_account settlement ----
class MultiCustomerSettlementTest(P0_11AcceptanceBase):
    async def _done_order(self, session, *, customer_id, total, status="done", source="miniprogram"):
        order = Order(
            tenant_id=TENANT, dining_session_id=session.id, table_no=TABLE,
            customer_id=customer_id, total=total, status=status,
            payment_status="unpaid", payment_mode="table_account", source=source,
        )
        self.db.add(order)
        await self.db.flush()
        self.db.add(OrderItem(id=generate_snowflake_id(), order_id=order.id, name="dish", price=total, qty=1))
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def test_h_and_w_orders_settle_into_one_bill(self):
        session = await self._open_session()
        h1 = await self._done_order(session, customer_id=9001, total="30.00")
        w1 = await self._done_order(session, customer_id=9002, total="40.00")

        res = await settle_table(
            {"table_no": TABLE, "dining_session_id": str(session.id)},
            make_merchant_request(), self.db,
        )
        self.assertEqual(res.code, 200, res.msg)
        self.assertEqual(res.data["settled_count"], 2)
        self.assertAlmostEqual(float(res.data["total"]), 70.0)

        await self.db.refresh(h1)
        await self.db.refresh(w1)
        self.assertEqual(h1.status, "settled")
        self.assertEqual(w1.status, "settled")

    async def test_cancelled_order_excluded_staff_order_included(self):
        session = await self._open_session()
        h1 = await self._done_order(session, customer_id=9011, total="30.00")
        w1 = await self._done_order(session, customer_id=9012, total="40.00", status="cancelled")
        s1 = await self._done_order(session, customer_id=None, total="20.00", source="staff")

        res = await settle_table(
            {"table_no": TABLE, "dining_session_id": str(session.id)},
            make_merchant_request(), self.db,
        )
        self.assertEqual(res.code, 200, res.msg)
        self.assertEqual(res.data["settled_count"], 2)  # h1 + s1, not w1 (cancelled)
        self.assertAlmostEqual(float(res.data["total"]), 50.0)

        await self.db.refresh(h1)
        await self.db.refresh(w1)
        await self.db.refresh(s1)
        self.assertEqual(h1.status, "settled")
        self.assertEqual(w1.status, "cancelled")  # untouched by settlement
        self.assertEqual(s1.status, "settled")

    async def test_h1_cancel_does_not_affect_w1_status(self):
        session = await self._open_session()
        await self._join(session, customer_id=9021)
        await self._join(session, customer_id=9022)
        h1_resp = await create_order(
            self._body(session, self.dish_gongbao, request_id="H-INDEP-1"),
            make_request(customer_id=9021), db=self.db,
        )
        w1_resp = await create_order(
            self._body(session, self.dish_yuxiang, request_id="W-INDEP-1"),
            make_request(customer_id=9022), db=self.db,
        )
        h1_id = int(h1_resp.data["order_id"])
        w1_id = int(w1_resp.data["order_id"])

        cancel_result = await OrderLifecycleService(self.db).cancel_order(
            h1_id, customer_id=9021, participant_token=None,
        )
        self.assertEqual(cancel_result.code, 200, cancel_result.msg)

        h1 = await self.db.get(Order, h1_id)
        w1 = await self.db.get(Order, w1_id)
        self.assertEqual(h1.status, "cancelled")
        self.assertNotEqual(w1.status, "cancelled")


# ---- Staff add-order: session-attached, never misbound to a customer ----
class StaffAddOrderNoMisbindTest(P0_11AcceptanceBase):
    async def test_staff_add_order_has_no_customer_or_participant_binding(self):
        session = await self._open_session()
        await self._join(session, customer_id=10001)
        h_result = await create_order(
            self._body(session, self.dish_gongbao, request_id="H-STAFF-CTX-1"),
            make_request(customer_id=10001), db=self.db,
        )
        self.assertEqual(h_result.code, 200, h_result.msg)

        staff_body = OrderCreate(
            shop=TENANT, table=TABLE, dining_session_id=session.id,
            items=[OrderItemIn(dish_id=self.dish_rice.id, name=self.dish_rice.name, price=5.0, qty=1)],
            total=5.0, request_id="STAFF-ADD-1",
        )
        staff_result = await create_order(
            staff_body, make_request(tenant_id=TENANT, token_type="merchant"), db=self.db,
        )
        self.assertEqual(staff_result.code, 200, staff_result.msg)
        staff_order = await self.db.get(Order, int(staff_result.data["order_id"]))
        self.assertIsNone(staff_order.customer_id)
        self.assertIsNone(staff_order.participant_id)
        self.assertEqual(staff_order.dining_session_id, session.id)


# ---- Sections 50-52: N-participant acceptance matrices ----
class ParticipantMatrixTest(P0_11AcceptanceBase):
    async def test_five_participants_one_order_each_no_leak(self):
        session = await self._open_session()
        customer_ids = [11001, 11002, 11003, 11004, 11005]
        for cid in customer_ids:
            await self._join(session, customer_id=cid)

        order_ids = set()
        for idx, cid in enumerate(customer_ids):
            result = await create_order(
                self._body(session, self.dish_rice, request_id=f"FIVE-{cid}"),
                make_request(customer_id=cid), db=self.db,
            )
            self.assertEqual(result.code, 200, result.msg)
            order_ids.add(result.data["order_id"])

        self.assertEqual(len(order_ids), 5)  # no duplicates, no missing
        open_sessions = await self.db.execute(
            select(DiningSession).where(
                DiningSession.tenant_id == TENANT, DiningSession.table_no == TABLE, DiningSession.status == "OPEN",
            )
        )
        self.assertEqual(len(open_sessions.scalars().all()), 1)

        orders = await self.db.execute(select(Order).where(Order.dining_session_id == session.id))
        owners = sorted(o.customer_id for o in orders.scalars().all())
        self.assertEqual(owners, customer_ids)

    async def test_twenty_order_matrix_four_participants_five_orders_each(self):
        session = await self._open_session()
        customer_ids = [12001, 12002, 12003, 12004]
        for cid in customer_ids:
            await self._join(session, customer_id=cid)

        order_ids = set()
        for cid in customer_ids:
            for n in range(5):
                result = await create_order(
                    self._body(session, self.dish_rice, request_id=f"TWENTY-{cid}-{n}"),
                    make_request(customer_id=cid), db=self.db,
                )
                self.assertEqual(result.code, 200, result.msg)
                order_ids.add(result.data["order_id"])

        self.assertEqual(len(order_ids), 20)

        orders_result = await self.db.execute(select(Order).where(Order.dining_session_id == session.id))
        orders = orders_result.scalars().all()
        self.assertEqual(len(orders), 20)
        self.assertTrue(all(o.dining_session_id == session.id for o in orders))
        by_owner = {}
        for o in orders:
            by_owner.setdefault(o.customer_id, 0)
            by_owner[o.customer_id] += 1
        self.assertEqual(by_owner, {cid: 5 for cid in customer_ids})


if __name__ == "__main__":
    unittest.main()
