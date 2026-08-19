"""F1F-D1B -- async optional side-effect enforcement:

- KITCHEN_PRINT gates every *auto* print path through the single common
  choke point `_print_paid_order_ticket` (order creation background print,
  payment-success print, pickup-assigned print, and both print-recovery
  paths all funnel through it). Manual reprint is untouched -- it already
  has its own interactive (F1F-B) gate upstream of this function.
- MARKETING_AUTOMATION gates the three subscribe_message_service send
  functions directly (order success / pickup / queue reminders), plus the
  two app.main background loops (marketing recall, coupon expiry
  reminder) at their per-tenant / per-coupon call sites.

Both capabilities reuse the same optional_capability_enabled() safe-check
primitive from F1F-D0/D1A: granted -> True, denied -> False, system error
-> False (never raises, never blocks the underlying transaction).
"""
import asyncio
import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.config import settings
from app.core.plan_capabilities import CAP_KITCHEN_PRINT, CAP_MARKETING_AUTOMATION
from app.models.base import Base
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.models.order import Order
from app.models.queue_ticket import QueueTicket
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.services.subscription_service import STATUS_ACTIVE, SubscriptionService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_FREE = "tenant-d1b-free"
TENANT_STANDARD = "tenant-d1b-standard"
TENANT_PRO = "tenant-d1b-pro"


