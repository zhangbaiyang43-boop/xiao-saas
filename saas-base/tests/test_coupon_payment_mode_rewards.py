import asyncio
import json
import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

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
from app.models.point_ledger import PointLedger
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.api.v1.orders import settle_table, update_order_status, OrderStatusUpdate
from app.services.order_lifecycle_service import build_member_value_for_order
from app.services.coupon_service import CouponService
from app.services.subscription_service import STATUS_ACTIVE, SubscriptionService

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

        # A real file-backed SQLite DB, not :memory: -- settle_table now calls
        # optional_capability_enabled() mid-transaction (via
        # _apply_paid_order_member_assets_once), which opens its own
        # AsyncSessionLocal() session. With :memory:, that nested session can
        # spuriously roll back this session's already-flushed-but-uncommitted
        # writes when it closes (a SQLite/aiosqlite test-only artifact; see
        # tests/test_optional_side_effect_wiring.py for the full writeup and a
        # standalone repro -- it disappears entirely on a real file-backed DB,
        # i.e. on any real production database each session already has its
        # own independent connection/transaction with no such interference).
        self._db_file = f"{tempfile.gettempdir()}/f1fd1a_coupon_reward_{uuid.uuid4().hex}.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_file}")
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
        # Phase F1F-D1A: order_payment_service.py's offline-settlement auto-coupon
        # issuance now calls optional_capability_enabled(CAP_COUPONS) before
        # issuing. This file predates subscription-awareness and tests coupon
        # reward rule selection, unrelated to plan tier -- give TENANT_A a real
        # PRO baseline so the reward-issuance assertions below keep exercising
        # real (not skipped) behavior.
        self.db.add_all(
            [
                Plan(code="FREE", name="免费版", is_active=True, price_month_cents=0, price_year_cents=0, sort_order=0),
                Plan(code="STANDARD", name="普通版", is_active=True, price_month_cents=5900, price_year_cents=60900, sort_order=1),
                Plan(code="PRO", name="专业版", is_active=True, price_month_cents=9900, price_year_cents=102200, sort_order=2),
            ]
        )
        await self.db.commit()
        pro_plan = await SubscriptionService(self.db).get_plan_by_code("PRO")
        now = datetime.utcnow()
        self.db.add(Subscription(
            tenant_id=TENANT_A, plan_id=pro_plan.id, status=STATUS_ACTIVE,
            started_at=now, ends_at=now + timedelta(days=30),
        ))
        await self.db.commit()

        # optional_capability_enabled() opens its own AsyncSessionLocal() session
        # -- point that factory at this test's own in-memory engine instead of
        # the real production DB.
        self._session_patch = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._session_patch.start()

    async def asyncTearDown(self):
        self._session_patch.stop()
        settings.REDIS_ENABLED = self._original_redis_enabled
        await self.db.close()
        await self.engine.dispose()
        try:
            os.remove(self._db_file)
        except OSError:
            pass

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
        pending_value = await build_member_value_for_order(self.db, order)
        self.assertEqual(pending_value["status"], "pending")

        result = await settle_table({"table_no": "A1", "dining_session_id": str(session.id)}, make_merchant_request(), db=self.db)
        self.assertEqual(result.code, 200)
        self.assertEqual(await self._unused_coupon_count(self.customer.id), 1)
        await self.db.refresh(order)
        reward = json.loads(order.reward_coupon_snapshot)
        self.assertTrue(reward["id"])
        self.assertIn("name", reward)
        available_value = await build_member_value_for_order(self.db, order)
        self.assertEqual(available_value["status"], "available")
        self.assertEqual(available_value["reward_coupon_status"], "issued")

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
        pending_value = await build_member_value_for_order(self.db, order)
        self.assertEqual(pending_value["status"], "pending")

        result = await update_order_status(
            str(order.id), OrderStatusUpdate(status="settled"), make_merchant_request(), db=self.db,
        )
        self.assertEqual(result.code, 200)
        self.assertEqual(await self._unused_coupon_count(self.customer.id), 1)
        await self.db.refresh(order)
        reward = json.loads(order.reward_coupon_snapshot)
        self.assertTrue(reward["id"])
        available_value = await build_member_value_for_order(self.db, order)
        self.assertEqual(available_value["status"], "available")
        self.assertEqual(available_value["reward_coupon_status"], "issued")

    async def test_postpay_no_reward_persists_explicit_json_null(self):
        self.tenant.payment_mode = "postpay"
        order = Order(
            tenant_id=TENANT_A, customer_id=self.customer.id, table_no="B3", total="25.00",
            status="done", payment_status="unpaid", payment_mode="postpay",
        )
        self.db.add(order)
        await self.db.commit()

        with (
            patch.object(CouponService, "resolve_consumption_coupon_rule_type", new=AsyncMock(return_value="new_customer_coupon")),
            patch.object(CouponService, "issue_auto_coupon", new=AsyncMock(return_value={"success_count": 0})),
        ):
            result = await update_order_status(
                str(order.id), OrderStatusUpdate(status="settled"), make_merchant_request(), db=self.db,
            )

        self.assertEqual(result.code, 200)
        await self.db.refresh(order)
        self.assertEqual(order.reward_coupon_snapshot, "null")
        value = await build_member_value_for_order(self.db, order)
        self.assertEqual(value["status"], "available")
        self.assertEqual(value["reward_coupon_status"], "none")

    async def test_multi_order_table_settlement_persists_known_none_per_order(self):
        session, first = await self._make_table_account_order(self.customer.id)
        participant = await self.db.get(DiningParticipant, first.participant_id)
        second = Order(
            tenant_id=TENANT_A, customer_id=self.customer.id,
            dining_session_id=session.id, participant_id=participant.id,
            table_no="A1", total="30.00", status="done",
            payment_status="unpaid", payment_mode="table_account",
        )
        self.db.add(second)
        await self.db.commit()

        with (
            patch.object(CouponService, "resolve_consumption_coupon_rule_type", new=AsyncMock(return_value="new_customer_coupon")),
            patch.object(CouponService, "issue_auto_coupon", new=AsyncMock(return_value={"success_count": 0})),
        ):
            result = await settle_table(
                {"table_no": "A1", "dining_session_id": str(session.id)},
                make_merchant_request(), db=self.db,
            )

        self.assertEqual(result.code, 200)
        await self.db.refresh(first)
        await self.db.refresh(second)
        self.assertEqual(first.reward_coupon_snapshot, "null")
        self.assertEqual(second.reward_coupon_snapshot, "null")
        first_value = await build_member_value_for_order(self.db, first)
        second_value = await build_member_value_for_order(self.db, second)
        self.assertEqual(first_value["reward_coupon_status"], "none")
        self.assertEqual(second_value["reward_coupon_status"], "none")

    async def test_offline_member_assets_roll_back_with_later_settlement_failure(self):
        session, order = await self._make_table_account_order(self.customer.id)
        order_id = int(order.id)
        customer_id = int(self.customer.id)
        with (
            patch.object(CouponService, "resolve_consumption_coupon_rule_type", new=AsyncMock(return_value="new_customer_coupon")),
            patch.object(CouponService, "issue_auto_coupon", new=AsyncMock(return_value={"success_count": 0})),
            patch(
                "app.services.coupon_service._mark_order_coupon_used_if_locked",
                new=AsyncMock(side_effect=RuntimeError("simulated later settlement failure")),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "simulated later settlement failure"):
                await settle_table(
                    {"table_no": "A1", "dining_session_id": str(session.id)},
                    make_merchant_request(), db=self.db,
                )

        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.status, "settled")
        self.assertEqual(order.reward_coupon_snapshot, "null")
        in_transaction_ledgers = await self.db.execute(
            select(func.count()).select_from(PointLedger).where(
                PointLedger.tenant_id == TENANT_A,
                PointLedger.customer_id == self.customer.id,
                PointLedger.event_type == "consumption",
                PointLedger.ref_id == str(order.id),
            )
        )
        self.assertEqual(int(in_transaction_ledgers.scalar() or 0), 1)

        await self.db.rollback()
        async with self.SessionLocal() as verify_db:
            persisted_order = await verify_db.get(Order, order_id)
            self.assertEqual(persisted_order.payment_status, "unpaid")
            self.assertEqual(persisted_order.status, "done")
            self.assertIsNone(persisted_order.reward_coupon_snapshot)
            persisted_ledgers = await verify_db.execute(
                select(func.count()).select_from(PointLedger).where(
                    PointLedger.tenant_id == TENANT_A,
                    PointLedger.customer_id == customer_id,
                    PointLedger.event_type == "consumption",
                    PointLedger.ref_id == str(order_id),
                )
            )
            self.assertEqual(int(persisted_ledgers.scalar() or 0), 0)

    async def test_one_table_settlement_attributes_each_reward_to_its_own_order(self):
        session, first = await self._make_table_account_order(self.customer.id)
        participant = await self.db.get(DiningParticipant, first.participant_id)
        second = Order(
            tenant_id=TENANT_A,
            customer_id=self.customer.id,
            dining_session_id=session.id,
            participant_id=participant.id,
            table_no="A1",
            total="30.00",
            status="done",
            payment_status="unpaid",
            payment_mode="table_account",
        )
        self.db.add(second)
        await self.db.commit()

        result = await settle_table(
            {"table_no": "A1", "dining_session_id": str(session.id)},
            make_merchant_request(),
            db=self.db,
        )

        self.assertEqual(result.code, 200)
        await self.db.refresh(first)
        await self.db.refresh(second)
        first_reward = json.loads(first.reward_coupon_snapshot)
        second_reward = json.loads(second.reward_coupon_snapshot)
        self.assertNotEqual(first_reward["id"], second_reward["id"])


if __name__ == "__main__":
    unittest.main()
