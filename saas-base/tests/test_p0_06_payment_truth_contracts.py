import asyncio
import os
import pathlib
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, PropertyMock, patch

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.orders import wxpay_notify
from app.models.base import Base
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.models.member_account import MemberAccount
from app.models.order import Order
from app.models.point_ledger import PointLedger
from app.models.staff_assisted_payment_handoff import StaffAssistedPaymentHandoff
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.services.order_payment_service import OrderPaymentService
from app.services.payment_handoff_service import PaymentHandoffService
from app.services.subscription_service import STATUS_ACTIVE, SubscriptionService
from app.services.wxpay_service import WxPayService


if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


TENANT_ID = "p0-06-tenant"


def make_notify_request() -> Request:
    async def _body():
        return b"{}"

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/orders/wxpay-notify",
            "headers": [],
            "query_string": f"tenant_id={TENANT_ID}".encode(),
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    request.body = _body
    return request


class PaymentTruthContractsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # A real file-backed SQLite DB, not :memory: -- see
        # tests/test_optional_side_effect_wiring.py for why: a nested
        # optional_capability_enabled() session mid-transaction can spuriously
        # roll back this session's pending writes under :memory:, a
        # SQLite/aiosqlite test-only artifact absent on any real DB.
        self._db_file = f"{tempfile.gettempdir()}/f1fd1a_p006_{uuid.uuid4().hex}.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_file}")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.Session()

        # Phase F1F-D1A: order_payment_service.py's _on_payment_success now calls
        # optional_capability_enabled(), which opens its own AsyncSessionLocal()
        # session -- point that factory at this test's own file-backed engine
        # instead of the real production DB.
        self._session_patch = patch("app.core.database.AsyncSessionLocal", self.Session)
        self._session_patch.start()

        self.db.add(
            Tenant(
                tenant_id=TENANT_ID,
                name="P0-06",
                password_hash="x",
                status=True,
                is_open=True,
                payment_mode="prepay",
                wx_pay_enabled=True,
                wx_mchid="1900000109",
            )
        )
        # Phase F1F-D1A: order_payment_service.py's post-payment membership/coupon
        # accrual now requires real capability data to resolve -- this file
        # predates subscription-awareness and asserts on real MemberAccount
        # accrual, unrelated to plan tier, so give TENANT_ID a real PRO baseline.
        self.db.add_all(
            [
                Plan(code="FREE", name="免费版", is_active=True, price_month_cents=0, price_year_cents=0, sort_order=0),
                Plan(code="STANDARD", name="普通版", is_active=True, price_month_cents=5900, price_year_cents=60900, sort_order=1),
                Plan(code="PRO", name="专业版", is_active=True, price_month_cents=9900, price_year_cents=102200, sort_order=2),
            ]
        )
        await self.db.commit()
        pro_plan = await SubscriptionService(self.db).get_plan_by_code("PRO")
        now = datetime.utcnow()
        self.db.add(Subscription(
            tenant_id=TENANT_ID, plan_id=pro_plan.id, status=STATUS_ACTIVE,
            started_at=now, ends_at=now + timedelta(days=30),
        ))
        await self.db.commit()

    async def asyncTearDown(self):
        self._session_patch.stop()
        await self.db.close()
        await self.engine.dispose()
        try:
            os.remove(self._db_file)
        except OSError:
            pass

    async def make_order(self, total="28.00", **overrides) -> Order:
        values = {
            "tenant_id": TENANT_ID,
            "total": total,
            "status": "pending_payment",
            "payment_status": "unpaid",
            "payment_mode": "prepay",
        }
        values.update(overrides)
        order = Order(**values)
        self.db.add(order)
        await self.db.commit()
        return order

    @staticmethod
    def resource(order: Order, **overrides) -> dict:
        fact = {
            "out_trade_no": str(order.id),
            "trade_state": "SUCCESS",
            "transaction_id": f"wx-tx-{order.id}",
            "amount": {"total": int(float(order.total) * 100), "currency": "CNY"},
        }
        fact.update(overrides)
        return fact

    async def notify(self, fact: dict) -> dict:
        with (
            patch.object(WxPayService, "enabled", new_callable=PropertyMock, return_value=True),
            patch.object(WxPayService, "verify_notify", return_value=fact),
            patch(
                "app.services.order_payment_service._print_paid_order_ticket",
                new_callable=AsyncMock,
            ),
            patch("app.services.coupon_service.settings.REDIS_ENABLED", False),
        ):
            return await wxpay_notify(make_notify_request(), db=self.db)

    async def recover(self, order: Order, fact: dict) -> bool:
        with (
            patch.object(WxPayService, "enabled", new_callable=PropertyMock, return_value=True),
            patch.object(
                WxPayService,
                "query_order_by_out_trade_no",
                new_callable=AsyncMock,
                return_value=fact,
            ),
            patch(
                "app.services.order_payment_service._print_paid_order_ticket",
                new_callable=AsyncMock,
            ),
        ):
            return await OrderPaymentService(self.db)._recover_wxpay_order_if_paid(order)

    async def assert_unpaid_after_notify(self, order: Order, fact: dict):
        response = await self.notify(fact)
        self.assertEqual(response.get("code"), "FAIL")
        await self.db.refresh(order)
        self.assertEqual(order.payment_status, "unpaid")
        self.assertEqual(order.status, "pending_payment")

    async def test_callback_rejects_missing_amount_currency_or_transaction_id(self):
        cases = (
            lambda fact: fact.pop("amount"),
            lambda fact: fact["amount"].pop("currency"),
            lambda fact: fact["amount"].update(currency="USD"),
            lambda fact: fact.pop("transaction_id"),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                order = await self.make_order()
                fact = self.resource(order)
                mutate(fact)
                await self.assert_unpaid_after_notify(order, fact)

    async def test_query_and_callback_share_exact_fact_validation(self):
        mutations = (
            lambda fact: fact.update(out_trade_no="999999"),
            lambda fact: fact["amount"].update(total=1),
            lambda fact: fact["amount"].update(currency="USD"),
            lambda fact: fact.pop("transaction_id"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                order = await self.make_order()
                fact = self.resource(order)
                mutate(fact)
                self.assertFalse(await self.recover(order, fact))
                await self.db.refresh(order)
                self.assertEqual(order.payment_status, "unpaid")

    async def test_transaction_id_is_claimed_once_and_cross_order_reuse_fails_closed(self):
        first = await self.make_order()
        second = await self.make_order()
        transaction_id = "wx-shared-transaction"

        first_response = await self.notify(self.resource(first, transaction_id=transaction_id))
        second_response = await self.notify(self.resource(second, transaction_id=transaction_id))

        self.assertEqual(first_response.get("code"), "SUCCESS")
        self.assertEqual(second_response.get("code"), "FAIL")
        await self.db.refresh(first)
        await self.db.refresh(second)
        self.assertEqual(first.wx_transaction_id, transaction_id)
        self.assertEqual(second.payment_status, "unpaid")
        self.assertIsNone(second.wx_transaction_id)

    async def test_same_callback_three_times_has_one_transition_and_one_post_commit_print(self):
        order = await self.make_order()
        fact = self.resource(order)
        printer = AsyncMock()
        with (
            patch.object(WxPayService, "enabled", new_callable=PropertyMock, return_value=True),
            patch.object(WxPayService, "verify_notify", return_value=fact),
            patch("app.services.order_payment_service._print_paid_order_ticket", printer),
        ):
            responses = [await wxpay_notify(make_notify_request(), db=self.db) for _ in range(3)]

        self.assertEqual([item.get("code") for item in responses], ["SUCCESS"] * 3)
        await self.db.refresh(order)
        self.assertEqual(order.wx_transaction_id, fact["transaction_id"])
        self.assertEqual(printer.await_count, 1)

    async def test_verified_transaction_can_bind_legacy_paid_order_without_side_effect_replay(self):
        order = await self.make_order(status="pending", payment_status="paid", payment_method="wxpay")
        fact = self.resource(order)
        printer = AsyncMock()
        with (
            patch.object(WxPayService, "enabled", new_callable=PropertyMock, return_value=True),
            patch.object(WxPayService, "verify_notify", return_value=fact),
            patch("app.services.order_payment_service._print_paid_order_ticket", printer),
        ):
            response = await wxpay_notify(make_notify_request(), db=self.db)

        self.assertEqual(response.get("code"), "SUCCESS")
        await self.db.refresh(order)
        self.assertEqual(order.wx_transaction_id, fact["transaction_id"])
        self.assertEqual(printer.await_count, 0)

    async def test_db_effect_failure_rolls_back_order_and_transaction_claim_then_retry_succeeds(self):
        customer = Customer(tenant_id=TENANT_ID, openid="p0-06-customer", name="P0-06")
        template = CouponTemplate(
            tenant_id=TENANT_ID,
            name="rollback coupon",
            type="FIXED",
            value="2.00",
            min_amount="20.00",
            total_stock=1,
            used_stock=1,
            start_time=datetime.utcnow() - timedelta(days=1),
            end_time=datetime.utcnow() + timedelta(days=7),
            status=1,
        )
        self.db.add_all([customer, template])
        await self.db.flush()
        coupon = Coupon(
            tenant_id=TENANT_ID,
            template_id=template.id,
            customer_id=customer.id,
            code="p0-06-locked-coupon",
            status="LOCKED",
            expire_time=datetime.utcnow() + timedelta(days=7),
        )
        self.db.add(coupon)
        await self.db.flush()
        order = await self.make_order(customer_id=customer.id, coupon_id=coupon.id)
        handoff = StaffAssistedPaymentHandoff(
            tenant_id=TENANT_ID,
            order_id=order.id,
            token_hash="a" * 64,
            status="CLAIMED",
            claimed_customer_id=customer.id,
            expires_at=datetime.utcnow() + timedelta(minutes=10),
        )
        self.db.add(handoff)
        await self.db.commit()
        customer_id = customer.id
        fact = self.resource(order)

        original_mark_paid = PaymentHandoffService.mark_order_paid

        async def fail_after_handoff_mutation(service, order_id):
            await original_mark_paid(service, order_id)
            raise RuntimeError("fault after partial DB effects")

        with patch.object(PaymentHandoffService, "mark_order_paid", fail_after_handoff_mutation):
            failed = await self.notify(fact)

        self.assertEqual(failed.get("code"), "FAIL")
        await self.db.refresh(order)
        await self.db.refresh(coupon)
        await self.db.refresh(handoff)
        self.assertEqual(order.payment_status, "unpaid")
        self.assertIsNone(order.wx_transaction_id)
        self.assertEqual(coupon.status, "LOCKED")
        self.assertEqual(handoff.status, "CLAIMED")
        member_count = await self.db.scalar(
            select(func.count(MemberAccount.id)).where(MemberAccount.customer_id == customer_id)
        )
        points_count = await self.db.scalar(
            select(func.count(PointLedger.id)).where(PointLedger.customer_id == customer_id)
        )
        self.assertEqual(member_count, 0)
        self.assertEqual(points_count, 0)

        retried = await self.notify(fact)
        self.assertEqual(retried.get("code"), "SUCCESS")
        duplicate_responses = [await self.notify(fact) for _ in range(2)]
        self.assertEqual(
            [item.get("code") for item in duplicate_responses],
            ["SUCCESS", "SUCCESS"],
        )
        await self.db.refresh(order)
        await self.db.refresh(coupon)
        await self.db.refresh(handoff)
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.wx_transaction_id, fact["transaction_id"])
        self.assertEqual(coupon.status, "USED")
        self.assertEqual(handoff.status, "PAID")
        account = await self.db.scalar(
            select(MemberAccount).where(MemberAccount.customer_id == customer_id)
        )
        self.assertEqual(float(account.total_consumption), 28.0)
        points_count = await self.db.scalar(
            select(func.count(PointLedger.id)).where(
                PointLedger.customer_id == customer_id,
                PointLedger.event_type == "consumption",
                PointLedger.ref_id == str(order.id),
            )
        )
        self.assertEqual(points_count, 1)

    async def test_query_then_callback_and_callback_then_query_converge_without_replay(self):
        for query_first in (True, False):
            with self.subTest(query_first=query_first):
                order = await self.make_order()
                fact = self.resource(order)
                printer = AsyncMock()
                with (
                    patch.object(WxPayService, "enabled", new_callable=PropertyMock, return_value=True),
                    patch.object(
                        WxPayService,
                        "query_order_by_out_trade_no",
                        new_callable=AsyncMock,
                        return_value=fact,
                    ),
                    patch.object(WxPayService, "verify_notify", return_value=fact),
                    patch("app.services.order_payment_service._print_paid_order_ticket", printer),
                ):
                    if query_first:
                        self.assertTrue(
                            await OrderPaymentService(self.db)._recover_wxpay_order_if_paid(order)
                        )
                        response = await wxpay_notify(make_notify_request(), db=self.db)
                    else:
                        response = await wxpay_notify(make_notify_request(), db=self.db)
                        self.assertTrue(
                            await OrderPaymentService(self.db)._recover_wxpay_order_if_paid(order)
                        )

                self.assertEqual(response.get("code"), "SUCCESS")
                await self.db.refresh(order)
                self.assertEqual(order.payment_status, "paid")
                self.assertEqual(order.wx_transaction_id, fact["transaction_id"])
                self.assertEqual(printer.await_count, 1)

    async def test_valid_late_payment_for_cancelled_order_records_truth_without_refund(self):
        order = await self.make_order(status="cancelled")
        fact = self.resource(order)
        refund = AsyncMock()
        with (
            patch.object(WxPayService, "enabled", new_callable=PropertyMock, return_value=True),
            patch.object(WxPayService, "verify_notify", return_value=fact),
            patch.object(OrderPaymentService, "_refund_orphaned_wxpay_payment", refund),
        ):
            response = await wxpay_notify(make_notify_request(), db=self.db)

        self.assertEqual(response.get("code"), "SUCCESS")
        refund.assert_not_called()
        await self.db.refresh(order)
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(order.wx_transaction_id, fact["transaction_id"])

    async def test_mock_payment_never_fabricates_wechat_transaction_identity(self):
        self.assertTrue(hasattr(Order, "wx_transaction_id"))
        order = await self.make_order()
        await OrderPaymentService(self.db)._on_payment_success(order, payment_method="mock")
        await self.db.commit()
        await self.db.refresh(order)
        self.assertIsNone(order.wx_transaction_id)

    async def test_unknown_order_callback_preserves_existing_success_ack_policy(self):
        order = await self.make_order()
        response = await self.notify(self.resource(order, out_trade_no="999999999999"))
        self.assertEqual(response, {"code": "SUCCESS", "message": "ok"})
        await self.db.refresh(order)
        self.assertEqual(order.payment_status, "unpaid")

    def test_additive_migration_and_model_define_nullable_unique_transaction_identity(self):
        column = Order.__table__.c.wx_transaction_id
        self.assertTrue(column.nullable)
        self.assertEqual(column.type.length, 64)
        indexes = {index.name: index for index in Order.__table__.indexes}
        self.assertIn("ux_orders_wx_transaction_id", indexes)
        self.assertTrue(indexes["ux_orders_wx_transaction_id"].unique)

        migration = (
            pathlib.Path(__file__).resolve().parents[1]
            / "alembic"
            / "versions"
            / "20260814_0002_add_order_wx_transaction_id.py"
        ).read_text(encoding="utf-8")
        self.assertIn('revision = "20260814_0002"', migration)
        self.assertIn('down_revision = "20260814_0001"', migration)
        self.assertNotIn("op.execute", migration)
        self.assertNotIn("op.bulk_insert", migration)


if __name__ == "__main__":
    unittest.main()
