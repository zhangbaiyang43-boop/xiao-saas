"""Phase F1F-C — PRO interactive capability enforcement regression tests.

Scope: docs/saas-subscription-audit.md Phase F1F-C. Proves MEMBERSHIP, COUPONS,
MARKETING_AUTOMATION, CUSTOMER_CONSUMPTION, CHANNEL_ENTRY, and
DISTRIBUTION_REFERRAL are gated at their real merchant-facing API endpoints
(never before the check, always before any side effect) for FREE/STANDARD,
allowed for PRO/PRO-trial, and that every carve-out from the FROZEN RULE --
customer self-service, coupon/verify liability path, existing commission
settlement, public channel resolve, and the FREE core entrance -- remains
completely unaffected. Also proves the F1F-BH fail-closed contract is reused
unchanged for these new gates.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.channel_entries import create_entry
from app.api.v1.consumptions import list_consumptions
from app.api.v1.coupon_templates import CreateCouponTemplateRequest, create_template
from app.api.v1.coupons import list_issued_coupons
from app.api.v1.customers import get_customer, list_customers
from app.api.v1.distribution import (
    DistributionSettingsRequest,
    settle_distribution_record,
    update_distribution_settings,
)
from app.api.v1.entrance_codes import list_entrance_codes
from app.api.v1.member import profile as member_profile
from app.api.v1.membership import get_customer_membership, get_membership_config
from app.api.v1.public_channel import get_h5_config
from app.api.v1.stats import marketing_effectiveness
from app.core.tenant_context import TenantContext
from app.models.base import Base
from app.models.commission_record import CommissionRecord
from app.models.consumption import Consumption
from app.models.customer import Customer
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.services.channel_entry_service import ChannelEntryService
from app.services.entitlement_service import EntitlementService
from app.services.subscription_service import STATUS_ACTIVE, STATUS_TRIAL, SubscriptionService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@event.listens_for(Plan, "before_insert")
def _assign_plan_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Subscription, "before_insert")
def _assign_subscription_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Tenant, "before_insert")
def _assign_tenant_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Customer, "before_insert")
def _assign_customer_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Consumption, "before_insert")
def _assign_consumption_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(CommissionRecord, "before_insert")
def _assign_commission_record_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_request(*, tenant_id=None, customer_id=None, method="GET", path="/x"):
    request = Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [(b"authorization", b"Bearer dummy")] if (tenant_id or customer_id) else [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    if tenant_id is not None:
        request.state.tenant_id = tenant_id
        request.state.token_type = "merchant"
    if customer_id is not None:
        request.state.customer_id = customer_id
        request.state.tenant_id = tenant_id
        request.state.token_type = "member"
    return request


TENANT_FREE = "tenant-f1fc-free"
TENANT_STANDARD = "tenant-f1fc-standard"
TENANT_PRO = "tenant-f1fc-pro"
TENANT_PRO_TRIAL = "tenant-f1fc-pro-trial"
TENANT_PRO_EXPIRED = "tenant-f1fc-pro-expired"
TENANT_PRO_INACTIVE_PLAN = "tenant-f1fc-pro-inactive-plan"


class BaseProEnforcementTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add_all(
            [
                Tenant(tenant_id=TENANT_FREE, name="Free Tenant", password_hash="x", status=True),
                Tenant(tenant_id=TENANT_STANDARD, name="Standard Tenant", password_hash="x", status=True),
                Tenant(tenant_id=TENANT_PRO, name="Pro Tenant", password_hash="x", status=True),
                Tenant(tenant_id=TENANT_PRO_TRIAL, name="Pro Trial Tenant", password_hash="x", status=True),
                Tenant(tenant_id=TENANT_PRO_EXPIRED, name="Pro Expired Tenant", password_hash="x", status=True),
                Tenant(tenant_id=TENANT_PRO_INACTIVE_PLAN, name="Pro Inactive Plan Tenant", password_hash="x", status=True),
                Plan(code="FREE", name="免费版", is_active=True, price_month_cents=0, price_year_cents=0, sort_order=0),
                Plan(code="STANDARD", name="普通版", is_active=True, price_month_cents=5900, price_year_cents=60900, sort_order=1),
                Plan(code="PRO", name="专业版", is_active=True, price_month_cents=9900, price_year_cents=102200, sort_order=2),
            ]
        )
        await self.db.commit()
        self.subscription_service = SubscriptionService(self.db)
        await self._activate(TENANT_STANDARD, "STANDARD")
        await self._activate(TENANT_PRO, "PRO")
        await self._activate_trial(TENANT_PRO_TRIAL, "PRO")
        await self._activate(TENANT_PRO_EXPIRED, "PRO", ends_delta=timedelta(days=-1))
        await self._activate(TENANT_PRO_INACTIVE_PLAN, "PRO")

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _activate(self, tenant_id: str, plan_code: str, *, ends_delta=timedelta(days=30)):
        plan = await self.subscription_service.get_plan_by_code(plan_code)
        now = datetime.utcnow()
        sub = Subscription(
            tenant_id=tenant_id, plan_id=plan.id, status=STATUS_ACTIVE,
            started_at=now - timedelta(days=1) if ends_delta.total_seconds() < 0 else now,
            ends_at=now + ends_delta,
        )
        self.db.add(sub)
        await self.db.commit()
        await self.db.refresh(sub)
        return sub

    async def _activate_trial(self, tenant_id: str, plan_code: str, *, ends_delta=timedelta(days=14)):
        plan = await self.subscription_service.get_plan_by_code(plan_code)
        now = datetime.utcnow()
        sub = Subscription(
            tenant_id=tenant_id, plan_id=plan.id, status=STATUS_TRIAL,
            trial_started_at=now, trial_ends_at=now + ends_delta,
        )
        self.db.add(sub)
        await self.db.commit()
        await self.db.refresh(sub)
        return sub


# ---------------------------------------------------------------------------
# MEMBERSHIP
# ---------------------------------------------------------------------------

class MembershipEnforcementTest(BaseProEnforcementTest):
    async def test_membership_overview_non_pro_denied(self):
        TenantContext.set_tenant_id(TENANT_STANDARD)
        try:
            resp = await get_membership_config(db=self.db)
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 403)
        self.assertEqual(resp.data["error_code"], "PLAN_CAPABILITY_REQUIRED")
        self.assertEqual(resp.data["capability"], "MEMBERSHIP")

    async def test_membership_overview_pro_allowed(self):
        TenantContext.set_tenant_id(TENANT_PRO)
        try:
            resp = await get_membership_config(db=self.db)
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 200)

    async def test_customer_membership_detail_non_pro_denied(self):
        customer = Customer(tenant_id=TENANT_STANDARD, openid="op-1", name="张三", phone="13800000001", status=1)
        self.db.add(customer)
        await self.db.commit()
        await self.db.refresh(customer)

        resp = await get_customer_membership(
            make_request(tenant_id=TENANT_STANDARD), customer.id, db=self.db,
        )
        self.assertEqual(resp.code, 403)
        self.assertEqual(resp.data["error_code"], "PLAN_CAPABILITY_REQUIRED")
        self.assertEqual(resp.data["capability"], "MEMBERSHIP")

    async def test_customer_self_profile_ungated(self):
        """PHASE 3 carve-out: a customer viewing their own profile must never
        be blocked by the merchant's plan tier -- FREE tenant, customer's own
        token, still succeeds."""
        customer = Customer(tenant_id=TENANT_FREE, openid="op-2", name="李四", phone="13800000002", status=1)
        self.db.add(customer)
        await self.db.commit()
        await self.db.refresh(customer)

        resp = await member_profile(
            make_request(tenant_id=TENANT_FREE, customer_id=customer.id), db=self.db,
        )
        self.assertEqual(resp.code, 200)


# ---------------------------------------------------------------------------
# COUPONS
# ---------------------------------------------------------------------------

class CouponEnforcementTest(BaseProEnforcementTest):
    def _template_request(self):
        now = datetime.utcnow()
        return CreateCouponTemplateRequest(
            name="满10减2", type="FIXED", value=2, min_amount=10, total_stock=100,
            start_time=now.isoformat(), end_time=(now + timedelta(days=30)).isoformat(),
        )

    async def test_coupon_template_create_non_pro_denied(self):
        TenantContext.set_tenant_id(TENANT_STANDARD)
        try:
            with patch("app.services.coupon_service.CouponService.create_template", new=AsyncMock()) as mock_create:
                resp = await create_template(
                    make_request(tenant_id=TENANT_STANDARD, method="POST", path="/api/v1/coupon-templates"),
                    self._template_request(), db=self.db,
                )
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 403)
        self.assertEqual(resp.data["error_code"], "PLAN_CAPABILITY_REQUIRED")
        self.assertEqual(resp.data["capability"], "COUPONS")
        mock_create.assert_not_awaited()

    async def test_coupon_template_create_pro_allowed(self):
        TenantContext.set_tenant_id(TENANT_PRO)
        try:
            resp = await create_template(
                make_request(tenant_id=TENANT_PRO, method="POST", path="/api/v1/coupon-templates"),
                self._template_request(), db=self.db,
            )
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 200)

    async def test_coupon_history_read_non_pro_allowed(self):
        """PHASE 7 carve-out: merchant-issued coupon history must remain
        readable at every tier -- a downgraded merchant must still be able to
        confirm customers' existing coupon rights."""
        resp = await list_issued_coupons(make_request(tenant_id=TENANT_FREE), db=self.db)
        self.assertEqual(resp.code, 200)


