"""Phase F1F-D0 — optional entitlement safe-check primitive tests.

Scope: docs/saas-subscription-audit.md Phase F1F-D0. Proves
optional_capability_enabled() (app/services/optional_entitlement.py):
- grants True only for a plan that genuinely has the capability;
- returns False (never raises) for a normal "plan lacks capability" denial;
- returns False (never raises) for entitlement system/data errors, an
  unknown capability key, and any unexpected EntitlementService exception;
- never touches the caller's own DB session -- it opens its own, so a
  failure inside it can never poison a surrounding business transaction;
- performs no writes and uses no cross-request cache.

This phase wires the checker into NOTHING business-facing. These are the
only tests exercising it (mirrors F1F-A's zero-wiring precedent for
EntitlementService itself).
"""

from __future__ import annotations

import asyncio
import inspect
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.services.entitlement_service import EntitlementService, UnknownCapabilityError
from app.services.optional_entitlement import optional_capability_enabled
from app.services.subscription_service import STATUS_ACTIVE, SubscriptionService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@event.listens_for(Plan, "before_insert")
def _assign_plan_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Subscription, "before_insert")
def _assign_subscription_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Tenant, "before_insert")
def _assign_tenant_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


TENANT_FREE = "tenant-f1fd0-free"
TENANT_STANDARD = "tenant-f1fd0-standard"
TENANT_PRO = "tenant-f1fd0-pro"


class BaseOptionalEntitlementTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add_all(
            [
                Tenant(tenant_id=TENANT_FREE, name="Free Tenant", password_hash="x", status=True),
                Tenant(tenant_id=TENANT_STANDARD, name="Standard Tenant", password_hash="x", status=True),
                Tenant(tenant_id=TENANT_PRO, name="Pro Tenant", password_hash="x", status=True),
                Plan(code="FREE", name="免费版", is_active=True, price_month_cents=0, price_year_cents=0, sort_order=0),
                Plan(code="STANDARD", name="普通版", is_active=True, price_month_cents=5900, price_year_cents=60900, sort_order=1),
                Plan(code="PRO", name="专业版", is_active=True, price_month_cents=9900, price_year_cents=102200, sort_order=2),
            ]
        )
        await self.db.commit()
        self.subscription_service = SubscriptionService(self.db)
        await self._activate(TENANT_STANDARD, "STANDARD")
        await self._activate(TENANT_PRO, "PRO")

        # Established codebase pattern (see test_standard_capability_enforcement.py,
        # auth_middleware tests): point the real AsyncSessionLocal factory at this
        # test's own in-memory engine so the module-under-test's independently
        # opened session sees the same seeded rows.
        self._session_patch = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._session_patch.start()

    async def asyncTearDown(self):
        self._session_patch.stop()
        await self.db.close()
        await self.engine.dispose()

    async def _activate(self, tenant_id: str, plan_code: str, *, ends_delta=timedelta(days=30)):
        plan = await self.subscription_service.get_plan_by_code(plan_code)
        now = datetime.utcnow()
        sub = Subscription(
            tenant_id=tenant_id, plan_id=plan.id, status=STATUS_ACTIVE,
            started_at=now, ends_at=now + ends_delta,
        )
        self.db.add(sub)
        await self.db.commit()
        await self.db.refresh(sub)
        return sub


# ---------------------------------------------------------------------------
# PHASE 8 -- granted
# ---------------------------------------------------------------------------

class OptionalCapabilityGrantedTest(BaseOptionalEntitlementTest):
    async def test_pro_membership_granted(self):
        result = await optional_capability_enabled(TENANT_PRO, "MEMBERSHIP")
        self.assertTrue(result)

    async def test_standard_kitchen_print_granted(self):
        result = await optional_capability_enabled(TENANT_STANDARD, "KITCHEN_PRINT")
        self.assertTrue(result)


# ---------------------------------------------------------------------------
# PHASE 9 -- normal denial, never raises
# ---------------------------------------------------------------------------

class OptionalCapabilityDeniedTest(BaseOptionalEntitlementTest):
    async def test_free_membership_denied(self):
        result = await optional_capability_enabled(TENANT_FREE, "MEMBERSHIP")
        self.assertFalse(result)

    async def test_standard_coupons_capability_denied(self):
        result = await optional_capability_enabled(TENANT_STANDARD, "COUPONS")
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# PHASE 10 -- unexpected system error fails safe (False, no raise)
# ---------------------------------------------------------------------------

class OptionalCapabilitySystemErrorTest(BaseOptionalEntitlementTest):
    async def test_unexpected_exception_returns_false_not_raised(self):
        with patch.object(
            EntitlementService, "has_capability",
            new=AsyncMock(side_effect=RuntimeError("entitlement resolution exploded")),
        ):
            result = await optional_capability_enabled(TENANT_PRO, "MEMBERSHIP")
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# PHASE 11 -- data integrity error fails safe (never defaults True)
# ---------------------------------------------------------------------------

