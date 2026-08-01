import asyncio
import inspect
import unittest
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.queue_ticket import QueueTicket
from app.services.queue_service import QueueCallBlocked, QueueService, generate_queue_query_token

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


class CallNextLockingTest(unittest.IsolatedAsyncioTestCase):
    """call_next used to pick the earliest "waiting" ticket with a plain, unlocked SELECT.
    Two concurrent calls (two front-desk terminals, or a double-tap) could both read the
    same earliest ticket before either committed, both mark it "called", and the real next
    ticket in line would never get called at all. Real concurrent-transaction proof against
    SQLite isn't possible here (see test_coupon_redis_fallback_idempotency.py for why -- same
    limitation, this repo's precedent for documenting it). What IS verified: the read is now
    a locking read (with_for_update, the same mechanism this codebase already relies on for
    equivalent races elsewhere), and single-threaded correctness is unaffected."""

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

    async def _make_ticket(self, seq: int, status: str = "waiting", queue_type: str = "A"):
        ticket = QueueTicket(
            tenant_id=TENANT_A, queue_no=f"{queue_type}{seq:03d}", queue_type=queue_type,
            queue_date=date.today(), daily_sequence=seq, query_token=generate_queue_query_token(),
            party_size=2, status=status,
        )
        self.db.add(ticket)
        await self.db.flush()
        return ticket

    async def test_call_next_read_is_a_locking_read(self):
        source = inspect.getsource(QueueService.call_next)
        waiting_query = source[source.index('QueueTicket.status == "waiting"'):]
        self.assertIn("with_for_update()", waiting_query[:waiting_query.index("ticket = result")])

    async def test_calls_earliest_waiting_ticket_first(self):
        first = await self._make_ticket(1)
        await self._make_ticket(2)

        called = await self.service.call_next(TENANT_A, "A")

        self.assertEqual(called.id, first.id)
        self.assertEqual(called.status, "called")

    async def test_raises_when_a_ticket_is_already_called(self):
        await self._make_ticket(1, status="called")
        await self._make_ticket(2)

        with self.assertRaises(QueueCallBlocked):
            await self.service.call_next(TENANT_A, "A")

    async def test_second_sequential_call_moves_to_the_next_waiting_ticket(self):
        first = await self._make_ticket(1)
        second = await self._make_ticket(2)
        called_first = await self.service.call_next(TENANT_A, "A")
        self.assertEqual(called_first.id, first.id)

        # Seat/skip the first before calling next again, same as the real flow requires.
        called_first.status = "seated"
        await self.db.commit()

        called_second = await self.service.call_next(TENANT_A, "A")
        self.assertEqual(called_second.id, second.id)

    async def test_different_queue_types_do_not_interfere(self):
        a_ticket = await self._make_ticket(1, queue_type="A")
        b_ticket = await self._make_ticket(1, queue_type="B")

        called_a = await self.service.call_next(TENANT_A, "A")
        called_b = await self.service.call_next(TENANT_A, "B")

        self.assertEqual(called_a.id, a_ticket.id)
        self.assertEqual(called_b.id, b_ticket.id)


if __name__ == "__main__":
    unittest.main()
