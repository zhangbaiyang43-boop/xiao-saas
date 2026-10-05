"""Synthetic fixtures for the Phase 03R Super Admin certification runtime.

Runs inside the backend image (so it uses the pinned candidate code and models) against the
disposable MySQL of the `xiao-super-admin-cert` Compose project, once, after `alembic upgrade
head`. Idempotent: re-running changes nothing that already exists.

Safety: refuses to run unless it is talking to that exact database. Every value is synthetic.
The fake merchant numbers below are placeholders that only drive the *displayed* payment state
(the super console derives it from wx_mchid / wx_pay_enabled / receiver_verified); no real
WeChat key, certificate or merchant number is created, and the runtime has no outbound
WeChat/SMS/printer configuration at all.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta

EXPECTED_DB_URL_PART = "@mysql:3306/xiao_super_admin_cert"
ACK_VALUE = "SUPER_ADMIN_CERT_V1"

# Synthetic, clearly fake identities (no real phone numbers).
MERCHANTS = {
    "cert-merchant-a": dict(name="认证商户A（正常）", phone="13800000001"),
    "cert-merchant-b": dict(name="认证商户B（已停用·免费版）", phone="13800000002"),
    "cert-merchant-c": dict(name="认证商户C（待验证·试用）", phone="13800000003"),
}


def _guard() -> None:
    from app.config import settings

    problems = []
    if os.environ.get("CERT_SEED_ACK") != ACK_VALUE:
        problems.append("CERT_SEED_ACK missing")
    if settings.APP_ENV != "staging":
        problems.append("APP_ENV is not staging")
    if EXPECTED_DB_URL_PART not in os.environ.get("DATABASE_URL", ""):
        problems.append("DATABASE_URL is not the disposable certification database")
    if problems:
        print("SEED_REFUSED:", "; ".join(problems))
        sys.exit(2)


async def _plan(db, code):
    from sqlalchemy import select

    from app.models.subscription import Plan

    plan = (await db.execute(select(Plan).where(Plan.code == code))).scalar_one_or_none()
    if plan is None:
        raise RuntimeError(f"plan {code} missing: migrations did not seed the catalog")
    return plan


async def _ensure_tenant(db, tenant_id, **fields):
    from sqlalchemy import select

    from app.models.tenant import Tenant

    tenant = (await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))).scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(tenant_id=tenant_id, password_hash="!cert-fixture-no-login", **fields)
        db.add(tenant)
        await db.flush()
    return tenant


async def _ensure_subscription(db, tenant_id, plan, *, status, **dates):
    from sqlalchemy import select

    from app.models.subscription import Subscription

    existing = (await db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))).first()
    if existing is None:
        db.add(Subscription(tenant_id=tenant_id, plan_id=plan.id, status=status, **dates))


async def _ensure_orders(db, tenant_id, specs):
    from sqlalchemy import func, select

    from app.models.order import Order

    have = (await db.execute(select(func.count(Order.id)).where(Order.tenant_id == tenant_id))).scalar() or 0
    if have:
        return
    for table_no, total, status, paid in specs:
        db.add(Order(
            tenant_id=tenant_id, table_no=table_no, total=total, status=status,
            payment_status="paid" if paid else "unpaid", payment_mode="prepay",
            payment_method="mock" if paid else None, source="h5",
        ))


async def _seed() -> None:
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models.billing import BillingInvoice, BillingPayment
    from app.models.channel_revenue import ChannelPartner, ChannelPartnerTenantBinding

    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        pro = await _plan(db, "PRO")
        standard = await _plan(db, "STANDARD")

        # A: enabled, payment verified (display state only), active PRO, bound channel, orders today.
        a = await _ensure_tenant(
            db, "cert-merchant-a", name=MERCHANTS["cert-merchant-a"]["name"],
            phone=MERCHANTS["cert-merchant-a"]["phone"], status=True, is_open=True,
            wx_mchid="1900000001", wx_pay_enabled=True, receiver_verified=True, payment_locked=True,
            receiver_name="认证商户A", receiver_type="enterprise", verified_time=now,
        )
        await _ensure_subscription(
            db, a.tenant_id, pro, status="ACTIVE",
            started_at=now - timedelta(days=10), ends_at=now + timedelta(days=20),
        )
        await _ensure_orders(db, a.tenant_id, [("A1", 36, "pending", True), ("A2", 58, "done", True), ("A3", 22, "preparing", True)])

        # B: account disabled, payment unconfigured, free plan (expired trial), no channel.
        b = await _ensure_tenant(
            db, "cert-merchant-b", name=MERCHANTS["cert-merchant-b"]["name"],
            phone=MERCHANTS["cert-merchant-b"]["phone"], status=False, is_open=True,
        )
        await _ensure_subscription(
            db, b.tenant_id, pro, status="TRIAL",
            trial_started_at=now - timedelta(days=60), trial_ends_at=now - timedelta(days=30),
        )

        # C: payment pending verification, trial plan, one manual payment waiting for confirmation.
        c = await _ensure_tenant(
            db, "cert-merchant-c", name=MERCHANTS["cert-merchant-c"]["name"],
            phone=MERCHANTS["cert-merchant-c"]["phone"], status=True, is_open=True,
            wx_mchid="1900000003", wx_pay_enabled=True, receiver_verified=False, payment_locked=False,
        )
        await _ensure_subscription(
            db, c.tenant_id, pro, status="TRIAL",
            trial_started_at=now - timedelta(days=3), trial_ends_at=now + timedelta(days=11),
        )
        await db.flush()

        # Channel: one partner, one active binding to A.
        partner = (await db.execute(select(ChannelPartner).where(ChannelPartner.partner_code == "CERT-P1"))).scalar_one_or_none()
        if partner is None:
            partner = ChannelPartner(
                partner_code="CERT-P1", name="认证渠道伙伴", mobile="13900000001",
                mobile_normalized="13900000001", partner_type="OTHER", status="ACTIVE",
            )
            db.add(partner)
            await db.flush()
        bound = (await db.execute(select(ChannelPartnerTenantBinding).where(ChannelPartnerTenantBinding.tenant_id == a.tenant_id))).scalar_one_or_none()
        if bound is None:
            db.add(ChannelPartnerTenantBinding(
                tenant_id=a.tenant_id, partner_id=partner.id, status="ACTIVE",
                commission_rate_bps=1000, commission_term_months=12,
                commission_started_at=now - timedelta(days=10), commission_ends_at=now + timedelta(days=355),
            ))

        # Billing: history for A (paid) and one WAITING_CONFIRMATION manual payment for C.
        async def invoice(invoice_no, tenant_id, plan_code, status, paid_at=None):
            row = (await db.execute(select(BillingInvoice).where(BillingInvoice.invoice_no == invoice_no))).scalar_one_or_none()
            if row is None:
                row = BillingInvoice(
                    invoice_no=invoice_no, tenant_id=tenant_id, charge_type="SAAS_SUBSCRIPTION",
                    description="认证数据：订阅付款", amount_cents=5900, plan_code=plan_code,
                    billing_period="MONTH", status=status, paid_at=paid_at,
                )
                db.add(row)
                await db.flush()
            return row

        inv_a = await invoice("CERT-INV-0001", a.tenant_id, "PRO", "PAID", paid_at=now - timedelta(days=10))
        inv_c = await invoice("CERT-INV-0002", c.tenant_id, "STANDARD", "PENDING")
        for payment_no, out_trade_no, inv, status, review, claimed in (
            ("CERT-PAY-0001", "CERT-OUT-0001", inv_a, "PAID", None, None),
            ("CERT-PAY-0002", "CERT-OUT-0002", inv_c, "PENDING", "WAITING_CONFIRMATION", now - timedelta(hours=2)),
        ):
            exists = (await db.execute(select(BillingPayment).where(BillingPayment.payment_no == payment_no))).scalar_one_or_none()
            if exists is None:
                db.add(BillingPayment(
                    invoice_id=inv.id, tenant_id=inv.tenant_id, payment_no=payment_no, out_trade_no=out_trade_no,
                    provider="MANUAL", amount_cents=5900, status=status,
                    paid_at=(now - timedelta(days=10)) if status == "PAID" else None,
                    manual_review_status=review, manual_claimed_at=claimed,
                ))
        await db.commit()
    _ = standard  # kept so a missing STANDARD plan fails loudly above


async def _summary() -> None:
    from sqlalchemy import func, select

    from app.core.database import AsyncSessionLocal
    from app.models.billing import BillingPayment
    from app.models.channel_revenue import ChannelPartnerTenantBinding
    from app.models.order import Order
    from app.models.subscription import Subscription
    from app.models.tenant import Tenant

    async with AsyncSessionLocal() as db:
        async def count(model, *where):
            return (await db.execute(select(func.count()).select_from(model).where(*where))).scalar() or 0

        ids = list(MERCHANTS)
        print("SEED_DONE")
        print("MERCHANT_FIXTURE_COUNT=%d" % await count(Tenant, Tenant.tenant_id.in_(ids)))
        print("HAS_ENABLED_MERCHANT=%s" % (await count(Tenant, Tenant.tenant_id.in_(ids), Tenant.status.is_(True)) > 0))
        print("HAS_DISABLED_MERCHANT=%s" % (await count(Tenant, Tenant.tenant_id.in_(ids), Tenant.status.is_(False)) > 0))
        print("HAS_UNCONFIGURED_PAYMENT=%s" % (await count(Tenant, Tenant.tenant_id.in_(ids), Tenant.wx_mchid.is_(None)) > 0))
        print("HAS_PENDING_PAYMENT=%s" % (await count(Tenant, Tenant.tenant_id.in_(ids), Tenant.wx_mchid.is_not(None), Tenant.receiver_verified.is_(False)) > 0))
        print("HAS_ACTIVE_SUBSCRIPTION=%s" % (await count(Subscription, Subscription.status == "ACTIVE") > 0))
        print("HAS_FREE_SUBSCRIPTION=%s" % (await count(Subscription, Subscription.tenant_id == "cert-merchant-b") > 0))
        print("HAS_CHANNEL_BINDING=%s" % (await count(ChannelPartnerTenantBinding) > 0))
        print("HAS_WAITING_CONFIRMATION_BILLING=%s" % (await count(BillingPayment, BillingPayment.manual_review_status == "WAITING_CONFIRMATION") > 0))
        print("ORDERS_FOR_MERCHANT_A=%d" % await count(Order, Order.tenant_id == "cert-merchant-a"))


def main() -> None:
    _guard()
    asyncio.run(_seed())
    asyncio.run(_summary())


if __name__ == "__main__":
    main()
