from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.super_admin import _verify_super_token
from app.models.base import Base
from app.models.billing import BillingInvoice, BillingPayment
from app.models.channel_revenue import (
    ChannelCommissionLedger,
    ChannelCommissionSettlementItem,
    ChannelLead,
    ChannelPartnerTenantBinding,
)
from app.models.tenant import Tenant
from app.services.billing_service import BillingService
from app.services.channel_commission_policy import CHANNEL_COMMISSION_POLICY_VERSION
from app.services.channel_commission_service import (
    CHANNEL_COMMISSION_STATUS_AVAILABLE,
    CHANNEL_COMMISSION_STATUS_PENDING,
    CHANNEL_COMMISSION_STATUS_SETTLED,
    ENTRY_TYPE_EARN,
    ENTRY_TYPE_REVERSAL,
    ChannelCommissionService,
)
from app.services.channel_partner_service import (
    BINDING_STATUS_ACTIVE,
    DEFAULT_COMMISSION_RATE_BPS,
    DEFAULT_COMMISSION_TERM_MONTHS,
    LEAD_STATUS_CONTACTED,
    LEAD_STATUS_PROTECTED,
    PARTNER_STATUS_ACTIVE,
    PARTNER_STATUS_DISABLED,
    ChannelPartnerService,
)
from app.services.channel_settlement_service import ChannelSettlementService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-channel-a"
TENANT_B = "tenant-channel-b"


