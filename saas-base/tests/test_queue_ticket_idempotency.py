"""Bug fix: a customer re-opening the mini-program queue-take page (without their
ticket ever being called/seated/cancelled) used to get a brand-new ticket on every
tap of "排队取号", silently abandoning their real place in line. create_ticket()
must be idempotent per (tenant_id, customer identity) while a ticket is still
active ("waiting"/"called"); staff-created walk-in tickets carry no customer
identity and must be unaffected (each call always creates a fresh ticket)."""

import asyncio
import unittest
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.queue_ticket import QueueTicket
from app.services.queue_service import QueueService, generate_queue_query_token

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


class QueueTicketIdempotencyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.service = QueueService(self.db)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _tickets_for_tenant(self):
        result = await self.db.execute(select(QueueTicket).where(QueueTicket.tenant_id == TENANT_A))
        return list(result.scalars().all())

    async def test_repeated_create_by_customer_id_returns_same_ticket(self):
        first, _ = await self.service.create_ticket(TENANT_A, party_size=2, phone=None, note=None, customer_id=42)
        second, _ = await self.service.create_ticket(TENANT_A, party_size=2, phone=None, note=None, customer_id=42)

        self.assertEqual(first.id, second.id)
        self.assertEqual(len(await self._tickets_for_tenant()), 1)

    async def test_repeated_create_by_openid_returns_same_ticket(self):
        first, _ = await self.service.create_ticket(TENANT_A, party_size=2, phone=None, note=None, openid="wx-openid-1")
        second, _ = await self.service.create_ticket(TENANT_A, party_size=2, phone=None, note=None, openid="wx-openid-1")

        self.assertEqual(first.id, second.id)
        self.assertEqual(len(await self._tickets_for_tenant()), 1)

    async def test_new_ticket_created_once_previous_one_is_no_longer_active(self):
        first, _ = await self.service.create_ticket(TENANT_A, party_size=2, phone=None, note=None, customer_id=42)
        first.status = "seated"
        await self.db.commit()

        second, _ = await self.service.create_ticket(TENANT_A, party_size=2, phone=None, note=None, customer_id=42)

        self.assertNotEqual(first.id, second.id)
        self.assertEqual(len(await self._tickets_for_tenant()), 2)

    async def test_staff_walk_in_tickets_without_customer_identity_are_never_deduped(self):
        first, _ = await self.service.create_ticket(TENANT_A, party_size=2, phone="13800000000", note=None)
        second, _ = await self.service.create_ticket(TENANT_A, party_size=2, phone="13800000000", note=None)

        self.assertNotEqual(first.id, second.id)
        self.assertEqual(len(await self._tickets_for_tenant()), 2)

    async def test_find_active_ticket_for_customer_matches_by_customer_id_first(self):
        ticket = QueueTicket(
            tenant_id=TENANT_A, queue_no="A001", queue_type="A", queue_date=date.today(),
            daily_sequence=1, query_token=generate_queue_query_token(), party_size=2,
            status="waiting", customer_id=42, openid="wx-openid-1",
        )
        self.db.add(ticket)
        await self.db.commit()

        found = await self.service.find_active_ticket_for_customer(TENANT_A, customer_id=42)
        self.assertEqual(found.id, ticket.id)

        found_by_openid = await self.service.find_active_ticket_for_customer(TENANT_A, openid="wx-openid-1")
        self.assertEqual(found_by_openid.id, ticket.id)

    async def test_find_active_ticket_for_customer_returns_none_without_identity(self):
        found = await self.service.find_active_ticket_for_customer(TENANT_A)
        self.assertIsNone(found)


if __name__ == "__main__":
    unittest.main()
