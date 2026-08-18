"""Phase F1C — Billing -> Subscription Bridge regression tests.

Scope: docs/saas-subscription-audit.md Phase F1C. Proves that a verified
SAAS_SUBSCRIPTION BillingInvoice success is bridged into
SubscriptionService.apply_paid_purchase() exactly once, inside the SAME
local transaction as the existing payment/invoice/commission success path,
gated by the SAME invoice.success_processed_at authority -- not a second
idempotency mechanism. Also proves the legacy (both-null) vs malformed
(exactly-one-null) plan snapshot distinction, that a failed apply rolls the
whole local transaction back (money without entitlement, or the reverse,
must never durably happen), and that non-SAAS_SUBSCRIPTION billing and
ChannelCommissionService behavior are completely unchanged.

Reuses the exact FAKE-provider notify harness from
test_saas_billing_foundation.py (payload builder, before_insert id-assignment
listeners) so this exercises the real process_provider_notification() path,
never invoice.success_processed_at set directly and never a mocked "success".
"""

from __future__ import annotations

import asyncio
import json
import unittest
from datetime import datetime
from unittest.mock import patch

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.billing import billing_wxpay_notify
from app.config import settings
from app.models.base import Base
from app.models.billing import BillingInvoice, BillingPayment
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.services.billing_service import (
    INVOICE_STATUS_PAID,
    INVOICE_STATUS_PENDING,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PENDING,
    BillingService,
    SubscriptionSnapshotIntegrityError,
)
from app.services.channel_commission_service import ChannelCommissionService
from app.services.subscription_service import (
    BILLING_PERIOD_MONTH,
    BILLING_PERIOD_YEAR,
    STATUS_ACTIVE,
    SubscriptionService,
    _add_calendar_months_clamped,
)
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_ID = "tenant-billing-bridge-a"


@event.listens_for(BillingInvoice, "before_insert")
def _assign_invoice_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(BillingPayment, "before_insert")
def _assign_payment_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


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


def make_notify_request(payload: dict, *, signature: str = "valid", provider: str = "FAKE") -> Request:
    raw_body = json.dumps(payload).encode()

    async def _body():
        return raw_body

    headers = []
    if signature:
        headers.append((b"x-billing-fake-signature", signature.encode()))
    req = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/billing/wxpay-notify",
            "headers": headers,
            "query_string": f"provider={provider}".encode(),
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    req.body = _body
    return req


class BillingSubscriptionBridgeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add(Tenant(tenant_id=TENANT_ID, name="Bridge Tenant", password_hash="x", status=True))
        self.db.add_all(
            [
                Plan(code="FREE", name="免费版", is_active=True,
                     price_month_cents=0, price_year_cents=0, sort_order=0),
                Plan(code="STANDARD", name="普通版", is_active=True,
                     price_month_cents=5900, price_year_cents=60900, sort_order=1),
                Plan(code="PRO", name="专业版", is_active=True,
                     price_month_cents=9900, price_year_cents=102200, sort_order=2),
            ]
        )
        await self.db.commit()
        # F1G-CF-A: this file exercises the real FAKE provider path
        # end-to-end (never a mocked "success") -- that path is now gated by
        # settings.ALLOW_MOCK_MONEY_ENDPOINTS, same as every other mock-money
        # endpoint in this codebase.
        settings.ALLOW_MOCK_MONEY_ENDPOINTS = True

    async def asyncTearDown(self):
        settings.ALLOW_MOCK_MONEY_ENDPOINTS = False
        await self.db.close()
        await self.engine.dispose()

    # ---- fixtures -------------------------------------------------------

    async def _create_invoice(
        self,
        *,
        tenant_id: str = TENANT_ID,
        charge_type: str = "SAAS_SUBSCRIPTION",
        amount_cents: int,
        plan_code: str | None = None,
        billing_period: str | None = None,
    ) -> BillingInvoice:
        invoice = await BillingService(self.db).create_invoice(
            tenant_id=tenant_id,
            charge_type=charge_type,
            description="开心点单SaaS服务费",
            amount_cents=amount_cents,
        )
        if plan_code is not None or billing_period is not None:
            invoice.plan_code = plan_code
            invoice.billing_period = billing_period
            await self.db.commit()
            await self.db.refresh(invoice)
        return invoice

    async def _create_payment(self, invoice: BillingInvoice) -> BillingPayment:
        service = BillingService(self.db)
        service.set_tenant_id(invoice.tenant_id)
        payment, _ = await service.create_payment_attempt(int(invoice.id), provider_name="FAKE")
        return payment

    async def _notify_success(self, payment: BillingPayment, transaction_id: str | None = None, **overrides):
        payload = {
            "out_trade_no": payment.out_trade_no,
            "transaction_id": transaction_id or f"txn-{payment.id}",
            "amount_cents": payment.amount_cents,
            "currency": payment.currency,
            "trade_state": "SUCCESS",
            "provider_mchid": payment.provider_mchid,
            "provider_appid": payment.provider_appid,
        }
        payload.update(overrides)
        return await billing_wxpay_notify(make_notify_request(payload), db=self.db)

    async def _subscription_rows(self, tenant_id: str = TENANT_ID) -> list[Subscription]:
        result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))
        return list(result.scalars().all())

    async def _reload_invoice(self, invoice_id) -> BillingInvoice:
        result = await self.db.execute(select(BillingInvoice).where(BillingInvoice.id == invoice_id))
        return result.scalar_one()

    async def _reload_payment(self, payment_id) -> BillingPayment:
        result = await self.db.execute(select(BillingPayment).where(BillingPayment.id == payment_id))
        return result.scalar_one()

    # ---- Phase 10/11 -- exactly-once purchase application -----------------

    async def test_payment_success_extends_subscription_once(self):
        invoice = await self._create_invoice(
            amount_cents=5900, plan_code="STANDARD", billing_period=BILLING_PERIOD_MONTH
        )
        payment = await self._create_payment(invoice)

        before = datetime.utcnow()
        result = await self._notify_success(payment, transaction_id="txn-once")
        after = datetime.utcnow()

        self.assertEqual(result.get("code"), "SUCCESS")
        rows = await self._subscription_rows()
        self.assertEqual(len(rows), 1)
        sub = rows[0]
        self.assertEqual(sub.status, STATUS_ACTIVE)
        plan = await SubscriptionService(self.db).get_plan_by_code("STANDARD")
        self.assertEqual(sub.plan_id, plan.id)
        self.assertGreaterEqual(sub.started_at, before)
        self.assertLessEqual(sub.started_at, after)
        self.assertGreaterEqual(sub.ends_at, _add_calendar_months_clamped(before, 1))
        self.assertLessEqual(sub.ends_at, _add_calendar_months_clamped(after, 1))

    async def test_ten_x_duplicate_callback_extends_once(self):
        invoice = await self._create_invoice(
            amount_cents=5900, plan_code="STANDARD", billing_period=BILLING_PERIOD_MONTH
        )
        payment = await self._create_payment(invoice)

        before = datetime.utcnow()
        for _ in range(10):
            result = await self._notify_success(payment, transaction_id="txn-repeat-same")
            self.assertEqual(result.get("code"), "SUCCESS")
        after = datetime.utcnow()

        rows = await self._subscription_rows()
        self.assertEqual(len(rows), 1, "10x identical callback must apply the purchase exactly once")
        sub = rows[0]
        self.assertGreaterEqual(sub.ends_at, _add_calendar_months_clamped(before, 1))
        self.assertLessEqual(sub.ends_at, _add_calendar_months_clamped(after, 1))

    async def test_pro_year_purchase_applies_pro_twelve_months(self):
        invoice = await self._create_invoice(
            amount_cents=102200, plan_code="PRO", billing_period=BILLING_PERIOD_YEAR
        )
        payment = await self._create_payment(invoice)

        before = datetime.utcnow()
        result = await self._notify_success(payment, transaction_id="txn-pro-year")
        after = datetime.utcnow()

        self.assertEqual(result.get("code"), "SUCCESS")
        rows = await self._subscription_rows()
        self.assertEqual(len(rows), 1)
        sub = rows[0]
        pro_plan = await SubscriptionService(self.db).get_plan_by_code("PRO")
        self.assertEqual(sub.plan_id, pro_plan.id)
        self.assertGreaterEqual(sub.ends_at, _add_calendar_months_clamped(before, 12))
        self.assertLessEqual(sub.ends_at, _add_calendar_months_clamped(after, 12))

    # ---- Phase 12 -- legacy (pre-F1A) SAAS_SUBSCRIPTION invoice ----------

    async def test_legacy_subscription_invoice_completes_without_subscription_apply(self):
        invoice = await self._create_invoice(amount_cents=5900)  # plan_code/billing_period stay NULL
        self.assertIsNone(invoice.plan_code)
        self.assertIsNone(invoice.billing_period)
        payment = await self._create_payment(invoice)

        with patch("app.services.billing_service.logger") as mock_logger:
            result = await self._notify_success(payment, transaction_id="txn-legacy")

        self.assertEqual(result.get("code"), "SUCCESS")
        await self.db.refresh(payment)
        await self.db.refresh(invoice)
        self.assertEqual(payment.status, PAYMENT_STATUS_PAID)
        self.assertEqual(invoice.status, INVOICE_STATUS_PAID)
        self.assertIsNotNone(invoice.success_processed_at)
        self.assertEqual(await self._subscription_rows(), [])

        warning_calls = [c for c in mock_logger.warning.call_args_list
                          if c.args and "BILLING_LEGACY_SUBSCRIPTION_INVOICE" in c.args[0]]
        self.assertEqual(len(warning_calls), 1)

    # ---- Phase 13 -- malformed snapshot (exactly one field null) ---------

    async def test_malformed_snapshot_plan_code_only_blocks_local_success(self):
        invoice = await self._create_invoice(amount_cents=5900, plan_code="STANDARD", billing_period=None)
        payment = await self._create_payment(invoice)
        invoice_id, payment_id = invoice.id, payment.id  # captured before rollback expires the objects

        with self.assertRaises(SubscriptionSnapshotIntegrityError):
            await self._notify_success(payment, transaction_id="txn-malformed-a")
        await self.db.rollback()

        reloaded_invoice = await self._reload_invoice(invoice_id)
        reloaded_payment = await self._reload_payment(payment_id)
        self.assertEqual(reloaded_invoice.status, INVOICE_STATUS_PENDING)
        self.assertIsNone(reloaded_invoice.success_processed_at)
        self.assertEqual(reloaded_payment.status, PAYMENT_STATUS_PENDING)
        self.assertEqual(await self._subscription_rows(), [])

    async def test_malformed_snapshot_billing_period_only_blocks_local_success(self):
        invoice = await self._create_invoice(amount_cents=5900, plan_code=None, billing_period=BILLING_PERIOD_MONTH)
        payment = await self._create_payment(invoice)
        invoice_id, payment_id = invoice.id, payment.id  # captured before rollback expires the objects

        with self.assertRaises(SubscriptionSnapshotIntegrityError):
            await self._notify_success(payment, transaction_id="txn-malformed-b")
        await self.db.rollback()

        reloaded_invoice = await self._reload_invoice(invoice_id)
        reloaded_payment = await self._reload_payment(payment_id)
        self.assertEqual(reloaded_invoice.status, INVOICE_STATUS_PENDING)
        self.assertIsNone(reloaded_invoice.success_processed_at)
        self.assertEqual(reloaded_payment.status, PAYMENT_STATUS_PENDING)
        self.assertEqual(await self._subscription_rows(), [])

    # ---- Phase 14/15/16 -- verification/dispatch boundaries unchanged ----

    async def test_wrong_amount_rejected_before_subscription_apply(self):
        invoice = await self._create_invoice(
            amount_cents=5900, plan_code="STANDARD", billing_period=BILLING_PERIOD_MONTH
        )
        payment = await self._create_payment(invoice)

        result = await self._notify_success(payment, transaction_id="txn-wrong-amount", amount_cents=1)

        self.assertEqual(result.get("code"), "FAIL")
        await self.db.refresh(invoice)
        await self.db.refresh(payment)
        self.assertEqual(invoice.status, INVOICE_STATUS_PENDING)
        self.assertEqual(payment.status, PAYMENT_STATUS_PENDING)
        self.assertEqual(await self._subscription_rows(), [])

    async def test_pending_payment_does_not_apply_subscription(self):
        invoice = await self._create_invoice(
            amount_cents=5900, plan_code="STANDARD", billing_period=BILLING_PERIOD_MONTH
        )
        payment = await self._create_payment(invoice)

        result = await self._notify_success(payment, transaction_id="txn-pending", trade_state="NOTPAY")

        self.assertEqual(result.get("code"), "SUCCESS")  # ack receipt, no local mutation
        await self.db.refresh(invoice)
        await self.db.refresh(payment)
        self.assertEqual(invoice.status, INVOICE_STATUS_PENDING)
        self.assertEqual(payment.status, PAYMENT_STATUS_PENDING)
        self.assertEqual(await self._subscription_rows(), [])

    async def test_non_saas_charge_type_does_not_touch_subscription(self):
        invoice = await self._create_invoice(charge_type="SETUP_SERVICE", amount_cents=8800)
        payment = await self._create_payment(invoice)

        result = await self._notify_success(payment, transaction_id="txn-non-saas")

        self.assertEqual(result.get("code"), "SUCCESS")
        await self.db.refresh(invoice)
        self.assertEqual(invoice.status, INVOICE_STATUS_PAID)
        self.assertIsNotNone(invoice.success_processed_at)
        self.assertEqual(await self._subscription_rows(), [])

    # ---- Phase 17 -- apply failure rolls back the WHOLE local success ----

    async def test_apply_failure_rolls_back_then_retry_succeeds_exactly_once(self):
        invoice = await self._create_invoice(
            amount_cents=5900, plan_code="STANDARD", billing_period=BILLING_PERIOD_MONTH
        )
        payment = await self._create_payment(invoice)
        invoice_id, payment_id = invoice.id, payment.id  # captured before rollback expires the objects

        original_apply = SubscriptionService.apply_paid_purchase
        call_count = {"n": 0}

        async def flaky_apply(self_svc, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("simulated subscription failure")
            return await original_apply(self_svc, *args, **kwargs)

        with patch.object(SubscriptionService, "apply_paid_purchase", new=flaky_apply):
            # Provider fact: this notification IS a verified SUCCESS -- the
            # failure is purely local (apply_paid_purchase raising).
            with self.assertRaises(RuntimeError):
                await self._notify_success(payment, transaction_id="txn-flaky")
            await self.db.rollback()

            reloaded_invoice = await self._reload_invoice(invoice_id)
            reloaded_payment = await self._reload_payment(payment_id)
            self.assertEqual(
                reloaded_invoice.status, INVOICE_STATUS_PENDING,
                "a raised apply_paid_purchase must roll back the invoice PAID transition too",
            )
            self.assertIsNone(reloaded_invoice.success_processed_at)
            self.assertEqual(
                reloaded_payment.status, PAYMENT_STATUS_PENDING,
                "a raised apply_paid_purchase must roll back the payment PAID transition too",
            )
            self.assertEqual(await self._subscription_rows(), [])

            # Fault no longer reproduces (2nd call) -- same real provider
            # notification redelivered, exactly as WXPAY would retry.
            result = await self._notify_success(payment, transaction_id="txn-flaky")
            self.assertEqual(result.get("code"), "SUCCESS")

        rows = await self._subscription_rows()
        self.assertEqual(len(rows), 1, "the retry must apply the purchase exactly once, not twice")
        await self.db.refresh(invoice)
        await self.db.refresh(payment)
        self.assertEqual(invoice.status, INVOICE_STATUS_PAID)
        self.assertIsNotNone(invoice.success_processed_at)
        self.assertEqual(payment.status, PAYMENT_STATUS_PAID)

    # ---- Phase 18 -- commit=False composability from the Billing side ----

    async def test_subscription_apply_does_not_commit_billing_transaction_commits_once(self):
        invoice = await self._create_invoice(
            amount_cents=5900, plan_code="STANDARD", billing_period=BILLING_PERIOD_MONTH
        )
        payment = await self._create_payment(invoice)

        commit_calls = []
        original_commit = self.db.commit

        async def _tracking_commit():
            commit_calls.append(True)
            return await original_commit()

        self.db.commit = _tracking_commit
        try:
            result = await self._notify_success(payment, transaction_id="txn-commit-count")
        finally:
            self.db.commit = original_commit

        self.assertEqual(result.get("code"), "SUCCESS")
        self.assertEqual(
            len(commit_calls), 1,
            "process_provider_notification must commit exactly once total -- "
            "SubscriptionService.apply_paid_purchase(commit=False) must not add a second commit",
        )
        self.assertEqual(len(await self._subscription_rows()), 1)

    # ---- Phase 9 -- ChannelCommissionService regression -------------------

    async def test_channel_commission_still_invoked_for_saas_subscription_invoice(self):
        invoice = await self._create_invoice(
            amount_cents=5900, plan_code="STANDARD", billing_period=BILLING_PERIOD_MONTH
        )
        payment = await self._create_payment(invoice)
        calls = []
        original = ChannelCommissionService.handle_billing_payment_success

        async def counting(self_svc, invoice_obj, payment_obj):
            calls.append(invoice_obj.id)
            return await original(self_svc, invoice_obj, payment_obj)

        with patch.object(ChannelCommissionService, "handle_billing_payment_success", new=counting):
            result = await self._notify_success(payment, transaction_id="txn-commission-saas")

        self.assertEqual(result.get("code"), "SUCCESS")
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(await self._subscription_rows()), 1)

    async def test_channel_commission_unchanged_for_non_saas_invoice(self):
        invoice = await self._create_invoice(charge_type="SETUP_SERVICE", amount_cents=8800)
        payment = await self._create_payment(invoice)
        calls = []
        original = ChannelCommissionService.handle_billing_payment_success

        async def counting(self_svc, invoice_obj, payment_obj):
            calls.append(invoice_obj.id)
            return await original(self_svc, invoice_obj, payment_obj)

        with patch.object(ChannelCommissionService, "handle_billing_payment_success", new=counting):
            result = await self._notify_success(payment, transaction_id="txn-commission-non-saas")

        self.assertEqual(result.get("code"), "SUCCESS")
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(await self._subscription_rows()), 0)


if __name__ == "__main__":
    unittest.main()