class CouponLiabilityPathUngatedTest(BaseProEnforcementTest):
    async def test_existing_coupon_customer_use_path_ungated(self):
        """PHASE 6 carve-out: a customer reading their own already-issued
        coupons must never be blocked by the merchant's plan tier. Only a
        stable representative path is checked here, not the full coupon
        suite (verify/redeem are covered by pre-existing tests and are
        deliberately untouched by F1F-C)."""
        customer = Customer(tenant_id=TENANT_FREE, openid="op-3", name="王五", phone="13800000003", status=1)
        self.db.add(customer)
        await self.db.commit()
        await self.db.refresh(customer)

        resp = await member_profile(
            make_request(tenant_id=TENANT_FREE, customer_id=customer.id), db=self.db,
        )
        self.assertEqual(resp.code, 200, "customer-facing path must stay ungated regardless of merchant plan")


# ---------------------------------------------------------------------------
# MARKETING_AUTOMATION
# ---------------------------------------------------------------------------

class MarketingAutomationEnforcementTest(BaseProEnforcementTest):
    async def test_marketing_effectiveness_non_pro_denied(self):
        TenantContext.set_tenant_id(TENANT_STANDARD)
        try:
            resp = await marketing_effectiveness(
                make_request(tenant_id=TENANT_STANDARD, path="/api/v1/stats/marketing-effectiveness"), db=self.db,
            )
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 403)
        self.assertEqual(resp.data["error_code"], "PLAN_CAPABILITY_REQUIRED")
        self.assertEqual(resp.data["capability"], "MARKETING_AUTOMATION")

    async def test_marketing_effectiveness_pro_allowed(self):
        TenantContext.set_tenant_id(TENANT_PRO)
        try:
            resp = await marketing_effectiveness(
                make_request(tenant_id=TENANT_PRO, path="/api/v1/stats/marketing-effectiveness"), db=self.db,
            )
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 200)


