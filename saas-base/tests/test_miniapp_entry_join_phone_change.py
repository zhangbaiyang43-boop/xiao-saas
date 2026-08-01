import asyncio
import unittest
from unittest.mock import patch

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.tenant import Tenant
from app.api.v1.miniapp import entry_join
from app.schemas.miniapp import EntryJoinRequest
from app.services.customer_service import CustomerService
from app.services.customer_identity_service import CHANNEL_MINIAPP, CustomerIdentityService
from app.services.membership_service import MembershipService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"
raw_entry_join = entry_join.__wrapped__


def make_request(path="/api/v1/miniapp/entry/join"):
    return Request(
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


class EntryJoinPhoneChangeTest(unittest.IsolatedAsyncioTestCase):
    """A returning customer whose phone number changed used to be silently treated as a
    brand-new customer (their existing WeChat identity binding was reassigned to a freshly
    created, empty account instead of being reused) -- points, level, and history all
    appeared to vanish. Regression coverage: the same WeChat identity returning with a
    different phone must reuse the existing account and keep its assets."""

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
        await self.db.flush()
        await self.db.commit()

        customer_service = CustomerService(self.db)
        customer_service.set_tenant_id(TENANT_A)
        self.returning_customer = await customer_service.create_customer(
            tenant_id=TENANT_A, openid="returning-openid", name="老会员",
            phone="13800000000", tags=["小程序会员"],
        )
        identity_service = CustomerIdentityService(self.db)
        identity_service.set_tenant_id(TENANT_A)
        await identity_service.bind_identity(
            customer_id=self.returning_customer.id, channel=CHANNEL_MINIAPP,
            channel_user_id="returning-openid", phone="13800000000",
        )

        membership_service = MembershipService(self.db)
        membership_service.set_tenant_id(TENANT_A)
        account = await membership_service.ensure_account(self.returning_customer)  # grants register-bonus points
        await membership_service.add_points(account, "manual", 500, ref_id="seed")
        await self.db.commit()
        await self.db.refresh(account)
        self.points_before_rejoin = account.points_balance

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _identity_customer_id(self, channel_user_id):
        identity_service = CustomerIdentityService(self.db)
        identity_service.set_tenant_id(TENANT_A)
        identity = await identity_service.get_by_identity(CHANNEL_MINIAPP, channel_user_id)
        return identity.customer_id if identity else None

    @patch("app.services.coupon_service.CouponService.issue_auto_coupon")
    @patch("app.api.v1.miniapp.WechatService.code2session")
    async def test_same_identity_new_phone_reuses_existing_account_and_keeps_points(
        self, mock_code2session, mock_issue_auto_coupon
    ):
        mock_code2session.return_value = {"openid": "returning-openid", "unionid": None}
        mock_issue_auto_coupon.return_value = {"success_count": 0, "reason": "no template configured"}

        data = EntryJoinRequest(
            tenant_id=TENANT_A,
            code="returning-code",
            phone="13900000002",  # a brand-new number nobody has registered with yet
            phone_code=None,
            agreement_accepted=True,
        )
        result = await raw_entry_join(make_request(), data, db=self.db)

        self.assertEqual(result.code, 200)
        self.assertEqual(result.data["customer_id"], str(self.returning_customer.id))

        # Identity stays bound to the SAME account -- no orphaned second account.
        self.assertEqual(await self._identity_customer_id("returning-openid"), self.returning_customer.id)

        membership_service = MembershipService(self.db)
        membership_service.set_tenant_id(TENANT_A)
        account = await membership_service.get_account_by_customer(self.returning_customer.id)
        self.assertEqual(account.points_balance, self.points_before_rejoin)  # history preserved, not reset to 0

        await self.db.refresh(self.returning_customer)
        self.assertEqual(self.returning_customer.phone, "13900000002")  # phone updated in place


if __name__ == "__main__":
    unittest.main()
