"""P0-PRINT-04B: PRINT_FIRST removes the manual "accept" click from the normal path.

WORKBENCH is the default and the fail-closed answer; every legacy behaviour must be identical
there. PRINT_FIRST keeps ``pending`` as a resting state, still lets the owner reject, refuses a
manual accept with a clear business code, and lets a table settle only when money is accounted
for: paid prepay orders directly, postpay / table-account orders only when the cashier confirms
collection in the settle request. Nothing here enables a shop: the settings endpoint cannot
write the mode.
"""
from __future__ import annotations

import asyncio
import inspect
import unittest
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.v1.orders import (
    ORDER_ALLOWED_TRANSITIONS,
    TABLE_CLOSE_BLOCKING_STATUSES,
    TABLE_CLOSE_DONE_STATUSES,
    settle_table,
)
from app.models.base import Base
from app.models.order import Order, OrderItem
from app.models.tenant_config import TenantConfig
from app.services import fulfilment_mode as fm
from app.services.order_lifecycle_service import OrderLifecycleService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT = "t-print-first"
OTHER_TENANT = "t-workbench"


class FakeRequest:
    def __init__(self, **state):
        self.state = SimpleNamespace(**state)


def owner_request(tenant_id=TENANT):
    return FakeRequest(tenant_id=tenant_id, token_type="merchant", role="owner", account_id=None)


def _o(status="pending", payment_status="paid", payment_mode="prepay"):
    return SimpleNamespace(id=1, status=status, payment_status=payment_status, payment_mode=payment_mode)


class ModeResolutionTest(unittest.TestCase):
    def test_mode_1_2_14_missing_or_invalid_values_are_workbench(self):
        for raw in (None, "", "print_first", "PRINT-FIRST", " ", 1, True, [], {}, "UNKNOWN", "workbench"):
            self.assertEqual(fm.normalize_fulfilment_mode(raw), fm.FULFILMENT_WORKBENCH, repr(raw))
        for info in (None, {}, [], "x", {"fulfilment_mode": None}, {"other": "PRINT_FIRST"}):
            self.assertEqual(fm.fulfilment_mode_from_business_info(info), fm.FULFILMENT_WORKBENCH, repr(info))
        self.assertFalse(fm.is_print_first_mode(None))
        self.assertFalse(fm.is_print_first_mode(SimpleNamespace(business_info=None)))
        self.assertFalse(fm.is_print_first_mode("garbage"))

    def test_only_the_exact_value_enables_print_first(self):
        self.assertEqual(fm.normalize_fulfilment_mode("PRINT_FIRST"), "PRINT_FIRST")
        self.assertEqual(fm.normalize_fulfilment_mode("  PRINT_FIRST "), "PRINT_FIRST")
        self.assertTrue(fm.is_print_first_mode({"fulfilment_mode": "PRINT_FIRST"}))
        self.assertTrue(fm.is_print_first_mode(SimpleNamespace(business_info={"fulfilment_mode": "PRINT_FIRST"})))
        self.assertTrue(fm.is_print_first_mode("PRINT_FIRST"))
        self.assertFalse(fm.is_print_first_mode({"fulfilment_mode": "WORKBENCH"}))