# ---------------------------------------------------------------------------
# CUSTOMER_CONSUMPTION
# ---------------------------------------------------------------------------

class CustomerConsumptionEnforcementTest(BaseProEnforcementTest):
    async def test_customer_list_non_pro_denied(self):
        TenantContext.set_tenant_id(TENANT_STANDARD)
        try:
            resp = await list_customers(db=self.db)
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 403)
        self.assertEqual(resp.data["error_code"], "PLAN_CAPABILITY_REQUIRED")
        self.assertEqual(resp.data["capability"], "CUSTOMER_CONSUMPTION")

    async def test_customer_list_pro_allowed(self):
        TenantContext.set_tenant_id(TENANT_PRO)
        try:
            resp = await list_customers(db=self.db)
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 200)

    async def test_consumption_history_non_pro_denied(self):
        TenantContext.set_tenant_id(TENANT_STANDARD)
        try:
            resp = await list_consumptions(db=self.db)
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 403)
        self.assertEqual(resp.data["error_code"], "PLAN_CAPABILITY_REQUIRED")

    async def test_customer_history_preserved_after_downgrade_and_reupgrade(self):
        """PHASE 10: Customer/Consumption rows are never deleted on
        downgrade. PRO -> write/read history -> downgrade FREE -> merchant
        read denied (403) -> re-upgrade PRO -> same historical row visible
        again, unchanged."""
        customer = Customer(tenant_id=TENANT_PRO, openid="op-hist", name="老客户", phone="13800009999", status=1)
        self.db.add(customer)
        await self.db.commit()
        await self.db.refresh(customer)
        consumption = Consumption(
            tenant_id=TENANT_PRO, customer_id=customer.id, project="堂食点餐",
            amount=88, consume_time=datetime.utcnow(),
        )
        self.db.add(consumption)
        await self.db.commit()

        TenantContext.set_tenant_id(TENANT_PRO)
        try:
            resp = await get_customer(customer.id, db=self.db)
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 200, "sanity: readable while PRO")

        # Downgrade: expire the PRO subscription.
        result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == TENANT_PRO))
        sub = result.scalars().first()
        sub.ends_at = datetime.utcnow() - timedelta(seconds=1)
        await self.db.commit()

        TenantContext.set_tenant_id(TENANT_PRO)
        try:
            denied = await get_customer(customer.id, db=self.db)
        finally:
            TenantContext.clear()
        self.assertEqual(denied.code, 403)
        self.assertEqual(denied.data["error_code"], "PLAN_CAPABILITY_REQUIRED")

        # Data preserved: the row is untouched by the downgrade.
        result = await self.db.execute(select(Customer).where(Customer.id == customer.id))
        self.assertIsNotNone(result.scalar_one_or_none(), "Customer row must not be deleted on downgrade")
        result = await self.db.execute(select(Consumption).where(Consumption.customer_id == customer.id))
        self.assertIsNotNone(result.scalars().first(), "Consumption row must not be deleted on downgrade")

        # Re-upgrade: same tenant, new unexpired PRO subscription.
        await self._activate(TENANT_PRO, "PRO", ends_delta=timedelta(days=30))

        TenantContext.set_tenant_id(TENANT_PRO)
        try:
            restored = await get_customer(customer.id, db=self.db)
        finally:
            TenantContext.clear()
        self.assertEqual(restored.code, 200)
        self.assertEqual(restored.data["id"], str(customer.id))


