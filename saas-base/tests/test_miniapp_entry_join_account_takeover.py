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

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"

# @join_limit() wraps the endpoint in a slowapi rate limiter that needs a real
# FastAPI `app` on the request to look up its limiter state. functools.wraps
# leaves the raw, undecorated coroutine reachable so these tests can call it
# directly against an in-memory DB, same as the other direct-call contract tests.
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


class EntryJoinAccountTakeoverTest(unittest.IsolatedAsyncioTestCase):
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

        customer_service = CustomerService(self.db)
        customer_service.set_tenant_id(TENANT_A)
        self.victim = await customer_service.create_customer(
            tenant_id=TENANT_A,
            openid="victim-openid",
            name="victim",
            phone="13800000000",
            tags=["小程序会员"],
        )
        identity_service = CustomerIdentityService(self.db)
        identity_service.set_tenant_id(TENANT_A)
        await identity_service.bind_identity(
            customer_id=self.victim.id,
            channel=CHANNEL_MINIAPP,
            channel_user_id="victim-openid",
            phone="13800000000",
        )
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _identity_customer_id(self, channel_user_id):
        identity_service = CustomerIdentityService(self.db)
        identity_service.set_tenant_id(TENANT_A)
        identity = await identity_service.get_by_identity(CHANNEL_MINIAPP, channel_user_id)
        return identity.customer_id if identity else None

    @patch("app.api.v1.miniapp.WechatService.code2session")
    async def test_unverified_manual_phone_cannot_take_over_existing_account(self, mock_code2session):
        mock_code2session.return_value = {"openid": "attacker-openid", "unionid": None}

        data = EntryJoinRequest(
            tenant_id=TENANT_A,
            code="attacker-code",
            phone="13800000000",  # victim's phone, typed in manually by the attacker
            phone_code=None,
            agreement_accepted=True,
        )
        result = await raw_entry_join(make_request(), data, db=self.db)

        self.assertNotEqual(result.code, 200)
        # The attacker's WeChat identity must NOT end up bound to the victim's account.
        self.assertIsNone(await self._identity_customer_id("attacker-openid"))
        self.assertEqual(await self._identity_customer_id("victim-openid"), self.victim.id)

    @patch("app.services.coupon_service.CouponService.issue_auto_coupon")
    @patch("app.api.v1.miniapp.WechatService.get_phone_number")
    @patch("app.api.v1.miniapp.WechatService.code2session")
    async def test_wechat_verified_phone_can_still_rebind_same_owner(
        self, mock_code2session, mock_get_phone_number, mock_issue_auto_coupon
    ):
        # Legitimate case this endpoint is meant to support: victim reinstalls the app
        # (new openid) and proves ownership of the phone via WeChat's verified
        # getPhoneNumber flow, not by typing it in. Coupon issuance itself (which needs
        # Redis) is beside the point of this test, so it's stubbed out here.
        mock_code2session.return_value = {"openid": "victim-new-device-openid", "unionid": None}
        mock_get_phone_number.return_value = "13800000000"
        mock_issue_auto_coupon.return_value = {"success_count": 0, "reason": "no template configured"}

        data = EntryJoinRequest(
            tenant_id=TENANT_A,
            code="victim-new-device-code",
            phone=None,
            phone_code="wechat-verified-phone-code",
            agreement_accepted=True,
        )
        result = await raw_entry_join(make_request(), data, db=self.db)

        self.assertEqual(result.code, 200)
        self.assertEqual(await self._identity_customer_id("victim-new-device-openid"), self.victim.id)


if __name__ == "__main__":
    unittest.main()
