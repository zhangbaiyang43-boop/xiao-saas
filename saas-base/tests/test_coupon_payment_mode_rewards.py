import asyncio
import unittest
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.config import settings
from app.models.base import Base
from app.models.coupon import Coupon
from app.models.customer import Customer
from app.models.dining import DiningParticipant, DiningSession
from app.models.order import Order
from app.models.tenant import Tenant
from app.api.v1.orders import settle_table, update_order_status, OrderStatusUpdate

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


def make_merchant_request(tenant_id=TENANT_A, path="/api/v1/orders/settle-table"):
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
    req.state.tenant_id = tenant_id
    req.state.token_type = "merchant"
    req.state.user_id = "staff-1"
    # get_request_principal() requires role=="owner" for an account_id-less merchant
    # request (see app/middleware/auth_middleware.py:127-142, which is what a real
    # request gets from AuthMiddleware) -- this fixture predates that check.
    req.state.role = "owner"
    req.state.account_id = None
    return req


class CouponPaymentModeRewardsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._original_redis_enabled = settings.REDIS_ENABLED
        settings.REDIS_ENABLED = False

        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(
            tenant_id=TENANT_A, name="Test Restaurant", password_hash="x",
            status=True, is_open=True, payment_mode="table_account",
        )
        self.db.add(self.tenant)
        self.customer = Customer(tenant_id=TENANT_A, openid="openid-1", status=1)
        self.db.add(self.customer)
        await self.db.commit()

    async def asyncTearDown(self):
        settings.REDIS_ENABLED = self._original_redis_enabled
        await self.db.close()
        await self.engine.dispose()

    async def _unused_coupon_count(self, customer_id):
        result = await self.db.execute(
            select(func.count()).select_from(Coupon).where(
                Coupon.tenant_id == TENANT_A, Coupon.customer_id == customer_id, Coupon.status == "UNUSED",
            )
        )
        return int(result.scalar() or 0)

    async def _make_table_account_order(self, customer_id, status="done"):
        now = datetime.utcnow()
        session = DiningSession(
            tenant_id=TENANT_A, table_no="A1", status="OPEN",
            active_key=f"{TENANT_A}:A1:{customer_id}:{status}", started_at=now, last_activity_at=now,
        )
        self.db.add(session)
        await self.db.flush()
        participant = DiningParticipant(
            tenant_id=TENANT_A, session_id=session.id, customer_id=customer_id, joined_at=now, last_active_at=now,
        )
        self.db.add(participant)
        await self.db.flush()
        order = Order(
            tenant_id=TENANT_A, customer_id=customer_id, dining_session_id=session.id, participant_id=participant.id,
            table_no="A1", total="30.00", status=status, payment_status="unpaid", payment_mode="table_account",
        )
        self.db.add(order)
        await self.db.commit()
        return session, order

    async def test_table_account_settlement_issues_new_customer_coupon_on_first_paid_order(self):
        self.assertEqual(await self._unused_coupon_count(self.customer.id), 0)
        session, order = await self._make_table_account_order(self.customer.id)

        result = await settle_table({"table_no": "A1", "dining_session_id": str(session.id)}, make_merchant_request(), db=self.db)
        self.assertEqual(result.code, 200)
        self.assertEqual(await self._unused_coupon_count(self.customer.id), 1)

    async def test_table_account_settlement_issues_consumption_coupon_on_return_visit(self):
        # First visit: settle once, use up the resulting UNUSED coupon so the dedup check
        # on the second visit doesn't just skip because "still holding one unused".
        session1, order1 = await self._make_table_account_order(self.customer.id)
        await settle_table({"table_no": "A1", "dining_session_id": str(session1.id)}, make_merchant_request(), db=self.db)
        first_coupon_result = await self.db.execute(
            select(Coupon).where(Coupon.tenant_id == TENANT_A, Coupon.customer_id == self.customer.id)
        )
        first_coupon = first_coupon_result.scalars().first()
        first_coupon.status = "USED"
        await self.db.commit()

        session2, order2 = await self._make_table_account_order(self.customer.id)
        result = await settle_table({"table_no": "A1", "dining_session_id": str(session2.id)}, make_merchant_request(), db=self.db)
        self.assertEqual(result.code, 200)

        templates_result = await self.db.execute(select(Coupon).where(Coupon.customer_id == self.customer.id))
        all_coupons = templates_result.scalars().all()
        self.assertEqual(len(all_coupons), 2)

    async def test_anonymous_table_account_order_does_not_crash_and_issues_nothing(self):
        session, order = await self._make_table_account_order(None)
        result = await settle_table({"table_no": "A1", "dining_session_id": str(session.id)}, make_merchant_request(), db=self.db)
        self.assertEqual(result.code, 200)
        self.assertEqual(await self._unused_coupon_count(self.customer.id), 0)

    async def test_postpay_order_settled_directly_via_update_order_status_also_issues_reward(self):
        self.tenant.payment_mode = "postpay"
        await self.db.commit()

        now = datetime.utcnow()
        order = Order(
            tenant_id=TENANT_A, customer_id=self.customer.id, table_no="B2", total="25.00",
            status="done", payment_status="unpaid", payment_mode="postpay",
        )
        self.db.add(order)
        await self.db.commit()

        result = await update_order_status(
            str(order.id), OrderStatusUpdate(status="settled"), make_merchant_request(), db=self.db,
        )
        self.assertEqual(result.code, 200)
        self.assertEqual(await self._unused_coupon_count(self.customer.id), 1)


if __name__ == "__main__":
    unittest.main()
