"""Phase 05A service-period adjustment domain contracts.

These tests are authored for CI. The implementation phase policy forbids
executing local test suites; SQLite also cannot prove MySQL FOR UPDATE
semantics, so real lock concurrency remains a later runtime gate.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.billing import BillingPayment
from app.models.subscription import Plan, Subscription
from app.models.subscription_adjustment import SubscriptionAdjustment
from app.models.tenant import Tenant
from app.services.subscription_adjustment_service import (
    ADJUSTMENT_COMPENSATION,
    ADJUSTMENT_CORRECTION,
    ADJUSTMENT_GIFT,
    ADJUSTMENT_INTERNAL_TEST,
    ADJUSTMENT_OTHER,
    ADJUSTMENT_TRIAL_EXTENSION,
    OPERATION_ADD_DAYS,
    OPERATION_SET_EXPIRY_DATE,
    SubscriptionAdjustmentError,
    SubscriptionAdjustmentService,
)
from app.services.subscription_service import BILLING_PERIOD_MONTH, STATUS_ACTIVE, STATUS_CANCELLED, STATUS_EXPIRED, STATUS_TRIAL, SubscriptionService
from app.utils.id_generator import generate_snowflake_id


if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


for _model in (Plan, Subscription, SubscriptionAdjustment, Tenant):
    event.listen(
        _model,
        "before_insert",
        lambda mapper, connection, target: setattr(target, "id", target.id or generate_snowflake_id()),
    )


class SubscriptionAdjustmentServiceTest(unittest.IsolatedAsyncioTestCase):
    NOW = datetime(2026, 10, 5, 8, 0, 0)

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.tenant = Tenant(tenant_id="tenant-adjust", name="Adjustment Tenant", password_hash="x", status=True)
        self.free = Plan(code="FREE", name="免费版", is_active=True)
        self.pro = Plan(code="PRO", name="专业版", is_active=True, price_month_cents=9900, price_year_cents=102200)
        self.db.add_all([self.tenant, self.free, self.pro])
        await self.db.commit()
        self.service = SubscriptionAdjustmentService(self.db)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _add_subscription(
        self,
        *,
        status=STATUS_ACTIVE,
        expiry=None,
        created_at=None,
        plan=None,
    ) -> Subscription:
        created_at = created_at or self.NOW - timedelta(days=10)
        plan = plan or self.pro
        row = Subscription(
            tenant_id=self.tenant.tenant_id,
            plan_id=plan.id,
            status=status,
            started_at=created_at if status == STATUS_ACTIVE else None,
            ends_at=expiry if status == STATUS_ACTIVE else None,
            trial_started_at=created_at if status == STATUS_TRIAL else None,
            trial_ends_at=expiry if status == STATUS_TRIAL else None,
            created_at=created_at,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def _preview(self, **overrides):
        payload = {
            "operation_type": OPERATION_ADD_DAYS,
            "days": 7,
            "expires_at": None,
            "adjustment_type": ADJUSTMENT_GIFT,
            "reason": "  launch gift  ",
            "note": None,
            "now": self.NOW,
        }
        payload.update(overrides)
        return await self.service.preview(self.tenant.tenant_id, **payload)

    async def _commit(self, preview, **overrides):
        payload = {
            "operation_type": OPERATION_ADD_DAYS,
            "days": 7,
            "expires_at": None,
            "adjustment_type": ADJUSTMENT_GIFT,
            "reason": "launch gift",
            "note": None,
            "expected_subscription_id": int(preview["subscription_id"]),
            "expected_before_expiry": preview["before_expiry"],
            "idempotency_key": str(uuid4()),
            "operator_type": "SUPER_ADMIN",
            "operator_id": None,
            "operator_label": "super_admin",
            "operator_ip": "127.0.0.1",
            "request_id": str(uuid4()),
            "now": self.NOW,
        }
        payload.update(overrides)
        return await self.service.commit(self.tenant.tenant_id, **payload)

    async def _assert_error(self, code, awaitable):
        with self.assertRaises(SubscriptionAdjustmentError) as caught:
            await awaitable
        self.assertEqual(caught.exception.error_code, code)

    async def test_active_add_7_updates_ends_at_and_writes_ledger(self):
        row = await self._add_subscription(expiry=self.NOW + timedelta(days=20))
        preview = await self._preview(days=7)
        result = await self._commit(preview, days=7)
        await self.db.refresh(row)
        self.assertEqual(row.ends_at, self.NOW + timedelta(days=27))
        self.assertEqual(result["delta_days"], 7)
        self.assertIsInstance(result["subscription_id"], str)
        ledger = (await self.db.execute(select(SubscriptionAdjustment))).scalar_one()
        self.assertEqual(ledger.before_expiry, self.NOW + timedelta(days=20))
        self.assertEqual(ledger.after_expiry, self.NOW + timedelta(days=27))

    async def test_active_add_365_is_allowed(self):
        await self._add_subscription(expiry=self.NOW + timedelta(days=1))
        preview = await self._preview(days=365)
        self.assertEqual(preview["after_expiry"], "2027-10-06T08:00:00Z")

    async def test_add_days_rejects_zero_negative_decimal_and_over_limit(self):
        await self._add_subscription(expiry=self.NOW + timedelta(days=1))
        for value, code in ((0, "INVALID_DAYS"), (-7, "INVALID_DAYS"), (1.5, "INVALID_DAYS"), (366, "ADD_DAYS_EXCEEDS_LIMIT")):
            await self._assert_error(code, self._preview(days=value))

    async def test_trial_add_days_updates_trial_expiry_only(self):
        row = await self._add_subscription(status=STATUS_TRIAL, expiry=self.NOW + timedelta(days=3))
        preview = await self._preview(adjustment_type=ADJUSTMENT_TRIAL_EXTENSION)
        await self._commit(preview, adjustment_type=ADJUSTMENT_TRIAL_EXTENSION)
        await self.db.refresh(row)
        self.assertEqual(row.trial_ends_at, self.NOW + timedelta(days=10))
        self.assertIsNone(row.ends_at)

    async def test_active_rejects_trial_extension_type(self):
        await self._add_subscription(expiry=self.NOW + timedelta(days=3))
        await self._assert_error(
            "INVALID_ADJUSTMENT_TYPE_FOR_STATE",
            self._preview(adjustment_type=ADJUSTMENT_TRIAL_EXTENSION),
        )

    async def test_natural_expired_active_recovers_from_now(self):
        row = await self._add_subscription(expiry=self.NOW - timedelta(days=1))
        preview = await self._preview(days=7)
        self.assertTrue(preview["natural_expiry_recovery"])
        self.assertEqual(preview["subscription_status"], STATUS_EXPIRED)
        self.assertEqual(preview["after_expiry"], "2026-10-12T08:00:00Z")
        committed = await self._commit(preview, days=7)
        self.assertEqual(committed["subscription_status"], STATUS_ACTIVE)
        await self.db.refresh(row)
        self.assertEqual(row.status, STATUS_ACTIVE)
        self.assertEqual(row.ends_at, self.NOW + timedelta(days=7))

    async def test_natural_expired_trial_recovers_from_now(self):
        row = await self._add_subscription(status=STATUS_TRIAL, expiry=self.NOW - timedelta(seconds=1))
        preview = await self._preview(adjustment_type=ADJUSTMENT_TRIAL_EXTENSION)
        await self._commit(preview, adjustment_type=ADJUSTMENT_TRIAL_EXTENSION)
        await self.db.refresh(row)
        self.assertEqual(row.status, STATUS_TRIAL)
        self.assertEqual(row.trial_ends_at, self.NOW + timedelta(days=7))

    async def test_no_history_and_explicit_terminated_states_are_blocked(self):
        await self._assert_error("NO_ADJUSTABLE_SUBSCRIPTION", self._preview())
        for status, code in ((STATUS_EXPIRED, "SUBSCRIPTION_EXPIRED"), (STATUS_CANCELLED, "SUBSCRIPTION_CANCELLED")):
            await self._add_subscription(status=status, expiry=None, created_at=self.NOW)
            await self._assert_error(code, self._preview())
            await self.db.execute(Subscription.__table__.delete())
            await self.db.commit()

    async def test_free_plan_row_is_not_adjustable(self):
        await self._add_subscription(
            status=STATUS_ACTIVE,
            expiry=self.NOW + timedelta(days=30),
            plan=self.free,
        )
        await self._assert_error("NO_ADJUSTABLE_SUBSCRIPTION", self._preview())

    async def test_null_active_and_trial_expiry_are_blocked(self):
        for status in (STATUS_ACTIVE, STATUS_TRIAL):
            await self._add_subscription(status=status, expiry=None)
            await self._assert_error("INFINITE_EXPIRY", self._preview())
            await self.db.execute(Subscription.__table__.delete())
            await self.db.commit()

    async def test_effective_row_different_from_latest_is_stale(self):
        await self._add_subscription(expiry=self.NOW + timedelta(days=20), created_at=self.NOW - timedelta(days=2))
        await self._add_subscription(expiry=self.NOW - timedelta(days=1), created_at=self.NOW - timedelta(days=1))
        await self._assert_error("STALE_SUBSCRIPTION", self._preview())

    async def test_set_expiry_accepts_offset_and_normalizes_to_utc(self):
        await self._add_subscription(expiry=datetime(2026, 10, 25, 8))
        preview = await self._preview(
            operation_type=OPERATION_SET_EXPIRY_DATE,
            days=None,
            expires_at="2026-12-31T16:00:00+08:00",
            adjustment_type=ADJUSTMENT_CORRECTION,
            note="contract checked",
        )
        self.assertEqual(preview["after_expiry"], "2026-12-31T08:00:00Z")
        self.assertIsNone(preview["delta_days"])

    async def test_set_expiry_commit_materializes_exact_server_result(self):
        row = await self._add_subscription(expiry=self.NOW + timedelta(days=10))
        values = {
            "operation_type": OPERATION_SET_EXPIRY_DATE,
            "days": None,
            "expires_at": "2027-01-01T00:00:00+08:00",
            "adjustment_type": ADJUSTMENT_CORRECTION,
            "note": "contract checked",
        }
        preview = await self._preview(**values)
        committed = await self._commit(preview, **values)
        await self.db.refresh(row)
        self.assertEqual(committed["after_expiry"], "2026-12-31T16:00:00Z")
        self.assertEqual(row.ends_at, datetime(2026, 12, 31, 16))

    async def test_commit_recalculates_natural_recovery_base_at_commit_time(self):
        await self._add_subscription(expiry=self.NOW - timedelta(days=1))
        preview = await self._preview(days=7)
        committed = await self._commit(preview, days=7, now=self.NOW + timedelta(hours=2))
        self.assertEqual(committed["calculation_base_expiry"], "2026-10-05T10:00:00Z")
        self.assertEqual(committed["after_expiry"], "2026-10-12T10:00:00Z")
        ledger = (await self.db.execute(select(SubscriptionAdjustment))).scalar_one()
        self.assertEqual(ledger.before_status, STATUS_EXPIRED)
        self.assertEqual(ledger.after_status, STATUS_ACTIVE)
        self.assertTrue(ledger.natural_expiry_recovery)

    async def test_set_expiry_rejects_equal_shorter_and_naive(self):
        expiry = self.NOW + timedelta(days=10)
        await self._add_subscription(expiry=expiry)
        common = {"operation_type": OPERATION_SET_EXPIRY_DATE, "days": None, "adjustment_type": ADJUSTMENT_CORRECTION, "note": "checked"}
        await self._assert_error("EXPIRY_SHORTEN_NOT_ALLOWED", self._preview(expires_at="2026-10-15T08:00:00Z", **common))
        await self._assert_error("EXPIRY_SHORTEN_NOT_ALLOWED", self._preview(expires_at="2026-10-14T08:00:00Z", **common))
        await self._assert_error("INVALID_EXPIRY_TIMESTAMP", self._preview(expires_at="2026-12-31T08:00:00", **common))
        await self._assert_error("INVALID_EXPIRY_TIMESTAMP", self._preview(expires_at="20261231T080000+00:00", **common))

    async def test_stale_subscription_id_and_expiry_are_rejected(self):
        await self._add_subscription(expiry=self.NOW + timedelta(days=10))
        preview = await self._preview()
        await self._assert_error("STALE_SUBSCRIPTION", self._commit(preview, expected_subscription_id=1))
        await self._assert_error("STALE_SUBSCRIPTION", self._commit(preview, expected_before_expiry="2026-10-16T08:00:00Z"))

    async def test_same_key_same_fingerprint_replays_once(self):
        await self._add_subscription(expiry=self.NOW + timedelta(days=10))
        preview = await self._preview()
        key = str(uuid4())
        first = await self._commit(preview, idempotency_key=key)
        replay = await self._commit(preview, idempotency_key=key)
        self.assertEqual(replay["adjustment_id"], first["adjustment_id"])
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["after_expiry"], first["after_expiry"])
        self.assertEqual(replay["subscription_status"], first["subscription_status"])
        count = await self.db.scalar(select(func.count()).select_from(SubscriptionAdjustment))
        self.assertEqual(count, 1)

    async def test_same_key_different_fingerprint_conflicts(self):
        await self._add_subscription(expiry=self.NOW + timedelta(days=10))
        preview = await self._preview()
        key = str(uuid4())
        await self._commit(preview, idempotency_key=key)
        await self._assert_error("DUPLICATE_REQUEST", self._commit(preview, idempotency_key=key, days=8))

    async def test_flush_failure_rolls_back_ledger_and_expiry(self):
        row = await self._add_subscription(expiry=self.NOW + timedelta(days=10))
        preview = await self._preview()
        with patch.object(self.db, "flush", AsyncMock(side_effect=RuntimeError("forced flush failure"))):
            with self.assertRaises(RuntimeError):
                await self._commit(preview)
        fresh = (await self.db.execute(select(Subscription).where(Subscription.id == row.id))).scalar_one()
        count = await self.db.scalar(select(func.count()).select_from(SubscriptionAdjustment))
        self.assertEqual(fresh.ends_at, self.NOW + timedelta(days=10))
        self.assertEqual(count, 0)

    async def test_history_is_newest_first_and_enforces_limit(self):
        await self._add_subscription(expiry=self.NOW + timedelta(days=10))
        first_preview = await self._preview()
        first = await self._commit(first_preview)
        second_preview = await self._preview(now=self.NOW + timedelta(seconds=1))
        second = await self._commit(second_preview, now=self.NOW + timedelta(seconds=1))
        history = await self.service.list_history(self.tenant.tenant_id, limit=20)
        self.assertEqual([row["adjustment_id"] for row in history], [second["adjustment_id"], first["adjustment_id"]])
        self.assertIsInstance(history[0]["subscription_id"], str)
        self.assertEqual(history[0]["plan"]["plan_name"], "专业版")
        for field in ("before_expiry", "calculation_base_expiry", "after_expiry", "reason", "operator_label", "operator_ip"):
            self.assertIn(field, history[0])
        await self._assert_error("INVALID_HISTORY_LIMIT", self.service.list_history(self.tenant.tenant_id, limit=21))

    async def test_paid_purchase_carries_forward_adjusted_expiry(self):
        await self._add_subscription(expiry=self.NOW + timedelta(days=10))
        preview = await self._preview(days=7)
        adjusted = await self._commit(preview, days=7)
        purchased = await SubscriptionService(self.db).apply_paid_purchase(
            self.tenant.tenant_id,
            "PRO",
            BILLING_PERIOD_MONTH,
            self.NOW,
        )
        self.assertEqual(purchased.started_at, self.NOW)
        self.assertGreater(purchased.ends_at, datetime.fromisoformat(adjusted["after_expiry"].replace("Z", "+00:00")).replace(tzinfo=None))

    async def test_preview_writes_no_ledger_and_payment_history_is_unchanged(self):
        await self._add_subscription(expiry=self.NOW + timedelta(days=10))
        payments_before = await self.db.scalar(select(func.count()).select_from(BillingPayment))
        await self._preview()
        ledgers = await self.db.scalar(select(func.count()).select_from(SubscriptionAdjustment))
        payments_after = await self.db.scalar(select(func.count()).select_from(BillingPayment))
        self.assertEqual(ledgers, 0)
        self.assertEqual(payments_after, payments_before)

    async def test_note_requirement_matrix(self):
        await self._add_subscription(status=STATUS_TRIAL, expiry=self.NOW + timedelta(days=10))
        for adjustment_type in (ADJUSTMENT_COMPENSATION, ADJUSTMENT_CORRECTION, ADJUSTMENT_INTERNAL_TEST, ADJUSTMENT_OTHER):
            await self._assert_error("NOTE_REQUIRED", self._preview(adjustment_type=adjustment_type, note="  "))
        for adjustment_type in (ADJUSTMENT_GIFT, ADJUSTMENT_TRIAL_EXTENSION):
            preview = await self._preview(adjustment_type=adjustment_type, note=None)
            self.assertEqual(preview["adjustment_type"], adjustment_type)


if __name__ == "__main__":
    unittest.main()
