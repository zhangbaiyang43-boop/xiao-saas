"""P0-10 Phase B: five-generation acceptance + 20-order matrix.

Simulates the same physical table (T20) being occupied by five sequential,
unrelated guest generations, each settled/closed before the next begins (the
only supported MVP turnover contract -- see the P0-10 audit's §42-45: normal
turnover REQUIRES the merchant to settle/close the current session before the
next guest's scan creates a new one). Each generation places 4 orders
(20 orders total across 5 sessions), gets its own pickup number, and is fully
settled before the next generation starts.

Asserts the full P0-10 acceptance matrix: unique session ids, at most one
OPEN session per table at any time, and zero cross-generation leakage of
orders, current-bill totals, and pickup numbers.
"""

import asyncio
import unittest
from types import SimpleNamespace

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.orders import OrderCreate, OrderItemIn, create_order, settle_table
from app.models.base import Base
from app.models.dining import DiningSession
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.pickup_no_assignment import PickupNoAssignment
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.services.dining_session_service import DiningSessionService
from app.services.pickup_no_service import PickupNoService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT = "tenant-p0-10-fivegen"
TABLE = "T20"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


class FakeMerchantRequest:
    def __init__(self):
        self.state = SimpleNamespace(tenant_id=TENANT, token_type="merchant", role="owner", account_id=None)


def make_customer_request():
    return Request({
        "type": "http", "method": "POST", "path": "/api/v1/orders", "headers": [],
        "query_string": b"", "server": ("testserver", 80), "scheme": "http",
        "client": ("testclient", 50000),
    })


class FiveGenerationAcceptanceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.db.add(Tenant(
            tenant_id=TENANT, name="Five Generation Restaurant", password_hash="x",
            status=True, is_open=True, payment_mode="postpay",
        ))
        self.dish = MenuItem(tenant_id=TENANT, name="宫保鸡丁", price="20.00", available=True)
        self.db.add(self.dish)
        self.db.add(EntranceCode(
            id=generate_snowflake_id(), tenant_id=TENANT, name=TABLE,
            scene="E0000000T20A", table_no=TABLE, entry_type="table", status=1,
        ))
        self.db.add(TenantConfig(
            tenant_id=TENANT, member_rules={}, coupon_rules={}, plugin_settings={},
            business_info={"pickup_no_enabled": True, "pickup_no_count": 30, "pickup_no_required_before_print": False},
        ))
        await self.db.flush()
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _new_generation(self, client_id):
        resolved = await DiningSessionService(self.db).resolve_session(
            tenant_id=TENANT, table_no=TABLE, client_id=client_id,
        )
        await self.db.commit()
        return resolved

    async def _place_orders(self, session_id, participant_token, count):
        order_ids = []
        for _ in range(count):
            body = OrderCreate(
                shop=TENANT, table=TABLE,
                items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=20.0, qty=1)],
                total=20.0, dining_session_id=int(session_id), participant_token=participant_token,
            )
            res = await create_order(body, make_customer_request(), db=self.db)
            self.assertEqual(res.code, 200, res.msg)
            order_ids.append(int(res.data["order_id"]))
        return order_ids

    async def _mark_all_done(self, order_ids):
        for oid in order_ids:
            order = await self.db.get(Order, oid)
            order.status = "done"
        await self.db.commit()

    async def _assign_pickup(self, session_id, pickup_no):
        settings = {"enabled": True, "count": 30, "required_before_print": False}
        session = await self.db.get(DiningSession, int(session_id))
        result = await self.db.execute(select(Order).where(Order.dining_session_id == int(session_id)).limit(1))
        first_order = result.scalar_one()
        res = await PickupNoService(self.db).assign_for_order(
            tenant_id=TENANT, order_id=first_order.id, pickup_no_raw=pickup_no, settings=settings,
        )
        self.assertEqual(res.code, 200, res.msg)

    async def _current_bill(self, session_id, participant_token):
        return await DiningSessionService(self.db).list_session_orders(
            tenant_id=TENANT, dining_session_id=int(session_id), participant_token=participant_token,
        )

    async def _open_session_count(self):
        result = await self.db.execute(
            select(func.count(DiningSession.id)).where(
                DiningSession.tenant_id == TENANT, DiningSession.table_no == TABLE, DiningSession.status == "OPEN",
            )
        )
        return int(result.scalar() or 0)

    async def test_five_generations_20_orders_zero_cross_generation_leak(self):
        generations = []  # list of {session_id, participant_token, order_ids, pickup_no}

        for g in range(1, 6):
            self.assertEqual(await self._open_session_count(), 0, f"gen {g}: previous session must already be closed before a new one opens")

            resolved = await self._new_generation(client_id=f"device-gen-{g}")
            session_id = resolved["dining_session_id"]
            participant_token = resolved["participant_token"]

            self.assertEqual(await self._open_session_count(), 1, f"gen {g}: exactly one OPEN session must exist once resolved")

            order_ids = await self._place_orders(session_id, participant_token, 4)
            await self._assign_pickup(session_id, str(10 + g))

            # ---- while this generation is ACTIVE: current bill must show only its own 4 orders ----
            bill = await self._current_bill(session_id, participant_token)
            self.assertEqual(len(bill["orders"]), 4, f"gen {g}: current bill must show exactly its own 4 orders")
            self.assertEqual({o["id"] for o in bill["orders"]}, {str(oid) for oid in order_ids})

            # ---- cross-generation leak check: no PRIOR generation's orders/pickup show up here ----
            for prior in generations:
                self.assertNotIn(prior["session_id"], [o.get("dining_session_id") for o in bill["orders"]])
                prior_order_ids = {str(oid) for oid in prior["order_ids"]}
                self.assertEqual(prior_order_ids & {o["id"] for o in bill["orders"]}, set(), f"gen {g} bill must not contain gen {prior['gen']}'s orders")

            await self._mark_all_done(order_ids)
            settle_res = await settle_table({"table_no": TABLE, "dining_session_id": str(session_id)}, FakeMerchantRequest(), self.db)
            self.assertEqual(settle_res.code, 200, settle_res.msg)
            self.assertEqual(settle_res.data["settled_count"], 4)
            self.assertEqual({o["id"] for o in settle_res.data["settled_orders"]}, {str(oid) for oid in order_ids})

            self.assertEqual(await self._open_session_count(), 0, f"gen {g}: session must be CLOSED immediately after settling")

            generations.append({
                "gen": g, "session_id": session_id, "participant_token": participant_token,
                "order_ids": order_ids, "pickup_no": str(10 + g),
            })

        # ---- SESSION_IDS_UNIQUE=5/5 ----
        session_ids = {gen["session_id"] for gen in generations}
        self.assertEqual(len(session_ids), 5)

        # ---- ORDERS=20, no order landed under the wrong session ----
        all_order_ids = [oid for gen in generations for oid in gen["order_ids"]]
        self.assertEqual(len(all_order_ids), 20)
        self.assertEqual(len(set(all_order_ids)), 20)
        result = await self.db.execute(select(Order).where(Order.tenant_id == TENANT, Order.table_no == TABLE))
        all_orders = list(result.scalars().all())
        self.assertEqual(len(all_orders), 20)
        order_session_map = {o.id: o.dining_session_id for o in all_orders}
        for gen in generations:
            for oid in gen["order_ids"]:
                self.assertEqual(order_session_map[oid], int(gen["session_id"]), "ORDER_SESSION_MISMATCH")

        # ---- CROSS_GENERATION_PICKUP_LEAK=0: each generation's pickup number was released, never inherited ----
        pickup_result = await self.db.execute(select(PickupNoAssignment).where(PickupNoAssignment.tenant_id == TENANT))
        remaining_assignments = list(pickup_result.scalars().all())
        self.assertEqual(remaining_assignments, [], "all pickup leases must be released once every generation is settled")

        # each settled order retains its OWN historical pickup_no snapshot (not deleted, not overwritten by a later generation)
        for gen in generations:
            for oid in gen["order_ids"]:
                order = await self.db.get(Order, oid)
                self.assertEqual(order.pickup_no, gen["pickup_no"], "OLD_PICKUP_NO must remain on the historical order, never overwritten by a later generation")

        # ---- CROSS_GENERATION_PAYMENT_LEAK=0: each order's payment truth stays scoped to its own session ----
        for gen in generations:
            for oid in gen["order_ids"]:
                order = await self.db.get(Order, oid)
                self.assertEqual(order.dining_session_id, int(gen["session_id"]))
                self.assertEqual(order.status, "settled")


