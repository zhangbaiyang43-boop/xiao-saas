import asyncio
import unittest
from datetime import datetime

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.customer import Customer
from app.models.point_ledger import PointLedger
from app.models.tenant import Tenant
from app.services.membership_service import MembershipService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


class ReverseConsumptionSafetyTestBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(tenant_id=TENANT_A, name="Test Restaurant", password_hash="x", status=True, is_open=True)
        self.db.add(self.tenant)
        await self.db.flush()

        self.customer = Customer(
            id=generate_snowflake_id(), tenant_id=TENANT_A, openid="cust-openid",
            phone="13800000000", created_at=datetime.utcnow(),
        )
        self.db.add(self.customer)
        await self.db.flush()
        await self.db.commit()

        self.service = MembershipService(self.db)
        self.service.set_tenant_id(TENANT_A)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()


class ReverseConsumptionNeverGoesNegativeTest(ReverseConsumptionSafetyTestBase):
    async def test_reversal_clamps_to_current_balance_when_points_already_spent_elsewhere(self):
        consumption_id = 9001
        await self.service.apply_consumption(self.customer, 60.0, consumption_id=consumption_id)
        account = await self.service.get_account_by_customer(self.customer.id)
        earned = account.points_balance
        self.assertGreater(earned, 0)

        # Simulate those points having already been spent elsewhere (e.g. the automatic
        # points-milestone coupon redemption) before the refund/reversal happens.
        account.points_balance = 3
        await self.db.commit()

        result = await self.service.reverse_consumption(self.customer.id, 60.0, consumption_id=consumption_id)

        self.assertGreaterEqual(result.points_balance, 0)
        self.assertEqual(result.points_balance, 0)  # clamped to what was actually available (3), not earned-60

    async def test_reversal_deducts_full_amount_when_points_still_available(self):
        consumption_id = 9002
        await self.service.apply_consumption(self.customer, 60.0, consumption_id=consumption_id)
        account = await self.service.get_account_by_customer(self.customer.id)
        earned = account.points_balance
        self.assertGreater(earned, 0)

        result = await self.service.reverse_consumption(self.customer.id, 60.0, consumption_id=consumption_id)

        self.assertEqual(result.points_balance, 0)  # fully reversed, nothing was spent elsewhere

    async def test_consumption_totals_are_always_reversed_regardless_of_points(self):
        consumption_id = 9003
        await self.service.apply_consumption(self.customer, 60.0, consumption_id=consumption_id)

        result = await self.service.reverse_consumption(self.customer.id, 60.0, consumption_id=consumption_id)

        self.assertEqual(result.total_consumption, 0)
        self.assertEqual(result.yearly_consumption, 0)


class ReverseConsumptionIsIdempotentTest(ReverseConsumptionSafetyTestBase):
    async def test_calling_twice_for_the_same_consumption_only_deducts_once(self):
        consumption_id = 9101
        await self.service.apply_consumption(self.customer, 60.0, consumption_id=consumption_id)
        account = await self.service.get_account_by_customer(self.customer.id)
        earned = account.points_balance

        first = await self.service.reverse_consumption(self.customer.id, 60.0, consumption_id=consumption_id)
        self.assertEqual(first.points_balance, 0)
        self.assertEqual(first.total_consumption, 0)

        # Replay -- simulating a retried cancel/reject request after a crash/timeout.
        second = await self.service.reverse_consumption(self.customer.id, 60.0, consumption_id=consumption_id)

        self.assertEqual(second.points_balance, 0)  # not deducted a second time
        self.assertEqual(second.total_consumption, 0)  # not deducted a second time
        self.assertEqual(second.id, first.id)

    async def test_replay_writes_no_second_ledger_row(self):
        consumption_id = 9102
        await self.service.apply_consumption(self.customer, 60.0, consumption_id=consumption_id)

        await self.service.reverse_consumption(self.customer.id, 60.0, consumption_id=consumption_id)
        await self.service.reverse_consumption(self.customer.id, 60.0, consumption_id=consumption_id)

        from sqlalchemy import select

        result = await self.db.execute(
            select(PointLedger).filter(
                PointLedger.tenant_id == TENANT_A,
                PointLedger.customer_id == self.customer.id,
                PointLedger.event_type == "refund_reversal",
                PointLedger.ref_id == str(consumption_id),
            )
        )
        rows = result.scalars().all()
        self.assertEqual(len(rows), 1)

    async def test_idempotency_marker_is_written_even_when_zero_points_were_earned(self):
        # A consumption that earned 0 points (e.g. below the earn threshold) must still be
        # protected against being replayed and deducting total_consumption twice.
        consumption_id = 9103
        await self.service.apply_consumption(self.customer, 0.01, consumption_id=consumption_id)

        first = await self.service.reverse_consumption(self.customer.id, 0.01, consumption_id=consumption_id)
        second = await self.service.reverse_consumption(self.customer.id, 0.01, consumption_id=consumption_id)

        self.assertEqual(first.total_consumption, second.total_consumption)


if __name__ == "__main__":
    unittest.main()
