"""Phase F1A -- Plan Catalog + Price Resolution Service regression tests.

Scope: docs/saas-subscription-audit.md Phase F1A. Proves SubscriptionService's
new get_active_plans()/resolve_plan_price() against the frozen commercial
contract (FREE / STANDARD / PRO), and that Plan's application-layer price
validation actually rejects negative cents. No API router, no payment
provider, no billing bridge -- none of that exists yet in this phase.
"""

from __future__ import annotations

import asyncio
import unittest

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.subscription import Plan
from app.services.subscription_service import (
    BILLING_PERIOD_MONTH,
    BILLING_PERIOD_YEAR,
    InvalidBillingPeriodError,
    PlanInactiveError,
    PlanNotFoundError,
    SubscriptionPurchaseNotAllowedError,
    SubscriptionService,
)
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@event.listens_for(Plan, "before_insert")
def _assign_plan_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


class PlanCatalogPricingTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add_all(
            [
                Plan(code="FREE", name="免费版", is_active=True,
                     price_month_cents=0, price_year_cents=0, sort_order=0),
                Plan(code="STANDARD", name="普通版", is_active=True,
                     price_month_cents=5900, price_year_cents=60900, sort_order=1),
                Plan(code="PRO", name="专业版", is_active=True,
                     price_month_cents=9900, price_year_cents=102200, sort_order=2),
                Plan(code="RETIRED", name="停用版", is_active=False,
                     price_month_cents=1234, price_year_cents=5678, sort_order=99),
            ]
        )
        await self.db.commit()
        self.service = SubscriptionService(self.db)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    # ---- Phase 6: fixed price resolution ---------------------------------

    async def test_standard_month_price(self):
        self.assertEqual(await self.service.resolve_plan_price("STANDARD", BILLING_PERIOD_MONTH), 5900)

    async def test_standard_year_price(self):
        self.assertEqual(await self.service.resolve_plan_price("STANDARD", BILLING_PERIOD_YEAR), 60900)

    async def test_pro_month_price(self):
        self.assertEqual(await self.service.resolve_plan_price("PRO", BILLING_PERIOD_MONTH), 9900)

    async def test_pro_year_price(self):
        self.assertEqual(await self.service.resolve_plan_price("PRO", BILLING_PERIOD_YEAR), 102200)

    async def test_free_not_payable(self):
        with self.assertRaises(SubscriptionPurchaseNotAllowedError):
            await self.service.resolve_plan_price("FREE", BILLING_PERIOD_MONTH)

    async def test_invalid_billing_period(self):
        with self.assertRaises(InvalidBillingPeriodError):
            await self.service.resolve_plan_price("PRO", "WEEK")

    async def test_unknown_plan(self):
        with self.assertRaises(PlanNotFoundError):
            await self.service.resolve_plan_price("ENTERPRISE", BILLING_PERIOD_MONTH)

    async def test_inactive_plan(self):
        with self.assertRaises(PlanInactiveError):
            await self.service.resolve_plan_price("RETIRED", BILLING_PERIOD_MONTH)

    async def test_no_float_price(self):
        price = await self.service.resolve_plan_price("PRO", BILLING_PERIOD_YEAR)
        self.assertIsInstance(price, int)
        self.assertNotIsInstance(price, float)
        # Never derived as month_price * 12 * 0.86 at runtime -- read straight
        # from the fixed DB column, which is exactly why it lands on a cents
        # value (102200) that isn't 9900 * 12 (118800) or any float rounding
        # of a 14% discount off it.
        self.assertNotEqual(price, 9900 * 12)

    # ---- Plan catalog listing ----------------------------------------------

    async def test_get_active_plans_excludes_inactive_and_orders_by_sort_order(self):
        plans = await self.service.get_active_plans()
        self.assertEqual([p.code for p in plans], ["FREE", "STANDARD", "PRO"])
        self.assertNotIn("RETIRED", [p.code for p in plans])

    async def test_get_plan_by_code_still_works_for_new_fields(self):
        plan = await self.service.get_plan_by_code("PRO")
        self.assertEqual(plan.price_month_cents, 9900)
        self.assertEqual(plan.price_year_cents, 102200)
        self.assertEqual(plan.sort_order, 2)


class PlanPriceValidationTest(unittest.TestCase):
    """Application-layer non-negative price guard (PRICE_DB_CHECK_CONSTRAINT
    is DEFERred -- see the F1A migration docstring -- so this is the only
    enforcement point in this phase)."""

    def test_negative_month_price_rejected(self):
        with self.assertRaises(ValueError):
            Plan(code="X", name="x", price_month_cents=-1, price_year_cents=0)

    def test_negative_year_price_rejected(self):
        with self.assertRaises(ValueError):
            Plan(code="X", name="x", price_month_cents=0, price_year_cents=-1)

    def test_zero_price_is_allowed(self):
        plan = Plan(code="FREE", name="免费版", price_month_cents=0, price_year_cents=0)
        self.assertEqual(plan.price_month_cents, 0)
        self.assertEqual(plan.price_year_cents, 0)


if __name__ == "__main__":
    unittest.main()
