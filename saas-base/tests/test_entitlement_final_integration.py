"""F1F-E -- Entitlement Final Integration Gate.

Final, cross-cutting proof that the entitlement subsystem built across
F1F-A through F1F-D1B behaves as ONE coherent identity contract, not just
as a collection of individually-correct pieces:

- FREE < STANDARD < PRO capability containment, and the resolved effective
  plan matrix (no-subscription/active/trial/expired/cancelled/inactive-plan
  edge cases).
- FREE/STANDARD/PRO/TRIAL end-to-end identity: interactive gates, optional
  side-effect gates, and core transaction success all agree simultaneously.
- Downgrade/re-upgrade lifecycle: staff tokens, coupon liability, membership
  reversal, commission liability, and channel data all survive a downgrade
  without being deleted, while only *new* optional activity is blocked.
- Print and marketing complete contracts (interactive + auto + recovery/
  reminder), independent of coupon/order correctness.
- Failure-mode contract: interactive fails closed, optional fails open
  (skip-and-log, core transaction continues).
- Tenant isolation and downgrade data preservation across representative
  entities.

This file adds NO production code. If a real production defect is found,
the test documents it and the phase stops -- see the FINAL REPORT this
phase produces, not a fix committed here.
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
from starlette.responses import Response

from app.api.v1.channel_entries import list_entries as channel_list_entries
from app.api.v1.coupon_templates import create_template as create_coupon_template
from app.api.v1.merchant_accounts import (
    StaffCreateRequest,
    StaffLoginRequest,
    create_merchant_account,
    staff_login,
)
from app.api.v1.miniapp import invite_bind
from app.api.v1.public_channel import get_h5_config, record_visit
from app.config import settings
from app.core.entitlement_guard import require_capability_response
from app.core.plan_capabilities import (
    ALL_CAPABILITIES,
    CAP_CHANNEL_ENTRY,
    CAP_COUPONS,
    CAP_DISTRIBUTION_REFERRAL,
    CAP_KITCHEN_PRINT,
    CAP_MARKETING_AUTOMATION,
    CAP_MEMBER_LEVELS,
    CAP_MEMBERSHIP,
    CAP_MENU_ADVANCED_TOOLS,
    CAP_MENU_BASIC,
    CAP_ORDER_MANAGEMENT,
    CAP_POINTS,
    CAP_SCAN_ORDERING,
    CAP_STAFF_MANAGEMENT,
    CAP_TABLE_MANAGEMENT,
    CAP_WECHAT_PAYMENT,
    FREE_CAPABILITIES,
    PRO_CAPABILITIES,
    STANDARD_CAPABILITIES,
)
from app.models.base import Base
from app.models.channel_entry import ChannelEntry
from app.models.commission_record import CommissionRecord
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.models.member_account import MemberAccount
from app.models.merchant_account import MerchantAccount
from app.models.order import Order
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.schemas.coupon import CreateCouponTemplateRequest
from app.services.channel_entry_service import ChannelEntryService
from app.services.commission_service import CommissionService
from app.services.coupon_service import CouponService
from app.services.entitlement_service import EntitlementService
from app.services.membership_service import MembershipService
from app.services.merchant_account_service import MerchantAccountService
from app.services.optional_entitlement import optional_capability_enabled
from app.services.order_payment_service import OrderPaymentService
from app.services.order_print_service import _print_paid_order_ticket
from app.services.subscribe_message_service import (
    send_order_success_subscribe,
    send_queue_reminder_subscribe,
)
from app.services.subscription_service import (
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_EXPIRED,
    STATUS_TRIAL,
    SubscriptionService,
)
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


@event.listens_for(CommissionRecord, "before_insert")
def _assign_commission_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_request(*, tenant_id=None, role=None, account_id=None, customer_id=None, body=None):
    request = Request(
        {
            "type": "http", "method": "GET", "path": "/x", "headers": [],
            "query_string": b"", "server": ("testserver", 80), "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    if tenant_id is not None:
        request.state.tenant_id = tenant_id
    if role is not None:
        request.state.token_type = "merchant"
        request.state.role = role
        request.state.account_id = account_id
    if customer_id is not None:
        request.state.customer_id = customer_id
    if body is not None:
        import json as _json

        async def _body():
            return _json.dumps(body).encode()

        request.body = _body
    return request


TENANT_FREE = "tenant-f1fe-free"
TENANT_STANDARD = "tenant-f1fe-standard"
TENANT_PRO = "tenant-f1fe-pro"


class FinalIntegrationBaseTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._db_file = f"{tempfile.gettempdir()}/f1fe_{uuid.uuid4().hex}.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_file}")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add_all(
            [
                Plan(code="FREE", name="免费版", is_active=True, price_month_cents=0, price_year_cents=0, sort_order=0),
                Plan(code="STANDARD", name="普通版", is_active=True, price_month_cents=5900, price_year_cents=60900, sort_order=1),
                Plan(code="PRO", name="专业版", is_active=True, price_month_cents=9900, price_year_cents=102200, sort_order=2),
            ]
        )
        await self.db.commit()
        self.sub_service = SubscriptionService(self.db)

        self._session_patch = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._session_patch.start()
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

    async def _seed_tenant(self, tenant_id: str, phone: str | None = None) -> Tenant:
        tenant = Tenant(
            tenant_id=tenant_id, name=f"Shop {tenant_id}", password_hash="x",
            status=True, is_open=True, phone=phone,
        )
        self.db.add(tenant)
        await self.db.commit()
        await self.db.refresh(tenant)
        return tenant

    async def _subscribe(self, tenant_id: str, plan_code: str, *, status=STATUS_ACTIVE,
                          ends_delta=timedelta(days=30), trial_ends_delta=None) -> Subscription:
        plan = await self.sub_service.get_plan_by_code(plan_code)
        now = datetime.utcnow()
        sub = Subscription(
            tenant_id=tenant_id, plan_id=plan.id, status=status,
            started_at=now if status == STATUS_ACTIVE else None,
            ends_at=now + ends_delta if status == STATUS_ACTIVE else None,
            trial_started_at=now if status == STATUS_TRIAL else None,
            trial_ends_at=(now + (trial_ends_delta or timedelta(days=14))) if status == STATUS_TRIAL else None,
        )
        self.db.add(sub)
        await self.db.commit()
        await self.db.refresh(sub)
        return sub

    async def _expire(self, tenant_id: str) -> None:
        result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))
        sub = result.scalars().first()
        sub.ends_at = datetime.utcnow() - timedelta(seconds=1)
        await self.db.commit()

    async def _seed_customer(self, tenant_id: str, *, openid="op-1", phone="13800000001") -> Customer:
        customer = Customer(tenant_id=tenant_id, openid=openid, name="顾客", phone=phone, status=1)
        self.db.add(customer)
        await self.db.commit()
        await self.db.refresh(customer)
        return customer

    async def _seed_paid_order(self, tenant_id: str, customer_id: int | None = None, *, coupon_id=None) -> Order:
        order = Order(
            tenant_id=tenant_id, customer_id=customer_id, table_no="A1", total="50.00",
            status="pending_payment", payment_status="unpaid", payment_mode="prepay",
            coupon_id=coupon_id,
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def _seed_print_eligible_order(self, tenant_id: str, customer_id: int | None = None) -> Order:
        """Already-paid, print-eligible order -- _print_paid_order_ticket's non-manual
        path opens its own fresh AsyncSessionLocal() session and re-queries by id, so
        the paid state must be committed, not just set in-memory."""
        order = Order(
            tenant_id=tenant_id, customer_id=customer_id, table_no="A1", total="50.00",
            status="done", payment_status="paid", payment_mode="postpay",
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order


# ===========================================================================
# PHASE 2 -- FROZEN FINAL CAPABILITY MATRIX (pure, no DB)
# ===========================================================================
class CapabilityMatrixShapeTest(unittest.TestCase):
    def test_free_is_strict_subset_of_standard(self):
        self.assertTrue(FREE_CAPABILITIES < STANDARD_CAPABILITIES)

    def test_standard_is_strict_subset_of_pro(self):
        self.assertTrue(STANDARD_CAPABILITIES < PRO_CAPABILITIES)

    def test_pro_equals_all_capabilities(self):
        self.assertEqual(PRO_CAPABILITIES, ALL_CAPABILITIES)

    def test_frozen_matrix_exact_membership(self):
        self.assertEqual(
            FREE_CAPABILITIES,
            {CAP_SCAN_ORDERING, CAP_MENU_BASIC, CAP_ORDER_MANAGEMENT, CAP_WECHAT_PAYMENT, CAP_TABLE_MANAGEMENT},
        )
        self.assertEqual(
            STANDARD_CAPABILITIES - FREE_CAPABILITIES,
            {CAP_MENU_ADVANCED_TOOLS, CAP_KITCHEN_PRINT, CAP_STAFF_MANAGEMENT},
        )
        self.assertEqual(
            PRO_CAPABILITIES - STANDARD_CAPABILITIES,
            {
                CAP_MEMBERSHIP, CAP_POINTS, CAP_MEMBER_LEVELS, CAP_COUPONS, CAP_MARKETING_AUTOMATION,
                "CUSTOMER_CONSUMPTION", CAP_CHANNEL_ENTRY, CAP_DISTRIBUTION_REFERRAL,
            },
        )


# ===========================================================================
# PHASE 3 -- EFFECTIVE PLAN MATRIX
# ===========================================================================
class EffectivePlanMatrixTest(FinalIntegrationBaseTest):
    async def _effective_code(self, tenant_id: str) -> str:
        view = await self.sub_service.get_effective_subscription_view(tenant_id)
        return view.effective_plan.code

    async def test_no_subscription_resolves_free(self):
        await self._seed_tenant(TENANT_FREE)
        self.assertEqual(await self._effective_code(TENANT_FREE), "FREE")

    async def test_active_standard_resolves_standard(self):
        await self._seed_tenant(TENANT_STANDARD)
        await self._subscribe(TENANT_STANDARD, "STANDARD")
        self.assertEqual(await self._effective_code(TENANT_STANDARD), "STANDARD")

    async def test_active_pro_resolves_pro(self):
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO")
        self.assertEqual(await self._effective_code(TENANT_PRO), "PRO")

    async def test_trial_pro_resolves_pro(self):
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO", status=STATUS_TRIAL)
        self.assertEqual(await self._effective_code(TENANT_PRO), "PRO")

    async def test_expired_standard_resolves_free(self):
        await self._seed_tenant(TENANT_STANDARD)
        await self._subscribe(TENANT_STANDARD, "STANDARD", ends_delta=timedelta(seconds=-1))
        self.assertEqual(await self._effective_code(TENANT_STANDARD), "FREE")

    async def test_expired_pro_resolves_free(self):
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO", ends_delta=timedelta(seconds=-1))
        self.assertEqual(await self._effective_code(TENANT_PRO), "FREE")

    async def test_expired_trial_resolves_free(self):
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO", status=STATUS_TRIAL, trial_ends_delta=timedelta(seconds=-1))
        self.assertEqual(await self._effective_code(TENANT_PRO), "FREE")

    async def test_cancelled_resolves_free(self):
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO", status=STATUS_CANCELLED)
        self.assertEqual(await self._effective_code(TENANT_PRO), "FREE")

    async def test_ends_at_equals_now_resolves_free(self):
        await self._seed_tenant(TENANT_PRO)
        plan = await self.sub_service.get_plan_by_code("PRO")
        now = datetime.utcnow()
        sub = Subscription(tenant_id=TENANT_PRO, plan_id=plan.id, status=STATUS_ACTIVE, started_at=now, ends_at=now)
        self.db.add(sub)
        await self.db.commit()
        self.assertEqual(await self._effective_code(TENANT_PRO), "FREE", "now < ends_at is strict; ends_at==now must not grant")

    async def test_inactive_plan_row_with_existing_subscription_retains_rights(self):
        await self._seed_tenant(TENANT_STANDARD)
        await self._subscribe(TENANT_STANDARD, "STANDARD")
        plan = await self.sub_service.get_plan_by_code("STANDARD")
        plan.is_active = False
        await self.db.commit()
        self.assertEqual(
            await self._effective_code(TENANT_STANDARD), "STANDARD",
            "an existing unexpired subscription must not lose rights just because the Plan catalog row was later deactivated",
        )


# ===========================================================================
# PHASE 4/5/6/7 -- TIER END-TO-END IDENTITY
# ===========================================================================
class TierEndToEndTest(FinalIntegrationBaseTest):
    async def test_free_end_to_end(self):
        await self._seed_tenant(TENANT_FREE)
        ent = EntitlementService(self.db)

        # Interactive: core allowed, upgraded features denied.
        self.assertTrue(await ent.has_capability(TENANT_FREE, CAP_ORDER_MANAGEMENT))
        self.assertTrue(await ent.has_capability(TENANT_FREE, CAP_WECHAT_PAYMENT))
        self.assertFalse(await ent.has_capability(TENANT_FREE, CAP_MENU_ADVANCED_TOOLS))
        self.assertFalse(await ent.has_capability(TENANT_FREE, CAP_KITCHEN_PRINT))
        self.assertFalse(await ent.has_capability(TENANT_FREE, CAP_STAFF_MANAGEMENT))
        for cap in PRO_CAPABILITIES - STANDARD_CAPABILITIES:
            self.assertFalse(await ent.has_capability(TENANT_FREE, cap))

        denial = await require_capability_response(self.db, TENANT_FREE, CAP_KITCHEN_PRINT)
        self.assertIsNotNone(denial)
        self.assertEqual(denial.code, 403)

        # Optional/async: skipped, but the real core transaction still succeeds.
        customer = await self._seed_customer(TENANT_FREE)
        order = await self._seed_paid_order(TENANT_FREE, customer.id)
        with patch.object(MembershipService, "apply_consumption", new=AsyncMock(side_effect=AssertionError)), \
             patch.object(CouponService, "issue_auto_coupon", new=AsyncMock(side_effect=AssertionError)):
            await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")
        await self.db.commit()
        await self.db.refresh(order)
        self.assertEqual(order.payment_status, "paid", "core transaction must succeed despite every optional effect skipping")

        print_result = await _print_paid_order_ticket(order, self.db, reason="payment_success")
        self.assertEqual(print_result, {"success": False, "skipped": True, "code": "PLAN_CAPABILITY_DISABLED"})

        settings.WECHAT_ORDER_SUCCESS_TEMPLATE_ID = "tpl"
        with patch("app.services.wechat_service.WechatService.send_subscribe_message", new=AsyncMock(return_value=True)) as wechat:
            sent = await send_order_success_subscribe(self.db, order)
        self.assertFalse(sent)
        wechat.assert_not_called()

    async def test_standard_end_to_end(self):
        await self._seed_tenant(TENANT_STANDARD)
        await self._subscribe(TENANT_STANDARD, "STANDARD")
        ent = EntitlementService(self.db)

        self.assertTrue(await ent.has_capability(TENANT_STANDARD, CAP_ORDER_MANAGEMENT))
        self.assertTrue(await ent.has_capability(TENANT_STANDARD, CAP_MENU_ADVANCED_TOOLS))
        self.assertTrue(await ent.has_capability(TENANT_STANDARD, CAP_KITCHEN_PRINT))
        self.assertTrue(await ent.has_capability(TENANT_STANDARD, CAP_STAFF_MANAGEMENT))
        for cap in PRO_CAPABILITIES - STANDARD_CAPABILITIES:
            self.assertFalse(await ent.has_capability(TENANT_STANDARD, cap))
        self.assertIsNone(await require_capability_response(self.db, TENANT_STANDARD, CAP_KITCHEN_PRINT))
        pro_denial = await require_capability_response(self.db, TENANT_STANDARD, CAP_MEMBERSHIP)
        self.assertEqual(pro_denial.code, 403)

        customer = await self._seed_customer(TENANT_STANDARD)
        order = await self._seed_paid_order(TENANT_STANDARD, customer.id)
        with patch.object(MembershipService, "apply_consumption", new=AsyncMock(side_effect=AssertionError)):
            await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")
        await self.db.commit()
        await self.db.refresh(order)
        self.assertEqual(order.payment_status, "paid")

        with patch("app.services.order_print_service._execute_provider_with_frozen_route",
                   new=AsyncMock(return_value="task-1")) as provider:
            print_result = await _print_paid_order_ticket(order, self.db, reason="payment_success")
        self.assertTrue(print_result.get("success"))
        provider.assert_awaited_once()

    async def test_pro_end_to_end(self):
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO")
        ent = EntitlementService(self.db)

        for cap in ALL_CAPABILITIES:
            self.assertTrue(await ent.has_capability(TENANT_PRO, cap), f"PRO must have {cap}")
        self.assertIsNone(await require_capability_response(self.db, TENANT_PRO, CAP_MEMBERSHIP))

        customer = await self._seed_customer(TENANT_PRO)
        order = await self._seed_paid_order(TENANT_PRO, customer.id)
        await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")

        result = await self.db.execute(
            select(MemberAccount).where(MemberAccount.tenant_id == TENANT_PRO, MemberAccount.customer_id == customer.id)
        )
        accounts = result.scalars().all()
        self.assertEqual(len(accounts), 1, "membership accrual must run exactly once, no duplicate side effect")
        self.assertGreater(accounts[0].points_balance, 0)

    async def test_trial_pro_matches_pro(self):
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO", status=STATUS_TRIAL)

        # One PRO interactive endpoint.
        self.assertIsNone(await require_capability_response(self.db, TENANT_PRO, CAP_MEMBERSHIP))

        # One PRO transaction-adjacent optional effect.
        customer = await self._seed_customer(TENANT_PRO)
        order = await self._seed_paid_order(TENANT_PRO, customer.id)
        with patch.object(MembershipService, "apply_consumption", new=AsyncMock(return_value=None)) as mock_apply:
            await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")
        mock_apply.assert_awaited_once()
        await self.db.commit()

        # One PRO async optional effect.
        with patch("app.services.order_print_service._execute_provider_with_frozen_route",
                   new=AsyncMock(return_value="task-1")) as provider:
            print_result = await _print_paid_order_ticket(order, self.db, reason="payment_success")
        self.assertTrue(print_result.get("success"))
        provider.assert_awaited_once()


# ===========================================================================
# PHASE 8-12 -- DOWNGRADE / RE-UPGRADE LIFECYCLE & HISTORICAL LIABILITY
# ===========================================================================
class DowngradeReupgradeLifecycleTest(FinalIntegrationBaseTest):
    async def test_staff_downgrade_denies_then_reupgrade_restores_same_row(self):
        tenant = await self._seed_tenant(TENANT_STANDARD, phone="13900000001")
        await self._subscribe(TENANT_STANDARD, "STANDARD")

        owner_req = make_request(tenant_id=TENANT_STANDARD, role="owner", account_id=None)
        create_resp = await create_merchant_account(
            StaffCreateRequest(name="小张", role="waiter", username="xiaozhang", password="Passw0rd1"),
            owner_req, self.db,
        )
        self.assertEqual(create_resp.code, 200)
        account_id = int(create_resp.data["id"])

        login_body = StaffLoginRequest(shop_phone="13900000001", username="xiaozhang", password="Passw0rd1")
        ok = await staff_login.__wrapped__(make_request(), Response(), login_body, self.db)
        self.assertEqual(ok.code, 200, f"staff login must succeed while STANDARD: {ok}")

        await self._expire(TENANT_STANDARD)

        denied = await staff_login.__wrapped__(make_request(), Response(), login_body, self.db)
        self.assertEqual(denied.code, 403)
        self.assertEqual(denied.data.get("error_code"), "PLAN_CAPABILITY_REQUIRED")

        # Owner still operates FREE core.
        self.assertTrue(await EntitlementService(self.db).has_capability(TENANT_STANDARD, CAP_ORDER_MANAGEMENT))

        # Staff row itself must not have been deleted.
        row = await self.db.get(MerchantAccount, account_id)
        self.assertIsNotNone(row, "staff data must be preserved across downgrade")
        self.assertEqual(row.name, "小张")

        await self._subscribe(TENANT_STANDARD, "PRO")
        reupgraded = await staff_login.__wrapped__(make_request(), Response(), login_body, self.db)
        self.assertEqual(reupgraded.code, 200, "same staff row must be usable again after re-upgrade, no recreation needed")

    async def test_coupon_liability_survives_downgrade_new_issuance_blocked(self):
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO")
        customer = await self._seed_customer(TENANT_PRO)
        template = CouponTemplate(
            tenant_id=TENANT_PRO, name="老券", type="FIXED", value=5,
            start_time=datetime.utcnow() - timedelta(days=1), end_time=datetime.utcnow() + timedelta(days=30),
        )
        self.db.add(template)
        await self.db.commit()
        coupon = Coupon(
            tenant_id=TENANT_PRO, template_id=template.id, customer_id=customer.id,
            code="F1FELIABILITY1", status="LOCKED", expire_time=datetime.utcnow() + timedelta(days=30),
        )
        self.db.add(coupon)
        order = await self._seed_paid_order(TENANT_PRO, customer.id, coupon_id=None)
        order.coupon_id = coupon.id
        order.payment_status = "paid"
        order.payment_method = "balance"
        order.balance_deduct_requested = order.total
        await self.db.commit()

        await self._expire(TENANT_PRO)

        # Existing issued coupon: refund still unlocks it -- never entitlement-gated.
        await OrderPaymentService(self.db)._refund_order_payment(order, reason="test refund")
        await self.db.commit()
        await self.db.refresh(coupon)
        self.assertEqual(coupon.status, "UNUSED", "unlock/rollback on refund must run regardless of current plan")

        # New template creation and proactive recall are denied when non-PRO.
        request = make_request(tenant_id=TENANT_PRO)
        from app.core.tenant_context import TenantContext
        TenantContext.set_tenant_id(TENANT_PRO)
        create_resp = await create_coupon_template.__wrapped__(
            request,
            CreateCouponTemplateRequest(
                name="新券", type="FIXED", value=5, start_time=datetime.utcnow().isoformat(),
                end_time=(datetime.utcnow() + timedelta(days=30)).isoformat(),
            ),
            self.db,
        )
        self.assertEqual(create_resp.code, 403)
        self.assertEqual(create_resp.data.get("error_code"), "PLAN_CAPABILITY_REQUIRED")

    async def test_membership_reversal_survives_downgrade(self):
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO")
        customer = await self._seed_customer(TENANT_PRO)
        order = await self._seed_paid_order(TENANT_PRO, customer.id)
        await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")
        await self.db.commit()

        result = await self.db.execute(
            select(MemberAccount).where(MemberAccount.tenant_id == TENANT_PRO, MemberAccount.customer_id == customer.id)
        )
        account = result.scalar_one()
        points_before = account.points_balance
        self.assertGreater(points_before, 0)

        await self._expire(TENANT_PRO)

        # NOTE (F1G-CM-PD0-COMP): `wraps=` combined with `autospec=True` silently
        # no-ops for async methods in unittest.mock -- the mock returns a bare
        # AsyncMock instead of calling through, so the real reverse_consumption()
        # body never ran and this assertion was passing/failing for the wrong
        # reason. `side_effect=` is the correct pattern for an autospec'd async
        # spy that must actually execute the wrapped implementation.
        with patch.object(MembershipService, "reverse_consumption", side_effect=MembershipService.reverse_consumption, autospec=True) as spy:
            await OrderPaymentService(self.db)._refund_order_payment(order, reason="test refund")
        spy.assert_awaited_once()
        await self.db.commit()
        await self.db.refresh(account)
        self.assertLess(account.points_balance, points_before, "historical accrual must be reversed even after downgrade to FREE")

    async def test_distribution_commission_liability_survives_downgrade_new_accrual_blocked(self):
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO")
        inviter = await self._seed_customer(TENANT_PRO, openid="op-inviter", phone="13800000002")
        customer = await self._seed_customer(TENANT_PRO, openid="op-invitee", phone="13800000003")
        record = CommissionRecord(
            tenant_id=TENANT_PRO, user_id=customer.id, receiver_id=inviter.id,
            amount="5.00", commission_amount="5.00", level=1, status="PENDING", source_type="FIRST_VERIFY",
        )
        self.db.add(record)
        await self.db.commit()

        await self._expire(TENANT_PRO)

        # Read/settlement history preserved.
        commission_svc = CommissionService(self.db)
        commission_svc.set_tenant_id(TENANT_PRO)
        records, total = await commission_svc.list_records(receiver_id=inviter.id, receiver_type=None)
        self.assertEqual(total, 1)
        self.assertEqual(records[0].id, record.id)

        # New binding blocked (gated at the miniapp.invite_bind call site).
        new_customer = await self._seed_customer(TENANT_PRO, openid="op-new", phone="13800000004")
        request = make_request(tenant_id=TENANT_PRO, customer_id=new_customer.id,
                                body={"invite_code": str(inviter.id)})
        bind_result = await invite_bind(request, self.db)
        self.assertEqual(bind_result.data.get("bound"), False)
        await self.db.refresh(new_customer)
        self.assertIsNone(new_customer.inviter_id, "no new binding once non-PRO")

        # New accrual blocked (VerifyService gates before calling CommissionService).
        with patch.object(CommissionService, "record_after_verify", new=AsyncMock(return_value=[])) as mock_accrue:
            await VerifyService(self.db)._trigger_commission(
                type("C", (), {"tenant_id": TENANT_PRO, "customer_id": customer.id})(), None,
            )
        mock_accrue.assert_not_called()

    async def test_channel_downgrade_public_resolve_survives_visit_tracking_skipped(self):
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO")
        from app.core.tenant_context import TenantContext
        TenantContext.set_tenant_id(TENANT_PRO)
        service = ChannelEntryService(self.db)
        service.set_tenant_id(TENANT_PRO)
        entry = await service.create_entry(name="抖音渠道", channel_code="douyin")
        entry_id = entry.id
        visits_before = entry.visit_count or 0

        await self._expire(TENANT_PRO)

        # Public resolve still succeeds.
        resolve_result = await get_h5_config(make_request(), entry_id, self.db)
        self.assertEqual(resolve_result.code, 200)

        # Visit tracking side effect skipped.
        await record_visit(make_request(), entry_id, self.db)
        refreshed = await self.db.get(ChannelEntry, entry_id)
        self.assertEqual(refreshed.visit_count or 0, visits_before, "visit tracking must be skipped, not error, when non-PRO")

        # PRO-only merchant analytics/config endpoint denied.
        denied = await channel_list_entries(make_request(tenant_id=TENANT_PRO), db=self.db)
        self.assertEqual(denied.code, 403)

        # Re-upgrade: existing channel data reusable again.
        await self._subscribe(TENANT_PRO, "PRO")
        allowed = await channel_list_entries(make_request(tenant_id=TENANT_PRO), db=self.db)
        self.assertEqual(allowed.code, 200)
        ids = [row["id"] for row in allowed.data["items"]]
        self.assertIn(str(entry_id), ids)


# ===========================================================================
# PHASE 13/14 -- PRINT & MARKETING COMPLETE CONTRACT
# ===========================================================================
class PrintMarketingCompleteContractTest(FinalIntegrationBaseTest):
    async def test_print_complete_contract_free_standard_pro(self):
        await self._seed_tenant(TENANT_FREE)
        await self._seed_tenant(TENANT_STANDARD)
        await self._subscribe(TENANT_STANDARD, "STANDARD")
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO")

        self.assertEqual(
            (await require_capability_response(self.db, TENANT_FREE, CAP_KITCHEN_PRINT)).code, 403,
            "interactive print must 403 for FREE",
        )
        for tenant_id in (TENANT_STANDARD, TENANT_PRO):
            self.assertIsNone(
                await require_capability_response(self.db, tenant_id, CAP_KITCHEN_PRINT),
                f"interactive print must be allowed for {tenant_id}",
            )

        for tenant_id, should_print in ((TENANT_FREE, False), (TENANT_STANDARD, True), (TENANT_PRO, True)):
            customer = await self._seed_customer(tenant_id, openid=f"op-{tenant_id}")
            order = await self._seed_print_eligible_order(tenant_id, customer.id)
            with patch("app.services.order_print_service._execute_provider_with_frozen_route",
                       new=AsyncMock(return_value="task-1")) as provider:
                result = await _print_paid_order_ticket(order, self.db, reason="payment_success")
            self.assertEqual(bool(result.get("success")), should_print, f"auto print for {tenant_id}: {result}")
            self.assertEqual(provider.await_count, 1 if should_print else 0, f"recovery/print call count for {tenant_id}")

    async def test_manual_reprint_not_blocked_by_async_gate(self):
        await self._seed_tenant(TENANT_FREE)
        customer = await self._seed_customer(TENANT_FREE)
        order = await self._seed_paid_order(TENANT_FREE, customer.id)
        order.payment_status = "paid"
        order.status = "done"
        await self.db.commit()

        # Manual reprint path (manual=True) must never consult KITCHEN_PRINT itself --
        # F1F-B's interactive gate is the sole authority upstream of this call.
        with patch("app.services.order_print_service._execute_provider_with_frozen_route",
                   new=AsyncMock(return_value="task-1")) as provider:
            result = await _print_paid_order_ticket(order, self.db, manual=True, reason="manual", operator="owner")
        self.assertNotEqual(result.get("code"), "PLAN_CAPABILITY_DISABLED")
        provider.assert_awaited_once()

    async def test_marketing_complete_contract_free_standard_pro(self):
        await self._seed_tenant(TENANT_FREE)
        await self._seed_tenant(TENANT_STANDARD)
        await self._subscribe(TENANT_STANDARD, "STANDARD")
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO")
        settings.WECHAT_ORDER_SUCCESS_TEMPLATE_ID = "tpl"

        self.assertEqual((await require_capability_response(self.db, TENANT_FREE, CAP_MARKETING_AUTOMATION)).code, 403)
        self.assertEqual((await require_capability_response(self.db, TENANT_STANDARD, CAP_MARKETING_AUTOMATION)).code, 403)
        self.assertIsNone(await require_capability_response(self.db, TENANT_PRO, CAP_MARKETING_AUTOMATION))

        for tenant_id, should_send in ((TENANT_FREE, False), (TENANT_STANDARD, False), (TENANT_PRO, True)):
            customer = await self._seed_customer(tenant_id, openid=f"op-mkt-{tenant_id}")
            order = await self._seed_paid_order(tenant_id, customer.id)
            with patch("app.services.wechat_service.WechatService.send_subscribe_message",
                       new=AsyncMock(return_value=True)) as wechat:
                sent = await send_order_success_subscribe(self.db, order)
            self.assertEqual(sent, should_send, f"order-success reminder for {tenant_id}")
            self.assertEqual(wechat.await_count if should_send else wechat.call_count, 1 if should_send else 0)

    async def test_coupon_validity_independent_of_reminder_entitlement(self):
        await self._seed_tenant(TENANT_FREE)
        customer = await self._seed_customer(TENANT_FREE)
        template = CouponTemplate(
            tenant_id=TENANT_FREE, name="到期券", type="FIXED", value=5,
            start_time=datetime.utcnow() - timedelta(days=1), end_time=datetime.utcnow() + timedelta(days=5),
        )
        self.db.add(template)
        await self.db.commit()
        expire_at = datetime.utcnow() + timedelta(hours=5)
        coupon = Coupon(
            tenant_id=TENANT_FREE, template_id=template.id, customer_id=customer.id,
            code="F1FEVALIDITY1", status="UNUSED", expire_time=expire_at, remind_requested=True,
        )
        self.db.add(coupon)
        await self.db.commit()

        settings.WECHAT_COUPON_REMINDER_TEMPLATE_ID = "tpl-expiry"
        import app.main as main_module

        calls = {"n": 0}

        async def _one_shot_sleep(_seconds):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise asyncio.CancelledError()

        with patch("asyncio.sleep", new=_one_shot_sleep), \
             patch("app.services.wechat_service.WechatService.send_subscribe_message",
                   new=AsyncMock(return_value=True)) as wechat:
            with self.assertRaises(asyncio.CancelledError):
                await main_module._coupon_expiry_reminder_loop()

        wechat.assert_not_called()
        await self.db.refresh(coupon)
        self.assertEqual(coupon.status, "UNUSED")
        self.assertEqual(coupon.expire_time, expire_at)


# ===========================================================================
# PHASE 15-17 -- FAILURE MODE / TENANT ISOLATION / DATA PRESERVATION
# ===========================================================================
class FailureModeIsolationPreservationTest(FinalIntegrationBaseTest):
    async def test_interactive_system_error_fails_closed(self):
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO")
        with patch(
            "app.services.entitlement_service.EntitlementService.resolve_effective_plan_code",
            new=AsyncMock(side_effect=RuntimeError("entitlement backend unavailable")),
        ):
            denial = await require_capability_response(self.db, TENANT_PRO, CAP_MEMBERSHIP)
        self.assertIsNotNone(denial, "a system error must never implicitly grant a paid capability")
        self.assertEqual(denial.code, 500)
        self.assertEqual(denial.data.get("error_code"), "INTERNAL_ERROR")

    async def test_optional_system_error_skips_and_continues(self):
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO")
        customer = await self._seed_customer(TENANT_PRO)
        order = await self._seed_paid_order(TENANT_PRO, customer.id)
        with patch(
            "app.services.entitlement_service.EntitlementService.has_capability",
            new=AsyncMock(side_effect=RuntimeError("entitlement backend unavailable")),
        ):
            coupon_data, _ = await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")
        await self.db.commit()
        await self.db.refresh(order)
        self.assertEqual(order.payment_status, "paid", "core transaction must continue despite an entitlement system error")

    async def test_tenant_isolation_free_standard_pro_simultaneous(self):
        await self._seed_tenant(TENANT_FREE)
        await self._seed_tenant(TENANT_STANDARD)
        await self._subscribe(TENANT_STANDARD, "STANDARD")
        await self._seed_tenant(TENANT_PRO)
        await self._subscribe(TENANT_PRO, "PRO")

        # Interactive gate.
        self.assertEqual((await require_capability_response(self.db, TENANT_FREE, CAP_STAFF_MANAGEMENT)).code, 403)
        self.assertIsNone(await require_capability_response(self.db, TENANT_STANDARD, CAP_STAFF_MANAGEMENT))
        self.assertIsNone(await require_capability_response(self.db, TENANT_PRO, CAP_STAFF_MANAGEMENT))

        # Transaction-adjacent optional gate.
        for tenant_id, should_apply in ((TENANT_FREE, False), (TENANT_STANDARD, False), (TENANT_PRO, True)):
            customer = await self._seed_customer(tenant_id, openid=f"op-iso-{tenant_id}")
            order = await self._seed_paid_order(tenant_id, customer.id)
            with patch.object(MembershipService, "apply_consumption", new=AsyncMock(return_value=None)) as mock_apply:
                await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")
            self.assertEqual(mock_apply.await_count, 1 if should_apply else 0, tenant_id)

        # Async gate.
        for tenant_id, should_print in ((TENANT_FREE, False), (TENANT_STANDARD, True), (TENANT_PRO, True)):
            customer = await self._seed_customer(tenant_id, openid=f"op-iso-print-{tenant_id}")
            order = await self._seed_print_eligible_order(tenant_id, customer.id)
            with patch("app.services.order_print_service._execute_provider_with_frozen_route",
                       new=AsyncMock(return_value="task-1")) as provider:
                await _print_paid_order_ticket(order, self.db, reason="payment_success")
            self.assertEqual(provider.await_count, 1 if should_print else 0, tenant_id)

    async def test_downgrade_data_preservation_five_categories(self):
        await self._seed_tenant(TENANT_PRO, phone="13900000002")
        await self._subscribe(TENANT_PRO, "PRO")
        from app.core.tenant_context import TenantContext
        TenantContext.set_tenant_id(TENANT_PRO)

        owner_req = make_request(tenant_id=TENANT_PRO, role="owner", account_id=None)
        staff_resp = await create_merchant_account(
            StaffCreateRequest(name="员工A", role="waiter", username="staffa", password="Passw0rd1"),
            owner_req, self.db,
        )
        staff_id = int(staff_resp.data["id"])

        customer = await self._seed_customer(TENANT_PRO, openid="op-preserve")
        template = CouponTemplate(
            tenant_id=TENANT_PRO, name="留存券", type="FIXED", value=5,
            start_time=datetime.utcnow() - timedelta(days=1), end_time=datetime.utcnow() + timedelta(days=30),
        )
        self.db.add(template)
        await self.db.commit()
        coupon = Coupon(
            tenant_id=TENANT_PRO, template_id=template.id, customer_id=customer.id,
            code="F1FEPRESERVE1", status="UNUSED", expire_time=datetime.utcnow() + timedelta(days=30),
        )
        self.db.add(coupon)

        channel_service = ChannelEntryService(self.db)
        channel_service.set_tenant_id(TENANT_PRO)
        channel_entry = await channel_service.create_entry(name="留存渠道", channel_code="offline")

        commission = CommissionRecord(
            tenant_id=TENANT_PRO, user_id=customer.id, receiver_id=customer.id,
            amount="3.00", commission_amount="3.00", level=1, status="PENDING", source_type="FIRST_VERIFY",
        )
        self.db.add(commission)
        await self.db.commit()

        counts_before = {
            "staff": (await self.db.execute(select(MerchantAccount).where(MerchantAccount.tenant_id == TENANT_PRO))).scalars().all(),
            "coupon": (await self.db.execute(select(Coupon).where(Coupon.tenant_id == TENANT_PRO))).scalars().all(),
            "customer": (await self.db.execute(select(Customer).where(Customer.tenant_id == TENANT_PRO))).scalars().all(),
            "channel": (await self.db.execute(select(ChannelEntry).where(ChannelEntry.tenant_id == TENANT_PRO))).scalars().all(),
            "commission": (await self.db.execute(select(CommissionRecord).where(CommissionRecord.tenant_id == TENANT_PRO))).scalars().all(),
        }

        await self._expire(TENANT_PRO)

        counts_after = {
            "staff": (await self.db.execute(select(MerchantAccount).where(MerchantAccount.tenant_id == TENANT_PRO))).scalars().all(),
            "coupon": (await self.db.execute(select(Coupon).where(Coupon.tenant_id == TENANT_PRO))).scalars().all(),
            "customer": (await self.db.execute(select(Customer).where(Customer.tenant_id == TENANT_PRO))).scalars().all(),
            "channel": (await self.db.execute(select(ChannelEntry).where(ChannelEntry.tenant_id == TENANT_PRO))).scalars().all(),
            "commission": (await self.db.execute(select(CommissionRecord).where(CommissionRecord.tenant_id == TENANT_PRO))).scalars().all(),
        }

        for key in counts_before:
            before_ids = sorted(row.id for row in counts_before[key])
            after_ids = sorted(row.id for row in counts_after[key])
            self.assertEqual(before_ids, after_ids, f"{key} rows must be byte-identical in identity across a downgrade")
        self.assertEqual(len(counts_before["staff"]), 1)
        self.assertEqual(staff_id, counts_after["staff"][0].id)
        self.assertEqual(channel_entry.id, counts_after["channel"][0].id)


if __name__ == "__main__":
    unittest.main()