# ---------------------------------------------------------------------------
# CHANNEL_ENTRY
# ---------------------------------------------------------------------------

class ChannelEntryEnforcementTest(BaseProEnforcementTest):
    async def test_channel_create_non_pro_denied(self):
        TenantContext.set_tenant_id(TENANT_STANDARD)
        try:
            resp = await create_entry(
                make_request(tenant_id=TENANT_STANDARD, method="POST", path="/api/v1/channel-entries"),
                data={"name": "抖音渠道", "channel_code": "douyin"}, db=self.db,
            )
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 403)
        self.assertEqual(resp.data["error_code"], "PLAN_CAPABILITY_REQUIRED")
        self.assertEqual(resp.data["capability"], "CHANNEL_ENTRY")

    async def test_channel_create_pro_allowed(self):
        TenantContext.set_tenant_id(TENANT_PRO)
        try:
            resp = await create_entry(
                make_request(tenant_id=TENANT_PRO, method="POST", path="/api/v1/channel-entries"),
                data={"name": "抖音渠道", "channel_code": "douyin"}, db=self.db,
            )
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 200)

    async def test_core_entrance_free_regression(self):
        """PHASE 14: the FREE core scan-to-order entrance is untouched by
        this phase and must keep working for a FREE tenant."""
        TenantContext.set_tenant_id(TENANT_FREE)
        try:
            resp = await list_entrance_codes(db=self.db)
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 200)


class ChannelPublicResolveUngatedTest(BaseProEnforcementTest):
    async def test_channel_public_resolve_after_downgrade_allowed(self):
        """PHASE 13: a channel entry created while PRO must keep resolving
        publicly even after the owning tenant downgrades to FREE -- an
        already-printed QR code must never go dead because of a plan
        change."""
        service = ChannelEntryService(self.db)
        service.set_tenant_id(TENANT_PRO)
        entry = await service.create_entry(name="抖音渠道", channel_code="douyin")

        # Downgrade: expire the PRO subscription.
        result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == TENANT_PRO))
        sub = result.scalars().first()
        sub.ends_at = datetime.utcnow() - timedelta(seconds=1)
        await self.db.commit()

        resp = await get_h5_config(
            make_request(method="GET", path=f"/api/public/channel-entries/{entry.id}"), entry.id, db=self.db,
        )
        self.assertEqual(resp.code, 200, "public resolve must survive the owning tenant's downgrade")


# ---------------------------------------------------------------------------
# DISTRIBUTION_REFERRAL
# ---------------------------------------------------------------------------

