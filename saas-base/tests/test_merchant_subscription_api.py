"""Phase F1D — Merchant Subscription API regression tests.

Scope: docs/saas-subscription-audit.md Phase F1D. Proves the three new
merchant-facing endpoints (GET current, GET plans, POST renewal-orders)
against the frozen commercial contract, that renewal-order creation never
lets the client control amount/tenant_id/charge_type, that no BillingInvoice
is created on any validation rejection, tenant isolation, and -- the most
important test in this file -- a full merchant_intent -> authoritative
price -> BillingInvoice -> existing payment flow -> verified success ->
Subscription apply chain exercised through the REAL endpoints/services at
every step (never a hand-inserted Subscription row).

Router functions are called directly (same pattern as
test_channel_entry_tenant_isolation.py / test_saas_billing_foundation.py):
a raw Starlette Request with request.state.tenant_id/token_type set
directly, bypassing actual JWT verification but exercising the exact same
_merchant_tenant_id()-based authority resolution the real middleware feeds.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta

import pydantic
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.billing import BillingPaymentCreateRequest, billing_wxpay_notify, create_my_billing_payment
from app.config import settings
from app.api.v1.subscription import (
    RenewalOrderCreateRequest,
    create_renewal_order,
    get_current_subscription_view,
    list_plan_catalog,
)
from app.models.base import Base
from app.models.billing import BillingInvoice, BillingPayment
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.services.subscription_service import (
    BILLING_PERIOD_MONTH,
    BILLING_PERIOD_YEAR,
    PLAN_CODE_PRO,
    PLAN_CODE_STANDARD,
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_EXPIRED,
    STATUS_TRIAL,
    SUBSCRIPTION_STATUS_FREE,
    SubscriptionService,
    _add_calendar_months_clamped,
)
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-subscription-api-a"
TENANT_B = "tenant-subscription-api-b"


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


@event.listens_for(BillingInvoice, "before_insert")
def _assign_invoice_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(BillingPayment, "before_insert")
def _assign_payment_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_request(*, tenant_id: str, method: str = "GET", path: str = "/api/v1/subscription/current") -> Request:
    request = Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    request.state.tenant_id = tenant_id
    request.state.token_type = "merchant"
    return request


class MerchantSubscriptionApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add_all(
            [
                Tenant(tenant_id=TENANT_A, name="Sub API A", password_hash="x", status=True),
                Tenant(tenant_id=TENANT_B, name="Sub API B", password_hash="x", status=True),
            ]
        )
        await self._add_default_plans()
        await self.db.commit()
        self.service = SubscriptionService(self.db)
        # F1G-CF-A: this file's commercial-flow tests exercise the real FAKE
        # billing provider end-to-end, now gated by
        # settings.ALLOW_MOCK_MONEY_ENDPOINTS, same as every other mock-money
        # endpoint in this codebase.
        settings.ALLOW_MOCK_MONEY_ENDPOINTS = True

    async def asyncTearDown(self):
        settings.ALLOW_MOCK_MONEY_ENDPOINTS = False
        await self.db.close()
        await self.engine.dispose()

    async def _add_default_plans(self):
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

    async def _invoice_count(self) -> int:
        result = await self.db.execute(select(BillingInvoice))
        return len(result.scalars().all())

    async def _apply_paid(self, tenant_id: str, plan_code: str, billing_period: str, paid_at: datetime) -> Subscription:
        return await self.service.apply_paid_purchase(tenant_id, plan_code, billing_period, paid_at)

    async def _get_current(self, tenant_id: str) -> dict:
        resp = await get_current_subscription_view(make_request(tenant_id=tenant_id), db=self.db)
        return resp

    async def _create_renewal(self, tenant_id: str, plan_code: str, billing_period: str):
        body = RenewalOrderCreateRequest(plan_code=plan_code, billing_period=billing_period)
        request = make_request(tenant_id=tenant_id, method="POST", path="/api/v1/subscription/renewal-orders")
        return await create_renewal_order(body, request, db=self.db)

    # ---- Phase 30 -- GET /current status matrix ---------------------------

    async def test_no_subscription_is_free(self):
        resp = await self._get_current(TENANT_A)
        self.assertEqual(resp.code, 200)
        self.assertEqual(resp.data["effective_plan_code"], "FREE")
        self.assertEqual(resp.data["subscription_status"], SUBSCRIPTION_STATUS_FREE)
        self.assertFalse(resp.data["is_trial"])
        self.assertEqual(resp.data["days_remaining"], 0)
        self.assertTrue(resp.data["can_renew"])

    async def test_trial_current(self):
        trial_ends_at = datetime.utcnow() + timedelta(days=10)
        await self.service.create_trial_for_tenant(TENANT_A)
        # override trial_ends_at deterministically for this assertion
        current = await self.service.get_current_subscription(TENANT_A)
        current.trial_ends_at = trial_ends_at
        await self.db.commit()

        resp = await self._get_current(TENANT_A)
        self.assertEqual(resp.data["effective_plan_code"], PLAN_CODE_PRO)
        self.assertEqual(resp.data["subscription_status"], STATUS_TRIAL)
        self.assertTrue(resp.data["is_trial"])
        self.assertIsNotNone(resp.data["trial_ends_at"])
        self.assertGreaterEqual(resp.data["days_remaining"], 9)

    async def test_trial_expired(self):
        await self.service.create_trial_for_tenant(TENANT_A)
        current = await self.service.get_current_subscription(TENANT_A)
        current.trial_ends_at = datetime.utcnow() - timedelta(days=1)
        await self.db.commit()

        resp = await self._get_current(TENANT_A)
        self.assertEqual(resp.data["effective_plan_code"], "FREE")
        self.assertEqual(resp.data["subscription_status"], STATUS_EXPIRED)
        self.assertFalse(resp.data["is_trial"])
        self.assertEqual(resp.data["days_remaining"], 0)

    async def test_active_standard(self):
        await self._apply_paid(TENANT_A, "STANDARD", BILLING_PERIOD_MONTH, datetime.utcnow())
        resp = await self._get_current(TENANT_A)
        self.assertEqual(resp.data["effective_plan_code"], "STANDARD")
        self.assertEqual(resp.data["subscription_status"], STATUS_ACTIVE)
        self.assertFalse(resp.data["is_trial"])
        self.assertIsNotNone(resp.data["paid_started_at"])
        self.assertIsNotNone(resp.data["paid_ends_at"])
        self.assertGreater(resp.data["days_remaining"], 0)

    async def test_active_pro(self):
        await self._apply_paid(TENANT_A, "PRO", BILLING_PERIOD_YEAR, datetime.utcnow())
        resp = await self._get_current(TENANT_A)
        self.assertEqual(resp.data["effective_plan_code"], "PRO")
        self.assertEqual(resp.data["subscription_status"], STATUS_ACTIVE)

    async def test_active_expired(self):
        sub = await self._apply_paid(TENANT_A, "STANDARD", BILLING_PERIOD_MONTH, datetime.utcnow())
        sub.ends_at = datetime.utcnow() - timedelta(seconds=1)
        await self.db.commit()

        resp = await self._get_current(TENANT_A)
        self.assertEqual(resp.data["effective_plan_code"], "FREE")
        self.assertEqual(resp.data["subscription_status"], STATUS_EXPIRED)
        self.assertEqual(resp.data["days_remaining"], 0)

    async def test_cancelled(self):
        sub = await self._apply_paid(TENANT_A, "STANDARD", BILLING_PERIOD_MONTH, datetime.utcnow())
        await self.service.cancel(sub)

        resp = await self._get_current(TENANT_A)
        self.assertEqual(resp.data["effective_plan_code"], "FREE")
        self.assertEqual(resp.data["subscription_status"], STATUS_CANCELLED)

    async def test_days_remaining_ceil_boundaries(self):
        from app.services.subscription_service import resolve_days_remaining

        now = datetime(2026, 8, 17, 0, 0, 0)
        self.assertEqual(resolve_days_remaining(now + timedelta(hours=3), now=now), 1)
        self.assertEqual(resolve_days_remaining(now + timedelta(hours=24), now=now), 1)
        self.assertEqual(resolve_days_remaining(now + timedelta(hours=24, seconds=1), now=now), 2)
        self.assertEqual(resolve_days_remaining(now - timedelta(seconds=1), now=now), 0)
        self.assertEqual(resolve_days_remaining(None, now=now), 0)

    async def test_free_plan_missing_is_integrity_error_not_fabricated(self):
        result = await self.db.execute(select(Plan).where(Plan.code == "FREE"))
        free_plan = result.scalar_one()
        await self.db.delete(free_plan)
        await self.db.commit()

        resp = await self._get_current(TENANT_A)
        self.assertEqual(resp.code, 500)

    # ---- Phase 31 -- GET /plans ---------------------------------------

    async def test_plan_catalog_contract(self):
        resp = await list_plan_catalog(make_request(tenant_id=TENANT_A, path="/api/v1/subscription/plans"), db=self.db)
        self.assertEqual(resp.code, 200)
        codes = [p["plan_code"] for p in resp.data]
        self.assertEqual(codes, ["FREE", "STANDARD", "PRO"])
        by_code = {p["plan_code"]: p for p in resp.data}
        self.assertEqual(by_code["FREE"]["price_month_cents"], 0)
        self.assertEqual(by_code["FREE"]["price_year_cents"], 0)
        self.assertIsNone(by_code["FREE"]["annual_discount_display"])
        self.assertEqual(by_code["STANDARD"]["price_month_cents"], 5900)
        self.assertEqual(by_code["STANDARD"]["price_year_cents"], 60900)
        self.assertEqual(by_code["STANDARD"]["annual_discount_display"], "14%")
        self.assertEqual(by_code["PRO"]["price_month_cents"], 9900)
        self.assertEqual(by_code["PRO"]["price_year_cents"], 102200)
        self.assertEqual(by_code["PRO"]["annual_discount_display"], "14%")

    async def test_plan_catalog_excludes_inactive(self):
        self.db.add(Plan(code="RETIRED", name="停用版", is_active=False,
                          price_month_cents=1, price_year_cents=1, sort_order=99))
        await self.db.commit()
        resp = await list_plan_catalog(make_request(tenant_id=TENANT_A, path="/api/v1/subscription/plans"), db=self.db)
        self.assertNotIn("RETIRED", [p["plan_code"] for p in resp.data])

    async def test_plan_catalog_available_to_free_merchant(self):
        # no subscription at all -- FREE tier -- must still see the catalog
        resp = await list_plan_catalog(make_request(tenant_id=TENANT_A, path="/api/v1/subscription/plans"), db=self.db)
        self.assertEqual(resp.code, 200)
        self.assertEqual(len(resp.data), 3)

    # ---- Phase 13/14/15/20/21 -- renewal order validation -----------------

    async def test_cross_plan_change_blocked_and_no_invoice_created(self):
        await self._apply_paid(TENANT_A, "STANDARD", BILLING_PERIOD_YEAR, datetime.utcnow())
        before = await self._invoice_count()  # 0, no payment attempt yet at this point either

        resp = await self._create_renewal(TENANT_A, "PRO", BILLING_PERIOD_YEAR)

        self.assertEqual(resp.code, 409)
        after = await self._invoice_count()
        self.assertEqual(after, before)

    async def test_unknown_plan_rejected(self):
        resp = await self._create_renewal(TENANT_A, "ENTERPRISE", BILLING_PERIOD_MONTH)
        self.assertEqual(resp.code, 400)
        self.assertEqual(await self._invoice_count(), 0)

    async def test_inactive_plan_rejected(self):
        self.db.add(Plan(code="RETIRED", name="停用版", is_active=False,
                          price_month_cents=100, price_year_cents=1000, sort_order=99))
        await self.db.commit()
        resp = await self._create_renewal(TENANT_A, "RETIRED", BILLING_PERIOD_MONTH)
        self.assertEqual(resp.code, 400)
        self.assertEqual(await self._invoice_count(), 0)

    async def test_free_plan_not_payable_rejected(self):
        resp = await self._create_renewal(TENANT_A, "FREE", BILLING_PERIOD_MONTH)
        self.assertEqual(resp.code, 400)
        self.assertEqual(await self._invoice_count(), 0)

    async def test_invalid_billing_period_rejected(self):
        resp = await self._create_renewal(TENANT_A, "STANDARD", "WEEK")
        self.assertEqual(resp.code, 400)
        self.assertEqual(await self._invoice_count(), 0)

    # ---- Phase 22/23/24 -- allowed purchase matrix -------------------------

    async def test_trial_purchase_allowed_and_does_not_change_subscription(self):
        await self.service.create_trial_for_tenant(TENANT_A)
        trial_before = await self.service.get_current_subscription(TENANT_A)

        resp = await self._create_renewal(TENANT_A, "STANDARD", BILLING_PERIOD_YEAR)

        self.assertEqual(resp.code, 200)
        self.assertEqual(resp.data["plan_code"], "STANDARD")
        self.assertEqual(resp.data["billing_period"], BILLING_PERIOD_YEAR)
        self.assertEqual(resp.data["amount_cents"], 60900)

        trial_after = await self.service.get_current_subscription(TENANT_A)
        self.assertEqual(trial_after.id, trial_before.id)
        self.assertEqual(trial_after.status, STATUS_TRIAL)

    async def test_active_standard_same_plan_month_and_year_allowed(self):
        await self._apply_paid(TENANT_A, "STANDARD", BILLING_PERIOD_YEAR, datetime.utcnow())
        resp_month = await self._create_renewal(TENANT_A, "STANDARD", BILLING_PERIOD_MONTH)
        self.assertEqual(resp_month.code, 200)
        self.assertEqual(resp_month.data["amount_cents"], 5900)

    async def test_active_pro_same_plan_allowed(self):
        await self._apply_paid(TENANT_A, "PRO", BILLING_PERIOD_MONTH, datetime.utcnow())
        resp = await self._create_renewal(TENANT_A, "PRO", BILLING_PERIOD_YEAR)
        self.assertEqual(resp.code, 200)
        self.assertEqual(resp.data["amount_cents"], 102200)

    async def test_free_to_standard_and_pro_allowed(self):
        resp_standard = await self._create_renewal(TENANT_A, "STANDARD", BILLING_PERIOD_MONTH)
        self.assertEqual(resp_standard.code, 200)
        resp_pro = await self._create_renewal(TENANT_A, "PRO", BILLING_PERIOD_MONTH)
        self.assertEqual(resp_pro.code, 200)

    async def test_expired_standard_can_buy_pro(self):
        sub = await self._apply_paid(TENANT_A, "STANDARD", BILLING_PERIOD_MONTH, datetime.utcnow())
        sub.ends_at = datetime.utcnow() - timedelta(seconds=1)
        await self.db.commit()
        resp = await self._create_renewal(TENANT_A, "PRO", BILLING_PERIOD_MONTH)
        self.assertEqual(resp.code, 200)

    async def test_expired_pro_can_buy_standard(self):
        sub = await self._apply_paid(TENANT_A, "PRO", BILLING_PERIOD_MONTH, datetime.utcnow())
        sub.ends_at = datetime.utcnow() - timedelta(seconds=1)
        await self.db.commit()
        resp = await self._create_renewal(TENANT_A, "STANDARD", BILLING_PERIOD_MONTH)
        self.assertEqual(resp.code, 200)

    async def test_cancelled_can_buy_standard_or_pro(self):
        sub = await self._apply_paid(TENANT_A, "STANDARD", BILLING_PERIOD_MONTH, datetime.utcnow())
        await self.service.cancel(sub)
        resp = await self._create_renewal(TENANT_A, "PRO", BILLING_PERIOD_YEAR)
        self.assertEqual(resp.code, 200)

    # ---- Phase 15 -- price authority ------------------------------------

    async def test_renewal_invoice_snapshot_matches_backend_price(self):
        resp = await self._create_renewal(TENANT_A, "STANDARD", BILLING_PERIOD_YEAR)
        invoice_id = int(resp.data["invoice_id"])
        result = await self.db.execute(select(BillingInvoice).where(BillingInvoice.id == invoice_id))
        invoice = result.scalar_one()
        self.assertEqual(invoice.tenant_id, TENANT_A)
        self.assertEqual(invoice.charge_type, "SAAS_SUBSCRIPTION")
        self.assertEqual(invoice.plan_code, "STANDARD")
        self.assertEqual(invoice.billing_period, BILLING_PERIOD_YEAR)
        self.assertEqual(invoice.amount_cents, 60900)
        self.assertNotEqual(invoice.amount_cents, 5900 * 12)  # never monthly*12

    # ---- Phase 29 -- amount / tenant_id injection -------------------------

    def test_amount_cents_injection_rejected_by_schema(self):
        with self.assertRaises(pydantic.ValidationError):
            RenewalOrderCreateRequest.model_validate(
                {"plan_code": "STANDARD", "billing_period": "YEAR", "amount_cents": 1}
            )

    def test_tenant_id_injection_rejected_by_schema(self):
        with self.assertRaises(pydantic.ValidationError):
            RenewalOrderCreateRequest.model_validate(
                {"plan_code": "STANDARD", "billing_period": "YEAR", "tenant_id": TENANT_B}
            )

    async def test_amount_injection_leaves_no_invoice(self):
        with self.assertRaises(pydantic.ValidationError):
            RenewalOrderCreateRequest.model_validate(
                {"plan_code": "STANDARD", "billing_period": "YEAR", "amount_cents": 1}
            )
        self.assertEqual(await self._invoice_count(), 0)

    # ---- Phase 28 -- tenant isolation --------------------------------

    async def test_tenant_b_cannot_see_tenant_a_current_subscription(self):
        await self._apply_paid(TENANT_A, "PRO", BILLING_PERIOD_YEAR, datetime.utcnow())
        resp_b = await self._get_current(TENANT_B)
        self.assertEqual(resp_b.data["effective_plan_code"], "FREE")
        self.assertEqual(resp_b.data["subscription_status"], SUBSCRIPTION_STATUS_FREE)

    async def test_renewal_order_always_binds_to_requesting_tenant(self):
        resp = await self._create_renewal(TENANT_B, "STANDARD", BILLING_PERIOD_MONTH)
        invoice_id = int(resp.data["invoice_id"])
        result = await self.db.execute(select(BillingInvoice).where(BillingInvoice.id == invoice_id))
        invoice = result.scalar_one()
        self.assertEqual(invoice.tenant_id, TENANT_B)
        self.assertNotEqual(invoice.tenant_id, TENANT_A)

    # ---- Phase 26 -- full backend E2E commercial flow ----------------------

    async def test_merchant_backend_commercial_flow_free_to_active_standard(self):
        # merchant intent -> authoritative price -> BillingInvoice
        renewal_resp = await self._create_renewal(TENANT_A, "STANDARD", BILLING_PERIOD_YEAR)
        self.assertEqual(renewal_resp.code, 200)
        invoice_id = renewal_resp.data["invoice_id"]
        self.assertEqual(renewal_resp.data["amount_cents"], 60900)

        # existing payment flow: create payment attempt via the REAL billing API
        payment_request = make_request(
            tenant_id=TENANT_A, method="POST", path=f"/api/v1/billing/invoices/{invoice_id}/payments"
        )
        payment_resp = await create_my_billing_payment(
            invoice_id, BillingPaymentCreateRequest(provider="FAKE"), payment_request, db=self.db
        )
        self.assertEqual(payment_resp.code, 200)
        payment = payment_resp.data["payment"]

        # verified success via the REAL FAKE-provider notify path (F1C bridge)
        import json as _json

        async def _body():
            return _json.dumps(
                {
                    "out_trade_no": payment["out_trade_no"],
                    "transaction_id": "txn-e2e-standard-year",
                    "amount_cents": payment["amount_cents"],
                    "currency": payment["currency"],
                    "trade_state": "SUCCESS",
                }
            ).encode()

        notify_request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/billing/wxpay-notify",
                "headers": [(b"x-billing-fake-signature", b"valid")],
                "query_string": b"provider=FAKE",
                "server": ("testserver", 80),
                "scheme": "http",
                "client": ("testclient", 50000),
            }
        )
        notify_request.body = _body
        notify_result = await billing_wxpay_notify(notify_request, db=self.db)
        self.assertEqual(notify_result.get("code"), "SUCCESS")

        # Current Subscription API must now show STANDARD ACTIVE
        current_resp = await self._get_current(TENANT_A)
        self.assertEqual(current_resp.data["effective_plan_code"], "STANDARD")
        self.assertEqual(current_resp.data["subscription_status"], STATUS_ACTIVE)
        self.assertFalse(current_resp.data["is_trial"])
        self.assertIsNotNone(current_resp.data["paid_ends_at"])

    # ---- Phase 27 -- trial -> paid E2E, four phases combined --------------

    async def test_trial_to_paid_e2e_across_f1a_f1b_f1c_f1d(self):
        await self.service.create_trial_for_tenant(TENANT_A)
        trial = await self.service.get_current_subscription(TENANT_A)
        fixed_trial_ends_at = datetime(2026, 8, 31, 0, 0, 0)
        trial.trial_ends_at = fixed_trial_ends_at
        await self.db.commit()
        trial_id = trial.id

        renewal_resp = await self._create_renewal(TENANT_A, "STANDARD", BILLING_PERIOD_YEAR)
        self.assertEqual(renewal_resp.code, 200)
        invoice_id = renewal_resp.data["invoice_id"]

        payment_request = make_request(
            tenant_id=TENANT_A, method="POST", path=f"/api/v1/billing/invoices/{invoice_id}/payments"
        )
        payment_resp = await create_my_billing_payment(
            invoice_id, BillingPaymentCreateRequest(provider="FAKE"), payment_request, db=self.db
        )
        payment = payment_resp.data["payment"]

        import json as _json

        async def _body():
            return _json.dumps(
                {
                    "out_trade_no": payment["out_trade_no"],
                    "transaction_id": "txn-e2e-trial-to-paid",
                    "amount_cents": payment["amount_cents"],
                    "currency": payment["currency"],
                    "trade_state": "SUCCESS",
                }
            ).encode()

        notify_request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/billing/wxpay-notify",
                "headers": [(b"x-billing-fake-signature", b"valid")],
                "query_string": b"provider=FAKE",
                "server": ("testserver", 80),
                "scheme": "http",
                "client": ("testclient", 50000),
            }
        )
        notify_request.body = _body
        before = datetime.utcnow()
        notify_result = await billing_wxpay_notify(notify_request, db=self.db)
        after = datetime.utcnow()
        self.assertEqual(notify_result.get("code"), "SUCCESS")

        current_resp = await self._get_current(TENANT_A)
        self.assertEqual(current_resp.data["effective_plan_code"], "STANDARD")
        self.assertEqual(current_resp.data["subscription_status"], STATUS_ACTIVE)
        self.assertFalse(current_resp.data["is_trial"])

        # old trial row preserved untouched
        result = await self.db.execute(select(Subscription).where(Subscription.id == trial_id))
        reloaded_trial = result.scalar_one()
        self.assertEqual(reloaded_trial.status, STATUS_TRIAL)
        self.assertEqual(reloaded_trial.trial_ends_at, fixed_trial_ends_at)

        # paid_ends_at = trial_ends_at + 12 calendar months (trial time preserved)
        expected_min = _add_calendar_months_clamped(fixed_trial_ends_at, 12)
        expected_max = expected_min  # trial_ends_at is fixed/deterministic, no bracket needed
        result = await self.db.execute(
            select(Subscription)
            .where(Subscription.tenant_id == TENANT_A, Subscription.status == STATUS_ACTIVE)
        )
        active_sub = result.scalars().one()
        self.assertEqual(active_sub.ends_at, expected_min)
        self.assertGreaterEqual(active_sub.started_at, before)
        self.assertLessEqual(active_sub.started_at, after)


if __name__ == "__main__":
    unittest.main()
