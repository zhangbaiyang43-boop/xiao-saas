"""P0-01: server-side table ownership authority contract tests.

Before this fix, POST /orders and DiningSessionService session creation trusted
client-supplied (tenant_id, table_no) with no independent verification against
any table registry -- a client could submit any tenant/table string and have it
persisted as a real dine-in order, including a table_no that belongs to a
*different* tenant. See the P0-01 audit report for the full trace.

These tests prove the fix's actual invariant: any new dine-in Order or
DiningSession with a non-empty table_no requires a matching, active,
entry_type='table' EntranceCode row for that exact tenant_id. Empty table_no
(takeaway/pickup/poster/douyin/staff_share) is explicitly exempt.
"""

import asyncio
import unittest
from datetime import datetime

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.dining import DiningSession
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.api.v1.orders import create_order, OrderCreate, OrderItemIn
from app.services.dining_session_service import DiningSessionService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# OrderItem.id relies on native DB autoincrement on production MySQL; SQLite only
# aliases autoincrement onto INTEGER, not BIGINT -- backfill in tests only (same
# workaround as test_order_entry_security.py).
@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


def make_request(path="/api/v1/orders"):
    return Request(
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


class TableRegistryAuthorityTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.db.add_all([
            Tenant(tenant_id=TENANT_A, name="Restaurant A", password_hash="x",
                   status=True, is_open=True, payment_mode="postpay"),
            Tenant(tenant_id=TENANT_B, name="Restaurant B", password_hash="x",
                   status=True, is_open=True, payment_mode="postpay"),
        ])
        await self.db.flush()

        self.dish = MenuItem(tenant_id=TENANT_A, name="Kung Pao Chicken", price="28.00", available=True)
        self.db.add(self.dish)
        await self.db.flush()
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _order_body(self, *, shop=TENANT_A, table, dining_session_id=None, participant_token=None, request_id=None):
        return OrderCreate(
            shop=shop, table=table,
            items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=28.0, qty=1)],
            total=28.0,
            dining_session_id=dining_session_id,
            participant_token=participant_token,
            request_id=request_id,
        )

    async def _order_count(self):
        result = await self.db.execute(select(Order))
        return len(list(result.scalars().all()))

    async def _session_count(self):
        result = await self.db.execute(select(DiningSession))
        return len(list(result.scalars().all()))

    def _add_table_code(self, tenant_id, table_no, *, entry_type="table", status=1, name=None):
        # EntranceCode.id has no Python-side default (unlike BaseModel.id) --
        # production always passes it explicitly (entrance_code_service.py's
        # create_entrance_code), and SQLite won't autoincrement a BigInteger PK.
        # scene must be unique per (tenant_id, scene) -- derive it from the
        # generated id (matching real _generate_scene's snowflake-based scheme)
        # rather than from tenant_id+table_no alone, so two active codes for the
        # same table (re-generated codes, TEST 11) don't collide on scene.
        code_id = generate_snowflake_id()
        self.db.add(EntranceCode(
            id=code_id,
            tenant_id=tenant_id, name=name or table_no, scene=f"E{code_id}"[:32],
            table_no=table_no, entry_type=entry_type, status=status,
        ))

    # ---- TEST 01: active registered table ----
    async def test_01_active_registered_table_order_succeeds(self):
        self._add_table_code(TENANT_A, "A01")
        await self.db.commit()

        result = await create_order(self._order_body(table="A01"), make_request(), db=self.db)
        self.assertEqual(result.code, 200)

    # ---- TEST 02: unregistered table ----
    async def test_02_unregistered_table_rejected_and_no_order_persisted(self):
        # No EntranceCode for A99 at all.
        result = await create_order(self._order_body(table="A99"), make_request(), db=self.db)
        self.assertEqual(result.code, 400)
        self.assertEqual(await self._order_count(), 0)

    # ---- TEST 03: cross-tenant table ----
    async def test_03_cross_tenant_table_rejected_and_no_order_persisted(self):
        # A08 is a real, active table -- but only for tenant B.
        self._add_table_code(TENANT_B, "A08")
        await self.db.commit()

        result = await create_order(self._order_body(shop=TENANT_A, table="A08"), make_request(), db=self.db)
        self.assertEqual(result.code, 400)
        self.assertEqual(await self._order_count(), 0)

    # ---- TEST 04: disabled table ----
    async def test_04_disabled_table_rejected(self):
        self._add_table_code(TENANT_A, "A03", status=0)
        await self.db.commit()

        result = await create_order(self._order_body(table="A03"), make_request(), db=self.db)
        self.assertEqual(result.code, 400)
        self.assertEqual(await self._order_count(), 0)

    # ---- TEST 05: non-table entry type doesn't count as table authority ----
    async def test_05_non_table_entry_type_does_not_grant_table_authority(self):
        # A takeaway code that happens to reuse "A06" as its table_no field --
        # must not be treated as proof "A06" is a real dine-in table.
        self._add_table_code(TENANT_A, "A06", entry_type="takeaway")
        await self.db.commit()

        result = await create_order(self._order_body(table="A06"), make_request(), db=self.db)
        self.assertEqual(result.code, 400)
        self.assertEqual(await self._order_count(), 0)

    # ---- TEST 06: whitespace normalization (validation only, not persistence) ----
    async def test_06_whitespace_stripped_for_validation_but_not_for_persistence(self):
        self._add_table_code(TENANT_A, "A01")
        await self.db.commit()

        result = await create_order(self._order_body(table=" A01 "), make_request(), db=self.db)
        self.assertEqual(result.code, 200)
        # Persistence contract unchanged: Order.table_no keeps exactly what the
        # client sent (existing `body.table or ""` assignment, untouched by this
        # fix) -- only the *validation comparison* strips.
        order = (await self.db.execute(select(Order))).scalar_one()
        self.assertEqual(order.table_no, " A01 ")

    # ---- TEST 07: empty table is a legitimate non-table flow, not validated ----
    async def test_07_empty_table_is_exempt_from_table_validation(self):
        # No EntranceCode registered anywhere -- if the check applied, this would
        # be rejected as "unregistered." It must not apply at all when table is empty.
        result = await create_order(self._order_body(table=""), make_request(), db=self.db)
        self.assertEqual(result.code, 200)

    # ---- TEST 08: DiningSession creation rejects invalid table ----
    async def test_08_dining_session_resolve_rejects_unregistered_table(self):
        with self.assertRaises(ValueError):
            await DiningSessionService(self.db).resolve_session(tenant_id=TENANT_A, table_no="A99")
        self.assertEqual(await self._session_count(), 0)

    # ---- TEST 09: DiningSession creation rejects cross-tenant table ----
    async def test_09_dining_session_resolve_rejects_cross_tenant_table(self):
        self._add_table_code(TENANT_B, "A08")
        await self.db.commit()

        with self.assertRaises(ValueError):
            await DiningSessionService(self.db).resolve_session(tenant_id=TENANT_A, table_no="A08")
        self.assertEqual(await self._session_count(), 0)

    # ---- TEST 10: DiningSession creation succeeds for an active registered table ----
    async def test_10_dining_session_resolve_succeeds_for_active_table(self):
        self._add_table_code(TENANT_A, "A01")
        await self.db.commit()

        data = await DiningSessionService(self.db).resolve_session(tenant_id=TENANT_A, table_no="A01")
        self.assertTrue(data["dining_session_id"])
        self.assertEqual(await self._session_count(), 1)

    # ---- TEST 11: duplicate active codes for the same table must not raise ----
    async def test_11_duplicate_active_codes_do_not_raise(self):
        # Production has confirmed cases of more than one active table EntranceCode
        # for the same (tenant_id, table_no) pair (re-generated codes).
        self._add_table_code(TENANT_A, "A01", name="A01-v1")
        self._add_table_code(TENANT_A, "A01", name="A01-v2")
        await self.db.commit()

        order_result = await create_order(self._order_body(table="A01"), make_request(), db=self.db)
        self.assertEqual(order_result.code, 200)

        session_data = await DiningSessionService(self.db).resolve_session(tenant_id=TENANT_A, table_no="A01")
        self.assertTrue(session_data["dining_session_id"])

    # ---- TEST 12: order-creation-time authority applies even without dining_session_id ----
    async def test_12_order_authority_enforced_even_when_client_omits_dining_session_id(self):
        # This is the core P0 regression: the anonymous prepay/postpay path that
        # can (and, before this fix, did) omit dining_session_id entirely must
        # still be independently gated by table authority, not rely on session
        # validation alone.
        result = await create_order(
            self._order_body(table="A99", dining_session_id=None), make_request(), db=self.db
        )
        self.assertEqual(result.code, 400)
        self.assertEqual(await self._order_count(), 0)

    # ---- TEST 13: order against an existing valid session on a registered table ----
    async def test_13_order_with_existing_valid_session_succeeds(self):
        self._add_table_code(TENANT_A, "A01")
        await self.db.commit()

        identity = await DiningSessionService(self.db).resolve_session(
            tenant_id=TENANT_A, table_no="A01", client_id="dc_test"
        )
        await self.db.commit()

        result = await create_order(
            self._order_body(
                table="A01",
                dining_session_id=int(identity["dining_session_id"]),
                participant_token=identity["participant_token"],
            ),
            make_request(), db=self.db,
        )
        self.assertEqual(result.code, 200)

    # ---- TEST 14: forged session (existing tenant-scoped protection, must still hold) ----
    async def test_14_forged_session_from_another_tenant_still_rejected(self):
        # A08 must be registered for BOTH tenants here so this test isolates the
        # *session* mismatch check (orders.py's DiningSession.tenant_id == tenant_id
        # filter, pre-existing, not new) from the new table-authority check --
        # otherwise a rejection here wouldn't prove the old protection still works,
        # it would just prove the new check also fires.
        self._add_table_code(TENANT_A, "A08", name="A08-tenant-a")
        self._add_table_code(TENANT_B, "A08", name="A08-tenant-b")
        await self.db.commit()

        # Real session belongs to tenant B.
        b_identity = await DiningSessionService(self.db).resolve_session(
            tenant_id=TENANT_B, table_no="A08", client_id="dc_b"
        )
        await self.db.commit()

        # Attacker claims tenant A, but supplies tenant B's session id.
        result = await create_order(
            self._order_body(
                shop=TENANT_A, table="A08",
                dining_session_id=int(b_identity["dining_session_id"]),
                participant_token=b_identity["participant_token"],
            ),
            make_request(), db=self.db,
        )
        # A forged/stale table session is a recoverable session-identity conflict:
        # the canonical create-order response is 409, while the security invariant
        # is that the forged cross-tenant session is rejected and no Order persists.
        self.assertEqual(result.code, 409)
        # Only the legitimate tenant-B session exists; no cross-tenant order
        # should have been created against tenant A.
        orders = (await self.db.execute(select(Order))).scalars().all()
        self.assertEqual(len(orders), 0)


if __name__ == "__main__":
    unittest.main()
