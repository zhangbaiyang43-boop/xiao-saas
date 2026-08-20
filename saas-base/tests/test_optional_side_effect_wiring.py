"""Phase F1F-D1A — transaction-adjacent optional side-effect wiring tests.

Scope: docs/saas-subscription-audit.md Phase F1F-D1A. Proves that wiring
optional_capability_enabled() into the payment/registration/verify paths
never puts the core transaction at risk:

- non-PRO tenants skip the optional side effect and the core transaction
  (payment success, registration, verification) still completes exactly
  as before;
- PRO tenants keep the exact pre-D1A behavior, called at most once;
- the liability/reversal paths this phase is forbidden from touching
  (reverse_consumption, coupon redeem/verify/unlock/rollback, commission
  settlement) are provably unaffected;
- an entitlement-resolution exception, simulated all the way down at
  EntitlementService, never surfaces to the business caller -- it only
  ever sees a boolean, and the core transaction still succeeds;
- tenant isolation: one tenant's plan never leaks into another's side
  effects in the same test run.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.miniapp import entry_join, invite_bind
from app.api.v1.public_channel import get_h5_config, record_visit
from app.config import settings
from app.models.base import Base
from app.models.channel_entry import ChannelEntry
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.models.member_account import MemberAccount
from app.models.merchant_account import MerchantAccount
from app.models.order import Order
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.schemas.miniapp import EntryJoinRequest
from app.services.channel_entry_service import ChannelEntryService
from app.services.commission_service import CommissionService
from app.services.coupon_service import CouponService
from app.services.customer_identity_service import CHANNEL_MINIAPP, CustomerIdentityService
from app.services.customer_service import CustomerService
from app.services.entitlement_service import EntitlementService
from app.services.membership_service import MembershipService
from app.services.order_payment_service import OrderPaymentService
from app.services.subscription_service import STATUS_ACTIVE, SubscriptionService
from app.services.verify_service import VerifyService
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


@event.listens_for(Order, "before_insert")
def _assign_order_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(CouponTemplate, "before_insert")
def _assign_template_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Coupon, "before_insert")
def _assign_coupon_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(ChannelEntry, "before_insert")
def _assign_entry_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(MerchantAccount, "before_insert")
def _assign_account_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


raw_entry_join = entry_join.__wrapped__
raw_invite_bind = invite_bind


def make_request(*, tenant_id=None, customer_id=None, method="GET", path="/x", body=None):
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
    if tenant_id is not None:
        request.state.tenant_id = tenant_id
    if customer_id is not None:
        request.state.customer_id = customer_id
    if body is not None:
        import json as _json

        async def _body():
            return _json.dumps(body).encode()

        request.body = _body
    return request


TENANT_FREE = "tenant-d1fa-free"
TENANT_STANDARD = "tenant-d1fa-standard"
TENANT_PRO = "tenant-d1fa-pro"
TENANT_PRO_B = "tenant-d1fa-pro-b"


class BaseWiringTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # A real file-backed SQLite DB, not :memory:. optional_capability_enabled()
        # deliberately opens its own AsyncSessionLocal() session mid-transaction on
        # the caller's session (that's the whole point -- see app/services/
        # optional_entitlement.py). With :memory:, nested sessions sharing (or
        # racing over) the same in-process connection can spuriously roll back the
        # outer session's already-flushed-but-uncommitted writes when the nested
        # session closes -- a SQLite/aiosqlite test-only artifact verified via a
        # standalone repro to disappear entirely on a real file-backed DB (i.e. on
        # any real multi-connection production database, each session already has
        # its own independent connection/transaction with no such interference).
        self._db_file = f"{tempfile.gettempdir()}/f1fd1a_{uuid.uuid4().hex}.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_file}")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add_all(
            [
                Tenant(tenant_id=TENANT_FREE, name="Free Tenant", password_hash="x", status=True),
                Tenant(tenant_id=TENANT_STANDARD, name="Standard Tenant", password_hash="x", status=True),
                Tenant(tenant_id=TENANT_PRO, name="Pro Tenant", password_hash="x", status=True),
                Tenant(tenant_id=TENANT_PRO_B, name="Pro Tenant B", password_hash="x", status=True),
                Plan(code="FREE", name="免费版", is_active=True, price_month_cents=0, price_year_cents=0, sort_order=0),
                Plan(code="STANDARD", name="普通版", is_active=True, price_month_cents=5900, price_year_cents=60900, sort_order=1),
                Plan(code="PRO", name="专业版", is_active=True, price_month_cents=9900, price_year_cents=102200, sort_order=2),
            ]
        )
        await self.db.commit()
        self.subscription_service = SubscriptionService(self.db)
        await self._activate(TENANT_STANDARD, "STANDARD")
        await self._activate(TENANT_PRO, "PRO")
        await self._activate(TENANT_PRO_B, "PRO")

        # Established pattern: point the real AsyncSessionLocal factory at this
        # test's own in-memory engine so optional_capability_enabled's
        # independently opened session sees the same seeded rows.
        self._session_patch = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._session_patch.start()

        # No real Redis server in this test environment -- coupon issuance's
        # distributed dedup lock falls back to a DB-only guard when disabled.
        self._original_redis_enabled = settings.REDIS_ENABLED
        settings.REDIS_ENABLED = False

    async def asyncTearDown(self):
        settings.REDIS_ENABLED = self._original_redis_enabled
        self._session_patch.stop()
        await self.db.close()
        await self.engine.dispose()
        try:
            os.remove(self._db_file)
        except OSError:
            pass

    async def _activate(self, tenant_id: str, plan_code: str, *, ends_delta=timedelta(days=30)):
        plan = await self.subscription_service.get_plan_by_code(plan_code)
        now = datetime.utcnow()
        sub = Subscription(
            tenant_id=tenant_id, plan_id=plan.id, status=STATUS_ACTIVE,
            started_at=now, ends_at=now + ends_delta,
        )
        self.db.add(sub)
        await self.db.commit()
        await self.db.refresh(sub)
        return sub

    async def _seed_customer(self, tenant_id: str, *, openid="op-1", phone="13800000001") -> Customer:
        customer = Customer(tenant_id=tenant_id, openid=openid, name="顾客", phone=phone, status=1)
        self.db.add(customer)
        await self.db.commit()
        await self.db.refresh(customer)
        return customer

    async def _seed_paid_order(self, tenant_id: str, customer_id: int, *, coupon_id=None) -> Order:
        order = Order(
            tenant_id=tenant_id, customer_id=customer_id, table_no="A1", total="50.00",
            status="pending_payment", payment_status="unpaid", payment_mode="prepay",
            coupon_id=coupon_id,
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order


# ---------------------------------------------------------------------------
# PHASE 4/5/6 -- MEMBERSHIP new accrual at payment success
# ---------------------------------------------------------------------------

class MembershipAccrualPaymentSafetyTest(BaseWiringTest):
    async def test_non_pro_payment_membership_disabled_succeeds(self):
        customer = await self._seed_customer(TENANT_FREE)
        order = await self._seed_paid_order(TENANT_FREE, customer.id)

        with patch.object(MembershipService, "apply_consumption", new=AsyncMock()) as mock_apply:
            coupon_data, _ = await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")

        mock_apply.assert_not_awaited()
        await self.db.commit()
        await self.db.refresh(order)
        self.assertEqual(order.payment_status, "paid")

    async def test_pro_payment_membership_still_applies_once(self):
        customer = await self._seed_customer(TENANT_PRO)
        order = await self._seed_paid_order(TENANT_PRO, customer.id)

        with patch.object(MembershipService, "apply_consumption", new=AsyncMock(return_value=None)) as mock_apply:
            await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")

        mock_apply.assert_awaited_once()
        await self.db.commit()
        await self.db.refresh(order)
        self.assertEqual(order.payment_status, "paid")

    async def test_pro_payment_real_membership_accrual_applies_once_no_duplicate(self):
        """Un-mocked proof: exactly one MemberAccount/points accrual per paid order."""
        customer = await self._seed_customer(TENANT_PRO)
        order = await self._seed_paid_order(TENANT_PRO, customer.id)

        await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")

        result = await self.db.execute(
            select(MemberAccount).where(
                MemberAccount.tenant_id == TENANT_PRO, MemberAccount.customer_id == customer.id
            )
        )
        accounts = result.scalars().all()
        self.assertEqual(len(accounts), 1, "exactly one MemberAccount row, no duplication")
        self.assertGreater(accounts[0].points_balance, 0)

    async def test_offline_settlement_non_pro_membership_skipped(self):
        customer = await self._seed_customer(TENANT_STANDARD)
        order = await self._seed_paid_order(TENANT_STANDARD, customer.id)
        order.payment_mode = "table_account"
        order.payment_status = "paid"
        await self.db.commit()

        with patch.object(MembershipService, "apply_consumption", new=AsyncMock()) as mock_apply:
            await OrderPaymentService(self.db)._apply_paid_order_member_assets_once(order)

        mock_apply.assert_not_awaited()

    async def test_offline_settlement_pro_membership_still_applies(self):
        customer = await self._seed_customer(TENANT_PRO)
        order = await self._seed_paid_order(TENANT_PRO, customer.id)
        order.payment_mode = "table_account"
        order.payment_status = "paid"
        await self.db.commit()

        with patch.object(MembershipService, "apply_consumption", new=AsyncMock(return_value=None)) as mock_apply:
            await OrderPaymentService(self.db)._apply_paid_order_member_assets_once(order)

        mock_apply.assert_awaited_once()

    async def test_membership_reversal_never_gated_still_runs_after_downgrade(self):
        """PHASE 6: a PRO tenant already accrued membership assets; downgrade
        to FREE; a real refund must still reverse the historical accrual --
        reverse_consumption is never entitlement-gated."""
        customer = await self._seed_customer(TENANT_PRO)
        order = await self._seed_paid_order(TENANT_PRO, customer.id)
        await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")
        await self.db.commit()

        result = await self.db.execute(
            select(MemberAccount).where(
                MemberAccount.tenant_id == TENANT_PRO, MemberAccount.customer_id == customer.id
            )
        )
        account = result.scalar_one()
        points_before_refund = account.points_balance
        self.assertGreater(points_before_refund, 0, "sanity: accrual happened while PRO")

        # Downgrade to FREE.
        sub_result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == TENANT_PRO))
        sub = sub_result.scalars().first()
        sub.ends_at = datetime.utcnow() - timedelta(seconds=1)
        await self.db.commit()

        with patch.object(MembershipService, "reverse_consumption", side_effect=MembershipService.reverse_consumption, autospec=True) as spy:
            await OrderPaymentService(self.db)._refund_order_payment(order, reason="test refund")
        spy.assert_awaited_once()

        await self.db.commit()
        await self.db.refresh(account)
        self.assertLess(account.points_balance, points_before_refund, "historical accrual must be reversed even after downgrade")


# ---------------------------------------------------------------------------
# PHASE 7/8/9 -- COUPONS new auto-issuance + existing liability untouched
# ---------------------------------------------------------------------------

class AutoCouponPaymentSafetyTest(BaseWiringTest):
    async def test_non_pro_auto_coupon_skipped_core_flow_succeeds(self):
        customer = await self._seed_customer(TENANT_STANDARD)
        order = await self._seed_paid_order(TENANT_STANDARD, customer.id)

        with patch.object(
            CouponService, "issue_auto_coupon",
            new=AsyncMock(side_effect=AssertionError("must not be called for non-PRO")),
        ):
            await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")

        await self.db.commit()
        await self.db.refresh(order)
        self.assertEqual(order.payment_status, "paid", "core payment flow must succeed regardless")

    async def test_pro_auto_coupon_still_called(self):
        customer = await self._seed_customer(TENANT_PRO)
        order = await self._seed_paid_order(TENANT_PRO, customer.id)

        with patch.object(
            CouponService, "issue_auto_coupon",
            new=AsyncMock(return_value={"success_count": 0, "reason": "rule disabled"}),
        ) as mock_issue:
            await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")

        mock_issue.assert_awaited_once()

    async def test_offline_settlement_non_pro_auto_coupon_skipped(self):
        customer = await self._seed_customer(TENANT_FREE)
        order = await self._seed_paid_order(TENANT_FREE, customer.id)
        order.payment_mode = "postpay"
        order.payment_status = "paid"
        await self.db.commit()

        with patch.object(
            CouponService, "issue_auto_coupon",
            new=AsyncMock(side_effect=AssertionError("must not be called for non-PRO")),
        ):
            await OrderPaymentService(self.db)._apply_paid_order_member_assets_once(order)

    async def test_existing_coupon_liability_after_downgrade_still_works(self):
        """PHASE 9: an already-issued coupon must remain lockable/redeemable
        via the payment coupon write-off path even after the tenant
        downgrades to FREE -- coupon lock/redeem is never entitlement-gated."""
        customer = await self._seed_customer(TENANT_PRO)
        template = CouponTemplate(
            tenant_id=TENANT_PRO, name="满10减2", type="FIXED", value=2, min_amount=10,
            total_stock=100, used_stock=0,
            start_time=datetime.utcnow(), end_time=datetime.utcnow() + timedelta(days=30), status=1,
        )
        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)
        coupon = Coupon(
            tenant_id=TENANT_PRO, template_id=template.id, customer_id=customer.id,
            code="LIABILITY-CODE", status="LOCKED", expire_time=datetime.utcnow() + timedelta(days=30),
        )
        self.db.add(coupon)
        await self.db.commit()
        await self.db.refresh(coupon)

        order = await self._seed_paid_order(TENANT_PRO, customer.id, coupon_id=coupon.id)

        # Downgrade to FREE before the order is paid.
        sub_result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == TENANT_PRO))
        sub = sub_result.scalars().first()
        sub.ends_at = datetime.utcnow() - timedelta(seconds=1)
        await self.db.commit()

        await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")

        await self.db.commit()
        await self.db.refresh(coupon)
        self.assertEqual(coupon.status, "USED", "coupon write-off liability path must still complete after downgrade")


class VerifyServiceCommissionAndCouponSafetyTest(BaseWiringTest):
    async def _seed_unused_coupon(self, tenant_id: str, customer: Customer) -> Coupon:
        template = CouponTemplate(
            tenant_id=tenant_id, name="核销券", type="FIXED", value=2, min_amount=10,
            total_stock=100, used_stock=0,
            start_time=datetime.utcnow(), end_time=datetime.utcnow() + timedelta(days=30), status=1,
        )
        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)
        coupon = Coupon(
            tenant_id=tenant_id, template_id=template.id, customer_id=customer.id,
            code=f"VERIFYCODE{abs(hash(tenant_id)) % 100000}", status="UNUSED",
            expire_time=datetime.utcnow() + timedelta(days=30),
        )
        self.db.add(coupon)
        await self.db.commit()
        await self.db.refresh(coupon)
        return coupon

    async def test_non_pro_pos_verify_commission_and_coupon_skipped_verify_succeeds(self):
        customer = await self._seed_customer(TENANT_STANDARD)
        coupon = await self._seed_unused_coupon(TENANT_STANDARD, customer)

        service = VerifyService(self.db)
        service.set_tenant_id(TENANT_STANDARD)
        with patch.object(
            CommissionService, "record_after_verify",
            new=AsyncMock(side_effect=AssertionError("must not be called for non-PRO")),
        ), patch.object(
            CouponService, "issue_auto_coupon",
            new=AsyncMock(side_effect=AssertionError("must not be called for non-PRO")),
        ):
            result = await service.verify_coupon_with_result(coupon.code)

        self.assertTrue(result["success"], "coupon verify liability path must still succeed")
        await self.db.refresh(coupon)
        self.assertEqual(coupon.status, "USED")

    async def test_pro_pos_verify_commission_still_accrues(self):
        customer = await self._seed_customer(TENANT_PRO)
        coupon = await self._seed_unused_coupon(TENANT_PRO, customer)

        service = VerifyService(self.db)
        service.set_tenant_id(TENANT_PRO)
        with patch.object(
            CommissionService, "record_after_verify", new=AsyncMock(return_value=[]),
        ) as mock_commission:
            result = await service.verify_coupon_with_result(coupon.code)

        self.assertTrue(result["success"])
        mock_commission.assert_awaited_once()


# ---------------------------------------------------------------------------
# PHASE 10/11 -- DISTRIBUTION_REFERRAL new inviter binding
# ---------------------------------------------------------------------------

class DistributionBindingRegistrationSafetyTest(BaseWiringTest):
    @patch("app.api.v1.miniapp.WechatService.code2session")
    async def test_non_pro_join_inviter_bind_skipped_registration_succeeds(self, mock_code2session):
        mock_code2session.return_value = {"openid": "new-customer-openid-standard", "unionid": None}
        data = EntryJoinRequest(
            tenant_id=TENANT_STANDARD, code="wx-code", phone="13900000001",
            invite_code="SOMEBODY", agreement_accepted=True,
        )
        with patch.object(
            CommissionService, "bind_inviter_for_new_customer",
            new=AsyncMock(side_effect=AssertionError("must not be called for non-PRO")),
        ):
            result = await raw_entry_join(make_request(), data, db=self.db)

        self.assertEqual(result.code, 200, "registration must succeed even though binding is skipped")
        self.assertTrue(result.data.get("customer_id"))

    @patch("app.services.coupon_service.CouponService.issue_auto_coupon", new_callable=AsyncMock)
    @patch("app.api.v1.miniapp.WechatService.code2session")
    async def test_pro_join_inviter_bind_still_works(self, mock_code2session, mock_issue_coupon):
        mock_code2session.return_value = {"openid": "new-customer-openid-pro", "unionid": None}
        mock_issue_coupon.return_value = {"success_count": 0}
        data = EntryJoinRequest(
            tenant_id=TENANT_PRO, code="wx-code", phone="13900000002",
            invite_code="SOMEBODY", agreement_accepted=True,
        )
        async def _bind_noop(customer, invite_code):
            return customer

        with patch.object(
            CommissionService, "bind_inviter_for_new_customer", new=AsyncMock(side_effect=_bind_noop),
        ) as mock_bind:
            result = await raw_entry_join(make_request(), data, db=self.db)

        self.assertEqual(result.code, 200)
        mock_bind.assert_awaited_once()

    async def test_dedicated_bind_endpoint_non_pro_no_op_not_500(self):
        customer = await self._seed_customer(TENANT_STANDARD, openid="op-bind", phone="13900000003")
        with patch.object(
            CommissionService, "bind_inviter_for_new_customer",
            new=AsyncMock(side_effect=AssertionError("must not be called for non-PRO")),
        ):
            result = await raw_invite_bind(
                make_request(
                    tenant_id=TENANT_STANDARD, customer_id=customer.id, method="POST",
                    path="/api/v1/miniapp/invite/bind", body={"invite_code": "SOMEBODY"},
                ),
                db=self.db,
            )
        self.assertNotEqual(result.code, 500)
        self.assertNotEqual(result.code, 403)
        self.assertFalse(result.data.get("bound"))

    async def test_dedicated_bind_endpoint_pro_still_binds(self):
        customer = await self._seed_customer(TENANT_PRO, openid="op-bind-pro", phone="13900000004")
        with patch.object(
            CommissionService, "bind_inviter_for_new_customer", new=AsyncMock(),
        ) as mock_bind:
            updated_customer = Customer(tenant_id=TENANT_PRO, openid="inviter-x", inviter_id=999, status=1)
            mock_bind.return_value = updated_customer
            result = await raw_invite_bind(
                make_request(
                    tenant_id=TENANT_PRO, customer_id=customer.id, method="POST",
                    path="/api/v1/miniapp/invite/bind", body={"invite_code": "SOMEBODY"},
                ),
                db=self.db,
            )
        mock_bind.assert_awaited_once()
        self.assertEqual(result.code, 200)
        self.assertTrue(result.data.get("bound"))


# ---------------------------------------------------------------------------
# PHASE 16/17 -- CHANNEL_ENTRY visit attribution
# ---------------------------------------------------------------------------

class ChannelVisitAttributionSafetyTest(BaseWiringTest):
    async def _seed_entry(self, tenant_id: str) -> ChannelEntry:
        service = ChannelEntryService(self.db)
        service.set_tenant_id(tenant_id)
        return await service.create_entry(name="抖音渠道", channel_code="douyin")

    async def test_non_pro_channel_visit_skipped_response_succeeds(self):
        entry = await self._seed_entry(TENANT_STANDARD)
        before = entry.visit_count or 0

        result = await record_visit(
            make_request(method="POST", path=f"/api/public/channel-entries/{entry.id}/visit"),
            entry.id, db=self.db,
        )
        self.assertEqual(result.code, 200, "visit endpoint must never 403/500 for the scanning customer")
        self.assertEqual(result.data["visit_count"], before, "non-PRO must not increment visit_count")

    async def test_pro_channel_visit_tracking_still_works(self):
        entry = await self._seed_entry(TENANT_PRO)
        before = entry.visit_count or 0

        result = await record_visit(
            make_request(method="POST", path=f"/api/public/channel-entries/{entry.id}/visit"),
            entry.id, db=self.db,
        )
        self.assertEqual(result.code, 200)
        self.assertEqual(result.data["visit_count"], before + 1)

    async def test_public_resolve_always_allowed_regardless_of_plan(self):
        entry = await self._seed_entry(TENANT_STANDARD)
        result = await get_h5_config(
            make_request(method="GET", path=f"/api/public/channel-entries/{entry.id}"), entry.id, db=self.db,
        )
        self.assertEqual(result.code, 200)


# ---------------------------------------------------------------------------
# PHASE 18 -- optional checker system error never reaches the business caller
# ---------------------------------------------------------------------------

class OptionalCheckerSystemErrorCoreTransactionTest(BaseWiringTest):
    async def test_payment_membership_path_succeeds_despite_entitlement_system_error(self):
        customer = await self._seed_customer(TENANT_PRO)
        order = await self._seed_paid_order(TENANT_PRO, customer.id)

        with patch.object(
            EntitlementService, "has_capability",
            new=AsyncMock(side_effect=RuntimeError("simulated entitlement resolution failure")),
        ), patch.object(MembershipService, "apply_consumption", new=AsyncMock()) as mock_apply, patch.object(
            CouponService, "issue_auto_coupon", new=AsyncMock()
        ) as mock_coupon:
            await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")

        mock_apply.assert_not_awaited()
        mock_coupon.assert_not_awaited()
        await self.db.refresh(order)
        self.assertEqual(order.payment_status, "paid", "core payment must succeed even when entitlement resolution itself errors")

    async def test_distribution_accrual_path_succeeds_despite_entitlement_system_error(self):
        customer = await self._seed_customer(TENANT_PRO)
        template = CouponTemplate(
            tenant_id=TENANT_PRO, name="核销券", type="FIXED", value=2, min_amount=10,
            total_stock=100, used_stock=0,
            start_time=datetime.utcnow(), end_time=datetime.utcnow() + timedelta(days=30), status=1,
        )
        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)
        coupon = Coupon(
            tenant_id=TENANT_PRO, template_id=template.id, customer_id=customer.id,
            code="ERRORSIMULATIONCODE", status="UNUSED", expire_time=datetime.utcnow() + timedelta(days=30),
        )
        self.db.add(coupon)
        await self.db.commit()
        await self.db.refresh(coupon)

        service = VerifyService(self.db)
        service.set_tenant_id(TENANT_PRO)
        with patch.object(
            EntitlementService, "has_capability",
            new=AsyncMock(side_effect=RuntimeError("simulated entitlement resolution failure")),
        ), patch.object(
            CommissionService, "record_after_verify", new=AsyncMock()
        ) as mock_commission:
            result = await service.verify_coupon_with_result(coupon.code)

        mock_commission.assert_not_awaited()
        self.assertTrue(result["success"], "verify liability path must succeed even when entitlement resolution itself errors")


# ---------------------------------------------------------------------------
# PHASE 23 -- tenant isolation
# ---------------------------------------------------------------------------

class TenantIsolationTest(BaseWiringTest):
    async def test_standard_and_pro_tenants_get_independent_side_effects(self):
        customer_a = await self._seed_customer(TENANT_STANDARD, openid="op-a")
        customer_b = await self._seed_customer(TENANT_PRO_B, openid="op-b")
        order_a = await self._seed_paid_order(TENANT_STANDARD, customer_a.id)
        order_b = await self._seed_paid_order(TENANT_PRO_B, customer_b.id)

        with patch.object(MembershipService, "apply_consumption", new=AsyncMock()) as mock_apply:
            await OrderPaymentService(self.db)._on_payment_success(order_a, payment_method="mock")
            self.assertEqual(mock_apply.await_count, 0, "STANDARD tenant A must not accrue")

            await OrderPaymentService(self.db)._on_payment_success(order_b, payment_method="mock")
            self.assertEqual(mock_apply.await_count, 1, "PRO tenant B must accrue exactly once")


if __name__ == "__main__":
    unittest.main()