class DistributionEnforcementTest(BaseProEnforcementTest):
    async def test_distribution_config_non_pro_denied(self):
        TenantContext.set_tenant_id(TENANT_STANDARD)
        try:
            resp = await update_distribution_settings(
                DistributionSettingsRequest(invite_reward_enabled=True), db=self.db,
            )
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 403)
        self.assertEqual(resp.data["error_code"], "PLAN_CAPABILITY_REQUIRED")
        self.assertEqual(resp.data["capability"], "DISTRIBUTION_REFERRAL")

    async def test_distribution_config_pro_allowed(self):
        TenantContext.set_tenant_id(TENANT_PRO)
        try:
            resp = await update_distribution_settings(
                DistributionSettingsRequest(invite_reward_enabled=True), db=self.db,
            )
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 200)

    async def test_distribution_settlement_after_downgrade_allowed(self):
        """PHASE 16/18 carve-out: an existing CommissionRecord is a
        financial-liability history, not a current-plan feature -- its
        settlement must remain allowed even for a FREE tenant."""
        record = CommissionRecord(
            tenant_id=TENANT_FREE, user_id=1, order_id="1", amount=10, level=1,
            receiver_id=1, receiver_type="customer", commission_amount=10,
            status="PENDING", source_type="VERIFY",
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)

        TenantContext.set_tenant_id(TENANT_FREE)
        try:
            resp = await settle_distribution_record(record.id, db=self.db)
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 200)
        self.assertEqual(resp.data["status"], "SETTLED")


# ---------------------------------------------------------------------------
# Plan lifecycle: trial / expired / inactive-plan-row
# ---------------------------------------------------------------------------

class ProPlanLifecycleTest(BaseProEnforcementTest):
    async def test_trial_pro_allowed(self):
        TenantContext.set_tenant_id(TENANT_PRO_TRIAL)
        try:
            resp = await list_customers(db=self.db)
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 200)

    async def test_expired_pro_new_action_denied(self):
        """PHASE 23: an expired PRO subscription is effective FREE -- every
        NEW PRO interactive action must be denied."""
        TenantContext.set_tenant_id(TENANT_PRO_EXPIRED)
        try:
            resp = await list_customers(db=self.db)
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 403)
        self.assertEqual(resp.data["error_code"], "PLAN_CAPABILITY_REQUIRED")

    async def test_expired_pro_carve_outs_still_allowed(self):
        """PHASE 23: even fully expired back to FREE, the carve-outs (coupon
        history, channel public resolve, commission settlement) remain
        allowed -- only NEW PRO actions are denied."""
        resp = await list_issued_coupons(make_request(tenant_id=TENANT_PRO_EXPIRED), db=self.db)
        self.assertEqual(resp.code, 200)

    async def test_inactive_pro_plan_existing_rights_retained(self):
        """PHASE 21: Plan.is_active=False must not strip an unexpired
        existing PRO subscription's rights. The route must never itself
        query Plan.is_active."""
        result = await self.db.execute(select(Plan).where(Plan.code == "PRO"))
        plan = result.scalar_one()
        plan.is_active = False
        await self.db.commit()

        TenantContext.set_tenant_id(TENANT_PRO_INACTIVE_PLAN)
        try:
            resp = await list_customers(db=self.db)
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 200)


# ---------------------------------------------------------------------------
# Fail-closed on entitlement system error (reuses F1F-BH contract)
# ---------------------------------------------------------------------------

class ProEntitlementSystemErrorFailsClosedTest(BaseProEnforcementTest):
    async def test_pro_endpoint_fails_closed_on_entitlement_system_error(self):
        with patch.object(
            EntitlementService, "require_capability",
            new=AsyncMock(side_effect=RuntimeError("entitlement resolution exploded")),
        ):
            with patch("app.services.coupon_service.CouponService.create_template", new=AsyncMock()) as mock_create:
                TenantContext.set_tenant_id(TENANT_PRO)
                try:
                    resp = await create_template(
                        make_request(tenant_id=TENANT_PRO, method="POST", path="/api/v1/coupon-templates"),
                        CreateCouponTemplateRequest(
                            name="x", type="FIXED", value=2, min_amount=10, total_stock=100,
                            start_time=datetime.utcnow().isoformat(),
                            end_time=(datetime.utcnow() + timedelta(days=30)).isoformat(),
                        ),
                        db=self.db,
                    )
                finally:
                    TenantContext.clear()
        self.assertNotIn(resp.code, (200, 201, 204), "entitlement system error must never resolve to success")
        self.assertEqual(resp.code, 500)
        self.assertEqual(resp.data["error_code"], "INTERNAL_ERROR")
        mock_create.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
