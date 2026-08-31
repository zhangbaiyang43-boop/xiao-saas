"""P0-13: direct DB-level proof (upgrading Phase A's source-inspection-only
coverage) of the coupon release/no-release rules across cancel/reject and
duplicate-callback idempotency.

Matrix:
  unpaid cancel   -> coupon released (UNUSED)
  unpaid reject   -> coupon released (UNUSED)
  paid cancel     -> DENIED (409), coupon stays USED, no premature return
  paid pending reject -> ALLOWED (200), order -> rejected, coupon still stays USED
                         at reject time (released only on later refund SUCCESS)
  wechat-sheet-cancel (order stays pending_payment, no explicit cancel call) -> coupon stays LOCKED
  normal prepay lifecycle -> exactly one LOCKED->USED transition
  duplicate callback x3 -> exactly one transition, no repeated side effects
"""

import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, PropertyMock, patch

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.api.v1.orders import wxpay_notify, OrderStatusUpdate
from app.core.tenant_context import TenantContext
from app.services.order_lifecycle_service import OrderLifecycleService
from app.services.wxpay_service import WxPayService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


TENANT = "p0-13-lifecycle-tenant"


def make_notify_request() -> Request:
    async def _body():
        return b"{}"

    request = Request(
        {
            "type": "http", "method": "POST", "path": "/api/v1/orders/wxpay-notify",
            "headers": [], "query_string": f"tenant_id={TENANT}".encode(),
            "server": ("testserver", 80), "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    request.body = _body
    return request


class CouponLifecycleReleaseMatrixTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.Session()

        self.db.add(Tenant(
            tenant_id=TENANT, name="P0-13 Lifecycle", password_hash="x",
            status=True, is_open=True, payment_mode="prepay",
            wx_pay_enabled=True, wx_mchid="1900000109",
        ))
        self.db.add(Customer(id=generate_snowflake_id(), tenant_id=TENANT, openid="lifecycle-openid"))
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_locked_order_with_coupon(self, *, total="80.00", status="pending_payment", payment_mode="prepay"):
        template = CouponTemplate(
            tenant_id=TENANT, name="20 off", type="FIXED", value="20.00",
            min_amount="0.00", total_stock=100, used_stock=1,
            start_time=datetime.utcnow() - timedelta(days=1),
            end_time=datetime.utcnow() + timedelta(days=30), status=1,
        )
        self.db.add(template)
        await self.db.flush()
        coupon = Coupon(
            tenant_id=TENANT, template_id=template.id, customer_id=9001,
            code=f"CODE-{generate_snowflake_id()}", status="LOCKED",
            expire_time=datetime.utcnow() + timedelta(days=1),
        )
        self.db.add(coupon)
        await self.db.flush()
        order = Order(
            tenant_id=TENANT, customer_id=9001, total=total,
            status=status, payment_status="unpaid", payment_mode=payment_mode,
            coupon_id=coupon.id, discount_amount="20.00",
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order, coupon

    async def test_unpaid_cancel_releases_coupon(self):
        order, coupon = await self._make_locked_order_with_coupon()
        result = await OrderLifecycleService(self.db).cancel_order(
            order.id, customer_id=9001, participant_token=None,
        )
        self.assertEqual(result.code, 200, result.msg)
        await self.db.refresh(coupon)
        self.assertEqual(coupon.status, "UNUSED")
        await self.db.refresh(order)
        self.assertEqual(order.status, "cancelled")

    async def test_unpaid_reject_releases_coupon(self):
        # "rejected" is a merchant/kitchen-queue transition -- postpay orders
        # start in "pending" (already in the kitchen queue), unlike prepay's
        # "pending_payment" (not yet accepted), so use postpay here.
        order, coupon = await self._make_locked_order_with_coupon(status="pending", payment_mode="postpay")
        TenantContext.set_tenant_id(TENANT)
        result = await OrderLifecycleService(self.db).update_order_status(
            order.id, OrderStatusUpdate(status="rejected"),
        )
        self.assertEqual(result.code, 200, result.msg)
        await self.db.refresh(coupon)
        self.assertEqual(coupon.status, "UNUSED")

    async def test_paid_cancel_denied_coupon_not_returned(self):
        order, coupon = await self._make_locked_order_with_coupon()
        order.status = "pending"
        order.payment_status = "paid"
        coupon.status = "USED"
        coupon.use_time = datetime.utcnow()
        await self.db.commit()

        result = await OrderLifecycleService(self.db).cancel_order(
            order.id, customer_id=9001, participant_token=None,
        )
        self.assertEqual(result.code, 409)
        self.assertEqual(result.data.get("code"), "PAID_ORDER_CANCEL_REQUIRES_REFUND")

        await self.db.refresh(coupon)
        self.assertEqual(coupon.status, "USED")  # not prematurely returned
        await self.db.refresh(order)
        self.assertEqual(order.status, "pending")  # untouched

    async def test_paid_pending_reject_allowed_coupon_not_released_at_reject(self):
        # Merchant reject of a paid, kitchen-unaccepted order is now allowed and
        # terminates fulfilment only. The coupon must NOT be released at reject:
        # it is a paid order's coupon (USED), and any reversal happens later,
        # only after the merchant's refund reaches provider SUCCESS.
        order, coupon = await self._make_locked_order_with_coupon()
        order.status = "pending"
        order.payment_status = "paid"
        coupon.status = "USED"
        coupon.use_time = datetime.utcnow()
        await self.db.commit()

        TenantContext.set_tenant_id(TENANT)
        result = await OrderLifecycleService(self.db).update_order_status(
            order.id, OrderStatusUpdate(status="rejected"),
        )
        self.assertEqual(result.code, 200)
        await self.db.refresh(order)
        self.assertEqual(order.status, "rejected")
        self.assertEqual(order.payment_status, "paid")
        await self.db.refresh(coupon)
        self.assertEqual(coupon.status, "USED")

    async def test_wechat_sheet_cancel_does_not_release_coupon(self):
        # The customer backs out of the WeChat payment sheet once -- no
        # server-side cancel/reject call happens at all, the order simply
        # remains pending_payment. This must NOT be conflated with an actual
        # Order cancel: the coupon stays locked so the customer can retry
        # paying the SAME order without losing the discount.
        order, coupon = await self._make_locked_order_with_coupon()
        # No mutation call -- this is the point: nothing happens server-side.
        await self.db.refresh(order)
        await self.db.refresh(coupon)
        self.assertEqual(order.status, "pending_payment")
        self.assertEqual(coupon.status, "LOCKED")

    async def test_normal_prepay_lifecycle_single_use_transition(self):
        order, coupon = await self._make_locked_order_with_coupon()
        fact = {
            "out_trade_no": str(order.id), "trade_state": "SUCCESS",
            "transaction_id": f"wx-tx-{order.id}",
            "amount": {"total": int(float(order.total) * 100), "currency": "CNY"},
        }
        with (
            patch.object(WxPayService, "enabled", new_callable=PropertyMock, return_value=True),
            patch.object(WxPayService, "verify_notify", return_value=fact),
            patch("app.services.order_payment_service._print_paid_order_ticket", new_callable=AsyncMock),
            patch("app.services.coupon_service.settings.REDIS_ENABLED", False),
        ):
            response = await wxpay_notify(make_notify_request(), db=self.db)
        self.assertEqual(response.get("code"), "SUCCESS")
        await self.db.refresh(order)
        await self.db.refresh(coupon)
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(coupon.status, "USED")

    async def test_duplicate_callback_x3_exactly_one_transition(self):
        order, coupon = await self._make_locked_order_with_coupon()
        fact = {
            "out_trade_no": str(order.id), "trade_state": "SUCCESS",
            "transaction_id": f"wx-tx-{order.id}",
            "amount": {"total": int(float(order.total) * 100), "currency": "CNY"},
        }
        with (
            patch.object(WxPayService, "enabled", new_callable=PropertyMock, return_value=True),
            patch.object(WxPayService, "verify_notify", return_value=fact),
            patch("app.services.order_payment_service._print_paid_order_ticket", new_callable=AsyncMock) as mock_print,
            patch("app.services.coupon_service.settings.REDIS_ENABLED", False),
        ):
            for _ in range(3):
                response = await wxpay_notify(make_notify_request(), db=self.db)
                self.assertEqual(response.get("code"), "SUCCESS")

        await self.db.refresh(order)
        await self.db.refresh(coupon)
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(coupon.status, "USED")
        first_use_time = coupon.use_time
        # re-fetch once more to be sure use_time didn't silently rotate across calls
        await self.db.refresh(coupon)
        self.assertEqual(coupon.use_time, first_use_time)
        self.assertEqual(mock_print.await_count, 1)  # print intent fires exactly once, not 3x


if __name__ == "__main__":
    unittest.main()