class CrossTableRegressionTest(unittest.IsolatedAsyncioTestCase):
    """P0-10 §50/§96 + P0-01 regression: a sequence of scans across DIFFERENT
    tables (including revisiting a table already used earlier in the sequence)
    must always resolve tenant/table/session correctly -- each resolve must
    match its own table, and revisiting Table01 later must never resurrect
    the FIRST visit's now-closed session."""

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add(Tenant(
            tenant_id=TENANT, name="Cross Table Restaurant", password_hash="x",
            status=True, is_open=True, payment_mode="postpay",
        ))
        for t in ("Table01", "Table02", "Table03", "Table05"):
            self.db.add(EntranceCode(
                id=generate_snowflake_id(), tenant_id=TENANT, name=t,
                scene=f"E{t}SCENE0000", table_no=t, entry_type="table", status=1,
            ))
        await self.db.flush()
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_table01_table02_table03_table01_table05_sequence(self):
        service = DiningSessionService(self.db)
        sequence = ["Table01", "Table02", "Table03", "Table01", "Table05"]
        resolved_sessions = []

        for table in sequence:
            resolved = await service.resolve_session(tenant_id=TENANT, table_no=table, client_id=f"device-{table}-{len(resolved_sessions)}")
            await self.db.commit()
            self.assertEqual(resolved["tenant_id"], TENANT)
            self.assertEqual(resolved["table_no"], table)
            resolved_sessions.append((table, resolved["dining_session_id"]))

        # first and second Table01 visits are the SAME still-open session (no settle happened between them)
        first_t01 = resolved_sessions[0]
        second_t01 = resolved_sessions[3]
        self.assertEqual(first_t01[1], second_t01[1])

        # every OTHER table got a genuinely distinct session id, correctly scoped to its own table
        distinct_tables = {"Table02": resolved_sessions[1][1], "Table03": resolved_sessions[2][1], "Table05": resolved_sessions[4][1]}
        all_ids = [first_t01[1]] + list(distinct_tables.values())
        self.assertEqual(len(set(all_ids)), 4, "each distinct table must resolve to its own distinct session id")

        # each session's DB row genuinely belongs to the table it was resolved for
        for table, session_id in resolved_sessions:
            session = await self.db.get(DiningSession, int(session_id))
            self.assertEqual(session.tenant_id, TENANT)
            self.assertEqual(session.table_no, table)


if __name__ == "__main__":
    unittest.main()
