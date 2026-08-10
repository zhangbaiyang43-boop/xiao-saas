"""Phase 02 — Subscription Data Skeleton regression tests.

Scope: docs/saas-subscription-audit.md Phase 02. These tests only prove the new
Plan/Subscription tables exist, can be created/read, and that an existing Tenant
with zero Subscription rows keeps working exactly as before (the P0 requirement).
No enforcement, no registration/billing/payment wiring is exercised here — none
exists yet.
"""

from __future__ import annotations

import asyncio
import inspect
import unittest
from datetime import datetime

from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.services import subscription_service as subscription_service_module
from app.services.subscription_service import (
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_TRIAL,
    SubscriptionService,
)
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_LEGACY = "tenant-subscription-legacy"
TENANT_WITH_SUB = "tenant-subscription-a"


@event.listens_for(Plan, "before_insert")
def _assign_plan_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Subscription, "before_insert")
def _assign_subscription_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


class SubscriptionSkeletonTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    # ---- Test 1: model import -------------------------------------------------

    def test_models_import(self):
        self.assertTrue(hasattr(Plan, "__tablename__"))
        self.assertEqual(Plan.__tablename__, "plans")
        self.assertTrue(hasattr(Subscription, "__tablename__"))
        self.assertEqual(Subscription.__tablename__, "subscriptions")

    # ---- Test 2: Plan creation, code uniqueness --------------------------------

    async def test_plan_creation_free_and_pro(self):
        self.db.add_all(
            [
                Plan(code="FREE", name="免费版", is_active=True),
                Plan(code="PRO", name="专业版", is_active=True),
            ]
        )
        await self.db.commit()

        result = await self.db.execute(select(Plan).order_by(Plan.code))
        codes = sorted(p.code for p in result.scalars().all())
        self.assertEqual(codes, ["FREE", "PRO"])

    async def test_plan_code_must_be_unique(self):
        self.db.add(Plan(code="PRO", name="专业版", is_active=True))
        await self.db.commit()

        self.db.add(Plan(code="PRO", name="专业版重复", is_active=True))
        with self.assertRaises(IntegrityError):
            await self.db.commit()
        await self.db.rollback()

    # ---- Test 3: Subscription creation (tenant + plan + status) ---------------

    async def test_subscription_creation_links_tenant_and_plan(self):
        self.db.add(Tenant(tenant_id=TENANT_WITH_SUB, name="Sub Tenant", password_hash="x", status=True))
        plan = Plan(code="PRO", name="专业版", is_active=True)
        self.db.add(plan)
        await self.db.commit()
        await self.db.refresh(plan)

        service = SubscriptionService(self.db)
        subscription = await service.create_trial(
            tenant_id=TENANT_WITH_SUB,
            plan=plan,
            trial_started_at=datetime(2026, 8, 11, 0, 0, 0),
            trial_ends_at=datetime(2026, 9, 10, 0, 0, 0),
        )

        self.assertEqual(subscription.tenant_id, TENANT_WITH_SUB)
        self.assertEqual(subscription.plan_id, plan.id)
        self.assertEqual(subscription.status, STATUS_TRIAL)

        current = await service.get_current_subscription(TENANT_WITH_SUB)
        self.assertIsNotNone(current)
        self.assertEqual(current.id, subscription.id)

    # ---- Test 4: trial dates persist and read back correctly ------------------

    async def test_trial_dates_roundtrip(self):
        self.db.add(Tenant(tenant_id=TENANT_WITH_SUB, name="Sub Tenant", password_hash="x", status=True))
        plan = Plan(code="PRO", name="专业版", is_active=True)
        self.db.add(plan)
        await self.db.commit()
        await self.db.refresh(plan)

        started = datetime(2026, 8, 11, 9, 30, 0)
        ends = datetime(2026, 9, 10, 9, 30, 0)
        service = SubscriptionService(self.db)
        subscription = await service.create_trial(TENANT_WITH_SUB, plan, started, ends)
        subscription_id = subscription.id

        # Re-read from a fresh query (not the same in-memory object) to prove it
        # was actually persisted, not just held in the Python attribute.
        result = await self.db.execute(select(Subscription).where(Subscription.id == subscription_id))
        reloaded = result.scalar_one()
        self.assertEqual(reloaded.trial_started_at, started)
        self.assertEqual(reloaded.trial_ends_at, ends)

        self.assertTrue(service.is_trial(reloaded))
        self.assertTrue(service.is_active(reloaded, now=datetime(2026, 8, 20)))
        self.assertFalse(service.is_active(reloaded, now=datetime(2026, 9, 20)))

    # ---- Test 5 (P0): existing Tenant with NO Subscription must be unaffected --

    async def test_existing_tenant_without_subscription_is_fully_legal(self):
        self.db.add(Tenant(tenant_id=TENANT_LEGACY, name="Legacy Tenant", password_hash="x", status=True))
        await self.db.commit()

        service = SubscriptionService(self.db)

        # No exception, no auto-created row.
        current = await service.get_current_subscription(TENANT_LEGACY)
        self.assertIsNone(current)

        sub_count = await self.db.execute(
            select(Subscription).where(Subscription.tenant_id == TENANT_LEGACY)
        )
        self.assertEqual(len(sub_count.scalars().all()), 0)

        # Reading the Tenant row itself is completely unaffected: still exists,
        # status untouched by anything Subscription-related.
        tenant_result = await self.db.execute(select(Tenant).where(Tenant.tenant_id == TENANT_LEGACY))
        tenant = tenant_result.scalar_one()
        self.assertTrue(tenant.status)

        # is_active()/is_trial() on "no subscription" must be a plain False,
        # never an exception, and must never mutate anything.
        self.assertFalse(service.is_active(None))
        self.assertFalse(service.is_trial(None))

    # ---- Bonus: enforce the "no cross-domain side effects" design constraint --

    def test_subscription_service_has_no_cross_domain_imports(self):
        # Checks actual module bindings (i.e. real imports), not comments/docstrings —
        # the module intentionally documents these forbidden names in a comment
        # explaining the isolation rule, which a plain source-text search would
        # false-positive on.
        forbidden = [
            "TenantService",
            "OrderService",
            "OrderPaymentService",
            "WxPayService",
            "order_print_service",
            "MembershipService",
            "CouponService",
            "TencentSmsService",
        ]
        module_names = set(vars(subscription_service_module).keys())
        for name in forbidden:
            self.assertNotIn(name, module_names, f"SubscriptionService must not import {name}")

        import_lines = [
            line for line in inspect.getsource(subscription_service_module).splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for line in import_lines:
            for name in forbidden:
                self.assertNotIn(name, line, f"SubscriptionService must not import {name}")

    def test_subscription_service_status_constants(self):
        self.assertEqual({STATUS_TRIAL, STATUS_ACTIVE, STATUS_CANCELLED}, {"TRIAL", "ACTIVE", "CANCELLED"})


if __name__ == "__main__":
    unittest.main()
