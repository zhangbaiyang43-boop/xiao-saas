"""Phase 03A effective subscription selection regression tests.

The effective read path must retain the existing ``created_at DESC, id DESC``
ordering while skipping candidates that ``SubscriptionService.is_active()``
considers invalid.  ``get_current_subscription()`` deliberately keeps its
historical "newest row" meaning for trial, renewal, and billing write paths.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.services.subscription_service import (
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_EXPIRED,
    STATUS_TRIAL,
    SUBSCRIPTION_STATUS_FREE,
    SubscriptionService,
)
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@event.listens_for(Plan, "before_insert")
def _assign_plan_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Subscription, "before_insert")
def _assign_subscription_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Tenant, "before_insert")
def _assign_tenant_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


class SubscriptionEffectiveSelectionTest(unittest.IsolatedAsyncioTestCase):
    TENANT_ID = "tenant-phase03a-effective-selection"
    NOW = datetime(2026, 8, 21, 12, 0, 0)

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.service = SubscriptionService(self.db)

        self.plans = {
            plan.code: plan
            for plan in (
                Plan(code="FREE", name="免费版", is_active=True),
                Plan(code="STANDARD", name="普通版", is_active=True),
                Plan(code="PRO", name="专业版", is_active=True),
            )
        }
        self.db.add_all(
            [
                Tenant(
                    tenant_id=self.TENANT_ID,
                    name="Phase03A Tenant",
                    password_hash="x",
                    status=True,
                ),
                *self.plans.values(),
            ]
        )
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _add_subscription(
        self,
        *,
        plan_code: str,
        status: str,
        created_at: datetime,
        ends_at: datetime | None = None,
        trial_ends_at: datetime | None = None,
        subscription_id: int | None = None,
    ) -> Subscription:
        subscription = Subscription(
            id=subscription_id,
            tenant_id=self.TENANT_ID,
            plan_id=self.plans[plan_code].id,
            status=status,
            started_at=created_at,
            ends_at=ends_at,
            trial_started_at=created_at if status == STATUS_TRIAL else None,
            trial_ends_at=trial_ends_at,
            created_at=created_at,
        )
        self.db.add(subscription)
        await self.db.commit()
        await self.db.refresh(subscription)
        return subscription

    async def test_case_a_newer_expired_does_not_shadow_older_valid(self):
        older_valid = await self._add_subscription(
            plan_code="STANDARD",
            status=STATUS_ACTIVE,
            created_at=self.NOW - timedelta(days=2),
            ends_at=self.NOW + timedelta(days=10),
        )
        newer_expired = await self._add_subscription(
            plan_code="PRO",
            status=STATUS_ACTIVE,
            created_at=self.NOW - timedelta(days=1),
            ends_at=self.NOW - timedelta(seconds=1),
        )

        latest = await self.service.get_current_subscription(self.TENANT_ID)
        view = await self.service.get_effective_subscription_view(self.TENANT_ID, now=self.NOW)

        self.assertEqual(latest.id, newer_expired.id)
        self.assertEqual(view.effective_plan.code, "STANDARD")
        self.assertEqual(view.paid_started_at, older_valid.started_at)

    async def test_case_b_newer_valid_keeps_existing_recency_order(self):
        await self._add_subscription(
            plan_code="STANDARD",
            status=STATUS_ACTIVE,
            created_at=self.NOW - timedelta(days=2),
            ends_at=self.NOW + timedelta(days=10),
        )
        newer_valid = await self._add_subscription(
            plan_code="PRO",
            status=STATUS_ACTIVE,
            created_at=self.NOW - timedelta(days=1),
            ends_at=self.NOW + timedelta(days=5),
        )

        view = await self.service.get_effective_subscription_view(self.TENANT_ID, now=self.NOW)

        self.assertEqual(view.effective_plan.code, "PRO")
        self.assertEqual(view.paid_started_at, newer_valid.started_at)

    async def test_case_c_all_expired_keeps_existing_free_fallback(self):
        await self._add_subscription(
            plan_code="STANDARD",
            status=STATUS_ACTIVE,
            created_at=self.NOW - timedelta(days=2),
            ends_at=self.NOW - timedelta(days=1),
        )
        await self._add_subscription(
            plan_code="PRO",
            status=STATUS_ACTIVE,
            created_at=self.NOW - timedelta(hours=1),
            ends_at=self.NOW - timedelta(seconds=1),
        )

        view = await self.service.get_effective_subscription_view(self.TENANT_ID, now=self.NOW)

        self.assertEqual(view.effective_plan.code, "FREE")
        self.assertEqual(view.subscription_status, STATUS_EXPIRED)

    async def test_case_d_only_valid_subscription_is_selected(self):
        valid_trial = await self._add_subscription(
            plan_code="PRO",
            status=STATUS_TRIAL,
            created_at=self.NOW - timedelta(days=1),
            trial_ends_at=self.NOW + timedelta(days=5),
        )

        view = await self.service.get_effective_subscription_view(self.TENANT_ID, now=self.NOW)

        self.assertEqual(view.effective_plan.code, "PRO")
        self.assertEqual(view.subscription_status, STATUS_TRIAL)
        self.assertEqual(view.trial_ends_at, valid_trial.trial_ends_at)

    def test_case_e_not_applicable_started_at_is_not_an_existing_validity_gate(self):
        future_started = Subscription(
            tenant_id=self.TENANT_ID,
            plan_id=1,
            status=STATUS_ACTIVE,
            started_at=self.NOW + timedelta(days=1),
            ends_at=self.NOW + timedelta(days=10),
        )

        self.assertTrue(self.service.is_active(future_started, now=self.NOW))

    async def test_case_f_multiple_invalid_rows_before_valid_are_all_skipped(self):
        third_valid = await self._add_subscription(
            plan_code="PRO",
            status=STATUS_ACTIVE,
            created_at=self.NOW - timedelta(days=3),
            ends_at=self.NOW + timedelta(days=10),
        )
        await self._add_subscription(
            plan_code="STANDARD",
            status=STATUS_ACTIVE,
            created_at=self.NOW - timedelta(days=2),
            ends_at=self.NOW - timedelta(seconds=1),
        )
        await self._add_subscription(
            plan_code="STANDARD",
            status=STATUS_CANCELLED,
            created_at=self.NOW - timedelta(days=1),
            ends_at=self.NOW + timedelta(days=20),
        )

        view = await self.service.get_effective_subscription_view(self.TENANT_ID, now=self.NOW)

        self.assertEqual(view.effective_plan.code, "PRO")
        self.assertEqual(view.paid_started_at, third_valid.started_at)

    async def test_case_g_no_history_keeps_existing_free_fallback(self):
        view = await self.service.get_effective_subscription_view(self.TENANT_ID, now=self.NOW)

        self.assertEqual(view.effective_plan.code, "FREE")
        self.assertEqual(view.subscription_status, SUBSCRIPTION_STATUS_FREE)

    async def test_case_h_equal_created_at_uses_id_desc_tiebreak(self):
        same_created_at = self.NOW - timedelta(days=1)
        await self._add_subscription(
            plan_code="STANDARD",
            status=STATUS_ACTIVE,
            created_at=same_created_at,
            ends_at=self.NOW + timedelta(days=10),
            subscription_id=1001,
        )
        expected = await self._add_subscription(
            plan_code="PRO",
            status=STATUS_ACTIVE,
            created_at=same_created_at,
            ends_at=self.NOW + timedelta(days=5),
            subscription_id=1002,
        )

        view = await self.service.get_effective_subscription_view(self.TENANT_ID, now=self.NOW)

        self.assertEqual(view.effective_plan.code, "PRO")
        self.assertEqual(view.paid_started_at, expected.started_at)


if __name__ == "__main__":
    unittest.main()
