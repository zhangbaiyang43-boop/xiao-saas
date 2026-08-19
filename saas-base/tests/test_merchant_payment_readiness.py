"""Phase F1E-A — Merchant Payment Readiness regression tests.

Scope: docs/saas-subscription-audit.md Phase F1E-A. Proves the new
GET /api/v1/billing/payment-readiness endpoint: merchant-auth required,
response shape limited to a single boolean (no provider/config leakage),
the boolean tracks the SAME real payment-capability signal that actually
blocks WXPAY (not an environment-name hardcode), zero side effects (no
Invoice/Payment/Subscription rows touched), and that the pre-existing
SuperAdmin-only /api/super/billing/payment-config-status endpoint and
BillingService.payment_config_status() itself are untouched.
"""

from __future__ import annotations

import asyncio
import unittest

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.billing import get_merchant_payment_readiness
from app.api.v1.super_admin import _verify_super_token
from app.config import settings
from app.models.base import Base
from app.models.billing import BillingInvoice, BillingPayment
from app.models.subscription import Subscription
from app.models.tenant import Tenant
from app.services.billing_payment_provider import REAL_PAYMENT_BLOCKED_REASON
from app.services.billing_service import BillingService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-payment-readiness-a"


@event.listens_for(BillingInvoice, "before_insert")
def _assign_invoice_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(BillingPayment, "before_insert")
def _assign_payment_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Tenant, "before_insert")
def _assign_tenant_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_request(*, tenant_id: str | None = TENANT_A, token_type: str | None = "merchant") -> Request:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/billing/payment-readiness",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    if token_type is not None:
        request.state.token_type = token_type
    if tenant_id is not None:
        request.state.tenant_id = tenant_id
    return request


class MerchantPaymentReadinessTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add(Tenant(tenant_id=TENANT_A, name="Readiness Tenant", password_hash="x", status=True))
        await self.db.commit()
        # F1G-CF-A: test_fake_provider_actually_works_as_a_test_capability
        # exercises the real FAKE provider, now gated by
        # settings.ALLOW_MOCK_MONEY_ENDPOINTS.
        settings.ALLOW_MOCK_MONEY_ENDPOINTS = True

    async def asyncTearDown(self):
        settings.ALLOW_MOCK_MONEY_ENDPOINTS = False
        await self.db.close()
        await self.engine.dispose()

    async def _counts(self) -> tuple[int, int, int]:
        invoices = (await self.db.execute(select(BillingInvoice))).scalars().all()
        payments = (await self.db.execute(select(BillingPayment))).scalars().all()
        subs = (await self.db.execute(select(Subscription))).scalars().all()
        return len(invoices), len(payments), len(subs)

    # ---- Auth ------------------------------------------------------------

    async def test_no_merchant_auth_rejected(self):
        resp = await get_merchant_payment_readiness(make_request(tenant_id=None, token_type=None))
        self.assertEqual(resp.code, 401)

    async def test_non_merchant_token_type_rejected(self):
        resp = await get_merchant_payment_readiness(make_request(token_type="staff"))
        self.assertEqual(resp.code, 401)

    async def test_merchant_auth_accepted(self):
        resp = await get_merchant_payment_readiness(make_request())
        self.assertEqual(resp.code, 200)

    # ---- Response shape ----------------------------------------------

    async def test_response_shape_exposes_only_boolean(self):
        # F1G-CM: manual_payment_available is a second, independent boolean
        # authority added alongside online_payment_available -- the shape
        # widened intentionally, still both-booleans-only, no internal detail.
        resp = await get_merchant_payment_readiness(make_request())
        self.assertEqual(set(resp.data.keys()), {"online_payment_available", "manual_payment_available"})
        self.assertIsInstance(resp.data["online_payment_available"], bool)
        self.assertIsInstance(resp.data["manual_payment_available"], bool)
        forbidden_substrings = [
            "provider", "mchid", "appid", "wx_sp", "secret", "cert",
            "private_key", "RuntimeError", "blocked_reason", "audit_result",
        ]
        payload_text = str(resp.data).lower()
        for token in forbidden_substrings:
            self.assertNotIn(token.lower(), payload_text)

    # ---- Readiness value tracks the real capability signal ----------------

    async def test_fake_provider_actually_works_as_a_test_capability(self):
        # FAKE_READINESS: the test/QA provider genuinely creates a payment --
        # this is a separate fact from the merchant-facing boolean below,
        # since merchants are never offered FAKE as a real payment option.
        invoice = await BillingService(self.db).create_invoice(
            tenant_id=TENANT_A, charge_type="SAAS_SUBSCRIPTION",
            description="test", amount_cents=5900,
        )
        service = BillingService(self.db)
        service.set_tenant_id(TENANT_A)
        payment, provider_result = await service.create_payment_attempt(int(invoice.id), provider_name="FAKE")
        self.assertEqual(payment.provider, "FAKE")
        self.assertIn("pay_params", provider_result)

    async def test_wxpay_blocked_matches_readiness_false(self):
        # WXPAY_BLOCKED_READINESS: the real provider raises exactly the same
        # RuntimeError the readiness boolean must reflect as False.
        invoice = await BillingService(self.db).create_invoice(
            tenant_id=TENANT_A, charge_type="SAAS_SUBSCRIPTION",
            description="test", amount_cents=5900,
        )
        service = BillingService(self.db)
        service.set_tenant_id(TENANT_A)
        with self.assertRaisesRegex(RuntimeError, REAL_PAYMENT_BLOCKED_REASON):
            await service.create_payment_attempt(int(invoice.id), provider_name="WXPAY")

        resp = await get_merchant_payment_readiness(make_request())
        self.assertFalse(resp.data["online_payment_available"])

    async def test_readiness_matches_payment_config_status_field_not_env_hardcode(self):
        config_status = BillingService.payment_config_status()
        resp = await get_merchant_payment_readiness(make_request())
        self.assertEqual(resp.data["online_payment_available"], bool(config_status["real_payment_enabled"]))

    # ---- Zero side effects -----------------------------------------------

    async def test_no_invoice_created(self):
        before, _, _ = await self._counts()
        await get_merchant_payment_readiness(make_request())
        after, _, _ = await self._counts()
        self.assertEqual(before, after)

    async def test_no_payment_created(self):
        _, before, _ = await self._counts()
        await get_merchant_payment_readiness(make_request())
        _, after, _ = await self._counts()
        self.assertEqual(before, after)

    async def test_no_subscription_changed(self):
        _, _, before = await self._counts()
        await get_merchant_payment_readiness(make_request())
        _, _, after = await self._counts()
        self.assertEqual(before, after)

    # ---- SuperAdmin endpoint regression ------------------------------

    def test_super_payment_config_status_route_still_super_only(self):
        from app.api.v1 import super_billing

        self.assertTrue(
            any(dep.dependency is _verify_super_token for dep in super_billing.router.dependencies)
        )
        paths = {route.path: sorted(route.methods) for route in super_billing.router.routes}
        self.assertIn("/api/super/billing/payment-config-status", paths)
        self.assertEqual(paths["/api/super/billing/payment-config-status"], ["GET"])

    def test_payment_config_status_shape_is_structured_audit(self):
        # F1G-CF-C1: the old 4-field wx_sp_config_present/audit_result shape
        # was replaced with a flat, structured audit -- update this test to
        # the new intentional shape rather than pin the old one.
        status = BillingService.payment_config_status()
        for key in (
            "release_switch_enabled", "payment_mode", "payment_mode_valid",
            "mchid_present", "appid_present", "api_v3_key_present",
            "cert_serial_present", "private_key_present",
            "verification_material_present", "callback_url_valid",
            "provider_implementation_ready", "config_complete",
            "real_payment_enabled", "blocked_reason",
        ):
            self.assertIn(key, status)
        self.assertIs(status["real_payment_enabled"], False)
        self.assertIs(status["provider_implementation_ready"], False)


if __name__ == "__main__":
    unittest.main()
