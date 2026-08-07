import asyncio
import unittest

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.tenant import Tenant
from app.services.customer_identity_service import (
    CHANNEL_MINIAPP,
    CustomerIdentityService,
    JoinResolutionOutcome,
)
from app.services.customer_service import CustomerService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


class ResolveCustomerForJoinTest(unittest.IsolatedAsyncioTestCase):
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

        self.customer_service = CustomerService(self.db)
        self.customer_service.set_tenant_id(TENANT_A)
        self.identity_service = CustomerIdentityService(self.db)
        self.identity_service.set_tenant_id(TENANT_A)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _identity_customer_id(self, channel_user_id: str):
        identity = await self.identity_service.get_by_identity(CHANNEL_MINIAPP, channel_user_id)
        return identity.customer_id if identity else None

    async def test_brand_new_phone_and_openid_creates_customer(self):
        resolution = await self.identity_service.resolve_customer_for_join(
            phone="13911112222",
            phone_verified=False,
            openid="brand-new-openid",
            unionid=None,
            auto_member_name="会员2222",
        )

        self.assertEqual(resolution.outcome, JoinResolutionOutcome.SUCCESS)
        self.assertTrue(resolution.is_new_customer)
        self.assertIsNotNone(resolution.customer)
        self.assertEqual(resolution.customer.phone, "13911112222")
        self.assertEqual(await self._identity_customer_id("brand-new-openid"), resolution.customer.id)

    async def test_verified_phone_rebinds_existing_account(self):
        existing = await self.customer_service.create_customer(
            tenant_id=TENANT_A,
            openid="victim-openid",
            name="victim",
            phone="13800000000",
            tags=["小程序会员"],
        )
        await self.identity_service.bind_identity(
            customer_id=existing.id,
            channel=CHANNEL_MINIAPP,
            channel_user_id="victim-openid",
            phone="13800000000",
        )
        await self.db.commit()

        resolution = await self.identity_service.resolve_customer_for_join(
            phone="13800000000",
            phone_verified=True,
            openid="victim-new-device-openid",
            unionid=None,
            auto_member_name="会员0000",
        )

        self.assertEqual(resolution.outcome, JoinResolutionOutcome.SUCCESS)
        self.assertFalse(resolution.is_new_customer)
        self.assertEqual(resolution.customer.id, existing.id)
        self.assertEqual(await self._identity_customer_id("victim-new-device-openid"), existing.id)

    async def test_unverified_phone_matching_existing_account_is_blocked(self):
        existing = await self.customer_service.create_customer(
            tenant_id=TENANT_A,
            openid="victim-openid",
            name="victim",
            phone="13800000000",
            tags=["小程序会员"],
        )
        await self.identity_service.bind_identity(
            customer_id=existing.id,
            channel=CHANNEL_MINIAPP,
            channel_user_id="victim-openid",
            phone="13800000000",
        )
        await self.db.commit()

        resolution = await self.identity_service.resolve_customer_for_join(
            phone="13800000000",
            phone_verified=False,
            openid="attacker-openid",
            unionid=None,
            auto_member_name="会员0000",
        )

        self.assertEqual(resolution.outcome, JoinResolutionOutcome.UNVERIFIED_PHONE_BLOCKED)
        self.assertEqual(resolution.blocked_customer_id, existing.id)
        self.assertIsNone(await self._identity_customer_id("attacker-openid"))
        self.assertEqual(await self._identity_customer_id("victim-openid"), existing.id)

    async def test_openid_conflict_uses_phone_prefixed_customer_openid(self):
        other = await self.customer_service.create_customer(
            tenant_id=TENANT_A,
            openid="occupied-openid",
            name="other",
            phone="13700000001",
            tags=["小程序会员"],
        )
        await self.db.commit()

        resolution = await self.identity_service.resolve_customer_for_join(
            phone="13600000002",
            phone_verified=False,
            openid="occupied-openid",
            unionid=None,
            auto_member_name="会员0002",
        )

        self.assertEqual(resolution.outcome, JoinResolutionOutcome.SUCCESS)
        self.assertTrue(resolution.is_new_customer)
        self.assertEqual(resolution.openid_conflict_existing_id, other.id)
        self.assertEqual(resolution.customer.openid, "phone:13600000002")
        self.assertNotEqual(resolution.customer.id, other.id)
        self.assertEqual(await self._identity_customer_id("occupied-openid"), resolution.customer.id)


if __name__ == "__main__":
    unittest.main()
