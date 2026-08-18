from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.billing import billing_wxpay_notify
from app.config import settings
from app.middleware.auth_middleware import WHITELIST
from app.models.base import Base
from app.models.billing import BillingInvoice, BillingPayment
from app.models.tenant import Tenant
from app.services.billing_payment_provider import REAL_PAYMENT_BLOCKED_REASON
from app.services.billing_service import (
    DUPLICATE_INVOICE_PAYMENT,
    INVOICE_STATUS_PAID,
    INVOICE_STATUS_PENDING,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PENDING,
    BillingService,
)
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-billing-a"
TENANT_B = "tenant-billing-b"


@event.listens_for(BillingInvoice, "before_insert")
def _assign_invoice_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(BillingPayment, "before_insert")
def _assign_payment_id_for_sqlite(mapper, connection, target):
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


class SaasBillingFoundationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add_all(
            [
                Tenant(tenant_id=TENANT_A, name="Billing A", password_hash="x", status=True),
                Tenant(tenant_id=TENANT_B, name="Billing B", password_hash="x", status=True),
            ]
        )
        await self.db.commit()
        # F1G-CF-A: the FAKE provider path is now gated by
        # settings.ALLOW_MOCK_MONEY_ENDPOINTS, same as every other mock-money
        # endpoint in this codebase; this file's tests use it as a genuine
        # test capability (test_fake_provider_actually_works_as_a_test_capability).
        settings.ALLOW_MOCK_MONEY_ENDPOINTS = True

    async def asyncTearDown(self):
        settings.ALLOW_MOCK_MONEY_ENDPOINTS = False
        await self.db.close()
        await self.engine.dispose()

    async def _create_invoice(self, tenant_id: str = TENANT_A, amount_cents: int = 19900) -> BillingInvoice:
        return await BillingService(self.db).create_invoice(
            tenant_id=tenant_id,
            charge_type="SAAS_SUBSCRIPTION",
            description="开心点单SaaS服务费",
            amount_cents=amount_cents,
        )

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

    async def test_create_invoice_success(self):
        invoice = await self._create_invoice(amount_cents=8800)
        self.assertEqual(invoice.tenant_id, TENANT_A)
        self.assertEqual(invoice.amount_cents, 8800)
        self.assertEqual(invoice.status, INVOICE_STATUS_PENDING)
        self.assertTrue(invoice.invoice_no.startswith("BINV"))

    async def test_wrong_tenant_cannot_read_invoice(self):
        invoice = await self._create_invoice()
        service = BillingService(self.db)
        service.set_tenant_id(TENANT_B)
        self.assertIsNone(await service.get_invoice_for_tenant(int(invoice.id)))

    async def test_merchant_cannot_modify_invoice_amount_through_payment_attempt(self):
        invoice = await self._create_invoice(amount_cents=6600)
        payment = await self._create_payment(invoice)
        self.assertEqual(payment.amount_cents, 6600)
        invoice.amount_cents = 9900
        await self.db.rollback()
        await self.db.refresh(payment)
        self.assertEqual(payment.amount_cents, 6600)

    async def test_payment_attempt_created_with_invoice_amount_and_provider_identity(self):
        invoice = await self._create_invoice(amount_cents=12800)
        payment = await self._create_payment(invoice)
        self.assertEqual(payment.invoice_id, invoice.id)
        self.assertEqual(payment.amount_cents, invoice.amount_cents)
        self.assertEqual(payment.provider, "FAKE")
        self.assertEqual(payment.provider_mchid, "fake-platform-mchid")
        self.assertEqual(payment.provider_appid, "fake-platform-appid")

    async def test_successful_callback_marks_payment_and_invoice_paid_and_persists_transaction_id(self):
        invoice = await self._create_invoice()
        payment = await self._create_payment(invoice)

        result = await self._notify_success(payment, transaction_id="txn-success-1")

        self.assertEqual(result.get("code"), "SUCCESS")
        await self.db.refresh(payment)
        await self.db.refresh(invoice)
        self.assertEqual(payment.status, PAYMENT_STATUS_PAID)
        self.assertEqual(payment.transaction_id, "txn-success-1")
        self.assertIsNotNone(payment.paid_at)
        self.assertEqual(invoice.status, INVOICE_STATUS_PAID)
        self.assertIsNotNone(invoice.paid_at)
        self.assertIsNotNone(invoice.success_processed_at)

    async def test_duplicate_callback_x10_runs_success_hook_once(self):
        invoice = await self._create_invoice()
        payment = await self._create_payment(invoice)
        calls = []
        original = BillingService._on_billing_payment_success

        async def counting_hook(service, invoice_obj, payment_obj):
            calls.append((invoice_obj.id, payment_obj.id))
            await original(service, invoice_obj, payment_obj)

        with patch.object(BillingService, "_on_billing_payment_success", new=counting_hook):
            for _ in range(10):
                result = await self._notify_success(payment, transaction_id="txn-dup-callback")
                self.assertEqual(result.get("code"), "SUCCESS")

        await self.db.refresh(payment)
        await self.db.refresh(invoice)
        self.assertEqual(payment.status, PAYMENT_STATUS_PAID)
        self.assertEqual(invoice.status, INVOICE_STATUS_PAID)
        self.assertEqual(len(calls), 1)

    async def test_two_distinct_successful_payments_preserve_both_facts_but_success_hook_once(self):
        invoice = await self._create_invoice()
        first = await self._create_payment(invoice)
        second = await self._create_payment(invoice)
        calls = []
        original = BillingService._on_billing_payment_success

        async def counting_hook(service, invoice_obj, payment_obj):
            calls.append((invoice_obj.id, payment_obj.id))
            await original(service, invoice_obj, payment_obj)

        with patch.object(BillingService, "_on_billing_payment_success", new=counting_hook):
            self.assertEqual((await self._notify_success(first, transaction_id="txn-first")).get("code"), "SUCCESS")
            self.assertEqual((await self._notify_success(second, transaction_id="txn-second")).get("code"), "SUCCESS")

        await self.db.refresh(invoice)
        await self.db.refresh(first)
        await self.db.refresh(second)
        self.assertEqual(invoice.status, INVOICE_STATUS_PAID)
        self.assertEqual(first.status, PAYMENT_STATUS_PAID)
        self.assertEqual(second.status, PAYMENT_STATUS_PAID)
        self.assertEqual(second.anomaly_reason, DUPLICATE_INVOICE_PAYMENT)
        self.assertEqual(first.transaction_id, "txn-first")
        self.assertEqual(second.transaction_id, "txn-second")
        self.assertEqual(len(calls), 1)

    async def test_amount_mismatch_rejected_and_payment_stays_pending(self):
        invoice = await self._create_invoice()
        payment = await self._create_payment(invoice)

        result = await self._notify_success(payment, amount_cents=1)

        self.assertEqual(result.get("code"), "FAIL")
        await self.db.refresh(payment)
        await self.db.refresh(invoice)
        self.assertEqual(payment.status, PAYMENT_STATUS_PENDING)
        self.assertEqual(invoice.status, INVOICE_STATUS_PENDING)

    async def test_invalid_signature_rejected(self):
        invoice = await self._create_invoice()
        payment = await self._create_payment(invoice)
        payload = {
            "out_trade_no": payment.out_trade_no,
            "transaction_id": "txn-invalid-signature",
            "amount_cents": payment.amount_cents,
            "currency": payment.currency,
            "trade_state": "SUCCESS",
        }

        result = await billing_wxpay_notify(make_notify_request(payload, signature="bad"), db=self.db)

        self.assertEqual(result.get("code"), "FAIL")
        await self.db.refresh(payment)
        self.assertEqual(payment.status, PAYMENT_STATUS_PENDING)

    async def test_wrong_platform_merchant_rejected(self):
        invoice = await self._create_invoice()
        payment = await self._create_payment(invoice)

        result = await self._notify_success(payment, provider_mchid="wrong-mchid")

        self.assertEqual(result.get("code"), "FAIL")
        await self.db.refresh(payment)
        await self.db.refresh(invoice)
        self.assertEqual(payment.status, PAYMENT_STATUS_PENDING)
        self.assertEqual(invoice.status, INVOICE_STATUS_PENDING)

    async def test_multiple_failed_attempts_do_not_corrupt_invoice_and_later_attempt_can_pay(self):
        invoice = await self._create_invoice(amount_cents=30000)
        first = await self._create_payment(invoice)
        second = await self._create_payment(invoice)

        self.assertEqual((await self._notify_success(first, amount_cents=2)).get("code"), "FAIL")
        await self.db.refresh(invoice)
        self.assertEqual(invoice.status, INVOICE_STATUS_PENDING)

        self.assertEqual((await self._notify_success(second, transaction_id="txn-later-success")).get("code"), "SUCCESS")
        await self.db.refresh(invoice)
        await self.db.refresh(first)
        await self.db.refresh(second)
        self.assertEqual(invoice.status, INVOICE_STATUS_PAID)
        self.assertEqual(first.status, PAYMENT_STATUS_PENDING)
        self.assertEqual(second.status, PAYMENT_STATUS_PAID)

    async def test_invoice_already_paid_cannot_create_new_payment_attempt(self):
        invoice = await self._create_invoice()
        payment = await self._create_payment(invoice)
        await self._notify_success(payment)
        service = BillingService(self.db)
        service.set_tenant_id(TENANT_A)

        with self.assertRaisesRegex(ValueError, "账单当前状态不能发起支付"):
            await service.create_payment_attempt(int(invoice.id), provider_name="FAKE")

    async def test_real_wxpay_is_blocked_until_platform_receivables_config_is_confirmed(self):
        invoice = await self._create_invoice()
        service = BillingService(self.db)
        service.set_tenant_id(TENANT_A)

        with self.assertRaisesRegex(RuntimeError, REAL_PAYMENT_BLOCKED_REASON):
            await service.create_payment_attempt(int(invoice.id), provider_name="WXPAY")

    def test_billing_callback_does_not_depend_on_merchant_jwt(self):
        self.assertIn("/api/v1/billing/wxpay-notify", WHITELIST)

    def test_consumer_order_payment_system_remains_unchanged(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        order_payment_source = (root / "app" / "services" / "order_payment_service.py").read_text(encoding="utf-8-sig")
        order_api_source = (root / "app" / "api" / "v1" / "orders.py").read_text(encoding="utf-8-sig")
        self.assertIn('out_trade_no=str(order.id)', order_payment_source)
        self.assertIn('@router.post("/orders/wxpay-notify")', order_api_source)


if __name__ == "__main__":
    unittest.main()
