import asyncio
import unittest

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.tenant import Tenant
from app.api.v1.queue import list_queue_tickets
from app.services.queue_service import QueueService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


def make_request(tenant_id=None, token_type=None):
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/queue/tickets",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    request.state.tenant_id = tenant_id
    request.state.token_type = token_type
    return request


class QueueTicketsAuthorizationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        for tenant_id in (TENANT_A, TENANT_B):
            self.db.add(Tenant(
                tenant_id=tenant_id,
                name=f"Restaurant {tenant_id}",
                password_hash="x",
                status=True,
                is_open=True,
                payment_mode="postpay",
            ))
        await self.db.flush()
        await self.db.commit()

        service = QueueService(self.db)
        await service.create_ticket(tenant_id=TENANT_A, party_size=2, phone="13800000000", note=None)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_unauthenticated_request_cannot_list_tickets(self):
        result = await list_queue_tickets(
            tenant_id=TENANT_A,
            request=make_request(tenant_id=None, token_type=None),
            db=self.db,
        )
        self.assertFalse(result["success"])
        self.assertIsNone(result["data"])

    async def test_member_token_cannot_list_another_tenants_tickets(self):
        # A non-merchant token (e.g. a customer/member token) must not satisfy this either.
        result = await list_queue_tickets(
            tenant_id=TENANT_A,
            request=make_request(tenant_id=TENANT_A, token_type="member"),
            db=self.db,
        )
        self.assertFalse(result["success"])

    async def test_merchant_token_ignores_client_supplied_tenant_id(self):
        # Merchant of tenant B tries to read tenant A's queue by passing tenant_id=A in the
        # query string; the effective tenant must come from the token, not the query param.
        result = await list_queue_tickets(
            tenant_id=TENANT_A,
            request=make_request(tenant_id=TENANT_B, token_type="merchant"),
            db=self.db,
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["data"], [])

    async def test_merchant_token_can_list_own_tickets(self):
        result = await list_queue_tickets(
            tenant_id=TENANT_A,
            request=make_request(tenant_id=TENANT_A, token_type="merchant"),
            db=self.db,
        )
        self.assertTrue(result["success"])
        self.assertEqual(len(result["data"]), 1)
        # A merchant viewing their own queue legitimately sees the full phone number.
        self.assertEqual(result["data"][0]["phone"], "13800000000")


if __name__ == "__main__":
    unittest.main()
