"""P0-11 finding 01: client_request_id idempotency was scoped to
(tenant_id, client_request_id) only -- with no check that the caller replaying
a hit is the same principal who created it. Two different diners at the same
table/dining_session sharing (or adversarially reusing) a client_request_id
could otherwise have the second caller silently receive the first caller's
order as their own "replay".

R13 matrix (owner-replay authority), covering both replay paths:
  - the early check in _prepare_create_order_tenant_and_replay
  - the concurrent-conflict recovery after an IntegrityError on insert

A1 same owner + same key + same payload      -> replay (existing order, no new row)
A2 same owner + same key + different payload -> 409 IDEMPOTENCY_CONFLICT (P0-04, unchanged)
B1 different owner + same key + same payload  -> DENY, never returns the other owner's order
B2 different owner + same key + different payload -> DENY
C1 different anonymous participant + same key + same payload -> DENY
D1 different tenant + same key -> independent, unaffected by the owner check
"""

import asyncio
import unittest
from datetime import datetime

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.dining import DiningParticipant, DiningSession
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.api.v1.orders import create_order, OrderCreate, OrderItemIn
from app.services.dining_session_service import hash_participant_token
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-p0-11-a"
TENANT_B = "tenant-p0-11-b"
TABLE = "T08"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_request(customer_id=None, path="/api/v1/orders"):
    req = Request(
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
    req.state.customer_id = customer_id
    return req


class IdempotencyOwnerIsolationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        for tenant_id in (TENANT_A, TENANT_B):
            self.db.add(Tenant(
                tenant_id=tenant_id, name="Test Restaurant", password_hash="x",
                status=True, is_open=True, payment_mode="postpay",
            ))
        await self.db.flush()

        self.dish_a = MenuItem(tenant_id=TENANT_A, name="米饭", price="8.00", available=True)
        self.dish_a2 = MenuItem(tenant_id=TENANT_A, name="面条", price="18.00", available=True)
        self.dish_b = MenuItem(tenant_id=TENANT_B, name="米饭", price="8.00", available=True)
        self.db.add_all([self.dish_a, self.dish_a2, self.dish_b])
        for tenant_id in (TENANT_A, TENANT_B):
            self.db.add(EntranceCode(
                id=generate_snowflake_id(),
                tenant_id=tenant_id, name=TABLE, scene=f"E{tenant_id}",
                table_no=TABLE, entry_type="table", status=1,
            ))
        await self.db.flush()

        now = datetime.utcnow()
        self.session_a = DiningSession(
            tenant_id=TENANT_A, table_no=TABLE, status="OPEN",
            active_key=f"{TENANT_A}:{TABLE}", started_at=now, last_activity_at=now,
        )
        self.session_b = DiningSession(
            tenant_id=TENANT_B, table_no=TABLE, status="OPEN",
            active_key=f"{TENANT_B}:{TABLE}", started_at=now, last_activity_at=now,
        )
        self.db.add_all([self.session_a, self.session_b])
        await self.db.flush()

        self.customer_h = 5001
        self.customer_w = 5002
        self.participant_h = DiningParticipant(
            tenant_id=TENANT_A, session_id=self.session_a.id,
            customer_id=self.customer_h, joined_at=now, last_active_at=now,
        )
        self.participant_w = DiningParticipant(
            tenant_id=TENANT_A, session_id=self.session_a.id,
            customer_id=self.customer_w, joined_at=now, last_active_at=now,
        )
        self.anon_token_h = "anon-token-h-raw"
        self.anon_token_w = "anon-token-w-raw"
        self.anon_participant_h = DiningParticipant(
            tenant_id=TENANT_A, session_id=self.session_a.id,
            guest_token_hash=hash_participant_token(self.anon_token_h),
            joined_at=now, last_active_at=now,
        )
        self.anon_participant_w = DiningParticipant(
            tenant_id=TENANT_A, session_id=self.session_a.id,
            guest_token_hash=hash_participant_token(self.anon_token_w),
            joined_at=now, last_active_at=now,
        )
        self.customer_cross_tenant = 9001
        self.participant_cross_tenant = DiningParticipant(
            tenant_id=TENANT_B, session_id=self.session_b.id,
            customer_id=self.customer_cross_tenant, joined_at=now, last_active_at=now,
        )
        self.db.add_all([
            self.participant_h, self.participant_w,
            self.anon_participant_h, self.anon_participant_w,
            self.participant_cross_tenant,
        ])
        await self.db.flush()
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _body(self, *, tenant_id=TENANT_A, dish, request_id, participant_token=None):
        return OrderCreate(
            shop=tenant_id,
            table=TABLE,
            dining_session_id=self.session_a.id if tenant_id == TENANT_A else self.session_b.id,
            participant_token=participant_token,
            items=[OrderItemIn(dish_id=dish.id, name=dish.name, price=float(dish.price), qty=1)],
            total=float(dish.price),
            request_id=request_id,
        )

    async def _order_count(self):
        result = await self.db.execute(select(func.count()).select_from(Order))
        return int(result.scalar() or 0)

    # ---- A1: same owner, same key, same payload -> replay ----
    async def test_a1_same_owner_same_key_same_payload_replays(self):
        first = await create_order(
            self._body(dish=self.dish_a, request_id="R-A1"), make_request(self.customer_h), db=self.db,
        )
        second = await create_order(
            self._body(dish=self.dish_a, request_id="R-A1"), make_request(self.customer_h), db=self.db,
        )
        self.assertEqual(first.code, 200, first.msg)
        self.assertEqual(second.code, 200, second.msg)
        self.assertEqual(first.data["order_id"], second.data["order_id"])
        self.assertEqual(await self._order_count(), 1)

    # ---- A2: same owner, same key, different payload -> existing P0-04 conflict ----
    async def test_a2_same_owner_same_key_different_payload_conflicts(self):
        first = await create_order(
            self._body(dish=self.dish_a, request_id="R-A2"), make_request(self.customer_h), db=self.db,
        )
        second = await create_order(
            self._body(dish=self.dish_a2, request_id="R-A2"), make_request(self.customer_h), db=self.db,
        )
        self.assertEqual(first.code, 200, first.msg)
        self.assertEqual(second.code, 409)
        self.assertEqual(second.data["code"], "IDEMPOTENCY_CONFLICT")
        self.assertEqual(second.data["existing_order_id"], first.data["order_id"])
        self.assertEqual(await self._order_count(), 1)

    # ---- B1: different owner, same key, same payload -> DENY, no replay of H's order ----
    async def test_b1_different_owner_same_key_same_payload_denied(self):
        h_result = await create_order(
            self._body(dish=self.dish_a, request_id="R-B1"), make_request(self.customer_h), db=self.db,
        )
        self.assertEqual(h_result.code, 200, h_result.msg)

        w_result = await create_order(
            self._body(dish=self.dish_a, request_id="R-B1"), make_request(self.customer_w), db=self.db,
        )
        self.assertEqual(w_result.code, 409)
        self.assertEqual(w_result.data["code"], "IDEMPOTENCY_CONFLICT")
        # minimal disclosure: W must never learn H's order id/no/amount/items
        self.assertNotIn("existing_order_id", w_result.data)
        self.assertNotIn("existing_order_no", w_result.data)
        self.assertNotIn("payment_status", w_result.data)
        # and no second order was silently created for W under the reused key
        self.assertEqual(await self._order_count(), 1)

    # ---- B2: different owner, same key, different payload -> DENY, no leak either ----
    async def test_b2_different_owner_same_key_different_payload_denied(self):
        h_result = await create_order(
            self._body(dish=self.dish_a, request_id="R-B2"), make_request(self.customer_h), db=self.db,
        )
        self.assertEqual(h_result.code, 200, h_result.msg)

        w_result = await create_order(
            self._body(dish=self.dish_a2, request_id="R-B2"), make_request(self.customer_w), db=self.db,
        )
        self.assertEqual(w_result.code, 409)
        self.assertEqual(w_result.data["code"], "IDEMPOTENCY_CONFLICT")
        self.assertNotIn("existing_order_id", w_result.data)
        self.assertEqual(await self._order_count(), 1)

    # ---- C1: different anonymous participant, same key, same payload -> DENY ----
    async def test_c1_different_anonymous_participant_same_key_same_payload_denied(self):
        first = await create_order(
            self._body(dish=self.dish_a, request_id="R-C1", participant_token=self.anon_token_h),
            make_request(customer_id=None), db=self.db,
        )
        self.assertEqual(first.code, 200, first.msg)

        second = await create_order(
            self._body(dish=self.dish_a, request_id="R-C1", participant_token=self.anon_token_w),
            make_request(customer_id=None), db=self.db,
        )
        self.assertEqual(second.code, 409)
        self.assertEqual(second.data["code"], "IDEMPOTENCY_CONFLICT")
        self.assertNotIn("existing_order_id", second.data)
        self.assertEqual(await self._order_count(), 1)

    # ---- D1: different tenant, same key -> independent, unaffected by the owner check ----
    async def test_d1_cross_tenant_same_key_independent(self):
        a_result = await create_order(
            self._body(tenant_id=TENANT_A, dish=self.dish_a, request_id="R-D1"),
            make_request(self.customer_h), db=self.db,
        )
        b_result = await create_order(
            self._body(tenant_id=TENANT_B, dish=self.dish_b, request_id="R-D1"),
            make_request(customer_id=self.customer_cross_tenant), db=self.db,
        )
        self.assertEqual(a_result.code, 200, a_result.msg)
        self.assertEqual(b_result.code, 200, b_result.msg)
        self.assertNotEqual(a_result.data["order_id"], b_result.data["order_id"])
        self.assertEqual(await self._order_count(), 2)

    # ---- Concurrent-conflict recovery path must use the same owner contract ----
    async def test_concurrent_conflict_recovery_denies_cross_owner_replay(self):
        # Simulate the race: H's insert has already committed under this key
        # (as if the early replay check's read happened before H's write landed).
        h_result = await create_order(
            self._body(dish=self.dish_a, request_id="R-RACE"), make_request(self.customer_h), db=self.db,
        )
        self.assertEqual(h_result.code, 200, h_result.msg)

        # W's own insert now collides on the unique (tenant_id, client_request_id)
        # index and falls into the IntegrityError recovery branch, not the early
        # check -- this must deny exactly like the early path does.
        w_result = await create_order(
            self._body(dish=self.dish_a, request_id="R-RACE"), make_request(self.customer_w), db=self.db,
        )
        self.assertEqual(w_result.code, 409)
        self.assertEqual(w_result.data["code"], "IDEMPOTENCY_CONFLICT")
        self.assertNotIn("existing_order_id", w_result.data)
        self.assertEqual(await self._order_count(), 1)

    # ---- Control: legitimate same-owner retry through the race-recovery path still replays ----
    async def test_concurrent_conflict_recovery_still_replays_for_true_owner(self):
        pre_existing = Order(
            tenant_id=TENANT_A, dining_session_id=self.session_a.id, table_no=TABLE,
            customer_id=self.customer_h, total="8.00", status="pending",
            payment_status="unpaid", payment_mode="postpay",
            client_request_id="R-RACE-OWNER",
        )
        self.db.add(pre_existing)
        await self.db.commit()

        result = await create_order(
            self._body(dish=self.dish_a, request_id="R-RACE-OWNER"), make_request(self.customer_h), db=self.db,
        )
        self.assertEqual(result.code, 200, result.msg)
        self.assertEqual(result.data["order_id"], str(pre_existing.id))
        self.assertEqual(await self._order_count(), 1)


if __name__ == "__main__":
    unittest.main()