class SettleBlockerMatrixTest(unittest.TestCase):
    def _block(self, orders, *, print_first, confirmed=False):
        return fm.settle_blocking_orders(
            orders,
            blocking_statuses=TABLE_CLOSE_BLOCKING_STATUSES,
            done_statuses=TABLE_CLOSE_DONE_STATUSES,
            print_first=print_first,
            collection_confirmed=confirmed,
        )

    def test_mode_4_workbench_blocker_is_exactly_the_legacy_rule(self):
        statuses = ["pending_payment", "pending", "preparing", "refunding", "refund_pending",
                    "refund_requested", "done", "settled", "cancelled", "rejected", "weird"]
        for status in statuses:
            order = _o(status=status)
            legacy = status in TABLE_CLOSE_BLOCKING_STATUSES or status not in TABLE_CLOSE_DONE_STATUSES
            self.assertEqual(bool(self._block([order], print_first=False, confirmed=True)), legacy, status)

    def test_mode_9_print_first_paid_pending_does_not_block(self):
        self.assertEqual(self._block([_o("pending", "paid")], print_first=True), [])
        self.assertEqual(self._block([_o("pending", "paid"), _o("done")], print_first=True), [])

    def test_mode_10_print_first_unpaid_postpay_needs_cashier_confirmation(self):
        postpay = _o("pending", "unpaid", "postpay")
        table_account = _o("pending", "unpaid", "table_account")
        for order in (postpay, table_account):
            self.assertEqual(self._block([order], print_first=True, confirmed=False), [order])
            self.assertEqual(self._block([order], print_first=True, confirmed=True), [])

    def test_mode_10_print_first_never_lets_unpaid_prepay_through(self):
        unpaid_prepay = _o("pending", "unpaid", "prepay")
        self.assertEqual(self._block([unpaid_prepay], print_first=True, confirmed=True), [unpaid_prepay])

    def test_mode_11_print_first_money_and_kitchen_exceptions_still_block(self):
        for status in ("pending_payment", "preparing", "refunding", "refund_pending", "refund_requested", "weird"):
            order = _o(status, "paid")
            self.assertEqual(self._block([order], print_first=True, confirmed=True), [order], status)
        # a pending order whose payment is anything other than "paid" (refund states) blocks too
        for payment_status in ("refund_pending", "refunding", "refunded", "failed", ""):
            order = _o("pending", payment_status)
            self.assertEqual(self._block([order], print_first=True, confirmed=True), [order], payment_status)


class _DbCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _config(self, tenant_id, mode):
        info = {} if mode is None else {"fulfilment_mode": mode}
        self.db.add(TenantConfig(tenant_id=tenant_id, member_rules={}, coupon_rules={}, business_info=info,
                                 plugin_settings={}))
        await self.db.commit()

    async def _order(self, *, tenant_id=TENANT, table_no="A1", status="pending", payment_status="paid",
                     payment_mode="prepay", total="20.00", print_status="SUCCESS"):
        order = Order(
            tenant_id=tenant_id, dining_session_id=None, table_no=table_no, total=total, status=status,
            payment_status=payment_status, payment_mode=payment_mode, payment_method="mock", source="h5",
            print_status=print_status,
        )
        self.db.add(order)
        await self.db.flush()
        self.db.add(OrderItem(id=generate_snowflake_id(), order_id=order.id, name="牛肉汤", price=total, qty=1))
        await self.db.commit()
        return order

    def _service(self, tenant_id=TENANT):
        service = OrderLifecycleService(self.db)
        service.set_tenant_id(tenant_id)
        return service

    async def _status(self, order):
        await self.db.refresh(order)
        return order.status


class ManualAcceptPolicyTest(_DbCase):
    async def test_mode_3_workbench_pending_can_still_be_accepted(self):
        await self._config(TENANT, "WORKBENCH")
        order = await self._order()
        res = await self._service().update_order_status(order.id, SimpleNamespace(status="preparing"))
        self.assertEqual(res.code, 200, res.msg)
        self.assertEqual(await self._status(order), "preparing")

    async def test_mode_1_no_config_row_behaves_as_workbench(self):
        order = await self._order()
        res = await self._service().update_order_status(order.id, SimpleNamespace(status="preparing"))
        self.assertEqual(res.code, 200, res.msg)

    async def test_mode_2_invalid_value_behaves_as_workbench(self):
        await self._config(TENANT, "print_first")
        order = await self._order()
        res = await self._service().update_order_status(order.id, SimpleNamespace(status="preparing"))
        self.assertEqual(res.code, 200, res.msg)

    async def test_mode_7_print_first_refuses_manual_accept_with_a_business_code(self):
        await self._config(TENANT, "PRINT_FIRST")
        order = await self._order()
        res = await self._service().update_order_status(order.id, SimpleNamespace(status="preparing"))
        self.assertEqual(res.code, 409)
        self.assertEqual(res.data["code"], "MANUAL_ACCEPT_DISABLED_IN_PRINT_FIRST")
        self.assertEqual(await self._status(order), "pending")  # never pushed into preparing

    async def test_print_first_is_per_tenant(self):
        await self._config(TENANT, "PRINT_FIRST")
        await self._config(OTHER_TENANT, None)
        mine = await self._order(tenant_id=TENANT)
        theirs = await self._order(tenant_id=OTHER_TENANT)
        refused = await self._service(TENANT).update_order_status(mine.id, SimpleNamespace(status="preparing"))
        allowed = await self._service(OTHER_TENANT).update_order_status(theirs.id, SimpleNamespace(status="preparing"))
        self.assertEqual(refused.code, 409)
        self.assertEqual(allowed.code, 200, allowed.msg)

    async def test_mode_8_print_first_pending_can_still_be_rejected(self):
        await self._config(TENANT, "PRINT_FIRST")
        order = await self._order()
        res = await self._service().update_order_status(order.id, SimpleNamespace(status="rejected"))
        self.assertEqual(res.code, 200, res.msg)
        self.assertEqual(await self._status(order), "rejected")

    async def test_print_first_does_not_touch_other_transitions(self):
        await self._config(TENANT, "PRINT_FIRST")
        order = await self._order(status="preparing")  # a legacy order that was already accepted
        res = await self._service().update_order_status(order.id, SimpleNamespace(status="done"))
        self.assertEqual(res.code, 200, res.msg)


