"""F1G-CF-A -- SaaS billing FAKE payment provider security hardening.

F1G-C's real-WXPAY-readiness audit found a live P0: the FAKE billing
provider (BillingService.create_payment_attempt's default, and
billing_wxpay_notify's default query-param provider) had no
environment/feature gate at all, unlike every other mock-money endpoint in
this codebase (app/api/v1/member.py's /recharge, order_payment_service.py's
mock_pay_order -- both gated on settings.ALLOW_MOCK_MONEY_ENDPOINTS). Since
FAKE's "signature" verification is a static header check
(x-billing-fake-signature: valid), any authenticated merchant could grant
themselves a free STANDARD/PRO subscription with zero real payment, via the
PUBLIC (unauthenticated-by-necessity) /api/v1/billing/wxpay-notify callback
route.

This file proves the two-layer fix: create_payment_attempt() (Service) and
process_provider_notification() (Callback) each independently refuse FAKE
while settings.ALLOW_MOCK_MONEY_ENDPOINTS is not explicitly true -- and that
disabling FAKE does not disturb the existing FAKE-as-a-test-capability flow
(when the flag IS true) or its idempotency contract.
"""

from __future__ import annotations

import asyncio
import json
import unittest

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
    INVOICE_STATUS_PENDING,
    PAYMENT_STATUS_PENDING,
    BillingService,
    MockPaymentDisabledError,
)
from app.services.subscription_service import SubscriptionService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_ID = "tenant-fake-payment-security"


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


def make_notify_request(payload: dict, *, signature: str | None = "valid", provider: str | None = "FAKE") -> Request:
    raw_body = json.dumps(payload).encode()

    async def _body():
        return raw_body

    headers = []
    if signature:
        headers.append((b"x-billing-fake-signature", signature.encode()))
    query_string = f"provider={provider}".encode() if provider is not None else b""
    req = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/billing/wxpay-notify",
            "headers": headers,
            "query_string": query_string,
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    req.body = _body
    return req


class BillingFakePaymentSecurityGateTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add(Tenant(tenant_id=TENANT_ID, name="Security Gate Tenant", password_hash="x", status=True))
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
        # Default OFF for this whole file -- each test that needs the
        # legitimate test-capability path (Cases E/F) flips it on itself.
        settings.ALLOW_MOCK_MONEY_ENDPOINTS = False

    async def asyncTearDown(self):
        settings.ALLOW_MOCK_MONEY_ENDPOINTS = False
        await self.db.close()
        await self.engine.dispose()

    async def _create_invoice(self, *, amount_cents: int = 5900, plan_code: str | None = "STANDARD",
                               billing_period: str | None = "MONTH") -> BillingInvoice:
        invoice = await BillingService(self.db).create_invoice(
            tenant_id=TENANT_ID,
            charge_type="SAAS_SUBSCRIPTION",
            description="开心点单SaaS服务费",
            amount_cents=amount_cents,
        )
        if plan_code is not None or billing_period is not None:
            invoice.plan_code = plan_code
            invoice.billing_period = billing_period
            await self.db.commit()
            await self.db.refresh(invoice)
        return invoice

    async def _counts(self) -> tuple[int, int]:
        payments = (await self.db.execute(select(BillingPayment))).scalars().all()
        subs = (await self.db.execute(select(Subscription))).scalars().all()
        return len(payments), len(subs)

    async def _effective_plan_code(self) -> str:
        view = await SubscriptionService(self.db).get_effective_subscription_view(TENANT_ID)
        return view.effective_plan.code

    # ---- CASE A: create-payment-attempt gate, explicit FAKE ---------------

    async def test_case_a_fake_payment_creation_denied_when_mock_money_disabled(self):
        invoice = await self._create_invoice()
        service = BillingService(self.db)
        service.set_tenant_id(TENANT_ID)

        payments_before, subs_before = await self._counts()
        with self.assertRaises(MockPaymentDisabledError):
            await service.create_payment_attempt(int(invoice.id), provider_name="FAKE")
        payments_after, subs_after = await self._counts()

        await self.db.refresh(invoice)
        self.assertEqual(invoice.status, INVOICE_STATUS_PENDING)
        self.assertEqual(payments_before, payments_after, "no BillingPayment row must be created")
        self.assertEqual(subs_before, subs_after)

    # ---- CASE B: create-payment-attempt gate, provider omitted ------------

    async def test_case_b_omitted_provider_does_not_implicitly_create_fake_payment(self):
        invoice = await self._create_invoice()
        service = BillingService(self.db)
        service.set_tenant_id(TENANT_ID)

        payments_before, _ = await self._counts()
        # No provider_name argument at all -- must land on the safe
        # (already-blocked) WXPAY default, never silently become FAKE.
        with self.assertRaisesRegex(RuntimeError, "REAL PAYMENT BLOCKED"):
            await service.create_payment_attempt(int(invoice.id))
        payments_after, _ = await self._counts()
        self.assertEqual(payments_before, payments_after)

    # ---- CASE C: callback gate, explicit FAKE + valid fake signature -------

    async def test_case_c_forged_fake_callback_denied_when_mock_money_disabled(self):
        # Simulates an attacker who somehow obtained/guessed a payment record
        # (defense-in-depth: the callback gate must reject FAKE independently
        # of whether create_payment_attempt's own gate was ever reached).
        invoice = await self._create_invoice()
        settings.ALLOW_MOCK_MONEY_ENDPOINTS = True
        service = BillingService(self.db)
        service.set_tenant_id(TENANT_ID)
        payment, _ = await service.create_payment_attempt(int(invoice.id), provider_name="FAKE")
        settings.ALLOW_MOCK_MONEY_ENDPOINTS = False

        payload = {
            "out_trade_no": payment.out_trade_no,
            "transaction_id": "txn-forged",
            "amount_cents": payment.amount_cents,
            "currency": payment.currency,
            "trade_state": "SUCCESS",
        }
        result = await billing_wxpay_notify(make_notify_request(payload, provider="FAKE"), db=self.db)
        self.assertEqual(result.get("code"), "FAIL")

        await self.db.refresh(invoice)
        await self.db.refresh(payment)
        self.assertEqual(invoice.status, INVOICE_STATUS_PENDING)
        self.assertIsNone(invoice.success_processed_at)
        self.assertEqual(payment.status, PAYMENT_STATUS_PENDING)
        self.assertEqual(await self._effective_plan_code(), "FREE")

    # ---- CASE D: callback gate, provider omitted ---------------------------

    async def test_case_d_callback_with_omitted_provider_does_not_default_into_fake(self):
        invoice = await self._create_invoice()
        settings.ALLOW_MOCK_MONEY_ENDPOINTS = True
        service = BillingService(self.db)
        service.set_tenant_id(TENANT_ID)
        payment, _ = await service.create_payment_attempt(int(invoice.id), provider_name="FAKE")
        settings.ALLOW_MOCK_MONEY_ENDPOINTS = False

        payload = {
            "out_trade_no": payment.out_trade_no,
            "transaction_id": "txn-omitted-provider",
            "amount_cents": payment.amount_cents,
            "currency": payment.currency,
            "trade_state": "SUCCESS",
        }
        # No ?provider= query param at all -- the route must default to
        # WXPAY (which has no working verify_notify), never FAKE.
        result = await billing_wxpay_notify(make_notify_request(payload, provider=None), db=self.db)
        self.assertEqual(result.get("code"), "FAIL")

        await self.db.refresh(invoice)
        self.assertEqual(invoice.status, INVOICE_STATUS_PENDING)
        self.assertEqual(await self._effective_plan_code(), "FREE")

    # ---- CASE E: mock-money enabled -- existing test-capability flow works -

    async def test_case_e_explicit_fake_still_works_when_mock_money_enabled(self):
        settings.ALLOW_MOCK_MONEY_ENDPOINTS = True
        invoice = await self._create_invoice()
        service = BillingService(self.db)
        service.set_tenant_id(TENANT_ID)
        payment, provider_result = await service.create_payment_attempt(int(invoice.id), provider_name="FAKE")
        self.assertEqual(payment.provider, "FAKE")

        payload = {
            "out_trade_no": payment.out_trade_no,
            "transaction_id": "txn-case-e",
            "amount_cents": payment.amount_cents,
            "currency": payment.currency,
            "trade_state": "SUCCESS",
        }
        result = await billing_wxpay_notify(make_notify_request(payload, provider="FAKE"), db=self.db)
        self.assertEqual(result.get("code"), "SUCCESS")
        self.assertEqual(await self._effective_plan_code(), "STANDARD")

    # ---- CASE F: hardening does not break existing idempotency contract ---

    async def test_case_f_ten_duplicate_callbacks_still_extend_once_with_mock_money_enabled(self):
        settings.ALLOW_MOCK_MONEY_ENDPOINTS = True
        invoice = await self._create_invoice()
        service = BillingService(self.db)
        service.set_tenant_id(TENANT_ID)
        payment, _ = await service.create_payment_attempt(int(invoice.id), provider_name="FAKE")

        for _ in range(10):
            payload = {
                "out_trade_no": payment.out_trade_no,
                "transaction_id": "txn-case-f-repeat",
                "amount_cents": payment.amount_cents,
                "currency": payment.currency,
                "trade_state": "SUCCESS",
            }
            result = await billing_wxpay_notify(make_notify_request(payload, provider="FAKE"), db=self.db)
            self.assertEqual(result.get("code"), "SUCCESS")

        subs = (await self.db.execute(select(Subscription).where(Subscription.tenant_id == TENANT_ID))).scalars().all()
        self.assertEqual(len(subs), 1, "10x identical callback must apply the purchase exactly once")

    # ---- Phase 14: adversarial end-to-end escalation proof -----------------

    async def test_forged_fake_entitlement_escalation_fully_blocked(self):
        # 1. FREE tenant (no purchase has ever happened for this tenant).
        self.assertEqual(await self._effective_plan_code(), "FREE")

        # 2. Create a STANDARD invoice (legitimate -- order creation itself
        #    is not gated, only payment/entitlement is).
        invoice = await self._create_invoice(amount_cents=5900, plan_code="STANDARD", billing_period="MONTH")

        # 3. mock-money disabled (the asyncSetUp default for this class).
        self.assertFalse(settings.ALLOW_MOCK_MONEY_ENDPOINTS)

        # 4. Attempt FAKE payment creation -- must be denied, no payment
        #    record is ever created (so the attacker has no real
        #    out_trade_no to reference).
        service = BillingService(self.db)
        service.set_tenant_id(TENANT_ID)
        with self.assertRaises(MockPaymentDisabledError):
            await service.create_payment_attempt(int(invoice.id), provider_name="FAKE")
        self.assertEqual(await self._counts(), (0, 0))

        # 5a. Attempt a forged callback anyway, against a synthetic
        #     out_trade_no that matches no real BillingPayment -- must be
        #     rejected at the mock-money gate before any lookup even matters.
        forged_payload = {
            "out_trade_no": "BPAY-forged-no-such-payment",
            "transaction_id": "txn-forged-a",
            "amount_cents": 5900,
            "currency": "CNY",
            "trade_state": "SUCCESS",
        }
        result_a = await billing_wxpay_notify(make_notify_request(forged_payload, provider="FAKE"), db=self.db)
        self.assertEqual(result_a.get("code"), "FAIL")

        # 5b. Defense-in-depth: even if a payment record somehow existed
        #     (e.g. created while mock-money was briefly enabled, or via a
        #     hypothetical bypass of gate #1), the callback gate must reject
        #     FAKE independently.
        settings.ALLOW_MOCK_MONEY_ENDPOINTS = True
        payment, _ = await service.create_payment_attempt(int(invoice.id), provider_name="FAKE")
        settings.ALLOW_MOCK_MONEY_ENDPOINTS = False

        real_shaped_payload = {
            "out_trade_no": payment.out_trade_no,
            "transaction_id": "txn-forged-b",
            "amount_cents": payment.amount_cents,
            "currency": payment.currency,
            "trade_state": "SUCCESS",
        }
        result_b = await billing_wxpay_notify(make_notify_request(real_shaped_payload, provider="FAKE"), db=self.db)
        self.assertEqual(result_b.get("code"), "FAIL")

        await self.db.refresh(invoice)
        await self.db.refresh(payment)
        self.assertEqual(invoice.status, INVOICE_STATUS_PENDING)
        self.assertIsNone(invoice.success_processed_at)
        self.assertEqual(payment.status, PAYMENT_STATUS_PENDING)

        # 6. Effective subscription must still be FREE.
        self.assertEqual(await self._effective_plan_code(), "FREE")


if __name__ == "__main__":
    unittest.main()
