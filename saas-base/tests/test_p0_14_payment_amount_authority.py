"""P0-14: server final amount authority -- WeChat Pay amount boundary.

Phase A audit found that MONEY-07 (WxPay amount.total == persisted authoritative
order amount) and MONEY-08 (payment retry keeps the same amount) were already
PROVEN by direct code reading (order_payment_service.py: pay_amount is always
re-read from the persisted Order row, never from a client payload), but test
coverage was only a static source-text check (test_order_amount_security_
contracts.py:test_wxpay_amount_uses_server_order_total) -- no test actually
invoked OrderPaymentService.create_wxpay_order and inspected the amount sent to
a mocked WeChat Pay client. This file closes that gap with genuine runtime
contracts. It does not re-litigate P0-02 (menu/order price authority) or P0-06
(payment callback truth) -- those are already covered elsewhere.

Runtime mutation search performed before writing these tests (see Phase B
report): grepped the whole app/ tree for any ".total =" assignment, any
"update(Order)"/"values(total=", and any raw "UPDATE orders SET" -- zero
matches. Order.total is written exactly once, at construction in
_persist_create_order_and_build_response (orders.py:1069-1078). No real
runtime path exists that could mutate it after creation, so the TOCTOU
nuance in create_wxpay_order (pay_amount computed from a non-locked read,
before the later FOR UPDATE re-lock) is not exercised as a genuine RED here --
per the task's own instruction not to fabricate an unreachable race. It is
recorded as an accepted P2 residual in the Phase B report instead.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.config import settings
from app.models.base import Base
from app.models.customer import Customer
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.api.v1.orders import WxPayBody, create_order, OrderCreate, OrderItemIn
from app.services.order_payment_service import OrderPaymentService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


TENANT_A = "tenant-a"


def make_customer_request(customer_id, openid="wx-openid-1"):
    req = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/orders",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    req.state.customer_id = customer_id
    req.state.openid = openid
    return req


def mocked_wxpay_service():
    """Patch only the provider boundary (WxPayService.create_jsapi_order),
    never the money computation inside create_wxpay_order itself."""
    mock_cls = patch("app.services.wxpay_service.WxPayService")
    mock_instance = mock_cls.start()
    mock_instance.return_value.enabled = True
    mock_instance.return_value.create_jsapi_order = AsyncMock(
        return_value={
            "timeStamp": "1700000000",
            "nonceStr": "abc123",
            "package": "prepay_id=wx000000000000000000000000000000",
            "signType": "RSA",
            "paySign": "sig",
        }
    )
    return mock_cls, mock_instance.return_value


class WxPayAmountBoundaryTest(unittest.IsolatedAsyncioTestCase):
    """A01/A02/A03: WxPay amount_fen comes from persisted Order.total, not any
    client-supplied field -- WxPayBody has none to supply in the first place."""

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(
            tenant_id=TENANT_A, name="Restaurant A", password_hash="x",
            status=True, is_open=True, payment_mode="prepay",
        )
        self.customer = Customer(tenant_id=TENANT_A, openid="wx-openid-1")
        self.db.add_all([self.tenant, self.customer])
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_pending_payment_order(self, total: str) -> Order:
        order = Order(
            tenant_id=TENANT_A,
            customer_id=self.customer.id,
            table_no="",
            total=total,
            status="pending_payment",
            payment_status="unpaid",
            payment_mode="prepay",
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    def test_wxpay_body_schema_has_no_client_amount_field(self):
        # Section 9: prove WxPayBody cannot carry amount/total/pay_amount at all --
        # a real Pydantic model_fields introspection, not a source-text grep.
        fields = set(WxPayBody.model_fields.keys())
        self.assertEqual(fields, {"js_code", "participant_token"})
        for dangerous in ("amount", "total", "pay_amount", "amount_fen"):
            self.assertNotIn(dangerous, fields)

    async def _assert_amount_fen(self, total: str, expected_fen: int):
        order = await self._make_pending_payment_order(total)
        mock_cls, wxpay_instance = mocked_wxpay_service()
        try:
            result = await OrderPaymentService(self.db).create_wxpay_order(
                str(order.id), WxPayBody(), make_customer_request(self.customer.id)
            )
        finally:
            mock_cls.stop()
        self.assertEqual(result.code, 200)
        wxpay_instance.create_jsapi_order.assert_awaited_once()
        amount_fen = wxpay_instance.create_jsapi_order.call_args.kwargs["amount_fen"]
        self.assertEqual(amount_fen, expected_fen)

    async def test_A01_wxpay_amount_for_19_90_order(self):
        await self._assert_amount_fen("19.90", 1990)

    async def test_A02_wxpay_amount_for_0_01_order(self):
        await self._assert_amount_fen("0.01", 1)

    async def test_A03_wxpay_amount_for_99_99_order(self):
        await self._assert_amount_fen("99.99", 9999)

    async def test_A04_payment_retry_returns_identical_amount(self):
        order = await self._make_pending_payment_order("19.90")
        mock_cls, wxpay_instance = mocked_wxpay_service()
        try:
            result_1 = await OrderPaymentService(self.db).create_wxpay_order(
                str(order.id), WxPayBody(), make_customer_request(self.customer.id)
            )
            result_2 = await OrderPaymentService(self.db).create_wxpay_order(
                str(order.id), WxPayBody(), make_customer_request(self.customer.id)
            )
        finally:
            mock_cls.stop()
        self.assertEqual(result_1.code, 200)
        self.assertEqual(result_2.code, 200)
        self.assertEqual(wxpay_instance.create_jsapi_order.await_count, 2)
        fen_1 = wxpay_instance.create_jsapi_order.call_args_list[0].kwargs["amount_fen"]
        fen_2 = wxpay_instance.create_jsapi_order.call_args_list[1].kwargs["amount_fen"]
        self.assertEqual(fen_1, 1990)
        self.assertEqual(fen_2, 1990)
        await self.db.refresh(order)
        self.assertEqual(str(order.total), "19.90")


class OrderPriceSnapshotThenPaymentTest(unittest.IsolatedAsyncioTestCase):
    """A05/A06: an order created against Dish.price=28 must keep charging 28
    even after the merchant later changes the menu price to 32 -- both for the
    persisted snapshot (A05) and for the WxPay amount actually sent (A06),
    the single highest-value combined proof per the task's own Section 13."""

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(
            tenant_id=TENANT_A, name="Restaurant A", password_hash="x",
            status=True, is_open=True, payment_mode="prepay",
        )
        self.customer = Customer(tenant_id=TENANT_A, openid="wx-openid-1")
        self.db.add_all([self.tenant, self.customer])
        await self.db.flush()

        self.dish = MenuItem(tenant_id=TENANT_A, name="宫保鸡丁", price="28.00", available=True)
        self.db.add(self.dish)
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _make_request(self):
        req = Request(
            {
                "type": "http", "method": "POST", "path": "/api/v1/orders",
                "headers": [], "query_string": b"", "server": ("testserver", 80),
                "scheme": "http", "client": ("testclient", 50000),
            }
        )
        req.state.customer_id = self.customer.id
        req.state.openid = "wx-openid-1"
        return req

    async def test_A05_A06_price_snapshot_immutable_through_menu_change_and_payment(self):
        body = OrderCreate(
            shop=TENANT_A, table="",
            items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=28.00, qty=1)],
            total=28.00,
        )
        create_result = await create_order(body, self._make_request(), db=self.db)
        self.assertEqual(create_result.code, 200)
        order_id = create_result.data["order_id"]

        # A05: persisted snapshot is 28 right after creation.
        order = (await self.db.execute(select(Order).where(Order.id == order_id))).scalar_one()
        item = (await self.db.execute(select(OrderItem).where(OrderItem.order_id == order_id))).scalars().one()
        self.assertEqual(str(order.total), "28.00")
        self.assertEqual(str(item.price), "28.00")

        # Merchant changes the menu price -- via direct model update, since the
        # object under test is order-snapshot immutability, not the admin menu
        # API (already covered elsewhere).
        self.dish.price = "32.00"
        await self.db.commit()

        # A05 continued: re-fetching the OLD order must still show 28, not 32.
        # (expire only order/item, not the whole session -- expiring self.customer
        # too would force an out-of-band lazy load later and blow up under asyncio)
        self.db.expire(order)
        self.db.expire(item)
        order = (await self.db.execute(select(Order).where(Order.id == order_id))).scalar_one()
        item = (await self.db.execute(select(OrderItem).where(OrderItem.order_id == order_id))).scalars().one()
        self.assertEqual(str(order.total), "28.00")
        self.assertEqual(str(item.price), "28.00")

        # A06: paying for that same old order must still charge 28.00 -> 2800
        # fen, never 32.00 -> 3200 fen.
        mock_cls, wxpay_instance = mocked_wxpay_service()
        try:
            pay_result = await OrderPaymentService(self.db).create_wxpay_order(
                str(order_id), WxPayBody(), self._make_request()
            )
        finally:
            mock_cls.stop()
        self.assertEqual(pay_result.code, 200)
        amount_fen = wxpay_instance.create_jsapi_order.call_args.kwargs["amount_fen"]
        self.assertEqual(amount_fen, 2800)
        self.assertNotEqual(amount_fen, 3200)


if __name__ == "__main__":
    unittest.main()
