"""Regression: recovered participant must rotate guest_token_hash with returned token."""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.dining import DiningParticipant, DiningSession
from app.models.tenant import Tenant
from app.services.dining_session_service import (
    DiningSessionService,
    hash_participant_token,
    make_participant_token,
)

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT = "tenant-token-rot"


class DiningParticipantTokenRotationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add(
            Tenant(
                tenant_id=TENANT,
                name="Token Rot Shop",
                password_hash="x",
                status=True,
                is_open=True,
                payment_mode="table_account",
            )
        )
        await self.db.commit()
        self.service = DiningSessionService(self.db)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_stale_token_recovered_by_client_id_rotates_hash(self):
        """Client brings wrong token; same client_id finds participant → new token must work."""
        old_token = make_participant_token()
        client_id = "dc_device_1"
        session = DiningSession(
            tenant_id=TENANT,
            table_no="A01",
            status="OPEN",
            active_key=f"{TENANT}:A01",
            started_at=datetime.utcnow(),
            last_activity_at=datetime.utcnow(),
        )
        self.db.add(session)
        await self.db.flush()
        participant = DiningParticipant(
            tenant_id=TENANT,
            session_id=session.id,
            client_id=client_id,
            guest_token_hash=hash_participant_token(old_token),
            joined_at=datetime.utcnow(),
            last_active_at=datetime.utcnow(),
        )
        self.db.add(participant)
        await self.db.commit()
        await self.db.refresh(participant)

        data = await self.service.resolve_session(
            tenant_id=TENANT,
            table_no="A01",
            client_id=client_id,
            participant_token="deadbeefdeadbeefdeadbeefdeadbeef",  # wrong / unused shape still hashed
        )
        await self.db.commit()
        await self.db.refresh(participant)

        new_token = data["participant_token"]
        self.assertNotEqual(new_token, old_token)
        self.assertEqual(participant.guest_token_hash, hash_participant_token(new_token))

        # Second resolve with the rotated token must hit by hash (no further mint needed).
        data2 = await self.service.resolve_session(
            tenant_id=TENANT,
            table_no="A01",
            client_id=client_id,
            participant_token=new_token,
        )
        self.assertEqual(data2["participant_token"], new_token)
        self.assertEqual(data2["dining_session_id"], str(session.id))

    async def test_stale_token_recovered_by_customer_id_rotates_hash(self):
        old_token = make_participant_token()
        session = DiningSession(
            tenant_id=TENANT,
            table_no="B02",
            status="OPEN",
            active_key=f"{TENANT}:B02",
            started_at=datetime.utcnow(),
            last_activity_at=datetime.utcnow(),
        )
        self.db.add(session)
        await self.db.flush()
        participant = DiningParticipant(
            tenant_id=TENANT,
            session_id=session.id,
            customer_id=4242,
            client_id="dc_other",
            guest_token_hash=hash_participant_token(old_token),
            joined_at=datetime.utcnow(),
            last_active_at=datetime.utcnow(),
        )
        self.db.add(participant)
        await self.db.commit()
        await self.db.refresh(participant)

        data = await self.service.resolve_session(
            tenant_id=TENANT,
            table_no="B02",
            client_id="dc_new_device",
            participant_token="ffffffffffffffffffffffffffffffff",
            customer_id=4242,
        )
        await self.db.commit()
        await self.db.refresh(participant)

        new_token = data["participant_token"]
        self.assertEqual(participant.guest_token_hash, hash_participant_token(new_token))
        self.assertEqual(int(data["participant_id"]), int(participant.id))


if __name__ == "__main__":
    unittest.main()
