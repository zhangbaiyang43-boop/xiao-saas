from __future__ import annotations

import asyncio
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import httpx
import jwt
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.api.v1.billing import billing_wxpay_notify
from app.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, create_channel_partner_access_token, create_customer_access_token
from app.main import app
from app.models.base import Base
from app.models.billing import BillingInvoice, BillingPayment
from app.models.channel_revenue import (
    ChannelCommissionLedger,
    ChannelCommissionSettlement,
    ChannelLead,
    ChannelPartner,
    ChannelPartnerTenantBinding,
)
from app.models.tenant import Tenant
from app.services.billing_service import BillingService
from app.services.channel_auth_code_service import ChannelAuthCodeService
from app.services.channel_commission_service import ChannelCommissionService
from app.services.channel_partner_service import (
    PARTNER_STATUS_ACTIVE,
    PARTNER_STATUS_DISABLED,
    PARTNER_STATUS_SUSPENDED,
    ChannelPartnerService,
)
from app.services.channel_settlement_service import ChannelSettlementService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-portal-a"
TENANT_B = "tenant-portal-b"


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


class ChannelPortalSecurityGateTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add_all(
            [
                Tenant(tenant_id=TENANT_A, name="Merchant A", password_hash="x", status=True),
                Tenant(tenant_id=TENANT_B, name="Merchant B", password_hash="x", status=True),
            ]
        )
        await self.db.commit()

        async def override_get_db():
            yield self.db

        app.dependency_overrides[get_db] = override_get_db
        transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=transport, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        await self.db.close()
        await self.engine.dispose()

    async def _partner(self, code: str, mobile: str, status: str = PARTNER_STATUS_ACTIVE) -> ChannelPartner:
        return await ChannelPartnerService(self.db).create_partner(
            partner_code=code,
            name=f"Partner {code}",
            mobile=mobile,
            partner_type="WINE_SALES",
            status=status,
        )

    async def _binding(self, partner: ChannelPartner, tenant_id: str, mobile: str) -> ChannelPartnerTenantBinding:
        lead = await ChannelPartnerService(self.db).create_lead(
            partner_id=int(partner.id),
            merchant_name=f"Store {tenant_id}",
            merchant_mobile=mobile,
            contact_name="Boss",
        )
        return await ChannelPartnerService(self.db).convert_lead_to_tenant_binding(int(lead.id), tenant_id)

    async def _earn(self, partner: ChannelPartner, tenant_id: str, mobile: str, amount_cents: int = 59900) -> ChannelCommissionLedger:
        await self._binding(partner, tenant_id, mobile)
        invoice = await BillingService(self.db).create_invoice(
            tenant_id=tenant_id,
            charge_type="SAAS_SUBSCRIPTION",
            description="SaaS",
            amount_cents=amount_cents,
        )
        payment = BillingPayment(
            tenant_id=tenant_id,
            invoice_id=invoice.id,
            payment_no=f"PAY{invoice.id}",
            out_trade_no=f"PAY{invoice.id}",
            provider="FAKE",
            amount_cents=amount_cents,
            currency="CNY",
            status="PAID",
            transaction_id=f"txn-{invoice.id}",
            paid_at=datetime.utcnow() - timedelta(days=8),
        )
        self.db.add(payment)
        await self.db.flush()
        invoice.status = "PAID"
        invoice.paid_at = payment.paid_at
        ledger = await ChannelCommissionService(self.db).handle_billing_payment_success(invoice, payment)
        await self.db.commit()
        return ledger

    def _channel_headers(self, partner: ChannelPartner) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_channel_partner_access_token(int(partner.id))}"}

    async def test_partner_mobile_normalized_is_unique_auth_subject(self):
        first = await self._partner("CPA", "139 0000 0001")
        self.assertEqual(first.mobile_normalized, "13900000001")
        with self.assertRaisesRegex(ValueError, "mobile"):
            await self._partner("CPB", "139-0000-0001")

    async def test_channel_otp_can_succeed_only_once(self):
        partner = await self._partner("CPC", "13900000002")
        service = ChannelAuthCodeService()
        await service.store_login_code(partner.mobile_normalized, "246810")
        self.assertTrue(await service.verify_login_code(partner.mobile_normalized, "246810"))
        self.assertFalse(await service.verify_login_code(partner.mobile_normalized, "246810"))

    async def test_status_policy_active_suspended_disabled(self):
        active = await self._partner("CPD", "13900000003", PARTNER_STATUS_ACTIVE)
        suspended = await self._partner("CPE", "13900000004", PARTNER_STATUS_SUSPENDED)
        disabled = await self._partner("CPF", "13900000005", PARTNER_STATUS_DISABLED)
        for partner in [active, suspended, disabled]:
            await ChannelAuthCodeService().store_login_code(partner.mobile_normalized, "135790")

        active_login = await self.client.post("/api/v1/channel/auth/login", json={"mobile": active.mobile, "code": "135790"})
        suspended_login = await self.client.post("/api/v1/channel/auth/login", json={"mobile": suspended.mobile, "code": "135790"})
        disabled_login = await self.client.post("/api/v1/channel/auth/login", json={"mobile": disabled.mobile, "code": "135790"})
        self.assertEqual(active_login.json()["code"], 200)
        self.assertEqual(suspended_login.json()["code"], 200)
        self.assertEqual(disabled_login.json()["code"], 403)

        readonly = await self.client.get("/api/v1/channel/dashboard", headers=self._channel_headers(suspended))
        blocked = await self.client.post(
            "/api/v1/channel/leads",
            headers=self._channel_headers(suspended),
            json={"merchant_name": "Blocked", "merchant_mobile": "13800138001"},
        )
        self.assertEqual(readonly.json()["code"], 200)
        self.assertEqual(blocked.json()["code"], 403)

    async def test_cross_identity_auth_boundaries(self):
        partner = await self._partner("CPG", "13900000006")
        channel_headers = self._channel_headers(partner)
        merchant_headers = {"Authorization": f"Bearer {create_access_token(TENANT_A)}"}
        member_headers = {"Authorization": f"Bearer {create_customer_access_token(TENANT_A, 123)}"}
        super_token = jwt.encode(
            {"sub": "super_admin", "type": "super_admin", "exp": datetime.utcnow() + timedelta(hours=1)},
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        super_headers = {"Authorization": f"Bearer {super_token}"}

        self.assertEqual((await self.client.get("/api/v1/channel/me", headers=channel_headers)).json()["code"], 200)
        self.assertEqual((await self.client.get("/api/v1/channel/me", headers=merchant_headers)).status_code, 403)
        self.assertEqual((await self.client.get("/api/v1/channel/me", headers=member_headers)).status_code, 403)
        self.assertEqual((await self.client.get("/api/v1/channel/me", headers=super_headers)).status_code, 403)
        self.assertEqual((await self.client.get("/api/v1/customers", headers=channel_headers)).status_code, 403)

    async def test_partner_cannot_read_other_partner_objects_or_override_partner_id(self):
        partner_a = await self._partner("CPH", "13900000007")
        partner_b = await self._partner("CPI", "13900000008")
        own_ledger = await self._earn(partner_a, TENANT_A, "13800138002")
        other_ledger = await self._earn(partner_b, TENANT_B, "13800138003")
        settlement = await ChannelSettlementService(self.db).create_manual_settlement(
            partner_id=int(partner_b.id),
            operator="super",
            ledger_ids=[int(other_ledger.id)],
        )
        other_lead = (await self.db.execute(select(ChannelLead).where(ChannelLead.partner_id == partner_b.id))).scalar_one()
        other_binding = (
            await self.db.execute(select(ChannelPartnerTenantBinding).where(ChannelPartnerTenantBinding.partner_id == partner_b.id))
        ).scalar_one()
        headers = self._channel_headers(partner_a)

        self.assertEqual((await self.client.get(f"/api/v1/channel/leads/{other_lead.id}", headers=headers)).json()["code"], 404)
        self.assertEqual((await self.client.get(f"/api/v1/channel/merchants/{other_binding.id}", headers=headers)).json()["code"], 404)
        self.assertEqual((await self.client.get(f"/api/v1/channel/commissions/{other_ledger.id}", headers=headers)).json()["code"], 404)
        self.assertEqual((await self.client.get(f"/api/v1/channel/settlements/{settlement.id}", headers=headers)).json()["code"], 404)

        data = (await self.client.get(
            f"/api/v1/channel/commissions?partner_id={partner_b.id}&page=1&page_size=50",
            headers=headers,
        )).json()["data"]
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["id"], str(own_ledger.id))

    async def test_channel_mutation_routes_for_financial_core_do_not_exist(self):
        partner = await self._partner("CPJ", "13900000009")
        headers = self._channel_headers(partner)
        checks = [
            await self.client.post("/api/v1/channel/bindings", headers=headers, json={}),
            await self.client.patch("/api/v1/channel/commissions/1", headers=headers, json={"commission_amount_cents": 1}),
            await self.client.post("/api/v1/channel/settlements", headers=headers, json={}),
            await self.client.post("/api/v1/channel/settlements/1/approve", headers=headers, json={}),
        ]
        self.assertTrue(all(item.status_code in {404, 405} for item in checks))

    async def test_dashboard_uses_net_ledger_aggregation_with_reversals(self):
        partner = await self._partner("CPK", "13900000010")
        earn = await self._earn(partner, TENANT_A, "13800138004")
        await ChannelCommissionService(self.db).create_reversal(
            source_ledger_id=int(earn.id),
            source_event_id="refund-dashboard",
            amount_cents=1980,
        )
        await self.db.commit()
        data = (await self.client.get("/api/v1/channel/dashboard", headers=self._channel_headers(partner))).json()["data"]
        self.assertEqual(data["gross_earned_cents"], 11980)
        self.assertEqual(data["reversed_cents"], 1980)
        self.assertEqual(data["net_earned_cents"], 10000)
        self.assertEqual(data["available_cents"], 10000)

    async def test_billing_callback_repeated_x10_with_binding_creates_one_channel_earn(self):
        partner = await self._partner("CPL", "13900000011")
        await self._binding(partner, TENANT_A, "13800138005")
        invoice = await BillingService(self.db).create_invoice(
            tenant_id=TENANT_A,
            charge_type="SAAS_SUBSCRIPTION",
            description="SaaS",
            amount_cents=59900,
        )
        service = BillingService(self.db)
        service.set_tenant_id(TENANT_A)
        payment, _ = await service.create_payment_attempt(int(invoice.id), provider_name="FAKE")
        calls = []
        original = BillingService._on_billing_payment_success

        async def counting_hook(service_obj, invoice_obj, payment_obj):
            calls.append((invoice_obj.id, payment_obj.id))
            await original(service_obj, invoice_obj, payment_obj)

        payload = {
            "out_trade_no": payment.out_trade_no,
            "transaction_id": "txn-channel-x10",
            "amount_cents": payment.amount_cents,
            "currency": payment.currency,
            "trade_state": "SUCCESS",
            "provider_mchid": payment.provider_mchid,
            "provider_appid": payment.provider_appid,
        }
        with patch.object(BillingService, "_on_billing_payment_success", new=counting_hook):
            for _ in range(10):
                result = await billing_wxpay_notify(make_notify_request(payload), db=self.db)
                self.assertEqual(result.get("code"), "SUCCESS")

        await self.db.refresh(invoice)
        ledgers = (await self.db.execute(select(ChannelCommissionLedger))).scalars().all()
        self.assertEqual(invoice.status, "PAID")
        self.assertIsNotNone(invoice.success_processed_at)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(ledgers), 1)
        self.assertEqual(ledgers[0].billing_payment_id, payment.id)
        self.assertEqual(ledgers[0].commission_amount_cents, 11980)

    async def test_merchant_dto_includes_binding_scoped_net_earned_cents(self):
        partner = await self._partner("CPM", "13900000012")
        empty_binding = await self._binding(partner, TENANT_A, "13800138006")
        earned = await self._earn(partner, TENANT_B, "13800138007")
        await ChannelCommissionService(self.db).create_reversal(
            source_ledger_id=int(earned.id),
            source_event_id="refund-merchant-dto",
            amount_cents=3000,
        )
        await self.db.commit()

        headers = self._channel_headers(partner)
        listing = (await self.client.get("/api/v1/channel/merchants?page=1&page_size=20", headers=headers)).json()["data"]
        by_id = {item["id"]: item for item in listing["items"]}

        self.assertEqual(by_id[str(empty_binding.id)]["net_earned_cents"], 0)
        self.assertEqual(by_id[str(earned.binding_id)]["net_earned_cents"], 8980)

        detail = (await self.client.get(f"/api/v1/channel/merchants/{earned.binding_id}", headers=headers)).json()["data"]
        self.assertEqual(detail["net_earned_cents"], by_id[str(earned.binding_id)]["net_earned_cents"])

    async def test_merchant_net_earned_cents_is_not_reduced_by_settlement_status(self):
        partner = await self._partner("CPN", "13900000013")
        earned = await self._earn(partner, TENANT_A, "13800138008")
        await ChannelSettlementService(self.db).create_manual_settlement(
            partner_id=int(partner.id),
            operator="super",
            ledger_ids=[int(earned.id)],
        )

        detail = (
            await self.client.get(
                f"/api/v1/channel/merchants/{earned.binding_id}",
                headers=self._channel_headers(partner),
            )
        ).json()["data"]
        self.assertEqual(detail["net_earned_cents"], 11980)

    async def test_merchant_net_earned_cents_is_partner_scoped(self):
        partner_a = await self._partner("CPO", "13900000014")
        partner_b = await self._partner("CPP", "13900000015")
        own = await self._earn(partner_a, TENANT_A, "13800138009")
        other = await self._earn(partner_b, TENANT_B, "13800138010")

        hidden = await ChannelCommissionService(self.db).get_net_earned_cents_by_binding_ids(
            partner_id=int(partner_a.id),
            binding_ids=[int(own.binding_id), int(other.binding_id)],
        )
        self.assertEqual(hidden[int(own.binding_id)], 11980)
        self.assertNotIn(int(other.binding_id), hidden)

    async def test_merchant_list_uses_single_batch_earnings_aggregation(self):
        partner = await self._partner("CPQ", "13900000016")
        for index in range(20):
            tenant_id = f"tenant-page-{index}"
            self.db.add(Tenant(tenant_id=tenant_id, name=f"Merchant {index}", password_hash="x", status=True))
            await self.db.commit()
            await self._binding(partner, tenant_id, f"13800139{index:03d}")

        calls = []
        original = ChannelCommissionService.get_net_earned_cents_by_binding_ids

        async def counting_aggregate(service_obj, *, partner_id, binding_ids):
            calls.append(list(binding_ids))
            return await original(service_obj, partner_id=partner_id, binding_ids=binding_ids)

        with patch.object(ChannelCommissionService, "get_net_earned_cents_by_binding_ids", new=counting_aggregate):
            data = (
                await self.client.get(
                    "/api/v1/channel/merchants?page=1&page_size=20",
                    headers=self._channel_headers(partner),
                )
            ).json()["data"]

        self.assertEqual(data["total"], 20)
        self.assertEqual(len(data["items"]), 20)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0]), 20)
        self.assertTrue(all(item["net_earned_cents"] == 0 for item in data["items"]))


if __name__ == "__main__":
    unittest.main()