def make_merchant_request(tenant_id, path="/api/v1/orders/status"):
    req = Request(
        {
            "type": "http", "method": "POST", "path": path, "headers": [],
            "query_string": b"", "server": ("testserver", 80), "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    req.state.tenant_id = tenant_id
    req.state.token_type = "merchant"
    req.state.user_id = "staff-1"
    req.state.role = "owner"
    req.state.account_id = None
    return req


class D1BBaseTest(unittest.IsolatedAsyncioTestCase):
    """Shared fixture: file-backed SQLite (see test_optional_side_effect_wiring.py
    for why not :memory:) + a FREE/STANDARD/PRO tenant baseline, matching the
    F1F-D1A convention exactly."""

    async def asyncSetUp(self):
        self._original_redis_enabled = settings.REDIS_ENABLED
        settings.REDIS_ENABLED = False

        self._db_file = f"{tempfile.gettempdir()}/f1fd1b_{uuid.uuid4().hex}.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_file}")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self._session_patch = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._session_patch.start()

        self.db.add_all([
            Tenant(tenant_id=TENANT_FREE, name="Free Shop", password_hash="x", status=True, is_open=True),
            Tenant(tenant_id=TENANT_STANDARD, name="Standard Shop", password_hash="x", status=True, is_open=True),
            Tenant(tenant_id=TENANT_PRO, name="Pro Shop", password_hash="x", status=True, is_open=True),
            Plan(code="FREE", name="免费版", is_active=True, price_month_cents=0, price_year_cents=0, sort_order=0),
            Plan(code="STANDARD", name="普通版", is_active=True, price_month_cents=5900, price_year_cents=60900, sort_order=1),
            Plan(code="PRO", name="专业版", is_active=True, price_month_cents=9900, price_year_cents=102200, sort_order=2),
        ])
        await self.db.commit()

        sub_svc = SubscriptionService(self.db)
        standard_plan = await sub_svc.get_plan_by_code("STANDARD")
        pro_plan = await sub_svc.get_plan_by_code("PRO")
        now = datetime.utcnow()
        self.db.add_all([
            Subscription(tenant_id=TENANT_STANDARD, plan_id=standard_plan.id, status=STATUS_ACTIVE,
                         started_at=now, ends_at=now + timedelta(days=30)),
            Subscription(tenant_id=TENANT_PRO, plan_id=pro_plan.id, status=STATUS_ACTIVE,
                         started_at=now, ends_at=now + timedelta(days=30)),
        ])
        await self.db.commit()

    async def asyncTearDown(self):
        self._session_patch.stop()
        settings.REDIS_ENABLED = self._original_redis_enabled
        await self.db.close()
        await self.engine.dispose()
        try:
            os.remove(self._db_file)
        except OSError:
            pass

    async def _make_order(self, tenant_id, *, status="done", payment_mode="postpay",
                           payment_status="paid", customer_id=None, print_status=None,
                           updated_at=None):
        order = Order(
            tenant_id=tenant_id, customer_id=customer_id, table_no="A1", total="20.00",
            status=status, payment_mode=payment_mode, payment_status=payment_status,
        )
        if print_status is not None:
            order.print_status = print_status
        if updated_at is not None:
            order.updated_at = updated_at
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def _make_customer(self, tenant_id, openid="wx-openid-d1b"):
        customer = Customer(tenant_id=tenant_id, openid=openid, status=1)
        self.db.add(customer)
        await self.db.commit()
        await self.db.refresh(customer)
        return customer


# ---------------------------------------------------------------------------
# KITCHEN_PRINT -- common enforcement point: _print_paid_order_ticket
# ---------------------------------------------------------------------------
class PrintOptionalGateTest(D1BBaseTest):
    async def test_free_auto_print_skipped_order_succeeds(self):
        from app.services.order_print_service import _print_paid_order_ticket

        order = await self._make_order(TENANT_FREE)
        with patch("app.services.order_print_service._execute_provider_with_frozen_route", new=AsyncMock()) as provider:
            result = await _print_paid_order_ticket(order, self.db, reason="payment_success")

        self.assertEqual(result, {"success": False, "skipped": True, "code": "PLAN_CAPABILITY_DISABLED"})
        provider.assert_not_called()

    async def test_standard_auto_print_still_runs(self):
        from app.services.order_print_service import _print_paid_order_ticket

        order = await self._make_order(TENANT_STANDARD)
        with patch("app.services.order_print_service._execute_provider_with_frozen_route",
                   new=AsyncMock(return_value="task-1")) as provider:
            result = await _print_paid_order_ticket(order, self.db, reason="payment_success")

        self.assertTrue(result.get("success"))
        provider.assert_awaited_once()

    async def test_pro_auto_print_still_runs_exactly_once(self):
        from app.services.order_print_service import _print_paid_order_ticket

        order = await self._make_order(TENANT_PRO)
        with patch("app.services.order_print_service._execute_provider_with_frozen_route",
                   new=AsyncMock(return_value="task-1")) as provider:
            result = await _print_paid_order_ticket(order, self.db, reason="payment_success")

        self.assertTrue(result.get("success"))
        self.assertEqual(provider.await_count, 1)

    async def test_print_entitlement_error_skips_without_order_failure(self):
        from app.services.order_print_service import _print_paid_order_ticket

        order = await self._make_order(TENANT_PRO)
        with patch(
            "app.services.entitlement_service.EntitlementService.has_capability",
            new=AsyncMock(side_effect=RuntimeError("entitlement backend unavailable")),
        ), patch("app.services.order_print_service._execute_provider_with_frozen_route", new=AsyncMock()) as provider:
            result = await _print_paid_order_ticket(order, self.db, reason="payment_success")

        self.assertEqual(result, {"success": False, "skipped": True, "code": "PLAN_CAPABILITY_DISABLED"})
        provider.assert_not_called()

    async def test_free_print_recovery_skips_provider(self):
        from app.services.order_print_service import recover_pending_print_orders_once

        old = datetime.utcnow() - timedelta(seconds=60)
        await self._make_order(TENANT_FREE, print_status="PENDING", updated_at=old)

        with patch("app.services.order_print_service._execute_provider_with_frozen_route", new=AsyncMock()) as provider:
            handled = await recover_pending_print_orders_once(self.db)

        self.assertEqual(handled, 0)
        provider.assert_not_called()

    async def test_pro_print_recovery_still_runs(self):
        from app.services.order_print_service import recover_pending_print_orders_once

        old = datetime.utcnow() - timedelta(seconds=60)
        await self._make_order(TENANT_PRO, print_status="PENDING", updated_at=old)

        with patch("app.services.order_print_service._execute_provider_with_frozen_route",
                   new=AsyncMock(return_value="task-1")) as provider:
            handled = await recover_pending_print_orders_once(self.db)

        self.assertEqual(handled, 1)
        provider.assert_awaited_once()

    async def test_print_recovery_free_tenant_does_not_abort_pro_tenant(self):
        from app.services.order_print_service import recover_pending_print_orders_once

        old = datetime.utcnow() - timedelta(seconds=60)
        free_order = await self._make_order(TENANT_FREE, print_status="PENDING", updated_at=old)
        pro_order = await self._make_order(TENANT_PRO, print_status="PENDING", updated_at=old)

        with patch("app.services.order_print_service._execute_provider_with_frozen_route",
                   new=AsyncMock(return_value="task-1")) as provider:
            handled = await recover_pending_print_orders_once(self.db)

        # Only the PRO order counts as handled -- the FREE one is skipped, not aborted.
        self.assertEqual(handled, 1)
        self.assertEqual(provider.await_count, 1)
        await self.db.refresh(free_order)
        await self.db.refresh(pro_order)
        self.assertEqual(free_order.print_status, "PENDING")
        self.assertEqual(pro_order.print_status, "SUCCESS")


# ---------------------------------------------------------------------------
# MARKETING_AUTOMATION -- subscribe_message_service send functions
# ---------------------------------------------------------------------------
class SubscribeMessageGateTest(D1BBaseTest):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self._settings_patch = patch.multiple(
            settings,
            WECHAT_ORDER_SUCCESS_TEMPLATE_ID="tpl-order-success",
            WECHAT_PICKUP_REMINDER_TEMPLATE_ID="tpl-pickup",
            WECHAT_QUEUE_REMINDER_TEMPLATE_ID="tpl-queue",
        )
        self._settings_patch.start()

    async def asyncTearDown(self):
        self._settings_patch.stop()
        await super().asyncTearDown()

    async def test_free_order_success_message_skipped_core_flow_succeeds(self):
        from app.services.subscribe_message_service import send_order_success_subscribe

        customer = await self._make_customer(TENANT_FREE)
        order = await self._make_order(TENANT_FREE, customer_id=customer.id)

        with patch("app.services.wechat_service.WechatService.send_subscribe_message",
                   new=AsyncMock(return_value=True)) as send_mock:
            sent = await send_order_success_subscribe(self.db, order)

        self.assertFalse(sent)
        send_mock.assert_not_called()

    async def test_standard_order_success_message_skipped_core_flow_succeeds(self):
        from app.services.subscribe_message_service import send_order_success_subscribe

        customer = await self._make_customer(TENANT_STANDARD)
        order = await self._make_order(TENANT_STANDARD, customer_id=customer.id)

        with patch("app.services.wechat_service.WechatService.send_subscribe_message",
                   new=AsyncMock(return_value=True)) as send_mock:
            sent = await send_order_success_subscribe(self.db, order)

        self.assertFalse(sent)
        send_mock.assert_not_called()

    async def test_pro_order_success_message_still_runs(self):
        from app.services.subscribe_message_service import send_order_success_subscribe

        customer = await self._make_customer(TENANT_PRO)
        order = await self._make_order(TENANT_PRO, customer_id=customer.id)

        with patch("app.services.wechat_service.WechatService.send_subscribe_message",
                   new=AsyncMock(return_value=True)) as send_mock:
            sent = await send_order_success_subscribe(self.db, order)

        self.assertTrue(sent)
        send_mock.assert_awaited_once()

    async def test_non_pro_pickup_reminder_skipped_status_succeeds(self):
        from app.api.v1.orders import update_order_status, OrderStatusUpdate
        from app.services.order_lifecycle_service import OrderLifecycleService

        customer = await self._make_customer(TENANT_STANDARD)
        order = await self._make_order(
            TENANT_STANDARD, status="preparing", payment_mode="prepay",
            payment_status="paid", customer_id=customer.id,
        )
        service = OrderLifecycleService(self.db)
        service.set_tenant_id(TENANT_STANDARD)

        with patch("app.services.wechat_service.WechatService.send_subscribe_message",
                   new=AsyncMock(return_value=True)) as send_mock:
            result = await service.update_order_status(
                order.id, OrderStatusUpdate(status="done"), account_id=None, role="owner",
            )

        self.assertEqual(result.code, 200)
        await self.db.refresh(order)
        self.assertEqual(order.status, "done")
        send_mock.assert_not_called()

    async def test_non_pro_queue_reminder_skipped_status_succeeds(self):
        from app.services.queue_service import QueueService

        ticket = QueueTicket(
            tenant_id=TENANT_STANDARD, queue_no="A001", queue_type="A",
            queue_date=datetime.utcnow().date(), daily_sequence=1,
            query_token=uuid.uuid4().hex, party_size=2, status="waiting",
            openid="wx-queue-openid",
        )
        self.db.add(ticket)
        await self.db.commit()

        with patch("app.services.wechat_service.WechatService.send_subscribe_message",
                   new=AsyncMock(return_value=True)) as send_mock:
            called = await QueueService(self.db).call_next(TENANT_STANDARD, "A")

        self.assertIsNotNone(called)
        self.assertEqual(called.status, "called")
        send_mock.assert_not_called()

    async def test_pro_message_regression_queue_reminder_still_runs(self):
        from app.services.queue_service import QueueService

        ticket = QueueTicket(
            tenant_id=TENANT_PRO, queue_no="A001", queue_type="A",
            queue_date=datetime.utcnow().date(), daily_sequence=1,
            query_token=uuid.uuid4().hex, party_size=2, status="waiting",
            openid="wx-queue-openid",
        )
        self.db.add(ticket)
        await self.db.commit()

        with patch("app.services.wechat_service.WechatService.send_subscribe_message",
                   new=AsyncMock(return_value=True)) as send_mock:
            called = await QueueService(self.db).call_next(TENANT_PRO, "A")

        self.assertIsNotNone(called)
        self.assertEqual(called.status, "called")
        send_mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# MARKETING_AUTOMATION -- app.main background loops, per-tenant / per-coupon
# isolation. Both loops are `while True: ... await asyncio.sleep(INTERVAL)`;
# a fake sleep that raises after the startup delay + one full iteration lets
# the real loop body run exactly once without hanging or needing any
# production refactor.
# ---------------------------------------------------------------------------
class _StopLoop(Exception):
    pass


def _bounded_sleep(stop_after_call):
    calls = {"n": 0}

    async def _fake_sleep(_seconds):
        calls["n"] += 1
        if calls["n"] >= stop_after_call:
            raise _StopLoop()

    return _fake_sleep


class MarketingBackgroundLoopIsolationTest(D1BBaseTest):
    async def test_marketing_recall_free_skipped_pro_continues(self):
        import app.main as main_module

        outcomes = []

        async def fake_batch_issue_recall_coupon(self, *args, **kwargs):
            outcomes.append(self.tenant_id)
            return {"success_count": 0}

        with patch("asyncio.sleep", new=_bounded_sleep(2)), \
             patch("app.services.coupon_service.CouponService.batch_issue_recall_coupon",
                   new=fake_batch_issue_recall_coupon):
            with self.assertRaises(_StopLoop):
                await main_module._marketing_recall_loop()

        self.assertNotIn(TENANT_FREE, outcomes)
        self.assertNotIn(TENANT_STANDARD, outcomes)  # MARKETING_AUTOMATION is PRO-only
        self.assertIn(TENANT_PRO, outcomes)

    async def test_marketing_recall_entitlement_error_does_not_abort_batch(self):
        import app.main as main_module

        outcomes = []

        async def fake_batch_issue_recall_coupon(self, *args, **kwargs):
            outcomes.append(self.tenant_id)
            return {"success_count": 0}

        original_has_capability = None
        from app.services.entitlement_service import EntitlementService

        async def flaky_has_capability(self, tenant_id, capability):
            if tenant_id == TENANT_FREE:
                raise RuntimeError("entitlement backend unavailable")
            return await original_has_capability(self, tenant_id, capability)

        original_has_capability = EntitlementService.has_capability

        with patch("asyncio.sleep", new=_bounded_sleep(2)), \
             patch("app.services.coupon_service.CouponService.batch_issue_recall_coupon",
                   new=fake_batch_issue_recall_coupon), \
             patch.object(EntitlementService, "has_capability", new=flaky_has_capability):
            with self.assertRaises(_StopLoop):
                await main_module._marketing_recall_loop()

        # TENANT_FREE's entitlement check errors -> fail-safe skip, but the
        # batch must still reach the PRO tenant afterwards.
        self.assertNotIn(TENANT_FREE, outcomes)
        self.assertIn(TENANT_PRO, outcomes)

    async def test_coupon_expiry_reminder_non_pro_skipped(self):
        import app.main as main_module

        near_expiry = datetime.utcnow() + timedelta(hours=5)
        free_customer = await self._make_customer(TENANT_FREE, openid="wx-free-coupon")
        pro_customer = await self._make_customer(TENANT_PRO, openid="wx-pro-coupon")
        free_template = CouponTemplate(
            tenant_id=TENANT_FREE, name="到期券", type="FIXED", value=5,
            start_time=datetime.utcnow() - timedelta(days=1), end_time=near_expiry,
        )
        pro_template = CouponTemplate(
            tenant_id=TENANT_PRO, name="到期券", type="FIXED", value=5,
            start_time=datetime.utcnow() - timedelta(days=1), end_time=near_expiry,
        )
        self.db.add_all([free_template, pro_template])
        await self.db.commit()
        free_coupon = Coupon(
            tenant_id=TENANT_FREE, template_id=free_template.id, customer_id=free_customer.id,
            code="D1BFREECOUPON1", status="UNUSED", expire_time=near_expiry, remind_requested=True,
        )
        pro_coupon = Coupon(
            tenant_id=TENANT_PRO, template_id=pro_template.id, customer_id=pro_customer.id,
            code="D1BPROCOUPON1", status="UNUSED", expire_time=near_expiry, remind_requested=True,
        )
        self.db.add_all([free_coupon, pro_coupon])
        await self.db.commit()

        with patch("asyncio.sleep", new=_bounded_sleep(2)), \
             patch.object(settings, "WECHAT_COUPON_REMINDER_TEMPLATE_ID", "tpl-expiry"), \
             patch("app.services.wechat_service.WechatService.send_subscribe_message",
                   new=AsyncMock(return_value=True)) as send_mock:
            with self.assertRaises(_StopLoop):
                await main_module._coupon_expiry_reminder_loop()

        self.assertEqual(send_mock.await_count, 1)
        await self.db.refresh(free_coupon)
        await self.db.refresh(pro_coupon)
        self.assertIsNone(free_coupon.remind_sent_at)
        self.assertIsNotNone(pro_coupon.remind_sent_at)

    async def test_coupon_expiry_reminder_does_not_change_coupon_validity(self):
        import app.main as main_module

        near_expiry = datetime.utcnow() + timedelta(hours=5)
        free_customer = await self._make_customer(TENANT_FREE, openid="wx-free-coupon-2")
        free_template = CouponTemplate(
            tenant_id=TENANT_FREE, name="到期券", type="FIXED", value=5,
            start_time=datetime.utcnow() - timedelta(days=1), end_time=near_expiry,
        )
        self.db.add(free_template)
        await self.db.commit()
        free_coupon = Coupon(
            tenant_id=TENANT_FREE, template_id=free_template.id, customer_id=free_customer.id,
            code="D1BFREECOUPON2", status="UNUSED", expire_time=near_expiry, remind_requested=True,
        )
        self.db.add(free_coupon)
        await self.db.commit()

        with patch("asyncio.sleep", new=_bounded_sleep(2)), \
             patch.object(settings, "WECHAT_COUPON_REMINDER_TEMPLATE_ID", "tpl-expiry"), \
             patch("app.services.wechat_service.WechatService.send_subscribe_message",
                   new=AsyncMock(return_value=True)) as send_mock:
            with self.assertRaises(_StopLoop):
                await main_module._coupon_expiry_reminder_loop()

        send_mock.assert_not_called()
        await self.db.refresh(free_coupon)
        # Entitlement gating a reminder message must never touch coupon
        # validity/status/expiry -- only the reminder itself is skipped.
        self.assertEqual(free_coupon.status, "UNUSED")
        self.assertEqual(free_coupon.expire_time, near_expiry)
        self.assertIsNone(free_coupon.remind_sent_at)


if __name__ == "__main__":
    unittest.main()
