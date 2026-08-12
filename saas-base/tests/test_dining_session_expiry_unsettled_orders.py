import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.dining import DiningSession
from app.models.entrance_code import EntranceCode
from app.models.order import Order
from app.models.tenant import Tenant
from app.services.dining_session_service import SESSION_EXPIRE_HOURS, DiningSessionService
from app.api.v1.orders import list_orders
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


def make_request(tenant_id=TENANT_A, token_type="merchant"):
    req = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/orders",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    req.state.tenant_id = tenant_id
    req.state.token_type = token_type
    if token_type == "merchant":
        req.state.role = "owner"
        req.state.account_id = None
    return req


class DiningSessionExpiryTestBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(
            tenant_id=TENANT_A, name="Test Restaurant", password_hash="x",
            status=True, is_open=True, payment_mode="postpay",
        )
        self.db.add(self.tenant)
        # P0-01: expiry-then-recreate (the "still expires as before" tests) now goes
        # through the new table-authority check before opening the replacement
        # session -- this suite is about expiry semantics, not table validity.
        self.db.add(EntranceCode(
            id=generate_snowflake_id(),
            tenant_id=TENANT_A, name="A9", scene="E000000000A9",
            table_no="A9", entry_type="table", status=1,
        ))
        await self.db.flush()
        await self.db.commit()

        self.service = DiningSessionService(self.db)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_stale_session(self, table_no="A9"):
        stale_time = datetime.utcnow() - timedelta(hours=SESSION_EXPIRE_HOURS + 1)
        session = DiningSession(
            tenant_id=TENANT_A, table_no=table_no, status="OPEN",
            active_key=f"{TENANT_A}:{table_no}", started_at=stale_time, last_activity_at=stale_time,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def _make_order(self, session, status, **overrides):
        defaults = dict(
            tenant_id=TENANT_A, table_no=session.table_no, dining_session_id=session.id,
            status=status, payment_status="unpaid", payment_mode="postpay", total=50.0,
            created_at=datetime.utcnow() - timedelta(days=1),
        )
        defaults.update(overrides)
        order = Order(**defaults)
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order


class SessionWithUnsettledOrdersIsNotSilentlyExpiredTest(DiningSessionExpiryTestBase):
    async def test_stale_session_with_no_orders_still_expires_as_before(self):
        session = await self._make_stale_session()

        result = await self.service._get_or_create_open_session(TENANT_A, session.table_no, datetime.utcnow())

        self.assertNotEqual(result.id, session.id)  # a fresh session was created instead
        await self.db.refresh(session)
        self.assertEqual(session.status, "EXPIRED")

    async def test_stale_session_with_only_settled_orders_still_expires(self):
        session = await self._make_stale_session()
        await self._make_order(session, "settled")

        result = await self.service._get_or_create_open_session(TENANT_A, session.table_no, datetime.utcnow())

        self.assertNotEqual(result.id, session.id)
        await self.db.refresh(session)
        self.assertEqual(session.status, "EXPIRED")

    async def test_stale_session_with_a_done_unsettled_order_is_kept_open(self):
        session = await self._make_stale_session()
        order = await self._make_order(session, "done")

        result = await self.service._get_or_create_open_session(TENANT_A, session.table_no, datetime.utcnow())

        self.assertEqual(result.id, session.id)
        await self.db.refresh(session)
        self.assertEqual(session.status, "OPEN")  # not silently expired

    async def test_stale_session_with_a_pending_payment_order_is_kept_open(self):
        session = await self._make_stale_session()
        await self._make_order(session, "pending_payment")

        result = await self.service._get_or_create_open_session(TENANT_A, session.table_no, datetime.utcnow())

        self.assertEqual(result.id, session.id)
        await self.db.refresh(session)
        self.assertEqual(session.status, "OPEN")


class MerchantOrderListSurfacesUnsettledDoneOrdersAcrossDaysTest(DiningSessionExpiryTestBase):
    async def test_yesterdays_done_order_appears_in_default_merchant_list(self):
        session = await self._make_stale_session()
        await self._make_order(session, "done", created_at=datetime.utcnow() - timedelta(days=1))

        result = await list_orders(make_request(), db=self.db)

        self.assertEqual(result.code, 200)
        statuses = [o["status"] for o in result.data]
        self.assertIn("done", statuses)

    async def test_yesterdays_settled_order_does_not_appear_by_default(self):
        session = await self._make_stale_session()
        await self._make_order(session, "settled", created_at=datetime.utcnow() - timedelta(days=1))

        result = await list_orders(make_request(), db=self.db)

        self.assertEqual(result.code, 200)
        self.assertEqual(result.data, [])


if __name__ == "__main__":
    unittest.main()
