from __future__ import annotations

import asyncio
import re
import unittest
from datetime import datetime, timedelta

import httpx
import jwt
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, create_channel_partner_access_token
from app.main import app
from app.models.base import Base
from app.models.channel_revenue import ChannelPartner
from app.services.channel_partner_service import ChannelPartnerService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class SuperChannelPartnerAdminTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        async def override_get_db():
            yield self.db

        app.dependency_overrides[get_db] = override_get_db
        transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.db.close()
        await self.engine.dispose()

    def _super_headers(self) -> dict[str, str]:
        token = jwt.encode(
            {"sub": "super_admin", "type": "super_admin", "exp": datetime.utcnow() + timedelta(hours=1)},
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        return {"X-Super-Token": token}

    async def test_super_can_create_and_list_partner_without_manual_partner_code(self):
        created = await self.client.post(
            "/api/super/channel/partners",
            headers=self._super_headers(),
            json={
                "name": "Wine Channel",
                "mobile": "13900000001",
                "partner_type": "WINE_SALES",
                "status": "ACTIVE",
            },
        )

        self.assertEqual(created.json()["code"], 200)
        partner = created.json()["data"]
        self.assertRegex(partner["partner_code"], r"^CH\d{12}$")
        self.assertEqual(partner["mobile"], "13900000001")
        self.assertEqual(partner["mobile_normalized"], "13900000001")
        self.assertEqual(partner["partner_type"], "WINE_SALES")
        self.assertEqual(partner["status"], "ACTIVE")
        self.assertTrue(partner["created_at"])

        listing = await self.client.get("/api/super/channel/partners", headers=self._super_headers())
        self.assertEqual(listing.json()["code"], 200)
        self.assertEqual(len(listing.json()["data"]), 1)
        self.assertEqual(listing.json()["data"][0]["partner_code"], partner["partner_code"])

    async def test_duplicate_partner_mobile_returns_clear_error(self):
        service = ChannelPartnerService(self.db)
        await service.create_partner(name="First", mobile="13900000002", partner_type="OTHER", status="ACTIVE")

        duplicated = await self.client.post(
            "/api/super/channel/partners",
            headers=self._super_headers(),
            json={"name": "Second", "mobile": "139-0000-0002", "partner_type": "OTHER", "status": "ACTIVE"},
        )

        self.assertEqual(duplicated.json()["code"], 400)
        self.assertIn("mobile", duplicated.json()["msg"])

    async def test_auto_partner_codes_are_unique(self):
        service = ChannelPartnerService(self.db)
        first = await service.create_partner(name="First", mobile="13900000003", partner_type="OTHER", status="ACTIVE")
        second = await service.create_partner(name="Second", mobile="13900000004", partner_type="OTHER", status="ACTIVE")

        self.assertNotEqual(first.partner_code, second.partner_code)
        self.assertTrue(re.match(r"^CH\d{12}$", first.partner_code))
        self.assertTrue(re.match(r"^CH\d{12}$", second.partner_code))

    async def test_super_channel_partners_are_super_token_only(self):
        service = ChannelPartnerService(self.db)
        partner = await service.create_partner(name="Channel", mobile="13900000005", partner_type="OTHER", status="ACTIVE")
        merchant_token = create_access_token("tenant-a")
        channel_token = create_channel_partner_access_token(int(partner.id))

        no_token = await self.client.get("/api/super/channel/partners")
        merchant = await self.client.get("/api/super/channel/partners", headers={"X-Super-Token": merchant_token})
        channel = await self.client.get("/api/super/channel/partners", headers={"X-Super-Token": channel_token})

        self.assertNotEqual(no_token.status_code, 200)
        self.assertEqual(merchant.status_code, 401)
        self.assertEqual(channel.status_code, 401)


if __name__ == "__main__":
    unittest.main()