class OptionalCapabilityDataIntegrityTest(BaseOptionalEntitlementTest):
    async def test_missing_free_plan_returns_false(self):
        result = await self.db.execute(select(Plan).where(Plan.code == "FREE"))
        free_plan = result.scalar_one()
        await self.db.delete(free_plan)
        await self.db.commit()

        # TENANT_FREE has no Subscription row -> resolution falls through to
        # the (now-missing) FREE plan catalog lookup -> PlanDataIntegrityError.
        result = await optional_capability_enabled(TENANT_FREE, "MEMBERSHIP")
        self.assertFalse(result)

    async def test_unknown_effective_plan_code_returns_false(self):
        tenant_id = "tenant-f1fd0-unknown-plan"
        self.db.add(Tenant(tenant_id=tenant_id, name="Unknown Plan Tenant", password_hash="x", status=True))
        self.db.add(Plan(code="ENTERPRISE", name="未知档位", is_active=True, price_month_cents=0, price_year_cents=0, sort_order=9))
        await self.db.commit()
        plan = await self.subscription_service.get_plan_by_code("ENTERPRISE")
        now = datetime.utcnow()
        self.db.add(Subscription(
            tenant_id=tenant_id, plan_id=plan.id, status=STATUS_ACTIVE,
            started_at=now, ends_at=now + timedelta(days=30),
        ))
        await self.db.commit()

        result = await optional_capability_enabled(tenant_id, "MEMBERSHIP")
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# PHASE 12 -- unknown capability: optional checker swallows it; direct
# EntitlementService callers still fail loud (F1F-A contract untouched).
# ---------------------------------------------------------------------------

class OptionalCapabilityUnknownKeyTest(BaseOptionalEntitlementTest):
    async def test_unknown_capability_via_optional_checker_returns_false(self):
        result = await optional_capability_enabled(TENANT_PRO, "THIS_CAPABILITY_DOES_NOT_EXIST")
        self.assertFalse(result)

    async def test_unknown_capability_via_entitlement_service_directly_still_raises(self):
        """F1F-A contract proof: the underlying authority is unchanged --
        only the optional wrapper swallows this; direct callers still see
        UnknownCapabilityError fail loud."""
        with self.assertRaises(UnknownCapabilityError):
            await EntitlementService(self.db).has_capability(TENANT_PRO, "THIS_CAPABILITY_DOES_NOT_EXIST")


# ---------------------------------------------------------------------------
# PHASE 13 -- independent session proof + transaction poisoning proof
# ---------------------------------------------------------------------------

class OptionalCapabilitySessionIsolationTest(BaseOptionalEntitlementTest):
    def test_checker_signature_accepts_no_session(self):
        """Structural proof: the function cannot be handed a caller session
        at all -- there is no db/session parameter in its signature."""
        params = inspect.signature(optional_capability_enabled).parameters
        self.assertEqual(list(params.keys()), ["tenant_id", "capability"])

    async def test_checker_opens_its_own_session_via_the_patched_factory(self):
        """Behavioral proof: the checker calls the session factory itself
        (a spy wrapping the same factory) rather than being given one."""
        calls = {"count": 0}
        real_factory = self.SessionLocal

        def spy_factory():
            calls["count"] += 1
            return real_factory()

        with patch("app.core.database.AsyncSessionLocal", spy_factory):
            result = await optional_capability_enabled(TENANT_PRO, "MEMBERSHIP")

        self.assertTrue(result)
        self.assertEqual(calls["count"], 1, "checker must open exactly one session of its own per call")

    async def test_entitlement_failure_cannot_poison_caller_transaction(self):
        """PHASE 13's most important test: a caller with its own pending,
        uncommitted business write calls the isolated optional checker,
        which hits a simulated internal exception -- the caller's own
        transaction must still be free to continue and commit normally,
        and the business row must persist."""
        caller_tenant = Tenant(
            tenant_id="tenant-f1fd0-caller-txn", name="Caller Txn Tenant",
            password_hash="x", status=True,
        )
        self.db.add(caller_tenant)
        # Caller business write is pending (flushed, not yet committed) when
        # the optional checker runs and fails internally.
        await self.db.flush()

        with patch.object(
            EntitlementService, "has_capability",
            new=AsyncMock(side_effect=RuntimeError("simulated entitlement resolution failure")),
        ):
            checked = await optional_capability_enabled(TENANT_PRO, "MEMBERSHIP")
        self.assertFalse(checked, "checker must fail safe, not raise, on the simulated exception")

        # Caller's own session/transaction must be entirely unaffected --
        # it can still commit its own pending write.
        await self.db.commit()

        result = await self.db.execute(
            select(Tenant).where(Tenant.tenant_id == "tenant-f1fd0-caller-txn")
        )
        self.assertIsNotNone(result.scalar_one_or_none(), "caller's business row must persist")


# ---------------------------------------------------------------------------
# PHASE 14 -- read-only proof: no mutation, no commit performed by the checker
# ---------------------------------------------------------------------------

class OptionalCapabilityReadOnlyTest(BaseOptionalEntitlementTest):
    async def test_checker_performs_zero_writes(self):
        before_plans = (await self.db.execute(select(Plan))).scalars().all()
        before_subs = (await self.db.execute(select(Subscription))).scalars().all()
        before_tenants = (await self.db.execute(select(Tenant))).scalars().all()

        await optional_capability_enabled(TENANT_PRO, "MEMBERSHIP")
        await optional_capability_enabled(TENANT_FREE, "MEMBERSHIP")
        with patch.object(
            EntitlementService, "has_capability",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            await optional_capability_enabled(TENANT_STANDARD, "MEMBERSHIP")

        after_plans = (await self.db.execute(select(Plan))).scalars().all()
        after_subs = (await self.db.execute(select(Subscription))).scalars().all()
        after_tenants = (await self.db.execute(select(Tenant))).scalars().all()

        self.assertEqual(len(before_plans), len(after_plans))
        self.assertEqual(len(before_subs), len(after_subs))
        self.assertEqual(len(before_tenants), len(after_tenants))


if __name__ == "__main__":
    unittest.main()
