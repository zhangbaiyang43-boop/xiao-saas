"""P0-10 FINAL SESSION-AUTHORITY RECONCILIATION.

settle-table must require an EXACT dining_session_id from every remote
(merchant/Admin) caller. Omitting it and letting the server infer "whichever
session is currently open at this table" from tenant_id+table_no is exactly
the table-only inference this whole P0-10 effort exists to eliminate -- a
stale Admin page (or a lost-response retry) that never learned the table
turned over could otherwise settle a DIFFERENT, later guest generation's
bill without ever being told to.

S0 is the pre-fix verification proof (kept as a permanent regression once
fixed -- it now proves the FIXED behavior, i.e. that omitting the id is
denied). S01-S05 are the full negative/positive matrix.
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

TENANT = "tenant-p0-10-settle-required"
TABLE = "T03"
OTHER_TABLE = "T08"


class FakeRequest:
    def __init__(self, **state):
        self.state = SimpleNamespace(**state)


def make_merchant_request(tenant_id=TENANT):
    return FakeRequest(tenant_id=tenant_id, token_type="merchant", role="owner", account_id=None)


class SettleTableSessionRequiredTest(unittest.IsolatedAsyncioTestCase):
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

    async def _make_order(self, session, *, status="done", total="30.00"):
        order = Order(
            tenant_id=TENANT, dining_session_id=session.id, table_no=session.table_no,
            total=total, status=status, payment_status="paid", payment_method="mock",
            payment_mode="table_account", source="h5",
        )
        self.db.add(order)
        await self.db.flush()
        self.db.add(OrderItem(id=generate_snowflake_id(), order_id=order.id, name="宫保鸡丁", price=total, qty=1))
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def _status_of(self, session_id):
        result = await self.db.execute(select(DiningSession).where(DiningSession.id == session_id))
        return result.scalar_one().status

    # ---- S0: the exact blocker-verification scenario from the prompt ----
    async def test_s0_settle_without_session_id_must_be_denied_not_infer_current_table_session(self):
        sa = await self._make_session(status="CLOSED", active_key=None)
        await self._make_order(sa, status="settled")

        sb = await self._make_session(status="OPEN", active_key=f"{TENANT}:{TABLE}")
        b1 = await self._make_order(sb, status="done")

        res = await settle_table({"table_no": TABLE}, make_merchant_request(), self.db)

        self.assertIn(res.code, (400, 409))
        self.assertEqual(await self._status_of(sb.id), "OPEN")
        await self.db.refresh(b1)
        self.assertEqual(b1.status, "done")

    # ---- S01: same scenario, explicit contract name ----
    async def test_s01_missing_session_id_denied_sb_unchanged(self):
        sa = await self._make_session(status="CLOSED", active_key=None)
        await self._make_order(sa, status="settled")
        sb = await self._make_session(status="OPEN", active_key=f"{TENANT}:{TABLE}")
        b1 = await self._make_order(sb, status="done")

        res = await settle_table({"table_no": TABLE}, make_merchant_request(), self.db)

        self.assertIn(res.code, (400, 409))
        self.assertEqual(res.data.get("code"), "DINING_SESSION_REQUIRED_FOR_SETTLEMENT")
        self.assertEqual(await self._status_of(sb.id), "OPEN")
        await self.db.refresh(b1)
        self.assertEqual(b1.status, "done")

    # ---- S02: stale SA id supplied -> denied, SB unchanged ----
    async def test_s02_stale_sa_session_id_denied_sb_unchanged(self):
        sa = await self._make_session(status="CLOSED", active_key=None)
        await self._make_order(sa, status="settled")
        sb = await self._make_session(status="OPEN", active_key=f"{TENANT}:{TABLE}")
        b1 = await self._make_order(sb, status="done")

        res = await settle_table({"table_no": TABLE, "dining_session_id": str(sa.id)}, make_merchant_request(), self.db)

        self.assertEqual(res.code, 409)
        self.assertEqual(await self._status_of(sb.id), "OPEN")
        await self.db.refresh(b1)
        self.assertEqual(b1.status, "done")

    # ---- S03: exact SB id -> success, only SB settled ----
    async def test_s03_current_sb_session_id_succeeds_settles_only_sb(self):
        sa = await self._make_session(status="CLOSED", active_key=None)
        await self._make_order(sa, status="settled")
        sb = await self._make_session(status="OPEN", active_key=f"{TENANT}:{TABLE}")
        b1 = await self._make_order(sb, status="done")

        res = await settle_table({"table_no": TABLE, "dining_session_id": str(sb.id)}, make_merchant_request(), self.db)

        self.assertEqual(res.code, 200, res.msg)
        self.assertEqual(res.data["settled_count"], 1)
        self.assertEqual(await self._status_of(sb.id), "CLOSED")
        self.assertEqual(await self._status_of(sa.id), "CLOSED")  # unchanged, was already closed

    # ---- S04: session id belongs to a DIFFERENT table -> denied ----
    async def test_s04_session_id_for_different_table_denied(self):
        other = await self._make_session(status="OPEN", table_no=OTHER_TABLE, active_key=f"{TENANT}:{OTHER_TABLE}")
        await self._make_order(other, status="done")

        res = await settle_table({"table_no": TABLE, "dining_session_id": str(other.id)}, make_merchant_request(), self.db)

        self.assertEqual(res.code, 409)
        self.assertEqual(await self._status_of(other.id), "OPEN")

    # ---- S05: THE MOST IMPORTANT RETRY TEST -- lost-response retry of an already-settled SA must never reach SB ----
    async def test_s05_retry_of_already_settled_sa_never_touches_sb(self):
        sa = await self._make_session(status="OPEN", active_key=f"{TENANT}:{TABLE}")
        a1 = await self._make_order(sa, status="done")

        first = await settle_table({"table_no": TABLE, "dining_session_id": str(sa.id)}, make_merchant_request(), self.db)
        self.assertEqual(first.code, 200, first.msg)
        self.assertEqual(await self._status_of(sa.id), "CLOSED")

        # SB opens for the next guest generation at the same table.
        sb = await self._make_session(status="OPEN", active_key=f"{TENANT}:{TABLE}")
        b1 = await self._make_order(sb, status="done")

        # client never saw the first response (network drop) and retries the EXACT same request.
        retry = await settle_table({"table_no": TABLE, "dining_session_id": str(sa.id)}, make_merchant_request(), self.db)

        self.assertNotEqual(retry.code, 200)
        self.assertEqual(await self._status_of(sb.id), "OPEN")
        await self.db.refresh(b1)
        self.assertEqual(b1.status, "done")

    # ---- wrong tenant: session id belongs to a different tenant entirely ----
    async def test_wrong_tenant_session_id_denied(self):
        other_tenant_session = DiningSession(
            tenant_id="tenant-someone-else", table_no=TABLE, status="OPEN",
            active_key="tenant-someone-else:" + TABLE, started_at=datetime.utcnow(), last_activity_at=datetime.utcnow(),
        )
        self.db.add(other_tenant_session)
        await self.db.commit()
        await self.db.refresh(other_tenant_session)

        res = await settle_table(
            {"table_no": TABLE, "dining_session_id": str(other_tenant_session.id)},
            make_merchant_request(tenant_id=TENANT), self.db,
        )

        self.assertIn(res.code, (403, 404, 409))
        result = await self.db.execute(select(DiningSession).where(DiningSession.id == other_tenant_session.id))
        self.assertEqual(result.scalar_one().status, "OPEN")


if __name__ == "__main__":
    unittest.main()
