import asyncio
import unittest

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.base import Base
from app.models.coupon import Coupon
from app.models.customer import Customer
from app.models.tenant import Tenant
from app.services.coupon_service import CouponService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"

# NOTE on what this file can and cannot prove:
# The real bug (and the fix in CouponService._dedup_issue_lock) is about two
# genuinely concurrent DB transactions racing past a check-then-act window.
# SQLite fundamentally cannot reproduce that: its readers never block on another
# connection's uncommitted write (MySQL's real row locks do), so a true
# multi-connection race against SQLite either doesn't contend at all, or produces
# nondeterministic results that don't actually exercise the lock. This was
# confirmed empirically while writing this test (both a SELECT-based and an
# UPDATE-based row lock failed to serialize two aiosqlite connections against a
# shared on-disk file). That is a SQLite dialect limitation, not evidence the fix
# is wrong on production MySQL, where `UPDATE ... WHERE id=...` reliably takes a
# real row lock held until commit — the same mechanism CouponService already
# relies on elsewhere (send_coupons_with_result's `with_for_update()` on
# CouponTemplate for stock control) and that this fix deliberately reuses.
#
# What IS verified here with a real database, without relying on lock timing:
# 1. The dedup check itself is correct and durable across repeated calls once
#    Redis is unavailable (the exact configuration where the old code had zero
#    protection at all).
# 2. The new locking statement doesn't throw, doesn't corrupt state, and doesn't
#    change behavior for the legitimate "not a duplicate" path.
# Real concurrent-request verification against MySQL is listed as an explicit
# unverified item in the audit report.


class CouponRedisFallbackIdempotencyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._original_redis_enabled = settings.REDIS_ENABLED
        settings.REDIS_ENABLED = False  # simulate Redis being unavailable

        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(tenant_id=TENANT_A, name="Test Restaurant", password_hash="x", status=True, is_open=True)
        self.db.add(self.tenant)
        await self.db.flush()
        self.customer = Customer(tenant_id=TENANT_A, openid="openid-1")
        self.db.add(self.customer)
        await self.db.commit()

    async def asyncTearDown(self):
        settings.REDIS_ENABLED = self._original_redis_enabled
        await self.db.close()
        await self.engine.dispose()

    async def _coupon_count(self):
        result = await self.db.execute(
            select(func.count()).select_from(Coupon).where(
                Coupon.tenant_id == TENANT_A, Coupon.customer_id == self.customer.id,
            )
        )
        return int(result.scalar() or 0)

    async def test_repeated_entry_coupon_requests_with_redis_down_stay_deduped(self):
        svc = CouponService(self.db)
        svc.set_tenant_id(TENANT_A)

        first = await svc.issue_entry_coupon(self.customer.id)
        second = await svc.issue_entry_coupon(self.customer.id)
        third = await svc.issue_entry_coupon(self.customer.id)

        self.assertTrue(first and first.get("is_new"))
        self.assertFalse(second and second.get("is_new"))
        self.assertFalse(third and third.get("is_new"))
        self.assertEqual(await self._coupon_count(), 1)

    async def test_repeated_auto_coupon_requests_with_redis_down_stay_deduped(self):
        svc = CouponService(self.db)
        svc.set_tenant_id(TENANT_A)

        first = await svc.issue_auto_coupon(self.customer.id, "new_customer_coupon")
        second = await svc.issue_auto_coupon(self.customer.id, "new_customer_coupon")

        self.assertEqual(first.get("success_count"), 1)
        self.assertEqual(second.get("success_count"), 0)
        self.assertTrue(second.get("skipped_duplicate"))
        self.assertEqual(await self._coupon_count(), 1)

    async def test_dedup_lock_statement_does_not_error_and_does_not_block_legitimate_new_issuance(self):
        """Sanity check that the new row-lock UPDATE inside _dedup_issue_lock behaves
        correctly for two DIFFERENT customers (must not accidentally serialize/dedup
        across customers) and for two DIFFERENT rule_types for the SAME customer
        (must not accidentally dedup across unrelated rules)."""
        svc = CouponService(self.db)
        svc.set_tenant_id(TENANT_A)
        other_customer = Customer(tenant_id=TENANT_A, openid="openid-2")
        self.db.add(other_customer)
        await self.db.commit()

        r1 = await svc.issue_entry_coupon(self.customer.id)
        r2 = await svc.issue_entry_coupon(other_customer.id)
        r3 = await svc.issue_auto_coupon(self.customer.id, "new_customer_coupon")

        self.assertTrue(r1 and r1.get("is_new"))
        self.assertTrue(r2 and r2.get("is_new"))
        self.assertEqual(r3.get("success_count"), 1)


if __name__ == "__main__":
    unittest.main()
