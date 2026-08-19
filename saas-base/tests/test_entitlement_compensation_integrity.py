"""F1G-CM-PD0-COMP -- Entitlement Compensation Integrity regression tests.

Frozen invariant: entitlement gates CREATION of new optional side effects
(points accrual, coupon issuance, commission accrual). It must NEVER gate
COMPENSATION for side effects that were already persisted -- refund/reversal
must be driven by the ORIGINAL PERSISTED FACT (a ledger row, a coupon's own
status, a commission record's own existence), never by the tenant's CURRENT
plan.

Audit finding (see this phase's FINAL_REPORT for the full matrix): the only
concretely reproduced defect was in a TEST's own mock setup
(test_entitlement_final_integration.py::test_membership_reversal_survives_downgrade
used `wraps=` combined with `autospec=True` on an async method, which is a
confirmed unittest.mock bug -- it silently no-ops instead of calling through,
so the assertion was passing/failing for the wrong reason). The real
MembershipService.reverse_consumption() implementation was already correct
(reads the PointLedger by ref_id=consumption_id, never checks current
entitlement). That test was fixed in place (swapped to `side_effect=`, the
correct pattern) -- this file adds new, independent coverage using the same
corrected pattern, plus the coupon/distribution/consumption audit and the
grandfather-migration compatibility scenario the phase requires.

Coupon and distribution/referral were audited and found to have NO
compensation-gate defect:
  - Coupon refund unlock (`_refund_order_payment`) never calls
    optional_capability_enabled() at all -- it unconditionally restores
    coupon.status, already correct.
  - Distribution/referral has no refund-triggered commission reversal
    mechanism anywhere in this codebase (order refund never touches
    CommissionRecord) -- there is nothing for an entitlement check to
    incorrectly gate. Building a brand-new commission-reversal feature is
    out of this bug-fix phase's scope.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.base import Base
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.models.member_account import MemberAccount
from app.models.order import Order
from app.models.point_ledger import PointLedger
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.services.membership_service import MembershipService
from app.services.order_payment_service import OrderPaymentService
from app.services.subscription_service import (
    STATUS_ACTIVE,
    STATUS_TRIAL,
    SubscriptionService,
)
from app.services.tenant_commercialization_grandfather import backfill_zero_history_tenants
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


TENANT_PRO = "tenant-comp-pro"
TENANT_FREE = "tenant-comp-free"
TENANT_GF_LEGACY = "tenant-comp-gf-legacy"


class CompensationIntegrityBaseTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._db_file = f"{tempfile.gettempdir()}/f1gcomp_{uuid.uuid4().hex}.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_file}")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add_all(
            [
                Plan(code="FREE", name="免费版", is_active=True, price_month_cents=0, price_year_cents=0, sort_order=0),
                Plan(code="STANDARD", name="普通版", is_active=True, price_month_cents=5900, price_year_cents=60900, sort_order=1),
                Plan(code="PRO", name="专业版", is_active=True, price_month_cents=9900, price_year_cents=102200, sort_order=2),
            ]
        )
        await self.db.commit()
        self.sub_service = SubscriptionService(self.db)

        self._session_patch = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._session_patch.start()
        self._original_redis_enabled = settings.REDIS_ENABLED
        settings.REDIS_ENABLED = False

    async def asyncTearDown(self):
        settings.REDIS_ENABLED = self._original_redis_enabled
        self._session_patch.stop()
        await self.db.close()
        await self.engine.dispose()
        try:
            os.remove(self._db_file)
        except OSError:
            pass

    async def _seed_tenant(self, tenant_id: str, phone: str | None = None) -> Tenant:
        tenant = Tenant(tenant_id=tenant_id, name=f"Shop {tenant_id}", password_hash="x", status=True, is_open=True, phone=phone)
        self.db.add(tenant)
        await self.db.commit()
        await self.db.refresh(tenant)
        return tenant

    async def _subscribe(self, tenant_id: str, plan_code: str, *, status=STATUS_ACTIVE, ends_delta=timedelta(days=30)) -> Subscription:
        plan = await self.sub_service.get_plan_by_code(plan_code)
        now = datetime.utcnow()
        sub = Subscription(
            tenant_id=tenant_id, plan_id=plan.id, status=status,
            started_at=now if status == STATUS_ACTIVE else None,
            ends_at=now + ends_delta if status == STATUS_ACTIVE else None,
        )
        self.db.add(sub)
        await self.db.commit()
        await self.db.refresh(sub)
        return sub

    async def _expire(self, tenant_id: str) -> None:
        result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))
        sub = result.scalars().first()
        sub.status = "ACTIVE"
        sub.ends_at = datetime.utcnow() - timedelta(seconds=1)
        await self.db.commit()

    async def _seed_customer(self, tenant_id: str, *, openid="op-1", phone="13800000001") -> Customer:
        customer = Customer(tenant_id=tenant_id, openid=openid, name="顾客", phone=phone, status=1)
        self.db.add(customer)
        await self.db.commit()
        await self.db.refresh(customer)
        return customer

    async def _seed_paid_order(self, tenant_id: str, customer_id: int | None, total: str = "50.00") -> Order:
        order = Order(
            tenant_id=tenant_id, customer_id=customer_id, table_no="A1", total=total,
            status="pending_payment", payment_status="unpaid", payment_mode="prepay",
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def _points_balance(self, tenant_id: str, customer_id: int) -> int:
        result = await self.db.execute(
            select(MemberAccount).where(MemberAccount.tenant_id == tenant_id, MemberAccount.customer_id == customer_id)
        )
        account = result.scalar_one_or_none()
        return account.points_balance if account else 0


# ===========================================================================
# Phase 16 -- A-E membership compensation regressions
# ===========================================================================
class MembershipCompensationTest(CompensationIntegrityBaseTest):
    async def test_a_pro_grant_downgrade_free_refund_reverses_once(self):
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO")
        customer = await self._seed_customer(TENANT_PRO)
        order = await self._seed_paid_order(TENANT_PRO, customer.id)
        await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")
        await self.db.commit()

        points_before = await self._points_balance(TENANT_PRO, customer.id)
        self.assertGreater(points_before, 0)

        await self._expire(TENANT_PRO)
        view = await self.sub_service.get_effective_subscription_view(TENANT_PRO)
        self.assertEqual(view.effective_plan.code, "FREE")

        with patch.object(MembershipService, "reverse_consumption", side_effect=MembershipService.reverse_consumption, autospec=True) as spy:
            await OrderPaymentService(self.db)._refund_order_payment(order, reason="test refund")
        spy.assert_awaited_once()
        await self.db.commit()

        points_after = await self._points_balance(TENANT_PRO, customer.id)
        self.assertEqual(points_after, 0, "full reversal of exactly the points this order granted")

    async def test_b_refund_10x_reverses_exactly_once(self):
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO")
        customer = await self._seed_customer(TENANT_PRO)
        order = await self._seed_paid_order(TENANT_PRO, customer.id)
        await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")
        await self.db.commit()

        points_before = await self._points_balance(TENANT_PRO, customer.id)
        self.assertGreater(points_before, 0)
        await self._expire(TENANT_PRO)

        for _ in range(10):
            await OrderPaymentService(self.db)._refund_order_payment(order, reason="repeat refund")
            await self.db.commit()

        points_after = await self._points_balance(TENANT_PRO, customer.id)
        self.assertEqual(points_after, 0, "10 repeated refund calls must reverse exactly once, not 10 times")

        reversal_count = (
            await self.db.execute(
                select(PointLedger).where(
                    PointLedger.tenant_id == TENANT_PRO,
                    PointLedger.customer_id == customer.id,
                    PointLedger.event_type == "refund_reversal",
                )
            )
        ).scalars().all()
        self.assertEqual(len(reversal_count), 1, "exactly one refund_reversal ledger row, not one per call")

    async def test_c_free_new_order_no_points_accrual(self):
        await self._seed_tenant(TENANT_FREE)
        customer = await self._seed_customer(TENANT_FREE)
        order = await self._seed_paid_order(TENANT_FREE, customer.id)

        await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")
        await self.db.commit()

        points = await self._points_balance(TENANT_FREE, customer.id)
        self.assertEqual(points, 0, "FREE tenant must not accrue new membership points")

    async def test_d_refund_without_prior_points_creates_no_artificial_negative(self):
        await self._seed_tenant(TENANT_FREE)
        customer = await self._seed_customer(TENANT_FREE)
        order = await self._seed_paid_order(TENANT_FREE, customer.id)
        # Never paid via _on_payment_success -- no points were ever granted for this order.
        order.payment_status = "paid"
        order.payment_method = "balance"
        order.balance_deduct_requested = order.total
        await self.db.commit()

        await OrderPaymentService(self.db)._refund_order_payment(order, reason="refund never-earned")
        await self.db.commit()

        points = await self._points_balance(TENANT_FREE, customer.id)
        self.assertGreaterEqual(points, 0, "refunding an order that never earned points must never go negative")
        self.assertEqual(points, 0)

    async def test_e_downgrade_then_reupgrade_refund_still_reverses_once(self):
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO")
        customer = await self._seed_customer(TENANT_PRO)
        order = await self._seed_paid_order(TENANT_PRO, customer.id)
        await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")
        await self.db.commit()
        points_before = await self._points_balance(TENANT_PRO, customer.id)
        self.assertGreater(points_before, 0)

        await self._expire(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO")  # re-upgrade

        await OrderPaymentService(self.db)._refund_order_payment(order, reason="refund after reupgrade")
        await self.db.commit()

        points_after = await self._points_balance(TENANT_PRO, customer.id)
        self.assertEqual(points_after, 0, "original refund must still reverse the original grant after a reupgrade")


# ===========================================================================
# Phase 17 -- order-of-events matrices
# ===========================================================================
class EventOrderingTest(CompensationIntegrityBaseTest):
    async def test_pay_downgrade_refund(self):
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO")
        customer = await self._seed_customer(TENANT_PRO)
        order = await self._seed_paid_order(TENANT_PRO, customer.id)
        await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")
        await self.db.commit()
        points_before = await self._points_balance(TENANT_PRO, customer.id)

        await self._expire(TENANT_PRO)
        await OrderPaymentService(self.db)._refund_order_payment(order, reason="pay->downgrade->refund")
        await self.db.commit()

        self.assertGreater(points_before, 0)
        self.assertEqual(await self._points_balance(TENANT_PRO, customer.id), 0)

    async def test_pay_downgrade_upgrade_refund(self):
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO")
        customer = await self._seed_customer(TENANT_PRO)
        order = await self._seed_paid_order(TENANT_PRO, customer.id)
        await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")
        await self.db.commit()
        points_before = await self._points_balance(TENANT_PRO, customer.id)

        await self._expire(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO")
        await OrderPaymentService(self.db)._refund_order_payment(order, reason="pay->downgrade->upgrade->refund")
        await self.db.commit()

        self.assertGreater(points_before, 0)
        self.assertEqual(await self._points_balance(TENANT_PRO, customer.id), 0)

    async def test_pay_refund_then_downgrade(self):
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO")
        customer = await self._seed_customer(TENANT_PRO)
        order = await self._seed_paid_order(TENANT_PRO, customer.id)
        await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")
        await self.db.commit()
        points_before = await self._points_balance(TENANT_PRO, customer.id)

        await OrderPaymentService(self.db)._refund_order_payment(order, reason="pay->refund->downgrade")
        await self.db.commit()
        await self._expire(TENANT_PRO)

        self.assertGreater(points_before, 0)
        self.assertEqual(await self._points_balance(TENANT_PRO, customer.id), 0)


# ===========================================================================
# Phase 18 -- grandfather migration compatibility
# ===========================================================================
class GrandfatherCompensationCompatibilityTest(CompensationIntegrityBaseTest):
    async def test_gf_trial_expiry_then_refund_still_reverses(self):
        """Realistic 30-day-post-deploy path: a legacy tenant backfilled by
        20260819_0002's PRO TRIAL earns points on a paid order, the trial
        expires to FREE, and a later refund must still reverse the points --
        exactly the same invariant, exercised on a grandfathered tenant."""
        await self._seed_tenant(TENANT_GF_LEGACY)

        async with self.engine.begin() as conn:
            inserted = await conn.run_sync(
                lambda sync_conn: backfill_zero_history_tenants(sync_conn, now=datetime.utcnow())
            )
        self.assertEqual(inserted, 1)

        view = await self.sub_service.get_effective_subscription_view(TENANT_GF_LEGACY)
        self.assertEqual(view.effective_plan.code, "PRO")
        self.assertTrue(view.is_trial)

        customer = await self._seed_customer(TENANT_GF_LEGACY)
        order = await self._seed_paid_order(TENANT_GF_LEGACY, customer.id)
        await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")
        await self.db.commit()
        points_before = await self._points_balance(TENANT_GF_LEGACY, customer.id)
        self.assertGreater(points_before, 0)

        # Trial expires (30 days later).
        result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == TENANT_GF_LEGACY))
        sub = result.scalars().first()
        sub.trial_ends_at = datetime.utcnow() - timedelta(seconds=1)
        await self.db.commit()
        post_expiry_view = await self.sub_service.get_effective_subscription_view(TENANT_GF_LEGACY)
        self.assertEqual(post_expiry_view.effective_plan.code, "FREE")

        await OrderPaymentService(self.db)._refund_order_payment(order, reason="gf trial expiry refund")
        await self.db.commit()

        self.assertEqual(await self._points_balance(TENANT_GF_LEGACY, customer.id), 0)


# ===========================================================================
# Phase 9/10 -- coupon and distribution compensation audit (documentation +
# regression, not a fix: both were already safe)
# ===========================================================================
class CouponCompensationAlreadySafeTest(CompensationIntegrityBaseTest):
    async def test_coupon_unlock_on_refund_not_entitlement_gated(self):
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO")
        customer = await self._seed_customer(TENANT_PRO)
        template = CouponTemplate(
            tenant_id=TENANT_PRO, name="老券", type="FIXED", value=5,
            start_time=datetime.utcnow() - timedelta(days=1), end_time=datetime.utcnow() + timedelta(days=30),
        )
        self.db.add(template)
        await self.db.commit()
        coupon = Coupon(
            tenant_id=TENANT_PRO, template_id=template.id, customer_id=customer.id,
            code="COMPTEST1", status="LOCKED", expire_time=datetime.utcnow() + timedelta(days=30),
        )
        self.db.add(coupon)
        order = await self._seed_paid_order(TENANT_PRO, customer.id)
        order.coupon_id = coupon.id
        order.payment_status = "paid"
        order.payment_method = "balance"
        order.balance_deduct_requested = order.total
        await self.db.commit()

        await self._expire(TENANT_PRO)  # tenant now FREE -- COUPONS capability lost

        await OrderPaymentService(self.db)._refund_order_payment(order, reason="coupon compensation regression")
        await self.db.commit()
        await self.db.refresh(coupon)
        self.assertEqual(coupon.status, "UNUSED", "coupon compensation must run regardless of current plan (already safe, no fix needed)")
