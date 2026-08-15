"""P0-10 Phase B: settle-table must target an EXACT dining session, not infer
"whichever session is currently open at this table" from tenant_id+table_no
alone. A stale Admin page holding session SA's id must never be able to settle
a DIFFERENT, later session SB that has since opened at the same physical
table -- and the settle response must carry an authoritative snapshot of what
was actually settled, so the client can never build a receipt from its own
pre-click cache.

Covers R01 (stale SA settle vs current SB), R02/R03 (receipt authority), and
the P0-10-01 explicit status=="OPEN" regression for the legacy (no
dining_session_id) inference path.
"""

import asyncio
import unittest
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.api.v1.orders import settle_table
from app.models.base import Base
from app.models.dining import DiningSession
from app.models.order import Order, OrderItem
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT = "tenant-p0-10-settle"
TABLE = "T03"


class FakeRequest:
    def __init__(self, **state):
        self.state = SimpleNamespace(**state)


def make_merchant_request(tenant_id=TENANT):
    return FakeRequest(tenant_id=tenant_id, token_type="merchant", role="owner", account_id=None)


class SettleTableSessionAuthorityTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_session(self, *, status="OPEN", table_no=TABLE, active_key=None):
        now = datetime.utcnow()
        session = DiningSession(
            tenant_id=TENANT, table_no=table_no, status=status,
            active_key=active_key, started_at=now, last_activity_at=now,
            closed_at=now if status != "OPEN" else None,
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def _make_order(self, session, *, status="done", total="30.00", item_name="宫保鸡丁"):
        order = Order(
            tenant_id=TENANT, dining_session_id=session.id, table_no=session.table_no,
            total=total, status=status, payment_status="paid", payment_method="mock",
            payment_mode="table_account", source="h5",
        )
        self.db.add(order)
        await self.db.flush()
        self.db.add(OrderItem(id=generate_snowflake_id(), order_id=order.id, name=item_name, price=total, qty=1))
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def _count_status(self, table_no=TABLE):
        result = await self.db.execute(select(DiningSession).where(DiningSession.table_no == table_no))
        return {s.id: s.status for s in result.scalars().all()}

    # ---- R01: stale SA id must never settle current SB ----
    async def test_r01_stale_sa_id_cannot_settle_current_sb(self):
        sa = await self._make_session(status="CLOSED", active_key=None)
        await self._make_order(sa, status="settled")  # SA's own history, already settled

        sb = await self._make_session(status="OPEN", active_key=f"{TENANT}:{TABLE}")
        b1 = await self._make_order(sb, status="done")

        # stale Admin page still holds SA's id
        res = await settle_table(
            {"table_no": TABLE, "dining_session_id": str(sa.id)},
            make_merchant_request(), self.db,
        )

        self.assertEqual(res.code, 409, res.msg)
        statuses = await self._count_status()
        self.assertEqual(statuses[sb.id], "OPEN")  # SB untouched, still open
        await self.db.refresh(b1)
        self.assertEqual(b1.status, "done")  # SB's order untouched

    # ---- exact-id happy path: settling the CURRENT session by its real id works ----
    async def test_exact_current_session_id_settles_successfully(self):
        sb = await self._make_session(status="OPEN", active_key=f"{TENANT}:{TABLE}")
        b1 = await self._make_order(sb, status="done", total="30.00")
        b2 = await self._make_order(sb, status="done", total="12.00")

        res = await settle_table(
            {"table_no": TABLE, "dining_session_id": str(sb.id)},
            make_merchant_request(), self.db,
        )

        self.assertEqual(res.code, 200, res.msg)
        self.assertEqual(res.data["settled_count"], 2)
        statuses = await self._count_status()
        self.assertEqual(statuses[sb.id], "CLOSED")

    # ---- R02/R03: response must carry an authoritative settled-order snapshot ----
    async def test_settle_response_carries_authoritative_order_snapshot(self):
        sb = await self._make_session(status="OPEN", active_key=f"{TENANT}:{TABLE}")
        await self._make_order(sb, status="done", total="30.00", item_name="宫保鸡丁")
        await self._make_order(sb, status="done", total="12.00", item_name="米饭")

        res = await settle_table(
            {"table_no": TABLE, "dining_session_id": str(sb.id)},
            make_merchant_request(), self.db,
        )

        self.assertEqual(res.code, 200, res.msg)
        self.assertEqual(res.data.get("dining_session_id"), str(sb.id))
        snapshot = res.data.get("settled_orders")
        self.assertIsNotNone(snapshot, "settle-table response must include an authoritative settled_orders snapshot")
        self.assertEqual(len(snapshot), 2)
        names = sorted(item["name"] for order in snapshot for item in order["items"])
        self.assertEqual(names, ["宫保鸡丁", "米饭"])
        totals = sorted(float(order["total"]) for order in snapshot)
        self.assertEqual(totals, [12.0, 30.0])

    # ---- P0-10-01 regression: legacy (no dining_session_id) path must not settle a CLOSED session's leftovers ----
    async def test_legacy_no_session_id_path_still_requires_status_open(self):
        sa = await self._make_session(status="CLOSED", active_key=None)
        # SA has a stray non-terminal order that was never cleaned up (shouldn't
        # happen given other invariants, but this test proves the query itself
        # doesn't silently pick it up if it ever did).
        await self._make_order(sa, status="done")

        res = await settle_table({"table_no": TABLE}, make_merchant_request(), self.db)

        # No OPEN session exists for this table and no orphan (dining_session_id
        # IS NULL) orders exist either -- must be a clean 404, never a silent
        # settle of the CLOSED session's leftover order.
        self.assertEqual(res.code, 404, res.msg)
        statuses = await self._count_status()
        self.assertEqual(statuses[sa.id], "CLOSED")

    # ---- requested session belongs to a different table: denied, not silently retargeted ----
    async def test_session_id_for_a_different_table_is_denied(self):
        other_table_session = await self._make_session(status="OPEN", table_no="T09", active_key=f"{TENANT}:T09")
        await self._make_order(other_table_session, status="done")

        res = await settle_table(
            {"table_no": TABLE, "dining_session_id": str(other_table_session.id)},
            make_merchant_request(), self.db,
        )

        self.assertEqual(res.code, 409, res.msg)
        statuses = await self._count_status(table_no="T09")
        self.assertEqual(statuses[other_table_session.id], "OPEN")


if __name__ == "__main__":
    unittest.main()
