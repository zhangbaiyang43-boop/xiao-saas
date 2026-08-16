"""P0-16 Phase B2 -- durable settlement actor audit.

Covers B2-T08 (session settlement records actor), B2-T09 (orphan settlement
records actor -- both real orphan paths: settle_table's orphan branch and
update_order_status's non-table-settlement "settled" branch), and B2-T10
(a repeated/second settlement attempt preserves the first actor).

Order.completed_at remains the sole settlement-time field (Schema Gate
Section 70 froze this -- no new settled_at). Settlement is merchant/staff-
account-only in every reachable path (Schema Gate Section 29), so the actor
shape here is settled_by_account_id/settled_by_role -- not a polymorphic
actor_type triple.
"""

import asyncio
import unittest
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.api.v1.orders import OrderStatusUpdate, settle_table, update_order_status
from app.models.base import Base
from app.models.dining import DiningSession
from app.models.order import Order
from app.models.tenant import Tenant
from app.services.order_lifecycle_service import OrderLifecycleService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


class FakeRequest:
    def __init__(self, **state):
        self.state = SimpleNamespace(**state)


def make_merchant_request(tenant_id=TENANT_A, role="owner", account_id=None):
    return FakeRequest(tenant_id=tenant_id, token_type="merchant", role=role, account_id=account_id)


class SettlementAuditBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.tenant = Tenant(
            tenant_id=TENANT_A, name="Restaurant A", password_hash="x",
            status=True, is_open=True, payment_mode="postpay",
        )
        self.db.add(self.tenant)
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()


class SessionSettlementAuditTest(SettlementAuditBase):
    async def test_session_settlement_writes_staff_actor(self):
        # No current staff role holds PERM_FINANCE_SETTLE (owner-only, see
        # app/core/permissions.py ORDER_STATUS_PERMISSIONS["settled"]), so
        # this calls the service layer directly to prove the audit-write
        # logic itself is actor-generic, not hardcoded to the owner shape --
        # same reasoning as the termination audit's staff-cancel test.
        now = datetime.utcnow()
        session = DiningSession(
            tenant_id=TENANT_A, table_no="B01", status="OPEN",
            active_key=f"{TENANT_A}:B01", started_at=now, last_activity_at=now,
        )
        self.db.add(session)
        await self.db.flush()
        order = Order(
            tenant_id=TENANT_A, dining_session_id=session.id, table_no="B01",
            total="30.00", status="done", payment_status="paid", payment_mode="table_account",
        )
        self.db.add(order)
        await self.db.commit()

        service = OrderLifecycleService(self.db)
        service.set_tenant_id(TENANT_A)
        res = await service.settle_table(
            {"table_no": "B01", "dining_session_id": str(session.id)},
            closed_by="321", account_id=321, role="waiter",
        )
        self.assertEqual(res.code, 200, res.msg)

        await self.db.refresh(order)
        self.assertEqual(order.status, "settled")
        self.assertIsNotNone(order.completed_at)
        self.assertEqual(order.settled_by_account_id, 321)
        self.assertEqual(order.settled_by_role, "waiter")

    async def test_owner_session_settlement_writes_null_id_with_owner_role(self):
        now = datetime.utcnow()
        session = DiningSession(
            tenant_id=TENANT_A, table_no="B02", status="OPEN",
            active_key=f"{TENANT_A}:B02", started_at=now, last_activity_at=now,
        )
        self.db.add(session)
        await self.db.flush()
        order = Order(
            tenant_id=TENANT_A, dining_session_id=session.id, table_no="B02",
            total="30.00", status="done", payment_status="paid", payment_mode="table_account",
        )
        self.db.add(order)
        await self.db.commit()

        res = await settle_table(
            {"table_no": "B02", "dining_session_id": str(session.id)},
            make_merchant_request(role="owner", account_id=None),
            self.db,
        )
        self.assertEqual(res.code, 200, res.msg)

        await self.db.refresh(order)
        self.assertIsNone(order.settled_by_account_id)
        self.assertEqual(order.settled_by_role, "owner")


class OrphanSettlementAuditTest(SettlementAuditBase):
    async def test_settle_table_orphan_branch_writes_actor(self):
        order = Order(
            tenant_id=TENANT_A, dining_session_id=None, table_no="A05",
            total="25.00", status="done", payment_status="paid",
            payment_method="mock", source="h5",
        )
        self.db.add(order)
        await self.db.commit()

        # Service-level call for the same reason as test_session_settlement_writes_staff_actor
        # (no current staff role holds PERM_FINANCE_SETTLE).
        service = OrderLifecycleService(self.db)
        service.set_tenant_id(TENANT_A)
        res = await service.settle_table(
            {"table_no": "A05"}, closed_by="42", account_id=42, role="frontdesk",
        )
        self.assertEqual(res.code, 200, res.msg)

        await self.db.refresh(order)
        self.assertEqual(order.status, "settled")
        self.assertEqual(order.settled_by_account_id, 42)
        self.assertEqual(order.settled_by_role, "frontdesk")

    async def test_update_order_status_settled_branch_writes_actor(self):
        # payment_mode=prepay -> requires_table_settlement is False, so this
        # is a real, independent orphan-settlement path distinct from
        # settle_table.
        order = Order(
            tenant_id=TENANT_A, table_no="", status="done",
            payment_status="paid", payment_mode="prepay", total="19.90",
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)

        res = await update_order_status(
            str(order.id), OrderStatusUpdate(status="settled"),
            make_merchant_request(role="owner", account_id=None), db=self.db,
        )
        self.assertEqual(res.code, 200, res.msg)

        await self.db.refresh(order)
        self.assertEqual(order.status, "settled")
        self.assertIsNotNone(order.completed_at)
        self.assertIsNone(order.settled_by_account_id)
        self.assertEqual(order.settled_by_role, "owner")


class RepeatedSettlementPreservesAuditTest(SettlementAuditBase):
    async def test_second_settlement_attempt_preserves_first_actor(self):
        order = Order(
            tenant_id=TENANT_A, dining_session_id=None, table_no="A09",
            total="25.00", status="done", payment_status="paid",
            payment_method="mock", source="h5",
        )
        self.db.add(order)
        await self.db.commit()

        # Service-level call for the first (staff) settlement -- no current
        # staff role holds PERM_FINANCE_SETTLE, see the other tests in this
        # file for the same reasoning.
        service = OrderLifecycleService(self.db)
        service.set_tenant_id(TENANT_A)
        first = await service.settle_table(
            {"table_no": "A09"}, closed_by="11", account_id=11, role="waiter",
        )
        self.assertEqual(first.code, 200, first.msg)
        await self.db.refresh(order)
        self.assertEqual(order.settled_by_account_id, 11)
        original_completed_at = order.completed_at

        # A different actor retries settling the same (already-settled) table.
        # The orphan query excludes already-settled orders, so this
        # structurally cannot re-fire the write -- proving first-writer-wins
        # end to end, not just at the field-guard level.
        second = await settle_table(
            {"table_no": "A09"}, make_merchant_request(role="owner", account_id=None), self.db,
        )
        self.assertEqual(second.code, 404)  # nothing left to settle

        await self.db.refresh(order)
        self.assertEqual(order.settled_by_account_id, 11)
        self.assertEqual(order.settled_by_role, "waiter")
        self.assertEqual(order.completed_at, original_completed_at)


if __name__ == "__main__":
    unittest.main()
