"""Cancel slip: when an order the kitchen may already hold is rejected / cancelled, print a
"stop" ticket instead of letting the kitchen cook for a dead order.

Contract: best-effort, one slip per order, never blocks or fails the reject, never touches
the original print state, visible to staff through ``cancel_slip_status``, and only sent when a
kitchen ticket may physically exist (SUCCESS / UNKNOWN / SENDING initial print, or a manual
reprint). Nothing here changes how a normal order is printed.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.services import order_print_service as ops
from app.services.order_lifecycle_service import OrderLifecycleService
from app.services.order_print_service import (
    CANCEL_SLIP_BANNER,
    PrintResultUnknownError,
    _apply_cancel_slip_banner,
    _apply_cancel_slip_ticket_banner,
    _get_print_meta,
    _print_cancel_slip,
    _set_print_meta,
    build_staff_print_summary,
    cancel_slip_needed,
)
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT = "t-cancel-slip"
PROVIDER = "app.services.order_print_service._execute_provider_with_frozen_route"
CAPABILITY = "app.services.optional_entitlement.optional_capability_enabled"
ROUTE = {"provider": "kuaimai", "printer_identifier": "KM001", "template_or_route_mode": "1634998374"}


def _order_ns(status, print_status, manual=None):
    order = SimpleNamespace(status=status, print_status=print_status, merchant_note=None)
    if manual is not None:
        order.merchant_note = ops._compose_merchant_note_with_print_meta(None, {"manual_reprints": manual})
    return order


class BannerTest(unittest.TestCase):
    def test_kuaimai_banner_marks_every_certainly_printed_text_field_and_keeps_the_order(self):
        data = {
            "shop_name": "大宝羊肉馆", "order_no": "123456", "table_no": "A1", "remark": "少辣",
            "order_type_text": "", "items": [{"goods_name": "牛肉汤"}], "pay_amount": "20.00",
        }
        out = _apply_cancel_slip_banner(data)
        self.assertIn(CANCEL_SLIP_BANNER, out["shop_name"])
        self.assertIn("大宝羊肉馆", out["shop_name"])
        self.assertEqual(out["order_type_text"], CANCEL_SLIP_BANNER)
        self.assertTrue(out["remark"].startswith(CANCEL_SLIP_BANNER))
        self.assertIn("少辣", out["remark"])
        self.assertEqual(out["order_no"], "123456")
        self.assertEqual(out["table_no"], "A1")
        self.assertEqual(out["items"], [{"goods_name": "牛肉汤"}])
        self.assertEqual(data["shop_name"], "大宝羊肉馆", "input must not be mutated")

    def test_kuaimai_banner_survives_empty_shop_name_and_remark(self):
        out = _apply_cancel_slip_banner({"shop_name": "", "remark": None})
        self.assertEqual(out["shop_name"], CANCEL_SLIP_BANNER)
        self.assertEqual(out["remark"], CANCEL_SLIP_BANNER)

    def test_feieyun_ticket_title_is_replaced(self):
        ticket = "<CB>新订单</CB>\n桌号：A1\n牛肉汤  x1  ¥20.0\n<BR>"
        out = _apply_cancel_slip_ticket_banner(ticket)
        self.assertTrue(out.startswith(f"<CB>{CANCEL_SLIP_BANNER}</CB>"))
        self.assertNotIn("新订单", out)
        self.assertIn("牛肉汤", out)

    def test_feieyun_ticket_without_the_title_line_gets_the_banner_prepended(self):
        out = _apply_cancel_slip_ticket_banner("桌号：A1")
        self.assertEqual(out, f"<CB>{CANCEL_SLIP_BANNER}</CB>\n桌号：A1")


class CancelSlipNeededTest(unittest.TestCase):
    def test_needed_only_after_a_ticket_may_exist(self):
        for status in ("rejected", "cancelled"):
            for print_status, expected in (
                ("SUCCESS", True), ("UNKNOWN", True), ("SENDING", True),
                ("FAILED", False), ("PENDING", False), ("NOT_ELIGIBLE", False), ("", False), (None, False),
            ):
                self.assertEqual(
                    cancel_slip_needed(_order_ns(status, print_status)), expected, f"{status}/{print_status}",
                )

    def test_never_needed_for_orders_that_have_not_ended(self):
        for status in ("pending_payment", "pending", "preparing", "done", "settled"):
            self.assertFalse(cancel_slip_needed(_order_ns(status, "SUCCESS")), status)

    def test_a_manual_reprint_of_a_failed_initial_print_still_counts(self):
        self.assertTrue(cancel_slip_needed(_order_ns("rejected", "FAILED", manual=[{"status": "SUCCESS"}])))
        self.assertTrue(cancel_slip_needed(_order_ns("rejected", "FAILED", manual=[{"status": "UNKNOWN"}])))
        self.assertFalse(cancel_slip_needed(_order_ns("rejected", "FAILED", manual=[{"status": "FAILED"}])))


class _DbCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._db_file = f"{tempfile.gettempdir()}/cancel_slip_{uuid.uuid4().hex}.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_file}")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self._patches = [
            patch("app.core.database.AsyncSessionLocal", self.SessionLocal),
            patch(CAPABILITY, AsyncMock(return_value=True)),
        ]
        self.provider = AsyncMock(return_value="slip-task")
        self._patches.append(patch(PROVIDER, self.provider))
        for p in self._patches:
            p.start()
        self.db.add(Tenant(tenant_id=TENANT, name="大宝羊肉馆", password_hash="x", status=True, is_open=True,
                           payment_mode="prepay"))
        self.db.add(TenantConfig(
            tenant_id=TENANT, member_rules={}, coupon_rules={}, plugin_settings={},
            business_info={
                "printer_provider": "kuaimai",
                "kuaimai_printer": {"app_id": "app_1", "app_secret": "secret_1", "sn": "KM001"},
            },
        ))
        await self.db.commit()

    async def asyncTearDown(self):
        for p in reversed(self._patches):
            p.stop()
        await self.db.close()
        await self.engine.dispose()
        try:
            os.remove(self._db_file)
        except OSError:
            pass

    async def _order(self, *, status="pending", payment_status="paid", payment_mode="prepay",
                     print_status="SUCCESS", with_route=True):
        order = Order(
            tenant_id=TENANT, dining_session_id=None, table_no="A1", total="20.00", status=status,
            payment_status=payment_status, payment_mode=payment_mode, payment_method="mock", source="h5",
            print_status=print_status,
        )
        self.db.add(order)
        await self.db.flush()
        self.db.add(OrderItem(id=generate_snowflake_id(), order_id=order.id, name="牛肉汤", price="20.00", qty=1))
        if with_route:
            _set_print_meta(order, {"initial_print": {"status": print_status, "attempts": 1, "route": dict(ROUTE)}})
        await self.db.commit()
        return order

    def _service(self):
        service = OrderLifecycleService(self.db)
        service.set_tenant_id(TENANT)
        return service

    async def _reject(self, order, status="rejected"):
        res = await self._service().update_order_status(order.id, SimpleNamespace(status=status))
        await self.db.refresh(order)
        return res

    @staticmethod
    async def _drain_background():
        tasks = list(ops._background_print_tasks)
        if tasks:
            await asyncio.gather(*tasks)

    async def _slip(self, order):
        await self.db.refresh(order)
        return _get_print_meta(order).get("cancel_slip")


class RejectFlowTest(_DbCase):
    async def test_rejecting_a_printed_paid_order_prints_one_cancel_slip(self):
        order = await self._order()
        with patch.object(ops, "supports_independent_print_session", return_value=True):
            res = await self._reject(order)
            await self._drain_background()
        self.assertEqual(order.status, "rejected")
        self.assertTrue(res.success if hasattr(res, "success") else True)
        self.assertEqual(self.provider.await_count, 1)
        self.assertTrue(self.provider.await_args.kwargs.get("cancel_slip"))
        slip = await self._slip(order)
        self.assertEqual(slip["status"], "SUCCESS")
        self.assertEqual(slip["provider_task_id"], "slip-task")
        self.assertIsNone(slip["error_code"])
        self.assertIsNotNone(slip["completed_at"])

    async def test_the_original_print_state_is_untouched(self):
        order = await self._order()
        with patch.object(ops, "supports_independent_print_session", return_value=True):
            await self._reject(order)
            await self._drain_background()
        await self.db.refresh(order)
        initial = _get_print_meta(order)["initial_print"]
        self.assertEqual(order.print_status, "SUCCESS")
        self.assertEqual(initial["status"], "SUCCESS")
        self.assertEqual(initial["attempts"], 1)

    async def test_an_unpaid_postpay_order_cancelled_after_its_ticket_printed_also_gets_a_slip(self):
        order = await self._order(payment_status="unpaid", payment_mode="postpay")
        with patch.object(ops, "supports_independent_print_session", return_value=True):
            await self._reject(order, status="cancelled")
            await self._drain_background()
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(self.provider.await_count, 1)
        self.assertEqual((await self._slip(order))["status"], "SUCCESS")

    async def test_a_customer_cancelling_their_printed_postpay_order_also_gets_a_slip(self):
        order = await self._order(payment_status="unpaid", payment_mode="postpay")
        order.customer_id = 77
        await self.db.commit()
        with patch.object(ops, "supports_independent_print_session", return_value=True):
            res = await self._service().cancel_order(order.id, customer_id=77, participant_token=None)
            await self._drain_background()
        await self.db.refresh(order)
        self.assertEqual(order.status, "cancelled", res)
        self.assertEqual(self.provider.await_count, 1)
        self.assertTrue(self.provider.await_args.kwargs.get("cancel_slip"))
        self.assertEqual((await self._slip(order))["status"], "SUCCESS")

    async def test_no_slip_when_the_kitchen_never_got_a_ticket(self):
        for print_status in ("FAILED", "PENDING", "NOT_ELIGIBLE"):
            order = await self._order(print_status=print_status)
            with patch.object(ops, "supports_independent_print_session", return_value=True):
                await self._reject(order)
                await self._drain_background()
            self.assertEqual(order.status, "rejected")
            self.assertIsNone(await self._slip(order), print_status)
        self.assertEqual(self.provider.await_count, 0)

    async def test_an_unknown_initial_print_still_gets_a_slip(self):
        order = await self._order(print_status="UNKNOWN")
        with patch.object(ops, "supports_independent_print_session", return_value=True):
            await self._reject(order)
            await self._drain_background()
        self.assertEqual(self.provider.await_count, 1)

    async def test_without_an_independent_session_the_reject_still_succeeds_and_prints_nothing(self):
        order = await self._order()
        await self._reject(order)  # sqlite: supports_independent_print_session is False
        await self._drain_background()
        self.assertEqual(order.status, "rejected")
        self.assertEqual(self.provider.await_count, 0)

    async def test_a_scheduling_crash_never_breaks_the_reject(self):
        order = await self._order()
        with patch.object(ops, "schedule_cancel_slip", side_effect=RuntimeError("boom")):
            await self._reject(order)
        self.assertEqual(order.status, "rejected")

    async def test_other_status_changes_never_print_a_slip(self):
        order = await self._order()
        await self._service().update_order_status(order.id, SimpleNamespace(status="preparing"))
        await self._drain_background()
        self.assertEqual(self.provider.await_count, 0)
        self.assertIsNone(await self._slip(order))


class SlipOutcomeTest(_DbCase):
    async def test_a_provider_failure_is_recorded_not_raised_and_the_reject_stands(self):
        order = await self._order()
        self.provider.side_effect = RuntimeError("PRINTER_CONFIG_INCOMPLETE")
        with patch.object(ops, "supports_independent_print_session", return_value=True):
            await self._reject(order)
            await self._drain_background()
        self.assertEqual(order.status, "rejected")
        slip = await self._slip(order)
        self.assertEqual(slip["status"], "FAILED")
        self.assertEqual(slip["error_code"], "PRINTER_CONFIG_INCOMPLETE")

    async def test_an_unknown_provider_result_is_recorded_as_unknown(self):
        order = await self._order()
        self.provider.side_effect = PrintResultUnknownError("KUAIMAI_TIMEOUT")
        order.status = "rejected"
        await self.db.commit()
        result = await _print_cancel_slip(order, self.db)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual((await self._slip(order))["status"], "UNKNOWN")

    async def test_the_slip_is_sent_at_most_once_per_order(self):
        order = await self._order(status="rejected")
        first = await _print_cancel_slip(order, self.db)
        second = await _print_cancel_slip(order, self.db)
        self.assertTrue(first["success"])
        self.assertTrue(second["skipped"])
        self.assertEqual(self.provider.await_count, 1)

    async def test_unknown_and_sending_slips_are_never_reclaimed_but_failed_can_be_retried(self):
        for status, retried in (("UNKNOWN", False), ("SENDING", False), ("SUCCESS", False), ("FAILED", True)):
            self.provider.reset_mock()
            order = await self._order(status="rejected")
            meta = _get_print_meta(order)
            meta["cancel_slip"] = {"status": status}
            _set_print_meta(order, meta)
            await self.db.commit()
            await _print_cancel_slip(order, self.db)
            self.assertEqual(self.provider.await_count, 1 if retried else 0, status)

    async def test_a_disabled_kitchen_print_plan_sends_nothing(self):
        order = await self._order(status="rejected")
        with patch(CAPABILITY, AsyncMock(return_value=False)):
            result = await _print_cancel_slip(order, self.db)
        self.assertEqual(result["code"], "PLAN_CAPABILITY_DISABLED")
        self.assertEqual(self.provider.await_count, 0)
        self.assertIsNone(await self._slip(order))

    async def test_a_reprint_only_ticket_without_a_frozen_route_fails_visibly(self):
        order = await self._order(status="rejected", print_status="FAILED", with_route=False)
        meta = {"manual_reprints": [{"status": "SUCCESS"}]}
        _set_print_meta(order, meta)
        await self.db.commit()
        result = await _print_cancel_slip(order, self.db)
        self.assertEqual(result["code"], "PRINT_ROUTE_UNAVAILABLE")
        self.assertEqual(self.provider.await_count, 0)
        self.assertEqual((await self._slip(order))["status"], "FAILED")

    async def test_staff_summary_exposes_the_slip_status(self):
        order = await self._order(status="rejected")
        self.assertIsNone(build_staff_print_summary(order)["cancel_slip_status"])
        await _print_cancel_slip(order, self.db)
        await self.db.refresh(order)
        self.assertEqual(build_staff_print_summary(order)["cancel_slip_status"], "SUCCESS")


class RealRoutePayloadTest(_DbCase):
    """No provider patch: the real frozen-route executor with only the Kuaimai HTTP call faked."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self._patches[-1].stop()  # un-patch the provider executor

    async def asyncTearDown(self):
        self._patches[-1] = patch(PROVIDER, self.provider)
        self._patches[-1].start()
        await super().asyncTearDown()

    async def test_the_kuaimai_payload_carries_the_banner_the_items_and_the_table(self):
        order = await self._order(status="rejected")
        sent = AsyncMock(return_value={"success": True, "provider_task_id": None})
        with patch("app.services.kuaimai_service.print_template_order", sent):
            result = await _print_cancel_slip(order, self.db)
        self.assertTrue(result["success"], result)
        render_data = sent.await_args.args[4]
        self.assertIn(CANCEL_SLIP_BANNER, render_data["shop_name"])
        self.assertEqual(render_data["order_type_text"], CANCEL_SLIP_BANNER)
        self.assertEqual(render_data["table_no"], "A1")
        self.assertEqual(render_data["items"][0]["goods_name"], "牛肉汤")
        self.assertEqual(sent.await_args.args[0], "app_1")
        self.assertEqual(sent.await_args.args[2], "KM001")

    async def test_a_normal_ticket_is_not_marked_as_a_cancel_slip(self):
        order = await self._order(status="pending")
        sent = AsyncMock(return_value={"success": True, "provider_task_id": None})
        initial = _get_print_meta(order)["initial_print"]
        with patch("app.services.kuaimai_service.print_template_order", sent):
            await ops._execute_provider_with_frozen_route(order, self.db, initial)
        render_data = sent.await_args.args[4]
        self.assertNotIn(CANCEL_SLIP_BANNER, render_data["shop_name"])
        self.assertNotEqual(render_data["order_type_text"], CANCEL_SLIP_BANNER)


if __name__ == "__main__":
    unittest.main()
