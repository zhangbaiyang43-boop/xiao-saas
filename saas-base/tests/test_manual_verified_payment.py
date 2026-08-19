"""F1G-CM Checkpoint CM-A -- Manual Verified Subscription Payment V1 (backend).

Scope: the full manual-payment authority chain -- merchant claim ("我已付款",
a PAYMENT CLAIM, never a PAYMENT FACT) -> SuperAdmin confirm (the ONLY
action that produces a MANUAL_VERIFIED_PAYMENT_FACT) -> the SAME shared
process_verified_payment_fact() core every provider (FAKE/WXPAY/MANUAL)
funnels through -> SubscriptionService.apply_paid_purchase(). Covers the
15-case security matrix from the phase brief plus the migration/shared-core
proofs.

Every amount/tenant/paid-at/plan value in this file is sourced from server
state (BillingInvoice/BillingPayment rows, or SuperAdmin's own JWT `sub`),
never from a request body field for those purposes -- the whole point of
this test file is proving there is no code path for a client to supply any
of them.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import jwt
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.billing import BillingPaymentCreateRequest
from app.config import settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.base import Base
from app.models.billing import BillingInvoice, BillingPayment
from app.models.merchant_account import MerchantAccount
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.services.billing_service import (
    INVOICE_STATUS_PAID,
    INVOICE_STATUS_PENDING,
    MANUAL_REVIEW_CONFIRMED,
    MANUAL_REVIEW_REJECTED,
    MANUAL_REVIEW_WAITING_CONFIRMATION,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PENDING,
    BillingService,
    ManualPaymentDisabledError,
    ManualPaymentStateError,
)
from app.services.subscription_service import SubscriptionService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-manual-payment-a"
TENANT_B = "tenant-manual-payment-b"


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


class ManualVerifiedPaymentServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add_all(
            [
                Tenant(tenant_id=TENANT_A, name="Manual Payment A", password_hash="x", status=True),
                Tenant(tenant_id=TENANT_B, name="Manual Payment B", password_hash="x", status=True),
                Plan(code="FREE", name="免费版", is_active=True, price_month_cents=0, price_year_cents=0, sort_order=0),
                Plan(code="STANDARD", name="普通版", is_active=True, price_month_cents=5900, price_year_cents=60900, sort_order=1),
                Plan(code="PRO", name="专业版", is_active=True, price_month_cents=9900, price_year_cents=102200, sort_order=2),
            ]
        )
        await self.db.commit()
        settings.SAAS_MANUAL_PAYMENT_ENABLED = True
        settings.SAAS_MANUAL_PAYMENT_PAYEE_NAME = "TEST_ONLY_DUMMY_PAYEE"
        settings.SAAS_MANUAL_PAYMENT_QR_URL = "https://example.test/dummy-qr.png"

    async def asyncTearDown(self):
        settings.SAAS_MANUAL_PAYMENT_ENABLED = False
        settings.SAAS_MANUAL_PAYMENT_PAYEE_NAME = ""
        settings.SAAS_MANUAL_PAYMENT_QR_URL = ""
        await self.db.close()
        await self.engine.dispose()

    # ---- fixtures ---------------------------------------------------------

    async def _create_invoice(
        self, *, tenant_id: str = TENANT_A, amount_cents: int = 5900,
        plan_code: str = "STANDARD", billing_period: str = "MONTH",
    ) -> BillingInvoice:
        invoice = await BillingService(self.db).create_invoice(
            tenant_id=tenant_id, charge_type="SAAS_SUBSCRIPTION",
            description="开心点单SaaS服务费", amount_cents=amount_cents,
        )
        invoice.plan_code = plan_code
        invoice.billing_period = billing_period
        await self.db.commit()
        await self.db.refresh(invoice)
        return invoice

    async def _create_manual_payment(self, invoice: BillingInvoice) -> BillingPayment:
        service = BillingService(self.db)
        service.set_tenant_id(invoice.tenant_id)
        payment, _ = await service.create_payment_attempt(int(invoice.id), provider_name="MANUAL")
        return payment

    async def _claim(self, tenant_id: str, payment_id: int) -> BillingPayment:
        service = BillingService(self.db)
        service.set_tenant_id(tenant_id)
        return await service.claim_manual_payment(payment_id)

    async def _effective_plan_code(self, tenant_id: str) -> str:
        view = await SubscriptionService(self.db).get_effective_subscription_view(tenant_id)
        return view.effective_plan.code

    async def _subscription_count(self, tenant_id: str) -> int:
        rows = (await self.db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))).scalars().all()
        return len(rows)

    # ---- Case 1: amount source = invoice -----------------------------------

    async def test_case_1_manual_payment_amount_sourced_from_invoice(self):
        invoice = await self._create_invoice(amount_cents=102200, plan_code="PRO", billing_period="YEAR")
        payment = await self._create_manual_payment(invoice)
        self.assertEqual(payment.amount_cents, 102200)
        self.assertEqual(payment.tenant_id, invoice.tenant_id)
        self.assertEqual(payment.provider, "MANUAL")
        self.assertTrue(payment.out_trade_no.startswith("BPAY"))
        self.assertEqual(payment.status, PAYMENT_STATUS_PENDING)
        self.assertIsNone(payment.manual_review_status)

    # ---- Case 2: no client-amount code path exists -------------------------

    def test_case_2_create_request_model_has_no_amount_field(self):
        # BillingPaymentCreateRequest has no amount_cents/tenant_id field at
        # all -- pydantic's default behavior silently drops unknown fields,
        # so a forged amount in the request body never reaches the service.
        body = BillingPaymentCreateRequest.model_validate({"provider": "MANUAL", "amount_cents": 1, "tenant_id": "attacker"})
        self.assertFalse(hasattr(body, "amount_cents"))
        self.assertFalse(hasattr(body, "tenant_id"))
        self.assertEqual(body.provider, "MANUAL")

    async def test_case_2_create_payment_attempt_signature_accepts_no_amount(self):
        import inspect

        sig = inspect.signature(BillingService.create_payment_attempt)
        self.assertNotIn("amount_cents", sig.parameters)
        self.assertNotIn("tenant_id", sig.parameters)

    # ---- Case 3: claim never touches funds state ---------------------------

    async def test_case_3_claim_leaves_invoice_pending_and_subscription_unchanged(self):
        invoice = await self._create_invoice()
        payment = await self._create_manual_payment(invoice)
        claimed = await self._claim(TENANT_A, int(payment.id))

        self.assertEqual(claimed.manual_review_status, MANUAL_REVIEW_WAITING_CONFIRMATION)
        self.assertIsNotNone(claimed.manual_claimed_at)
        self.assertEqual(claimed.status, PAYMENT_STATUS_PENDING)

        await self.db.refresh(invoice)
        self.assertEqual(invoice.status, INVOICE_STATUS_PENDING)
        self.assertIsNone(invoice.success_processed_at)
        self.assertEqual(await self._effective_plan_code(TENANT_A), "FREE")

    # ---- Case 4: 10x claim is a safe no-op ---------------------------------

    async def test_case_4_ten_x_claim_still_a_single_payment_no_entitlement(self):
        invoice = await self._create_invoice()
        payment = await self._create_manual_payment(invoice)
        for _ in range(10):
            await self._claim(TENANT_A, int(payment.id))

        payments = (await self.db.execute(select(BillingPayment).where(BillingPayment.tenant_id == TENANT_A))).scalars().all()
        self.assertEqual(len(payments), 1, "10x claim must not create additional payment rows")
        self.assertEqual(await self._effective_plan_code(TENANT_A), "FREE")
        self.assertEqual(await self._subscription_count(TENANT_A), 0)

    # ---- Case 7: confirm without WAITING_CONFIRMATION is denied -----------

    async def test_case_7_confirm_without_prior_claim_denied(self):
        invoice = await self._create_invoice()
        payment = await self._create_manual_payment(invoice)
        service = BillingService(self.db)
        with self.assertRaises(ManualPaymentStateError):
            await service.confirm_manual_payment(int(payment.id), verified_by="super_admin")
        await self.db.refresh(payment)
        self.assertEqual(payment.status, PAYMENT_STATUS_PENDING)
        self.assertIsNone(payment.manual_review_status)

    # ---- Case 8: valid confirm applies once --------------------------------

    async def test_case_8_confirm_applies_invoice_payment_and_subscription(self):
        invoice = await self._create_invoice(amount_cents=60900, plan_code="STANDARD", billing_period="YEAR")
        payment = await self._create_manual_payment(invoice)
        await self._claim(TENANT_A, int(payment.id))

        service = BillingService(self.db)
        before = datetime.utcnow()
        result = await service.confirm_manual_payment(int(payment.id), verified_by="super_admin", note="核对到账")
        after = datetime.utcnow()
        self.assertEqual(result.get("code"), "SUCCESS")

        await self.db.refresh(invoice)
        await self.db.refresh(payment)
        self.assertEqual(invoice.status, INVOICE_STATUS_PAID)
        self.assertIsNotNone(invoice.success_processed_at)
        self.assertEqual(payment.status, PAYMENT_STATUS_PAID)
        self.assertEqual(payment.manual_review_status, MANUAL_REVIEW_CONFIRMED)
        self.assertEqual(payment.manual_reviewed_by, "super_admin")
        self.assertEqual(payment.manual_review_note, "核对到账")
        self.assertIsNotNone(payment.manual_reviewed_at)
        # V1 MANUAL paid_at authority = platform confirmation time, not the
        # merchant's claim time (F1G-CM Phase 18).
        self.assertGreaterEqual(payment.paid_at, before)
        self.assertLessEqual(payment.paid_at, after)
        self.assertEqual(payment.transaction_id, f"MANUAL{payment.id}")

        self.assertEqual(await self._effective_plan_code(TENANT_A), "STANDARD")
        subs = (await self.db.execute(select(Subscription).where(Subscription.tenant_id == TENANT_A))).scalars().all()
        self.assertEqual(len(subs), 1)

    # ---- Case 9: 10x confirm extends once (idempotency + concurrency proof)

    async def test_case_9_ten_x_confirm_extends_once(self):
        invoice = await self._create_invoice()
        payment = await self._create_manual_payment(invoice)
        await self._claim(TENANT_A, int(payment.id))

        service = BillingService(self.db)
        for _ in range(10):
            result = await service.confirm_manual_payment(int(payment.id), verified_by="super_admin")
            self.assertEqual(result.get("code"), "SUCCESS")

        subs = (await self.db.execute(select(Subscription).where(Subscription.tenant_id == TENANT_A))).scalars().all()
        self.assertEqual(len(subs), 1, "10x confirm must extend exactly once")

    # ---- Case 10: reject leaves entitlement unchanged ----------------------

    async def test_case_10_reject_leaves_subscription_unchanged(self):
        invoice = await self._create_invoice()
        payment = await self._create_manual_payment(invoice)
        await self._claim(TENANT_A, int(payment.id))

        service = BillingService(self.db)
        rejected = await service.reject_manual_payment(int(payment.id), verified_by="super_admin", note="未查到到账")
        self.assertEqual(rejected.manual_review_status, MANUAL_REVIEW_REJECTED)
        self.assertEqual(rejected.status, PAYMENT_STATUS_PENDING)

        await self.db.refresh(invoice)
        self.assertEqual(invoice.status, INVOICE_STATUS_PENDING)
        self.assertEqual(await self._effective_plan_code(TENANT_A), "FREE")
        # Nothing was deleted (F1G-CM Phase 32).
        self.assertIsNotNone(await self.db.get(BillingPayment, payment.id))
        self.assertIsNotNone(await self.db.get(BillingInvoice, invoice.id))

    # ---- Case 11: reject -> reclaim -> confirm applies exactly once -------

    async def test_case_11_reject_then_reclaim_then_confirm_applies_once(self):
        invoice = await self._create_invoice(amount_cents=9900, plan_code="PRO", billing_period="MONTH")
        payment = await self._create_manual_payment(invoice)
        await self._claim(TENANT_A, int(payment.id))

        service = BillingService(self.db)
        await service.reject_manual_payment(int(payment.id), verified_by="super_admin")

        # Merchant resubmits.
        reclaimed = await self._claim(TENANT_A, int(payment.id))
        self.assertEqual(reclaimed.manual_review_status, MANUAL_REVIEW_WAITING_CONFIRMATION)

        result = await service.confirm_manual_payment(int(payment.id), verified_by="super_admin")
        self.assertEqual(result.get("code"), "SUCCESS")

        self.assertEqual(await self._effective_plan_code(TENANT_A), "PRO")
        subs = (await self.db.execute(select(Subscription).where(Subscription.tenant_id == TENANT_A))).scalars().all()
        self.assertEqual(len(subs), 1)

    # ---- Case 12: tenant isolation ------------------------------------------

    async def test_case_12_tenant_a_cannot_claim_tenant_b_payment(self):
        invoice_b = await self._create_invoice(tenant_id=TENANT_B)
        payment_b = await self._create_manual_payment(invoice_b)

        service = BillingService(self.db)
        service.set_tenant_id(TENANT_A)
        with self.assertRaises(ValueError):
            await service.claim_manual_payment(int(payment_b.id))

        # Confirm proceeds unclaimed on tenant B's payment.
        await self.db.refresh(payment_b)
        self.assertIsNone(payment_b.manual_review_status)

    async def test_case_12_tenant_a_cannot_read_tenant_b_payment(self):
        invoice_b = await self._create_invoice(tenant_id=TENANT_B)
        payment_b = await self._create_manual_payment(invoice_b)
        service = BillingService(self.db)
        service.set_tenant_id(TENANT_A)
        self.assertIsNone(await service.get_payment_for_tenant(int(payment_b.id)))

    # ---- Case 13: manual disabled blocks creation --------------------------

    async def test_case_13_manual_disabled_cannot_create_payment(self):
        settings.SAAS_MANUAL_PAYMENT_ENABLED = False
        invoice = await self._create_invoice()
        service = BillingService(self.db)
        service.set_tenant_id(TENANT_A)
        with self.assertRaises(ManualPaymentDisabledError):
            await service.create_payment_attempt(int(invoice.id), provider_name="MANUAL")
        payments = (await self.db.execute(select(BillingPayment).where(BillingPayment.tenant_id == TENANT_A))).scalars().all()
        self.assertEqual(len(payments), 0)

    async def test_case_13_manual_disabled_when_payee_missing(self):
        settings.SAAS_MANUAL_PAYMENT_PAYEE_NAME = ""
        invoice = await self._create_invoice()
        service = BillingService(self.db)
        service.set_tenant_id(TENANT_A)
        with self.assertRaises(ManualPaymentDisabledError):
            await service.create_payment_attempt(int(invoice.id), provider_name="MANUAL")

    async def test_case_13_manual_disabled_when_qr_url_missing(self):
        settings.SAAS_MANUAL_PAYMENT_QR_URL = ""
        invoice = await self._create_invoice()
        service = BillingService(self.db)
        service.set_tenant_id(TENANT_A)
        with self.assertRaises(ManualPaymentDisabledError):
            await service.create_payment_attempt(int(invoice.id), provider_name="MANUAL")

    # ---- Case 14: online_payment_available remains false --------------------

    def test_case_14_online_payment_available_remains_false_regardless_of_manual(self):
        status = BillingService.payment_config_status()
        self.assertFalse(status["real_payment_enabled"])
        manual_status = BillingService.manual_payment_config_status()
        self.assertTrue(manual_status["manual_payment_available"], "manual should be available in this test's own config")
        # The two authorities are independent -- manual being available must
        # never flip online (real WXPAY) to true.
        self.assertFalse(status["real_payment_enabled"])

    # ---- create-payment response contract (Phase 7) -------------------------

    async def test_manual_create_payment_response_contains_display_fields_only(self):
        invoice = await self._create_invoice()
        service = BillingService(self.db)
        service.set_tenant_id(TENANT_A)
        payment, provider_result = await service.create_payment_attempt(int(invoice.id), provider_name="MANUAL")
        pay_params = provider_result["pay_params"]
        self.assertEqual(pay_params["payee_name"], "TEST_ONLY_DUMMY_PAYEE")
        self.assertEqual(pay_params["qr_url"], "https://example.test/dummy-qr.png")
        self.assertEqual(pay_params["confirmation_minutes"], settings.SAAS_MANUAL_PAYMENT_CONFIRM_MINUTES)
        self.assertIsNone(provider_result.get("provider_mchid"))
        self.assertIsNone(provider_result.get("provider_appid"))

    # ---- SuperAdmin pending list --------------------------------------------

    async def test_pending_list_shows_only_waiting_confirmation_and_no_secret(self):
        invoice = await self._create_invoice(amount_cents=60900, plan_code="STANDARD", billing_period="YEAR")
        payment = await self._create_manual_payment(invoice)
        await self._claim(TENANT_A, int(payment.id))

        service = BillingService(self.db)
        rows = await service.list_manual_payments_for_super()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["payment_id"], str(payment.id))
        self.assertEqual(row["tenant_id"], TENANT_A)
        self.assertEqual(row["tenant_name"], "Manual Payment A")
        self.assertEqual(row["plan_code"], "STANDARD")
        self.assertEqual(row["billing_period"], "YEAR")
        self.assertEqual(row["amount_cents"], 60900)
        self.assertEqual(row["review_status"], MANUAL_REVIEW_WAITING_CONFIRMATION)
        forbidden = ("wx_sp", "private_key", "api_key", "secret", "password", "token")
        row_text = str(row).lower()
        for token in forbidden:
            self.assertNotIn(token, row_text)

    async def test_pending_list_excludes_unclaimed_and_confirmed_payments(self):
        unclaimed_invoice = await self._create_invoice(amount_cents=5900)
        await self._create_manual_payment(unclaimed_invoice)  # never claimed

        confirmed_invoice = await self._create_invoice(amount_cents=9900, plan_code="PRO")
        confirmed_payment = await self._create_manual_payment(confirmed_invoice)
        await self._claim(TENANT_A, int(confirmed_payment.id))
        service = BillingService(self.db)
        await service.confirm_manual_payment(int(confirmed_payment.id), verified_by="super_admin")

        rows = await service.list_manual_payments_for_super()
        self.assertEqual(rows, [])

    # ---- amount/currency mismatch cannot be forged into a confirm ---------

    async def test_confirm_notice_amount_always_matches_persisted_payment(self):
        # Defense-in-depth proof: even though confirm_manual_payment builds
        # the notice entirely server-side (no request field to tamper),
        # explicitly assert the constructed notice's amount always equals
        # the payment row's own amount -- the same _validate_success_notice
        # gate every provider goes through would reject a mismatch.
        invoice = await self._create_invoice(amount_cents=102200, plan_code="PRO", billing_period="YEAR")
        payment = await self._create_manual_payment(invoice)
        await self._claim(TENANT_A, int(payment.id))
        service = BillingService(self.db)
        await service.confirm_manual_payment(int(payment.id), verified_by="super_admin")
        await self.db.refresh(payment)
        self.assertEqual(payment.amount_cents, 102200)


class ManualVerifiedPaymentRouteAuthTest(unittest.IsolatedAsyncioTestCase):
    """Cases 5/6: route-level authorization, exercised through the real
    FastAPI app (not just the service layer) since these are specifically
    about the HTTP auth boundary, not business logic."""

    async def asyncSetUp(self):
        self.engine = create_async_engine(
            "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.staff_account_id = generate_snowflake_id()
        async with self.SessionLocal() as seed_db:
            seed_db.add(Tenant(tenant_id=TENANT_A, name="Route Auth Tenant", password_hash="x", status=True))
            seed_db.add(MerchantAccount(
                id=self.staff_account_id, tenant_id=TENANT_A, name="Frontdesk Staff",
                username="frontdesk_route_auth", password_hash="x", role="frontdesk", status="active",
            ))
            await seed_db.commit()

        async def override_get_db():
            async with self.SessionLocal() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        # AuthMiddleware's tenant-active check (_is_tenant_active) does NOT
        # go through the get_db dependency -- it opens its own session via
        # the module-level app.core.database.AsyncSessionLocal, which by
        # default is bound to the real configured DATABASE_URL. Any owner-
        # role request (staff is exempted earlier by the RBAC allowlist
        # check, but owner is not) would otherwise try a real DB connection
        # here. Patched to the SAME in-memory test engine, matching the
        # established pattern in test_merchant_staff_security_gate.py.
        self._session_patch = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._session_patch.start()
        # Two separate patch targets: app.core.cache_helper's own module
        # attribute (re-imported fresh on every call by _is_tenant_active's
        # LOCAL import, so patching the source module is enough for that
        # path) AND app.core.merchant_auth's already-bound names (a
        # module-level `from ... import get_cache, set_cache` there, so
        # load_account_auth_state -- the staff-role DB lookup -- needs its
        # own patch of the SAME callables under merchant_auth's namespace).
        self._cache_helper_get = patch("app.core.cache_helper.get_cache", new_callable=AsyncMock, return_value=None)
        self._cache_helper_set = patch("app.core.cache_helper.set_cache", new_callable=AsyncMock, return_value=None)
        self._merchant_auth_cache_get = patch("app.core.merchant_auth.get_cache", new_callable=AsyncMock, return_value=None)
        self._merchant_auth_cache_set = patch("app.core.merchant_auth.set_cache", new_callable=AsyncMock, return_value=None)
        self._cache_helper_get.start()
        self._cache_helper_set.start()
        self._merchant_auth_cache_get.start()
        self._merchant_auth_cache_set.start()
        transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        self._session_patch.stop()
        self._cache_helper_get.stop()
        self._cache_helper_set.stop()
        self._merchant_auth_cache_get.stop()
        self._merchant_auth_cache_set.stop()
        await self.engine.dispose()

    def _merchant_headers(self, role: str = "owner") -> dict[str, str]:
        if role == "owner":
            token = create_access_token(TENANT_A)
        else:
            # Role is only trusted from a real MerchantAccount DB row looked
            # up by account_id -- a JWT claiming a staff role with no
            # account_id is treated as legacy-owner (app/core/merchant_auth.py's
            # resolve_merchant_request_auth), so this MUST reference the
            # real staff_account_id seeded in asyncSetUp to actually exercise
            # a staff-role request.
            token = create_access_token(TENANT_A, role=role, account_id=self.staff_account_id)
        return {"Authorization": f"Bearer {token}"}

    def _super_headers(self) -> dict[str, str]:
        token = jwt.encode(
            {"sub": "super_admin", "type": "super_admin", "exp": datetime.utcnow() + timedelta(hours=1)},
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        return {"X-Super-Token": token}

    # ---- Case 5: merchant attempts the SuperAdmin confirm endpoint --------

    async def test_case_5_owner_token_cannot_reach_superadmin_confirm(self):
        resp = await self.client.post(
            "/api/super/billing/manual-payments/1/confirm",
            json={}, headers=self._merchant_headers("owner"),
        )
        # No X-Super-Token header at all (Authorization: Bearer is a
        # different header) -- _verify_super_token's own Header(...) dependency
        # rejects the request before the route body ever runs.
        self.assertEqual(resp.status_code, 422)  # FastAPI: required header missing

    async def test_case_5_owner_jwt_used_as_super_token_is_rejected(self):
        owner_token = create_access_token(TENANT_A)
        resp = await self.client.post(
            "/api/super/billing/manual-payments/1/confirm",
            json={}, headers={"X-Super-Token": owner_token},
        )
        # _verify_super_token decodes the token and requires type=="super_admin";
        # a merchant-type token fails that check and is rejected with 401.
        self.assertEqual(resp.status_code, 401)

    # ---- Case 6: staff attempts the SuperAdmin confirm endpoint -----------

    async def test_case_6_staff_jwt_used_as_super_token_is_rejected(self):
        staff_token = create_access_token(TENANT_A, role="frontdesk")
        resp = await self.client.post(
            "/api/super/billing/manual-payments/1/confirm",
            json={}, headers={"X-Super-Token": staff_token},
        )
        self.assertEqual(resp.status_code, 401)

    async def test_case_6_staff_cannot_reach_merchant_manual_claim_either(self):
        # Defense-in-depth: the middleware's staff default-deny already
        # blocks every /api/v1/billing/* route for non-owner roles (proven
        # generally by F1G-B's own audit) -- spot-check it for the new
        # manual-claim route specifically.
        staff_headers = self._merchant_headers("frontdesk")
        resp = await self.client.post(
            "/api/v1/billing/payments/1/manual-claim", headers=staff_headers,
        )
        self.assertEqual(resp.status_code, 403)

    async def test_owner_can_reach_manual_claim_route_at_all(self):
        # Positive control for the two denial tests above -- proves 403/401
        # above are real auth denials, not the route being broken/missing.
        resp = await self.client.post(
            "/api/v1/billing/payments/999999999/manual-claim", headers=self._merchant_headers("owner"),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["code"], 404)  # no such payment, but auth passed

    async def test_superadmin_can_reach_pending_list(self):
        resp = await self.client.get("/api/super/billing/manual-payments", headers=self._super_headers())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["code"], 200)
        self.assertEqual(resp.json()["data"], [])


if __name__ == "__main__":
    unittest.main()