class SettleTableModeTest(_DbCase):
    async def _settle(self, body=None, tenant_id=TENANT):
        return await settle_table({"table_no": "A1", **(body or {})}, owner_request(tenant_id), self.db)

    async def test_mode_4_workbench_paid_pending_still_blocks_settlement(self):
        await self._config(TENANT, "WORKBENCH")
        order = await self._order()
        res = await self._settle()
        self.assertEqual(res.code, 409)
        self.assertIn("本桌还有未完成的订单", res.msg)
        self.assertEqual(await self._status(order), "pending")

    async def test_mode_14_unconfigured_tenant_blocks_exactly_like_workbench(self):
        order = await self._order()
        res = await self._settle({"collection_confirmed": True})  # the flag means nothing in WORKBENCH
        self.assertEqual(res.code, 409)
        self.assertEqual(await self._status(order), "pending")

    async def test_mode_5_9_print_first_paid_pending_settles_without_any_kitchen_click(self):
        await self._config(TENANT, "PRINT_FIRST")
        first = await self._order()
        second = await self._order(status="done")
        res = await self._settle()
        self.assertEqual(res.code, 200, res.msg)
        self.assertEqual(res.data["settled_count"], 2)
        self.assertEqual(await self._status(first), "settled")
        self.assertEqual(await self._status(second), "settled")
        self.assertIsNotNone(first.completed_at)

    async def test_mode_10_print_first_unpaid_postpay_is_not_bypassed(self):
        await self._config(TENANT, "PRINT_FIRST")
        order = await self._order(payment_status="unpaid", payment_mode="postpay")
        blocked = await self._settle()
        self.assertEqual(blocked.code, 409)
        self.assertEqual(blocked.data["code"], "POSTPAY_COLLECTION_NOT_CONFIRMED")
        self.assertEqual(await self._status(order), "pending")
        self.assertNotEqual(order.payment_status, "paid")

        confirmed = await self._settle({"collection_confirmed": True})
        self.assertEqual(confirmed.code, 200, confirmed.msg)
        self.assertEqual(await self._status(order), "settled")
        self.assertEqual(order.payment_status, "paid")  # collected at the till, exactly as for postpay done orders

    async def test_mode_10_confirmation_must_be_literally_true(self):
        await self._config(TENANT, "PRINT_FIRST")
        order = await self._order(payment_status="unpaid", payment_mode="postpay")
        for value in ("true", 1, "yes", None):
            res = await self._settle({"collection_confirmed": value})
            self.assertEqual(res.code, 409, repr(value))
        self.assertEqual(await self._status(order), "pending")

    async def test_mode_10_unpaid_prepay_is_never_settled_even_when_confirmed(self):
        await self._config(TENANT, "PRINT_FIRST")
        order = await self._order(payment_status="unpaid", payment_mode="prepay")
        res = await self._settle({"collection_confirmed": True})
        self.assertEqual(res.code, 409)
        self.assertEqual(await self._status(order), "pending")

    async def test_mode_11_print_first_money_exceptions_and_in_progress_orders_still_block(self):
        await self._config(TENANT, "PRINT_FIRST")
        await self._order()  # fine on its own
        refunding = await self._order(status="refund_pending")
        res = await self._settle()
        self.assertEqual(res.code, 409)
        self.assertEqual(res.data["blocking_order_ids"], [str(refunding.id)])

    async def test_mode_11_legacy_preparing_order_still_blocks_after_a_mode_switch(self):
        await self._config(TENANT, "PRINT_FIRST")
        await self._order(status="preparing")
        res = await self._settle()
        self.assertEqual(res.code, 409)

    async def test_mode_12_print_failure_does_not_change_settlement_or_hide_the_exception(self):
        await self._config(TENANT, "PRINT_FIRST")
        order = await self._order(print_status="FAILED")
        res = await self._settle()
        # settlement is about money, not printing; the print exception stays on the row for staff
        self.assertEqual(res.code, 200, res.msg)
        self.assertEqual(order.print_status, "FAILED")

    async def test_print_first_is_scoped_to_the_settling_tenant(self):
        await self._config(OTHER_TENANT, "PRINT_FIRST")  # another shop's mode must not leak
        await self._config(TENANT, None)
        order = await self._order()
        res = await self._settle()
        self.assertEqual(res.code, 409)
        self.assertEqual(await self._status(order), "pending")


