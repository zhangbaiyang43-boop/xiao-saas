import asyncio
import unittest

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.tenant import Tenant
from app.services.customer_service import CustomerService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


class CreateCustomerIntegrityErrorRecoveryTest(unittest.IsolatedAsyncioTestCase):
    """create_customer() retries on IntegrityError, which can only actually come from a
    (tenant_id, openid) or (tenant_id, store_member_no) unique-index collision -- phone has
    no unique constraint at all. The recovery path used to check `phone` first and return
    whatever unrelated customer happened to match it, regardless of whether the real
    conflict was on openid. That let an attacker who merely knows a victim's phone number
    get the victim's account handed back to them (and then bind their own WeChat identity
    to it) any time an unrelated store_member_no race triggered the IntegrityError.
    """

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(
            tenant_id=TENANT_A,
            name="Test Restaurant",
            password_hash="x",
            status=True,
            is_open=True,
            payment_mode="postpay",
        )
        self.db.add(self.tenant)
        await self.db.flush()
        await self.db.commit()

        self.service = CustomerService(self.db)
        self.service.set_tenant_id(TENANT_A)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_integrity_error_recovery_matches_by_openid_not_by_unrelated_phone(self):
        # An unrelated existing customer who happens to own the phone number the caller
        # supplies. In the old buggy code this is exactly who got handed back.
        victim = await self.service.create_customer(
            tenant_id=TENANT_A,
            openid="victim-openid",
            name="victim",
            phone="13800000000",
        )
        # The customer whose openid actually collides -- this is who create_customer's
        # IntegrityError recovery is *supposed* to find.
        openid_owner = await self.service.create_customer(
            tenant_id=TENANT_A,
            openid="dup-openid",
            name="openid owner",
            phone="19999999999",
        )
        victim_id, openid_owner_id = victim.id, openid_owner.id

        # Attacker-controlled call: brand new WeChat identity ("dup-openid" forces the
        # IntegrityError), but claims the victim's phone number. create_customer's own
        # IntegrityError handling does a db.rollback(), which expires every object in the
        # session -- capture the ids we compare against beforehand rather than touching
        # `victim`/`openid_owner` again afterward.
        result = await self.service.create_customer(
            tenant_id=TENANT_A,
            openid="dup-openid",
            name="attacker claim",
            phone="13800000000",
        )
        result_id = result.id

        self.assertEqual(result_id, openid_owner_id)
        self.assertNotEqual(result_id, victim_id)


if __name__ == "__main__":
    unittest.main()
