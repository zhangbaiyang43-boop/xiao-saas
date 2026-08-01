import asyncio
import unittest
from datetime import datetime
from unittest.mock import PropertyMock, patch

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.order import Order
from app.models.tenant import Tenant
from app.api.v1.orders import wxpay_notify
from app.services.wxpay_service import WxPayService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


def make_notify_request(tenant_id=TENANT_A):
    async def _body():
        return b"{}"

    req = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/orders/wxpay-notify",
            "headers": [],
            "query_string": f"tenant_id={tenant_id}".encode(),
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    req.body = _body
    return req


class WxpayAmountReconciliationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(
            tenant_id=TENANT_A, name="Test Restaurant", password_hash="x",
            status=True, is_open=True, payment_mode="prepay",
            wx_pay_enabled=True, wx_mchid="1900000109",
        )
        self.db.add(self.tenant)
        await self.db.flush()

        self.order = Order(
            tenant_id=TENANT_A, total="28.00", status="pending_payment",
            payment_status="unpaid", payment_mode="prepay",
        )
        self.db.add(self.order)
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _fake_resource(self, paid_fen):
        return {
            "out_trade_no": str(self.order.id),
            "trade_state": "SUCCESS",
            "amount": {"total": paid_fen, "payer_total": paid_fen, "currency": "CNY"},
        }

    async def test_mismatched_callback_amount_is_rejected_and_order_stays_unpaid(self):
        with patch.object(WxPayService, "enabled", new_callable=PropertyMock, return_value=True), \
             patch.object(WxPayService, "verify_notify", return_value=self._fake_resource(1)):
            # order.total is 28.00 元 (2800 分)；回调却只带来 1 分钱的确认，必须被拒绝
            result = await wxpay_notify(make_notify_request(), db=self.db)

        self.assertEqual(result.get("code"), "FAIL")
        await self.db.refresh(self.order)
        self.assertEqual(self.order.payment_status, "unpaid")
        self.assertEqual(self.order.status, "pending_payment")

    async def test_matching_callback_amount_marks_order_paid(self):
        with patch.object(WxPayService, "enabled", new_callable=PropertyMock, return_value=True), \
             patch.object(WxPayService, "verify_notify", return_value=self._fake_resource(2800)):
            result = await wxpay_notify(make_notify_request(), db=self.db)

        self.assertEqual(result.get("code"), "SUCCESS")
        await self.db.refresh(self.order)
        self.assertEqual(self.order.payment_status, "paid")


if __name__ == "__main__":
    unittest.main()
