import asyncio
import unittest
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.orders import settle_table
from app.models.base import Base
from app.models.dining import DiningSession
from app.models.order import Order
from app.services.dining_session_service import DiningSessionService
from app.services.order_lifecycle_service import OrderLifecycleService
from app.utils.id_generator import generate_snowflake_id


if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


TENANT = "tenant-p0-05-lifecycle"


class FakeMerchantRequest:
    def __init__(self):
        self.state = SimpleNamespace(
            tenant_id=TENANT,
            token_type="merchant",
            role="owner",
            account_id=None,
            user_id="owner-p0-05",
        )


class P005PaymentModeLifecycleContractsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.db = self.SessionLocal()
        self.lifecycle = OrderLifecycleService(self.db)
        self.lifecycle.set_tenant_id(TENANT)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_session(self, table_no: str) -> DiningSession:
        now = datetime.utcnow()
        session = DiningSession(
            tenant_id=TENANT,
            table_no=table_no,
            status="OPEN",
            active_key=f"{TENANT}:{table_no}",
            started_at=now,
            last_activity_at=now,
        )
        self.db.add(session)
        await self.db.flush()
        await self.db.commit()
        return session

    async def _make_order(
        self,
        *,
        payment_mode: str,
        status: str,
        payment_status: str,
        session: DiningSession | None,
        table_no: str,
    ) -> Order:
        order = Order(
            tenant_id=TENANT,
            dining_session_id=session.id if session else None,
            table_no=table_no,
            total="20.00",
            status=status,
            payment_status=payment_status,
            payment_mode=payment_mode,
        )
        self.db.add(order)
        await self.db.commit()
        return order

    async def test_r01_table_account_single_order_settle_is_rejected_without_mutation(self):
        session = await self._make_session("T01")
        order = await self._make_order(
            payment_mode="table_account",
            status="done",
            payment_status="unpaid",
            session=session,
            table_no="T01",
        )

        response = await self.lifecycle.update_order_status(
            order.id, SimpleNamespace(status="settled")
        )

        self.assertEqual(response.code, 409)
        await self.db.refresh(order)
        await self.db.refresh(session)
        self.assertEqual(order.status, "done")
        self.assertEqual(order.payment_status, "unpaid")
        self.assertEqual(session.status, "OPEN")
        self.assertEqual(session.active_key, f"{TENANT}:T01")

    async def test_r02_session_bound_postpay_single_order_settle_is_rejected_without_mutation(self):
        session = await self._make_session("P02")
        order = await self._make_order(
            payment_mode="postpay",
            status="done",
            payment_status="unpaid",
            session=session,
            table_no="P02",
        )

        response = await self.lifecycle.update_order_status(
            order.id, SimpleNamespace(status="settled")
        )

        self.assertEqual(response.code, 409)
        await self.db.refresh(order)
        await self.db.refresh(session)
        self.assertEqual(order.status, "done")
        self.assertEqual(order.payment_status, "unpaid")
        self.assertEqual(session.status, "OPEN")
        self.assertEqual(session.active_key, f"{TENANT}:P02")

    async def test_r03_paid_prepay_single_order_settle_remains_allowed(self):
        session = await self._make_session("R03")
        order = await self._make_order(
            payment_mode="prepay",
            status="done",
            payment_status="paid",
            session=session,
            table_no="R03",
        )

        response = await self.lifecycle.update_order_status(
            order.id, SimpleNamespace(status="settled")
        )

        self.assertEqual(response.code, 200)
        await self.db.refresh(order)
        self.assertEqual(order.status, "settled")
        self.assertEqual(order.payment_status, "paid")

    async def test_unpaid_prepay_cannot_bypass_payment_authority_with_settle_table(self):
        session = await self._make_session("W03")
        order = await self._make_order(
            payment_mode="prepay",
            status="pending_payment",
            payment_status="unpaid",
            session=session,
            table_no="W03",
        )

        response = await settle_table(
            {"table_no": "W03", "dining_session_id": str(session.id)}, FakeMerchantRequest(), self.db
        )

        self.assertEqual(response.code, 409)
        await self.db.refresh(order)
        await self.db.refresh(session)
        self.assertEqual(order.status, "pending_payment")
        self.assertEqual(order.payment_status, "unpaid")
        self.assertIsNone(order.payment_method)
        self.assertEqual(session.status, "OPEN")

    async def test_r04_official_postpay_settle_updates_payment_and_closes_session(self):
        session = await self._make_session("R04")
        order = await self._make_order(
            payment_mode="postpay",
            status="done",
            payment_status="unpaid",
            session=session,
            table_no="R04",
        )

        response = await settle_table(
            {"table_no": "R04", "dining_session_id": str(session.id)}, FakeMerchantRequest(), self.db
        )

        self.assertEqual(response.code, 200)
        await self.db.refresh(order)
        await self.db.refresh(session)
        self.assertEqual(order.status, "settled")
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.payment_method, "offline")
        self.assertIsNotNone(order.payment_time)
        self.assertEqual(session.status, "CLOSED")
        self.assertIsNone(session.active_key)

    async def test_r05_official_table_account_settles_every_order_in_session(self):
        session = await self._make_session("R05")
        orders = [
            await self._make_order(
                payment_mode="table_account",
                status="done",
                payment_status="unpaid",
                session=session,
                table_no="R05",
            )
            for _ in range(3)
        ]

        response = await settle_table(
            {"table_no": "R05", "dining_session_id": str(session.id)}, FakeMerchantRequest(), self.db
        )

        self.assertEqual(response.code, 200)
        self.assertEqual(response.data["settled_count"], 3)
        self.assertEqual(response.data["paid_synced_count"], 3)
        for order in orders:
            await self.db.refresh(order)
            self.assertEqual(order.status, "settled")
            self.assertEqual(order.payment_status, "paid")
            self.assertEqual(order.payment_method, "offline")
            self.assertIsNotNone(order.payment_time)
        await self.db.refresh(session)
        self.assertEqual(session.status, "CLOSED")
        self.assertIsNone(session.active_key)

    async def test_r06_second_official_settle_is_deterministic_conflict_without_mutation(self):
        # P0-10 FINAL RECONCILIATION: a retry with the SAME (now-closed) session
        # id is a SESSION_SETTLE_CONFLICT (409), not a generic "no session" 404 --
        # more precise than before, but the underlying invariant this test exists
        # to prove is unchanged: the retry must not mutate anything a second time.
        session = await self._make_session("R06")
        order = await self._make_order(
            payment_mode="table_account",
            status="done",
            payment_status="unpaid",
            session=session,
            table_no="R06",
        )
        first = await settle_table(
            {"table_no": "R06", "dining_session_id": str(session.id)}, FakeMerchantRequest(), self.db
        )
        first_payment_time = order.payment_time
        first_closed_at = session.closed_at

        second = await settle_table(
            {"table_no": "R06", "dining_session_id": str(session.id)}, FakeMerchantRequest(), self.db
        )

        self.assertEqual(first.code, 200)
        self.assertEqual(second.code, 409)
        self.assertEqual(second.data.get("code"), "SESSION_SETTLE_CONFLICT")
        await self.db.refresh(order)
        await self.db.refresh(session)
        self.assertEqual(order.payment_time, first_payment_time)
        self.assertEqual(session.closed_at, first_closed_at)

    async def test_sessionless_postpay_keeps_legacy_single_order_settlement_contract(self):
        order = await self._make_order(
            payment_mode="postpay",
            status="done",
            payment_status="unpaid",
            session=None,
            table_no="ORPHAN",
        )

        response = await self.lifecycle.update_order_status(
            order.id, SimpleNamespace(status="settled")
        )

        self.assertEqual(response.code, 200)
        await self.db.refresh(order)
        self.assertEqual(order.status, "settled")
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.payment_method, "offline")

    async def test_valid_session_invariant_closes_s1_then_resolves_distinct_s2(self):
        from app.models.entrance_code import EntranceCode

        self.db.add(
            EntranceCode(
                id=generate_snowflake_id(),
                tenant_id=TENANT,
                name="R07",
                scene="P005R07SCENE",
                table_no="R07",
                entry_type="table",
                status=1,
            )
        )
        await self.db.commit()
        service = DiningSessionService(self.db)
        first_data = await service.resolve_session(
            tenant_id=TENANT, table_no="R07", client_id="phone-a"
        )
        first_session_id = int(first_data["dining_session_id"])
        first_session = await self.db.get(DiningSession, first_session_id)
        await self._make_order(
            payment_mode="table_account",
            status="done",
            payment_status="unpaid",
            session=first_session,
            table_no="R07",
        )
        settled = await settle_table(
            {"table_no": "R07", "dining_session_id": str(first_session_id)}, FakeMerchantRequest(), self.db
        )

        second_data = await service.resolve_session(
            tenant_id=TENANT, table_no="R07", client_id="phone-b"
        )

        self.assertEqual(settled.code, 200)
        self.assertNotEqual(
            int(second_data["dining_session_id"]), first_session_id
        )
        await self.db.refresh(first_session)
        self.assertEqual(first_session.status, "CLOSED")
        self.assertIsNone(first_session.active_key)


if __name__ == "__main__":
    unittest.main()