class ChannelRevenueShareFoundationTest(unittest.IsolatedAsyncioTestCase):
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
                Tenant(tenant_id=TENANT_A, name="Channel A", password_hash="x", status=True),
                Tenant(tenant_id=TENANT_B, name="Channel B", password_hash="x", status=True),
            ]
        )
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _partner(self, code="P001", status=PARTNER_STATUS_ACTIVE):
        return await ChannelPartnerService(self.db).create_partner(
            partner_code=code,
            name=f"Partner {code}",
            mobile=f"1390000{code[-4:]}",
            partner_type="WINE_SALES",
            status=status,
        )

    async def _invoice_payment(
        self,
        *,
        tenant_id=TENANT_A,
        charge_type="SAAS_SUBSCRIPTION",
        amount_cents=59900,
        paid_at: datetime | None = None,
    ):
        invoice = await BillingService(self.db).create_invoice(
            tenant_id=tenant_id,
            charge_type=charge_type,
            description=charge_type,
            amount_cents=amount_cents,
        )
        payment = BillingPayment(
            tenant_id=tenant_id,
            invoice_id=invoice.id,
            payment_no=f"MANUAL{invoice.id}{charge_type}",
            out_trade_no=f"MANUAL{invoice.id}{charge_type}",
            provider="FAKE",
            amount_cents=amount_cents,
            currency="CNY",
            status="PAID",
            transaction_id=f"txn-{invoice.id}-{charge_type}",
            paid_at=paid_at or datetime(2026, 9, 1, 10, 0, 0),
        )
        self.db.add(payment)
        await self.db.flush()
        invoice.status = "PAID"
        invoice.paid_at = payment.paid_at
        return invoice, payment

    async def _binding(self, partner, tenant_id=TENANT_A):
        lead = await ChannelPartnerService(self.db).create_lead(
            partner_id=partner.id,
            merchant_name="Happy Restaurant",
            merchant_mobile="13800138000",
            contact_name="Boss",
        )
        return await ChannelPartnerService(self.db).convert_lead_to_tenant_binding(
            lead_id=lead.id,
            tenant_id=tenant_id,
        )

    async def test_partner_create_and_partner_code_unique(self):
        partner = await self._partner("P100")
        self.assertEqual(partner.partner_code, "P100")
        with self.assertRaisesRegex(ValueError, "partner_code"):
            await self._partner("P100")

    async def test_create_lead_and_same_active_mobile_cannot_be_protected_by_two_partners(self):
        first = await self._partner("P101")
        second = await self._partner("P102")
        lead = await ChannelPartnerService(self.db).create_lead(
            partner_id=first.id,
            merchant_name="Store",
            merchant_mobile="138-0013-8000",
            contact_name="A",
        )
        self.assertEqual(lead.status, LEAD_STATUS_PROTECTED)
        with self.assertRaisesRegex(ValueError, "protected"):
            await ChannelPartnerService(self.db).create_lead(
                partner_id=second.id,
                merchant_name="Store 2",
                merchant_mobile="13800138000",
                contact_name="B",
            )

    async def test_expired_lead_can_be_re_registered(self):
        first = await self._partner("P103")
        second = await self._partner("P104")
        lead = await ChannelPartnerService(self.db).create_lead(
            partner_id=first.id,
            merchant_name="Old Store",
            merchant_mobile="13900139000",
            contact_name="A",
        )
        lead.protected_until = datetime.utcnow() - timedelta(seconds=1)
        await self.db.commit()
        next_lead = await ChannelPartnerService(self.db).create_lead(
            partner_id=second.id,
            merchant_name="New Store",
            merchant_mobile="13900139000",
            contact_name="B",
        )
        self.assertEqual(next_lead.partner_id, second.id)

    async def test_same_mobile_concurrent_acquisition_only_one_wins(self):
        first = await self._partner("P105")
        second = await self._partner("P106")

        async def attempt(partner_id):
            session = self.SessionLocal()
            try:
                return await ChannelPartnerService(session).create_lead(
                    partner_id=partner_id,
                    merchant_name="Concurrent Store",
                    merchant_mobile="13700137000",
                    contact_name="A",
                )
            except ValueError as exc:
                return str(exc)
            finally:
                await session.close()

        results = await asyncio.gather(attempt(first.id), attempt(second.id))
        winners = [r for r in results if isinstance(r, ChannelLead)]
        rejects = [r for r in results if isinstance(r, str) and "protected" in r]
        self.assertEqual(len(winners), 1)
        self.assertEqual(len(rejects), 1)

    async def test_lead_converts_to_single_tenant_binding_with_snapshots_and_no_start(self):
        partner = await self._partner("P107")
        binding = await self._binding(partner)
        self.assertEqual(binding.partner_id, partner.id)
        self.assertEqual(binding.status, BINDING_STATUS_ACTIVE)
        self.assertEqual(binding.commission_rate_bps, DEFAULT_COMMISSION_RATE_BPS)
        self.assertEqual(binding.commission_term_months, DEFAULT_COMMISSION_TERM_MONTHS)
        self.assertIsNone(binding.commission_started_at)
        self.assertIsNone(binding.commission_ends_at)
        with self.assertRaisesRegex(ValueError, "tenant"):
            await self._binding(partner)

    async def test_lead_conversion_requires_active_partner_unexpired_lead_and_once_only(self):
        partner = await self._partner("P108", status=PARTNER_STATUS_DISABLED)
        with self.assertRaisesRegex(ValueError, "ACTIVE"):
            await ChannelPartnerService(self.db).create_lead(
                partner_id=partner.id,
                merchant_name="Disabled",
                merchant_mobile="13600136000",
                contact_name="A",
            )

        active = await self._partner("P109")
        lead = await ChannelPartnerService(self.db).create_lead(
            partner_id=active.id,
            merchant_name="Convert",
            merchant_mobile="13600136001",
            contact_name="A",
        )
        binding = await ChannelPartnerService(self.db).convert_lead_to_tenant_binding(lead.id, TENANT_A)
        self.assertEqual(binding.partner_id, active.id)
        with self.assertRaisesRegex(ValueError, "converted"):
            await ChannelPartnerService(self.db).convert_lead_to_tenant_binding(lead.id, TENANT_B)

    async def test_invoice_eligibility_snapshot_and_policy_change_does_not_pollute_history(self):
        invoice = await BillingService(self.db).create_invoice(
            tenant_id=TENANT_A,
            charge_type="SAAS_SUBSCRIPTION",
            description="sub",
            amount_cents=10000,
        )
        self.assertTrue(invoice.commission_eligible)
        self.assertEqual(invoice.commission_policy_version, CHANNEL_COMMISSION_POLICY_VERSION)
        invoice.charge_type = "HARDWARE"
        await self.db.commit()
        await self.db.refresh(invoice)
        self.assertTrue(invoice.commission_eligible)

    async def test_non_eligible_payment_does_not_start_term_then_first_eligible_starts_and_earns(self):
        partner = await self._partner("P110")
        binding = await self._binding(partner)
        hardware_invoice, hardware_payment = await self._invoice_payment(charge_type="HARDWARE", amount_cents=20000)
        await ChannelCommissionService(self.db).handle_billing_payment_success(hardware_invoice, hardware_payment)
        await self.db.refresh(binding)
        self.assertIsNone(binding.commission_started_at)
        self.assertEqual((await self.db.execute(select(ChannelCommissionLedger))).scalars().all(), [])

        invoice, payment = await self._invoice_payment(charge_type="SAAS_SUBSCRIPTION", amount_cents=59900)
        await ChannelCommissionService(self.db).handle_billing_payment_success(invoice, payment)
        ledgers = (await self.db.execute(select(ChannelCommissionLedger))).scalars().all()
        await self.db.refresh(binding)
        self.assertEqual(len(ledgers), 1)
        self.assertEqual(ledgers[0].commission_amount_cents, 11980)
        self.assertEqual(ledgers[0].status, CHANNEL_COMMISSION_STATUS_PENDING)
        self.assertEqual(ledgers[0].available_at, payment.paid_at + timedelta(days=7))
        self.assertEqual(binding.commission_started_at, payment.paid_at)

    async def test_duplicate_success_and_duplicate_real_payment_create_one_earn(self):
        partner = await self._partner("P111")
        await self._binding(partner)
        invoice, first = await self._invoice_payment(charge_type="ADDON", amount_cents=10000)
        await ChannelCommissionService(self.db).handle_billing_payment_success(invoice, first)
        await ChannelCommissionService(self.db).handle_billing_payment_success(invoice, first)
        second = BillingPayment(
            tenant_id=TENANT_A,
            invoice_id=invoice.id,
            payment_no=f"SECOND{invoice.id}",
            out_trade_no=f"SECOND{invoice.id}",
            provider="FAKE",
            amount_cents=10000,
            currency="CNY",
            status="PAID",
            transaction_id=f"txn-second-{invoice.id}",
            paid_at=first.paid_at,
            anomaly_reason="DUPLICATE_INVOICE_PAYMENT",
        )
        self.db.add(second)
        await self.db.flush()
        await ChannelCommissionService(self.db).handle_billing_payment_success(invoice, second)
        ledgers = (await self.db.execute(select(ChannelCommissionLedger))).scalars().all()
        self.assertEqual(len(ledgers), 1)
        self.assertEqual(ledgers[0].billing_payment_id, first.id)

    async def test_no_binding_and_retroactive_binding_create_no_commission_for_old_payment(self):
        invoice, payment = await self._invoice_payment(charge_type="SAAS_SUBSCRIPTION", amount_cents=10000)
        await ChannelCommissionService(self.db).handle_billing_payment_success(invoice, payment)
        self.assertEqual((await self.db.execute(select(ChannelCommissionLedger))).scalars().all(), [])
        partner = await self._partner("P112")
        await self._binding(partner)
        self.assertEqual((await self.db.execute(select(ChannelCommissionLedger))).scalars().all(), [])

    async def test_not_eligible_charge_types_create_no_commission(self):
        partner = await self._partner("P113")
        await self._binding(partner)
        for charge_type in ["MINIPROGRAM_CERTIFICATION", "HARDWARE", "SMS_TOPUP", "SETUP_SERVICE", "OTHER"]:
            invoice, payment = await self._invoice_payment(charge_type=charge_type, amount_cents=10000)
            await ChannelCommissionService(self.db).handle_billing_payment_success(invoice, payment)
        count = len((await self.db.execute(select(ChannelCommissionLedger))).scalars().all())
        self.assertEqual(count, 0)

    async def test_36_month_boundary_and_rate_snapshot(self):
        partner = await self._partner("P114")
        binding = await self._binding(partner)
        start = datetime(2026, 2, 28, 12, 0, 0)
        first_invoice, first_payment = await self._invoice_payment(paid_at=start)
        await ChannelCommissionService(self.db).handle_billing_payment_success(first_invoice, first_payment)
        await self.db.refresh(binding)
        before_end = binding.commission_ends_at - timedelta(seconds=1)
        at_end = binding.commission_ends_at
        for paid_at in [before_end, at_end, at_end + timedelta(seconds=1)]:
            invoice, payment = await self._invoice_payment(paid_at=paid_at)
            await ChannelCommissionService(self.db).handle_billing_payment_success(invoice, payment)
        ledgers = (await self.db.execute(select(ChannelCommissionLedger).order_by(ChannelCommissionLedger.earned_at))).scalars().all()
        self.assertEqual(len(ledgers), 2)
        self.assertEqual({ledger.commission_rate_bps for ledger in ledgers}, {2000})

    async def test_reversal_is_append_only_and_supports_settled_negative_balance(self):
        partner = await self._partner("P115")
        await self._binding(partner)
        invoice, payment = await self._invoice_payment()
        service = ChannelCommissionService(self.db)
        earn = await service.handle_billing_payment_success(invoice, payment)
        earn.status = CHANNEL_COMMISSION_STATUS_SETTLED
        await self.db.flush()
        reversal = await service.create_reversal(
            source_ledger_id=earn.id,
            source_event_id="refund-001",
            amount_cents=3000,
        )
        self.assertEqual(earn.commission_amount_cents, 11980)
        self.assertEqual(reversal.entry_type, ENTRY_TYPE_REVERSAL)
        self.assertEqual(reversal.commission_amount_cents, -3000)
        self.assertEqual(reversal.source_ledger_id, earn.id)
        self.assertEqual(reversal.status, CHANNEL_COMMISSION_STATUS_AVAILABLE)

    async def test_available_entries_can_be_settled_pending_cannot_and_entry_cannot_settle_twice(self):
        partner = await self._partner("P116")
        await self._binding(partner)
        invoice, payment = await self._invoice_payment(paid_at=datetime.utcnow() - timedelta(days=8))
        earn = await ChannelCommissionService(self.db).handle_billing_payment_success(invoice, payment)
        pending_invoice, pending_payment = await self._invoice_payment(paid_at=datetime.utcnow())
        pending = await ChannelCommissionService(self.db).handle_billing_payment_success(pending_invoice, pending_payment)
        settlement = await ChannelSettlementService(self.db).create_manual_settlement(
            partner_id=partner.id,
            operator="super",
            ledger_ids=[earn.id],
            transaction_reference="offline-001",
        )
        self.assertEqual(settlement.amount_cents, earn.commission_amount_cents)
        await self.db.refresh(earn)
        await self.db.refresh(pending)
        self.assertEqual(earn.status, CHANNEL_COMMISSION_STATUS_SETTLED)
        self.assertEqual(pending.status, CHANNEL_COMMISSION_STATUS_PENDING)
        items = (await self.db.execute(select(ChannelCommissionSettlementItem))).scalars().all()
        self.assertEqual(len(items), 1)
        with self.assertRaisesRegex(ValueError, "settled"):
            await ChannelSettlementService(self.db).create_manual_settlement(
                partner_id=partner.id,
                operator="super",
                ledger_ids=[earn.id],
            )
        with self.assertRaisesRegex(ValueError, "AVAILABLE"):
            await ChannelSettlementService(self.db).create_manual_settlement(
                partner_id=partner.id,
                operator="super",
                ledger_ids=[pending.id],
            )

    async def test_partner_earnings_summary_derives_from_ledger_with_lazy_promotion(self):
        partner = await self._partner("P117")
        await self._binding(partner)
        old_invoice, old_payment = await self._invoice_payment(paid_at=datetime.utcnow() - timedelta(days=8))
        new_invoice, new_payment = await self._invoice_payment(paid_at=datetime.utcnow())
        service = ChannelCommissionService(self.db)
        await service.handle_billing_payment_success(old_invoice, old_payment)
        await service.handle_billing_payment_success(new_invoice, new_payment)
        summary = await service.get_partner_earnings_summary(partner.id)
        self.assertEqual(summary["total_earned_cents"], 23960)
        self.assertEqual(summary["available_cents"], 11980)
        self.assertEqual(summary["pending_cents"], 11980)
        self.assertEqual(summary["bound_tenant_count"], 1)
        self.assertEqual(summary["lead_count"], 1)

    def test_super_channel_apis_are_super_only_and_existing_domains_unchanged(self):
        from app.api.v1 import super_channel

        self.assertTrue(any(dep.dependency is _verify_super_token for dep in super_channel.router.dependencies))
        root = Path(__file__).resolve().parents[1]
        commission_source = (root / "app" / "models" / "commission_record.py").read_text(encoding="utf-8-sig")
        channel_entry_source = (root / "app" / "models" / "channel_entry.py").read_text(encoding="utf-8-sig")
        order_payment_source = (root / "app" / "services" / "order_payment_service.py").read_text(encoding="utf-8-sig")
        self.assertIn('__tablename__ = "commission_record"', commission_source)
        self.assertIn('__tablename__ = "channel_entry"', channel_entry_source)
        self.assertIn('out_trade_no=str(order.id)', order_payment_source)


if __name__ == "__main__":
    unittest.main()
