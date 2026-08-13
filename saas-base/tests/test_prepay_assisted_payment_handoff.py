"""Prepay staff-assisted add payment handoff contracts."""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import PropertyMock, patch

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.orders import OrderCreate, OrderItemIn, create_order, wxpay_notify
from app.models.base import Base
from app.models.customer import Customer
from app.models.dining import DiningSession
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.merchant_account import MerchantAccount
from app.models.merchant_account_trusted_device import MerchantAccountTrustedDevice  # noqa: F401
from app.models.merchant_account_wechat_binding import MerchantAccountWechatBinding  # noqa: F401
from app.models.order import Order, OrderItem
from app.models.staff_assisted_payment_handoff import StaffAssistedPaymentHandoff
from app.models.tenant import Tenant
from app.services.payment_handoff_service import PaymentHandoffService
from app.services.wxpay_service import WxPayService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT = "tenant-handoff-a"
STAFF_ID = 91001
CUSTOMER_ID = 88001
CUSTOMER_B_ID = 88002


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_staff_request():
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
    req.state.token_type = "merchant"
    req.state.tenant_id = TENANT
    req.state.role = "frontdesk"
    req.state.account_id = STAFF_ID
    req.state.customer_id = None
    return req


def make_member_request(path="/api/v1/payment-handoffs/token/pay"):
    req = Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    req.state.token_type = "member"
    req.state.tenant_id = TENANT
    req.state.customer_id = CUSTOMER_ID
    req.state.openid = "openid-customer-a"
    return req


def make_notify_request(order_id: int):
    async def _body():
        return b"{}"

    req = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/orders/wxpay-notify",
            "headers": [],
            "query_string": f"tenant_id={TENANT}".encode(),
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    req.body = _body
    return req


class PrepayAssistedPaymentHandoffTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.session_id = generate_snowflake_id()
        self.parent_order_id = generate_snowflake_id()
        self.dish_id = generate_snowflake_id()
        async with self.SessionLocal() as db:
            db.add_all(
                [
                    Tenant(
                        tenant_id=TENANT,
                        name="Handoff店",
                        password_hash="x",
                        phone="13900006666",
                        status=True,
                        is_open=True,
                        payment_mode="prepay",
                        wx_pay_enabled=True,
                        wx_mchid="1900000109",
                    ),
                    MerchantAccount(
                        id=STAFF_ID,
                        tenant_id=TENANT,
                        name="前台H",
                        username="fd-handoff",
                        password_hash="x",
                        role="frontdesk",
                        status="active",
                    ),
                    Customer(
                        id=CUSTOMER_ID,
                        tenant_id=TENANT,
                        openid="openid-customer-a",
                        name="顾客A",
                        phone="",
                        status=1,
                    ),
                    Customer(
                        id=CUSTOMER_B_ID,
                        tenant_id=TENANT,
                        openid="openid-customer-b",
                        name="顾客B",
                        phone="",
                        status=1,
                    ),
                    DiningSession(
                        id=self.session_id,
                        tenant_id=TENANT,
                        table_no="8",
                        status="OPEN",
                        active_key=f"{TENANT}:8",
                        started_at=datetime.utcnow(),
                        last_activity_at=datetime.utcnow(),
                    ),
                    Order(
                        id=self.parent_order_id,
                        tenant_id=TENANT,
                        dining_session_id=self.session_id,
                        table_no="8",
                        total=20,
                        status="pending",
                        payment_status="paid",
                        payment_mode="prepay",
                        order_type="INITIAL",
                        source="miniprogram",
                    ),
                    MenuItem(
                        id=self.dish_id,
                        tenant_id=TENANT,
                        name="小酥肉",
                        price="18.00",
                        available=True,
                        category="小吃",
                    ),
                    # P0-01: this suite is about assisted-payment handoff, not table validity.
                    EntranceCode(
                        id=generate_snowflake_id(),
                        tenant_id=TENANT, name="8", scene="E000000000008",
                        table_no="8", entry_type="table", status=1,
                    ),
                ]
            )
            await db.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _create_staff_prepay_order(self, db: AsyncSession) -> Order:
        body = OrderCreate(
            shop=TENANT,
            table="8",
            dining_session_id=self.session_id,
            # P0-02: use the dish's real server price (18.00) instead of the old
            # 0.01 placeholder -- this suite is about assisted payment handoff, not
            # pricing, so the fixture should reflect a realistic order.
            items=[OrderItemIn(dish_id=self.dish_id, name="小酥肉", price=18.0, qty=1)],
            total=0.01,
            request_id="handoff-order-1",
        )
        with patch("app.api.v1.orders._spawn_background_print_task"):
            res = await create_order(body, make_staff_request(), db)
        self.assertEqual(res.code, 200)
        return (
            await db.execute(select(Order).where(Order.client_request_id == "handoff-order-1"))
        ).scalar_one()

    async def test_create_handoff_returns_short_scene_without_storing_raw_token(self):
        async with self.SessionLocal() as db:
            order = await self._create_staff_prepay_order(db)
            result = await PaymentHandoffService(db).create_for_order(
                tenant_id=TENANT,
                order_id=int(order.id),
                actor_account_id=STAFF_ID,
                actor_role="frontdesk",
            )
            await db.commit()

            self.assertLessEqual(len(result["scene"]), 32)
            self.assertEqual(result["page"], "subpkg-order/pages/payment-handoff")
            handoff = (
                await db.execute(select(StaffAssistedPaymentHandoff).where(
                    StaffAssistedPaymentHandoff.order_id == order.id
                ))
            ).scalar_one()
            self.assertEqual(handoff.status, "PENDING_SCAN")
            self.assertNotEqual(handoff.token_hash, result["scene"])
            self.assertEqual(handoff.created_by_account_id, STAFF_ID)

    async def test_claim_binds_customer_to_staff_order_before_payment(self):
        async with self.SessionLocal() as db:
            order = await self._create_staff_prepay_order(db)
            handoff = await PaymentHandoffService(db).create_for_order(
                tenant_id=TENANT,
                order_id=int(order.id),
                actor_account_id=STAFF_ID,
                actor_role="frontdesk",
            )
            claimed = await PaymentHandoffService(db).claim(
                token=handoff["scene"],
                customer_id=CUSTOMER_ID,
                openid="openid-customer-a",
            )
            await db.commit()

            self.assertEqual(claimed["status"], "CLAIMED")
            await db.refresh(order)
            self.assertEqual(order.customer_id, CUSTOMER_ID)
            self.assertEqual(order.status, "pending_payment")
            self.assertEqual(order.payment_status, "unpaid")

    async def test_regenerated_handoff_rejects_old_token_and_keeps_same_order(self):
        async with self.SessionLocal() as db:
            order = await self._create_staff_prepay_order(db)
            first = await PaymentHandoffService(db).create_for_order(
                tenant_id=TENANT,
                order_id=int(order.id),
                actor_account_id=STAFF_ID,
                actor_role="frontdesk",
            )
            second = await PaymentHandoffService(db).create_for_order(
                tenant_id=TENANT,
                order_id=int(order.id),
                actor_account_id=STAFF_ID,
                actor_role="frontdesk",
            )

            self.assertNotEqual(first["scene"], second["scene"])
            self.assertEqual(second["order_id"], str(order.id))

            with self.assertRaises(ValueError):
                await PaymentHandoffService(db).claim(
                    token=first["scene"],
                    customer_id=CUSTOMER_ID,
                    openid="openid-customer-a",
                )

            claimed = await PaymentHandoffService(db).claim(
                token=second["scene"],
                customer_id=CUSTOMER_ID,
                openid="openid-customer-a",
            )
            orders = (
                await db.execute(select(Order).where(Order.client_request_id == "handoff-order-1"))
            ).scalars().all()

            self.assertEqual(claimed["status"], "CLAIMED")
            self.assertEqual(claimed["order_id"], str(order.id))
            self.assertEqual(len(orders), 1)

    async def test_claim_binding_rejects_second_customer_without_overriding_first(self):
        async with self.SessionLocal() as db:
            order = await self._create_staff_prepay_order(db)
            handoff = await PaymentHandoffService(db).create_for_order(
                tenant_id=TENANT,
                order_id=int(order.id),
                actor_account_id=STAFF_ID,
                actor_role="frontdesk",
            )

            first_claim = await PaymentHandoffService(db).claim(
                token=handoff["scene"],
                customer_id=CUSTOMER_ID,
                openid="openid-customer-a",
            )
            repeat_claim = await PaymentHandoffService(db).claim(
                token=handoff["scene"],
                customer_id=CUSTOMER_ID,
                openid="openid-customer-a",
            )

            self.assertEqual(first_claim["claimed_customer_id"], str(CUSTOMER_ID))
            self.assertEqual(repeat_claim["claimed_customer_id"], str(CUSTOMER_ID))

            with self.assertRaises(ValueError):
                await PaymentHandoffService(db).claim(
                    token=handoff["scene"],
                    customer_id=CUSTOMER_B_ID,
                    openid="openid-customer-b",
                )

            row = (
                await db.execute(select(StaffAssistedPaymentHandoff).where(
                    StaffAssistedPaymentHandoff.order_id == order.id
                ))
            ).scalar_one()
            await db.refresh(order)
            self.assertEqual(row.claimed_customer_id, CUSTOMER_ID)
            self.assertEqual(row.claimed_openid, "openid-customer-a")
            self.assertEqual(order.customer_id, CUSTOMER_ID)

    async def test_expired_handoff_cannot_be_claimed(self):
        async with self.SessionLocal() as db:
            order = await self._create_staff_prepay_order(db)
            handoff = await PaymentHandoffService(db).create_for_order(
                tenant_id=TENANT,
                order_id=int(order.id),
                actor_account_id=STAFF_ID,
                actor_role="frontdesk",
            )
            row = (
                await db.execute(select(StaffAssistedPaymentHandoff).where(
                    StaffAssistedPaymentHandoff.order_id == order.id
                ))
            ).scalar_one()
            row.expires_at = datetime.utcnow() - timedelta(seconds=1)
            with self.assertRaises(ValueError) as ctx:
                await PaymentHandoffService(db).claim(
                    token=handoff["scene"],
                    customer_id=CUSTOMER_ID,
                    openid="openid-customer-a",
                )
            self.assertIn("已过期", str(ctx.exception))
            self.assertEqual(row.status, "EXPIRED")

    async def test_wxpay_notify_marks_claimed_handoff_paid(self):
        async with self.SessionLocal() as db:
            order = await self._create_staff_prepay_order(db)
            handoff = await PaymentHandoffService(db).create_for_order(
                tenant_id=TENANT,
                order_id=int(order.id),
                actor_account_id=STAFF_ID,
                actor_role="frontdesk",
            )
            await PaymentHandoffService(db).claim(
                token=handoff["scene"],
                customer_id=CUSTOMER_ID,
                openid="openid-customer-a",
            )
            await db.commit()

            resource = {
                "out_trade_no": str(order.id),
                "trade_state": "SUCCESS",
                "amount": {"total": 1800, "payer_total": 1800, "currency": "CNY"},
            }
            with patch.object(WxPayService, "enabled", new_callable=PropertyMock, return_value=True), \
                 patch.object(WxPayService, "verify_notify", return_value=resource), \
                 patch("app.services.order_payment_service._print_paid_order_ticket"), \
                 patch("app.services.coupon_service.CouponService.issue_auto_coupon", return_value=None), \
                 patch("app.services.membership_service.MembershipService.apply_consumption", return_value=None), \
                 patch("app.services.subscribe_message_service.send_order_success_subscribe", return_value=None), \
                 patch("app.services.order_payment_service.logger"):
                result = await wxpay_notify(make_notify_request(int(order.id)), db=db)

            self.assertEqual(result.get("code"), "SUCCESS")
            row = (
                await db.execute(select(StaffAssistedPaymentHandoff).where(
                    StaffAssistedPaymentHandoff.order_id == order.id
                ))
            ).scalar_one()
            self.assertEqual(row.status, "PAID")
            self.assertIsNotNone(row.paid_at)
