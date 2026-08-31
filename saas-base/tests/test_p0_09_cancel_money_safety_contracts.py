import asyncio
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.orders import OrderStatusUpdate, serialize_order
from app.models.base import Base
from app.models.order import Order
from app.models.tenant import Tenant
from app.services.order_lifecycle_service import OrderLifecycleService
from app.services.order_payment_service import OrderPaymentService
from app.services.order_print_service import _claim_initial_print_attempt


if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


TENANT_ID = "p0-09-tenant"


class P009MoneySafetyContractTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.db = self.SessionLocal()
        self.db.add(
            Tenant(
                tenant_id=TENANT_ID,
                name="P0-09 Restaurant",
                password_hash="x",
                status=True,
                is_open=True,
                payment_mode="prepay",
                wx_pay_enabled=True,
                wx_mchid="1900000900",
            )
        )
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def make_order(self, **overrides):
        values = {
            "tenant_id": TENANT_ID,
            "table_no": "A09",
            "status": "pending_payment",
            "payment_status": "unpaid",
            "payment_mode": "prepay",
            "total": 28.0,
            "created_at": datetime.utcnow(),
        }
        values.update(overrides)
        order = Order(**values)
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def test_r01a_paid_merchant_cancel_fails_closed_without_refund(self):
        # Cancel of a paid order stays fail-closed: a paid order is only ever
        # terminated by reject (while still "pending"), never by cancel.
        order = await self.make_order(status="pending", payment_status="paid")
        service = OrderLifecycleService(self.db)
        service.set_tenant_id(TENANT_ID)
        refund = AsyncMock(return_value={"success": True, "amount": 28.0, "error": None})
        with patch.object(OrderPaymentService, "_refund_order_payment", new=refund):
            result = await service.update_order_status(
                int(order.id), OrderStatusUpdate(status="cancelled")
            )

        self.assertEqual(result.code, 409)
        self.assertEqual((result.data or {}).get("code"), "PAID_ORDER_CANCEL_REQUIRES_REFUND")
        refund.assert_not_called()
        await self.db.refresh(order)
        self.assertEqual(order.status, "pending")
        self.assertEqual(order.payment_status, "paid")

    async def test_r01b_paid_pending_merchant_reject_allowed_but_never_refunds(self):
        # P0-PAID-PENDING gap fix: a merchant may reject a paid order the kitchen
        # has not accepted yet. This terminates fulfilment only -- it must NOT
        # submit a refund, mark refund success, or set refunded_at. The merchant
        # completes the refund separately through POST /orders/{id}/refund.
        order = await self.make_order(status="pending", payment_status="paid")
        service = OrderLifecycleService(self.db)
        service.set_tenant_id(TENANT_ID)
        refund = AsyncMock(return_value={"success": True, "amount": 28.0, "error": None})
        with patch.object(OrderPaymentService, "_refund_order_payment", new=refund):
            result = await service.update_order_status(
                int(order.id), OrderStatusUpdate(status="rejected")
            )

        self.assertEqual(result.code, 200)
        refund.assert_not_called()
        await self.db.refresh(order)
        self.assertEqual(order.status, "rejected")
        self.assertEqual(order.payment_status, "paid")
        self.assertNotEqual(getattr(order, "refund_status", None), "success")
        self.assertIsNone(getattr(order, "refunded_at", None))
        self.assertEqual(order.terminated_actor_type, "account")
        self.assertEqual(order.termination_source, "merchant_reject")
        self.assertIsNotNone(order.terminated_at)
        self.assertTrue(serialize_order(order, [])["refund_required"])

    async def test_r02_paid_customer_cancel_fails_closed_without_refund(self):
        order = await self.make_order(
            status="pending", payment_status="paid", customer_id=909
        )
        refund = AsyncMock(return_value={"success": True, "amount": 28.0, "error": None})
        with patch.object(OrderPaymentService, "_refund_order_payment", new=refund):
            result = await OrderLifecycleService(self.db).cancel_order(
                int(order.id), customer_id=909, participant_token=None
            )

        self.assertEqual(result.code, 409)
        self.assertEqual((result.data or {}).get("code"), "PAID_ORDER_CANCEL_REQUIRES_REFUND")
        refund.assert_not_called()
        await self.db.refresh(order)
        self.assertEqual(order.status, "pending")
        self.assertEqual(order.payment_status, "paid")

    async def test_non_terminal_merchant_transition_never_queries_payment_provider(self):
        order = await self.make_order(status="pending_payment", payment_status="unpaid")
        service = OrderLifecycleService(self.db)
        service.set_tenant_id(TENANT_ID)
        recover = AsyncMock(return_value=False)

        with patch.object(
            OrderPaymentService, "_recover_wxpay_order_if_paid", new=recover
        ):
            result = await service.update_order_status(
                int(order.id), OrderStatusUpdate(status="preparing")
            )

        self.assertEqual(result.code, 409)
        recover.assert_not_called()
        await self.db.refresh(order)
        self.assertEqual(order.status, "pending_payment")

    async def test_r03_late_callback_records_payment_then_orphaned_refund(self):
        order = await self.make_order(status="cancelled")
        resource = {
            "out_trade_no": str(order.id),
            "trade_state": "SUCCESS",
            "transaction_id": f"wx-p009-callback-{order.id}",
            "amount": {"total": 2800, "payer_total": 2800, "currency": "CNY"},
        }
        request = AsyncMock()
        request.headers = {}
        request.query_params = {"tenant_id": TENANT_ID}
        request.body = AsyncMock(return_value=b"{}")
        fake_wxpay = AsyncMock()
        fake_wxpay.enabled = True
        fake_wxpay.verify_notify = lambda _headers, _body: resource
        fake_wxpay.refund.return_value = {"status": "SUCCESS"}
        fake_wxpay.query_refund_by_out_refund_no.return_value = None

        with patch("app.services.wxpay_service.WxPayService", return_value=fake_wxpay), patch.object(
            OrderPaymentService, "_on_payment_success", new=AsyncMock()
        ) as fulfill:
            response = await OrderPaymentService(self.db).wxpay_notify(request)

        self.assertEqual(response["code"], "SUCCESS")
        fake_wxpay.refund.assert_awaited_once()
        fulfill.assert_not_called()
        await self.db.refresh(order)
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.wx_transaction_id, resource["transaction_id"])
        self.assertEqual(order.refund_status, "success")
        self.assertFalse(serialize_order(order, [])["refund_required"])

    async def test_r04_terminal_query_success_uses_same_reconciliation(self):
        order = await self.make_order(status="rejected")
        resource = {
            "out_trade_no": str(order.id),
            "trade_state": "SUCCESS",
            "transaction_id": f"wx-p009-query-{order.id}",
            "amount": {"total": 2800, "payer_total": 2800, "currency": "CNY"},
        }
        fake_wxpay = AsyncMock()
        fake_wxpay.enabled = True
        fake_wxpay.query_order_by_out_trade_no.return_value = resource
        fake_wxpay.refund.return_value = {"status": "SUCCESS"}
        fake_wxpay.query_refund_by_out_refund_no.return_value = None

        with patch("app.services.wxpay_service.WxPayService", return_value=fake_wxpay), patch.object(
            OrderPaymentService, "_run_post_commit_payment_effects", new=AsyncMock()
        ) as fulfill:
            recovered = await OrderPaymentService(self.db)._recover_wxpay_order_if_paid(order)

        self.assertTrue(recovered)
        fake_wxpay.refund.assert_awaited_once()
        fulfill.assert_not_called()
        await self.db.refresh(order)
        self.assertEqual((order.status, order.payment_status), ("rejected", "paid"))
        self.assertEqual(order.wx_transaction_id, resource["transaction_id"])

    async def test_r05_cancelled_order_cannot_win_initial_print_claim(self):
        order = await self.make_order(status="cancelled", print_status="PENDING")
        claimed, result = await _claim_initial_print_attempt(
            int(order.id), TENANT_ID, self.db, reason="p0_09_race"
        )

        self.assertIsNone(claimed)
        self.assertTrue(result["skipped"])
        self.assertEqual(result["code"], "ORDER_TERMINAL")
        await self.db.refresh(order)
        self.assertNotEqual(order.print_status, "SENDING")

    async def test_callback_x3_and_query_callback_orders_are_one_terminal_paid_fact(self):
        service = OrderPaymentService(self.db)
        fake_wxpay = AsyncMock()
        fake_wxpay.enabled = True
        current_resource = {}
        fake_wxpay.verify_notify = lambda _headers, _body: current_resource
        fake_wxpay.query_order_by_out_trade_no.side_effect = lambda _order_id: current_resource
        fake_wxpay.refund.return_value = {"status": "SUCCESS"}
        fake_wxpay.query_refund_by_out_refund_no.return_value = None

        def request():
            value = AsyncMock()
            value.headers = {}
            value.query_params = {"tenant_id": TENANT_ID}
            value.body = AsyncMock(return_value=b"{}")
            return value

        fulfill = AsyncMock()
        with patch("app.services.wxpay_service.WxPayService", return_value=fake_wxpay), patch.object(
            OrderPaymentService, "_on_payment_success", new=fulfill
        ), patch.object(
            OrderPaymentService, "_run_post_commit_payment_effects", new=AsyncMock()
        ) as post_commit:
            # Five cancelled orders, each receiving the same verified callback three times.
            for index in range(5):
                order = await self.make_order(status="cancelled")
                current_resource = {
                    "out_trade_no": str(order.id),
                    "trade_state": "SUCCESS",
                    "transaction_id": f"wx-p009-x3-{index}-{order.id}",
                    "amount": {"total": 2800, "payer_total": 2800, "currency": "CNY"},
                }
                for _ in range(3):
                    response = await service.wxpay_notify(request())
                    self.assertEqual(response["code"], "SUCCESS")
                await self.db.refresh(order)
                self.assertEqual((order.status, order.payment_status), ("cancelled", "paid"))
                self.assertEqual(order.wx_transaction_id, current_resource["transaction_id"])

            # query -> callback and callback -> query converge on the same durable fact.
            query_first = await self.make_order(status="cancelled")
            current_resource = {
                "out_trade_no": str(query_first.id),
                "trade_state": "SUCCESS",
                "transaction_id": f"wx-p009-qc-{query_first.id}",
                "amount": {"total": 2800, "payer_total": 2800, "currency": "CNY"},
            }
            self.assertTrue(await service._recover_wxpay_order_if_paid(query_first))
            self.assertEqual((await service.wxpay_notify(request()))["code"], "SUCCESS")

            callback_first = await self.make_order(status="rejected")
            current_resource = {
                "out_trade_no": str(callback_first.id),
                "trade_state": "SUCCESS",
                "transaction_id": f"wx-p009-cq-{callback_first.id}",
                "amount": {"total": 2800, "payer_total": 2800, "currency": "CNY"},
            }
            self.assertEqual((await service.wxpay_notify(request()))["code"], "SUCCESS")
            self.assertTrue(await service._recover_wxpay_order_if_paid(callback_first))

        self.assertEqual(fake_wxpay.refund.await_count, 7)
        fulfill.assert_not_called()
        post_commit.assert_not_called()
        for order in (query_first, callback_first):
            await self.db.refresh(order)
            self.assertEqual(order.payment_status, "paid")
            self.assertIn(order.status, ("cancelled", "rejected"))
            self.assertFalse(serialize_order(order, [])["refund_required"])

    async def test_twenty_order_option_a_matrix_has_no_illegal_paid_cancel(self):
        rows = []
        for _ in range(5):
            rows.append((await self.make_order(payment_mode="prepay"), "cancelled", True))
        # paid + pending: reject terminates fulfilment (allowed, no refund side effect);
        # cancel is still fail-closed.
        for _ in range(3):
            rows.append((
                await self.make_order(status="pending", payment_status="paid", payment_mode="prepay"),
                "cancelled",
                False,
            ))
        for _ in range(2):
            rows.append((
                await self.make_order(status="pending", payment_status="paid", payment_mode="prepay"),
                "rejected",
                True,
            ))
        for _ in range(5):
            rows.append((await self.make_order(status="pending", payment_mode="postpay"), "rejected", True))
        for _ in range(5):
            rows.append((await self.make_order(status="pending", payment_mode="table_account"), "cancelled", True))

        refund = AsyncMock()
        recover = AsyncMock(return_value=False)
        illegal_paid_cancels = 0
        status_mismatches = 0
        service = OrderLifecycleService(self.db)
        service.set_tenant_id(TENANT_ID)
        with patch.object(OrderPaymentService, "_refund_order_payment", new=refund), patch.object(
            OrderPaymentService, "_recover_wxpay_order_if_paid", new=recover
        ):
            for order, target, allowed in rows:
                response = await service.update_order_status(
                    int(order.id), OrderStatusUpdate(status=target)
                )
                await self.db.refresh(order)
                if allowed:
                    status_mismatches += int(response.code != 200 or order.status != target)
                else:
                    illegal_paid_cancels += int(response.code == 200 or order.status != "pending")

        self.assertEqual(len(rows), 20)
        self.assertEqual(illegal_paid_cancels, 0)
        self.assertEqual(status_mismatches, 0)
        refund.assert_not_called()

    async def test_terminal_print_history_is_immutable_and_recovery_never_resends(self):
        for print_status in ("SUCCESS", "UNKNOWN", "SENDING"):
            order = await self.make_order(status="cancelled", print_status=print_status)
            claimed, result = await _claim_initial_print_attempt(
                int(order.id), TENANT_ID, self.db, reason="terminal_recovery"
            )
            self.assertIsNone(claimed)
            self.assertEqual(result["code"], "ORDER_TERMINAL")
            await self.db.refresh(order)
            self.assertEqual(order.print_status, print_status)

    async def test_r07_owner_and_customer_dto_expose_server_financial_attention(self):
        paid_terminal = await self.make_order(status="cancelled", payment_status="paid")
        paid_pending = await self.make_order(status="pending", payment_status="paid")
        unpaid_pending = await self.make_order(status="pending", payment_status="unpaid")

        terminal = serialize_order(paid_terminal, [])
        paid = serialize_order(paid_pending, [])
        unpaid = serialize_order(unpaid_pending, [])
        self.assertTrue(terminal["refund_required"])
        self.assertFalse(terminal["can_cancel"])
        self.assertFalse(terminal["can_reject"])
        # paid + pending: reject is offered (fulfilment termination), cancel is not.
        self.assertFalse(paid["can_cancel"])
        self.assertTrue(paid["can_reject"])
        self.assertTrue(unpaid["can_cancel"])
        self.assertTrue(unpaid["can_reject"])

        service = OrderLifecycleService(self.db)
        service.set_tenant_id(TENANT_ID)
        result = await service.get_my_order(
            int(paid_terminal.id), customer_id=None, participant_token=None
        )
        self.assertTrue(result.data["refund_required"])
        self.assertFalse(result.data["can_cancel"])

    def test_r08_both_stale_cleanup_mutations_use_fresh_locked_paid_recheck(self):
        root = Path(__file__).parents[1]
        api_source = (root / "app/api/v1/orders.py").read_text(encoding="utf-8")
        create_cleanup = api_source.split(
            "async def _cleanup_stale_pending_payment_orders", 1
        )[1].split("async def _validate_create_order_items", 1)[0]
        main_source = (root / "app/main.py").read_text(encoding="utf-8")
        background_cleanup = main_source.split("async def _stale_order_cleanup_once", 1)[1].split(
            "PENDING_PAYMENT_RECONCILE_AFTER_SECONDS", 1
        )[0]

        for cleanup in (create_cleanup, background_cleanup):
            self.assertIn("with_for_update()", cleanup)
            self.assertIn('payment_status", None) == "paid"', cleanup)


if __name__ == "__main__":
    unittest.main()