class StaticContractsTest(unittest.TestCase):
    def test_state_machine_is_unchanged(self):
        self.assertEqual(
            ORDER_ALLOWED_TRANSITIONS,
            {
                "pending_payment": {"cancelled"},
                "pending": {"preparing", "rejected", "cancelled"},
                "preparing": {"done"},
                "done": {"settled"},
            },
        )
        self.assertEqual(
            TABLE_CLOSE_BLOCKING_STATUSES,
            {"pending_payment", "pending", "preparing", "refunding", "refund_pending", "refund_requested"},
        )

    def test_merchant_settings_endpoint_cannot_write_the_mode(self):
        from app.api.v1 import tenant

        source = inspect.getsource(tenant.update_settings)
        self.assertIn('merged_business_info.pop("fulfilment_mode", None)', source)
        # popped after both the flat fields and the nested business_info payload are merged
        self.assertLess(source.index("merged_business_info = {"), source.index('.pop("fulfilment_mode"'))
        self.assertLess(source.index('.pop("fulfilment_mode"'), source.index("update_tenant_settings("))

    def test_auth_me_exposes_the_mode_to_every_role_via_the_central_helper(self):
        from app.api.v1 import merchant_accounts

        source = inspect.getsource(merchant_accounts.auth_me)
        self.assertIn("get_fulfilment_mode(db, principal.tenant_id)", source)

    def test_single_semantics_everything_goes_through_the_helper_module(self):
        update_src = inspect.getsource(OrderLifecycleService.update_order_status)
        settle_src = inspect.getsource(OrderLifecycleService.settle_table)
        self.assertIn("get_fulfilment_mode", update_src)
        self.assertIn("get_fulfilment_mode", settle_src)
        self.assertIn("settle_blocking_orders(", settle_src)

    def test_no_schema_and_no_auto_enablement(self):
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1]
        self.assertFalse([p for p in (root / "alembic" / "versions").glob("*.py") if "fulfilment" in p.read_text("utf-8")])
        # the module only reads the mode; nothing in it writes business_info
        source = inspect.getsource(fm)
        import re

        self.assertIsNone(re.search(r"business_info\[[^\]]+\]\s*=", source))
        self.assertNotIn("flag_modified", source)

    def test_print_pipeline_is_not_mode_aware(self):
        import app.services.order_print_service as printing
        import app.services.print_exception_alert_service as alert

        for module in (printing, alert):
            self.assertNotIn("fulfilment_mode", inspect.getsource(module))


if __name__ == "__main__":
    unittest.main()
