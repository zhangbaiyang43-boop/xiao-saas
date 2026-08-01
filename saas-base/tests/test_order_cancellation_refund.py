import asyncio
import unittest
from datetime import datetime

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.dining import DiningParticipant, DiningSession
from app.models.order import Order
from app.models.tenant import Tenant
from app.api.v1.orders import cancel_order
from app.services.dining_session_service import hash_participant_token

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"
REAL_TOKEN = "guest-token-real-owner"
WRONG_TOKEN = "guest-token-someone-else"


def make_request(customer_id=None, path="/api/v1/orders/1/cancel"):
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
    if customer_id is not None:
        req.state.customer_id = customer_id
    return req


class OrderCancellationOwnershipTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(tenant_id=TENANT_A, name="Test Restaurant", password_hash="x", status=True, is_open=True)
        self.db.add(self.tenant)
        await self.db.flush()

        now = datetime.utcnow()
        self.session = DiningSession(
            tenant_id=TENANT_A, table_no="A12", status="OPEN",
            active_key=f"{TENANT_A}:A12", started_at=now, last_activity_at=now,
        )
        self.db.add(self.session)
        await self.db.flush()

        self.participant = DiningParticipant(
            tenant_id=TENANT_A, session_id=self.session.id,
            guest_token_hash=hash_participant_token(REAL_TOKEN),
            joined_at=now, last_active_at=now,
        )
        self.db.add(self.participant)
        await self.db.flush()
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_order(self, *, customer_id=None, participant_id=None, status="pending"):
        order = Order(
            tenant_id=TENANT_A, customer_id=customer_id, participant_id=participant_id,
            dining_session_id=self.session.id, table_no="A12", total="28.00",
            status=status, payment_status="unpaid", payment_mode="postpay",
        )
        self.db.add(order)
        await self.db.commit()
        return order

    # ---- Finding C: anonymous (no customer_id) orders must still require proof of ownership ----

    async def test_anonymous_order_cannot_be_cancelled_without_any_token(self):
        order = await self._make_order(participant_id=self.participant.id)
        result = await cancel_order(str(order.id), make_request(), participant_token=None, db=self.db)
        self.assertEqual(result.code, 403)
        await self.db.refresh(order)
        self.assertEqual(order.status, "pending")

    async def test_anonymous_order_cannot_be_cancelled_with_someone_elses_token(self):
        order = await self._make_order(participant_id=self.participant.id)
        result = await cancel_order(str(order.id), make_request(), participant_token=WRONG_TOKEN, db=self.db)
        self.assertEqual(result.code, 403)
        await self.db.refresh(order)
        self.assertEqual(order.status, "pending")

    async def test_anonymous_order_can_be_cancelled_by_its_own_participant_token(self):
        order = await self._make_order(participant_id=self.participant.id)
        result = await cancel_order(str(order.id), make_request(), participant_token=REAL_TOKEN, db=self.db)
        self.assertEqual(result.code, 200)
        await self.db.refresh(order)
        self.assertEqual(order.status, "cancelled")

    # ---- Regression: pre-existing logged-in-customer ownership check still works ----

    async def test_logged_in_customer_order_rejects_mismatched_customer(self):
        order = await self._make_order(customer_id=111)
        result = await cancel_order(str(order.id), make_request(customer_id=222), participant_token=None, db=self.db)
        self.assertEqual(result.code, 403)

    async def test_logged_in_customer_can_cancel_own_order(self):
        order = await self._make_order(customer_id=111)
        result = await cancel_order(str(order.id), make_request(customer_id=111), participant_token=None, db=self.db)
        self.assertEqual(result.code, 200)


if __name__ == "__main__":
    unittest.main()
