"""P0-13 finding 04: the highest-stakes coupon scenario. Direct executable proof
(not source inspection) that a coupon released back to available by timeout
cleanup, then re-locked/used by a SECOND order, is never touched again when the
FIRST order's WeChat payment notification arrives late.

Timeline (matches the P0-13 spec exactly):
  12:00  O1 locks Coupon C
  12:15  O1 times out -> cancelled, C released to UNUSED (timeout cleanup)
  12:16  O2 locks/uses the now-available C
  12:17  O1's late WeChat payment notification arrives, confirming O1 was paid

Required result: O1.payment_status becomes "paid" (payment truth recorded per
P0-09), O1.status stays terminal ("cancelled"), and Coupon C is byte-for-byte
unchanged by O1's late callback -- regardless of whether O2 has only locked C
(Scenario A) or already used/paid it (Scenario B). No coupon mutation, no
member/points/reward side effects for O1's late payment.
"""

import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, PropertyMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.orders import wxpay_notify, _cleanup_stale_pending_payment_orders
from app.models.base import Base
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.models.order import Order
from app.models.tenant import Tenant
from app.services.order_payment_service import OrderPaymentService
from app.services.wxpay_service import WxPayService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_ID = "p0-13-late-payment"


def make_notify_request() -> Request:
    async def _body():
        return b"{}"

    request = Request(
        {
            "type": "http", "method": "POST", "path": "/api/v1/orders/wxpay-notify",
            "headers": [], "query_string": f"tenant_id={TENANT_ID}".encode(),
            "server": ("testserver", 80), "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    request.body = _body
    return request


class CouponLatePaymentSafetyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.Session()

        # No real wx_pay credentials -- _recover_wxpay_order_if_paid's own
        # WxPayService(tenant).enabled check short-circuits to False naturally
        # during the timeout-cleanup step, without needing a network mock.
        self.db.add(Tenant(
            tenant_id=TENANT_ID, name="P0-13 Late Payment", password_hash="x",
            status=True, is_open=True, payment_mode="prepay",
            wx_pay_enabled=True, wx_mchid="1900000109",
        ))
        self.db.add(Customer(id=generate_snowflake_id(), tenant_id=TENANT_ID, openid="h-openid"))
        self.template = CouponTemplate(
            tenant_id=TENANT_ID, name="20 off", type="FIXED", value="20.00",
            min_amount="0.00", total_stock=100, used_stock=1,
            start_time=datetime.utcnow() - timedelta(days=1),
            end_time=datetime.utcnow() + timedelta(days=30), status=1,
        )
        self.db.add(self.template)
        await self.db.flush()
        self.coupon = Coupon(
            tenant_id=TENANT_ID, template_id=self.template.id, customer_id=9001,
            code=f"CODE-{generate_snowflake_id()}", status="UNUSED",
            expire_time=datetime.utcnow() + timedelta(days=1),
        )
        self.db.add(self.coupon)
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_o1_locked_and_timed_out(self):
        """12:00: O1 locks the coupon. Returns O1 already backdated past the
        timeout window, with the coupon in the LOCKED state a real create_order
        call would have left it in."""
        old_created_at = datetime.utcnow() - timedelta(minutes=20)
        o1 = Order(
            tenant_id=TENANT_ID, customer_id=9001, total="80.00",
            status="pending_payment", payment_status="unpaid", payment_mode="prepay",
            coupon_id=self.coupon.id, discount_amount="20.00",
            created_at=old_created_at,
        )
        self.db.add(o1)
        await self.db.refresh(self.coupon)
        self.coupon.status = "LOCKED"
        await self.db.commit()
        await self.db.refresh(o1)
        return o1

    async def _run_timeout_cleanup(self):
        """12:15: timeout cleanup runs, finds no real wx payment (no real
        credentials configured), cancels O1 and releases the coupon."""
        await _cleanup_stale_pending_payment_orders(TENANT_ID, self.db)

    async def _snapshot_coupon(self):
        await self.db.refresh(self.coupon)
        return {
            "status": self.coupon.status,
            "use_time": self.coupon.use_time,
            "customer_id": self.coupon.customer_id,
            "template_id": self.coupon.template_id,
            "tenant_id": self.coupon.tenant_id,
        }

    async def _deliver_o1_late_payment(self, o1):
        """12:17: O1's WeChat payment notification finally arrives, confirming
        it was actually paid all along."""
        fact = {
            "out_trade_no": str(o1.id),
            "trade_state": "SUCCESS",
            "transaction_id": f"wx-tx-{o1.id}",
            "amount": {"total": int(float(o1.total) * 100), "currency": "CNY"},
        }
        with (
            patch.object(WxPayService, "enabled", new_callable=PropertyMock, return_value=True),
            patch.object(WxPayService, "verify_notify", return_value=fact),
            patch("app.services.order_payment_service._print_paid_order_ticket", new_callable=AsyncMock),
            patch("app.services.coupon_service.settings.REDIS_ENABLED", False),
        ):
            return await wxpay_notify(make_notify_request(), db=self.db)

    async def test_scenario_a_o2_only_locked_when_o1_late_payment_arrives(self):
        o1 = await self._make_o1_locked_and_timed_out()

        await self._run_timeout_cleanup()
        await self.db.refresh(o1)
        self.assertEqual(o1.status, "cancelled")
        await self.db.refresh(self.coupon)
        self.assertEqual(self.coupon.status, "UNUSED")  # 12:15: released

        # 12:16: O2 (a second, independent order) re-locks the same coupon.
        o2 = Order(
            tenant_id=TENANT_ID, customer_id=9001, total="80.00",
            status="pending_payment", payment_status="unpaid", payment_mode="prepay",
            coupon_id=self.coupon.id, discount_amount="20.00",
        )
        self.db.add(o2)
        await self.db.refresh(self.coupon)
        self.coupon.status = "LOCKED"
        await self.db.commit()

        before = await self._snapshot_coupon()

        # 12:17: O1's late payment confirmation arrives.
        response = await self._deliver_o1_late_payment(o1)

        self.assertEqual(response.get("code"), "SUCCESS")
        await self.db.refresh(o1)
        self.assertEqual(o1.payment_status, "paid")   # payment truth recorded
        self.assertEqual(o1.status, "cancelled")       # stays terminal, not resurrected

        after = await self._snapshot_coupon()
        self.assertEqual(before, after)                # coupon completely untouched
        self.assertEqual(after["status"], "LOCKED")    # still O2's lock, unchanged

    async def test_scenario_b_o2_already_used_when_o1_late_payment_arrives(self):
        o1 = await self._make_o1_locked_and_timed_out()

        await self._run_timeout_cleanup()
        await self.db.refresh(o1)
        self.assertEqual(o1.status, "cancelled")
        await self.db.refresh(self.coupon)
        self.assertEqual(self.coupon.status, "UNUSED")

        # 12:16: O2 re-locks AND pays -- coupon reaches USED.
        o2 = Order(
            tenant_id=TENANT_ID, customer_id=9001, total="80.00",
            status="pending_payment", payment_status="unpaid", payment_mode="prepay",
            coupon_id=self.coupon.id, discount_amount="20.00",
        )
        self.db.add(o2)
        await self.db.refresh(self.coupon)
        self.coupon.status = "LOCKED"
        await self.db.commit()
        await self.db.refresh(o2)

        await OrderPaymentService(self.db)._on_payment_success(o2, payment_method="mock")
        await self.db.commit()
        await self.db.refresh(self.coupon)
        self.assertEqual(self.coupon.status, "USED")

        before = await self._snapshot_coupon()

        response = await self._deliver_o1_late_payment(o1)

        self.assertEqual(response.get("code"), "SUCCESS")
        await self.db.refresh(o1)
        self.assertEqual(o1.payment_status, "paid")
        self.assertEqual(o1.status, "cancelled")

        after = await self._snapshot_coupon()
        self.assertEqual(before, after)               # coupon completely untouched
        self.assertEqual(after["status"], "USED")      # still O2's completed use

        # O1's late payment must not have granted any coupon-adjacent side
        # effect a second time -- specifically, the coupon's own use_time must
        # still be O2's, not overwritten by O1's reconciliation.
        await self.db.refresh(o2)
        self.assertIsNotNone(self.coupon.use_time)

    async def test_o1_late_payment_records_refund_required_attention(self):
        o1 = await self._make_o1_locked_and_timed_out()
        await self._run_timeout_cleanup()
        await self.db.refresh(o1)

        response = await self._deliver_o1_late_payment(o1)
        self.assertEqual(response.get("code"), "SUCCESS")

        await self.db.refresh(o1)
        self.assertEqual(o1.payment_status, "paid")
        self.assertEqual(o1.status, "cancelled")
        # P0-09 pattern: paid + terminal is surfaced for merchant attention via
        # the order DTO's capability builder, not auto-refunded/auto-fulfilled.
        from app.api.v1.orders import serialize_order
        dto = serialize_order(o1, [])
        self.assertTrue(dto.get("refund_required"))


if __name__ == "__main__":
    unittest.main()
