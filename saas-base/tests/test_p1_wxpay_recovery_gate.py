"""PROD-STABILITY-P1-01: WxpayRecoveryGate dedup/cooldown/backoff/force-fresh tests.

Runs against real MySQL + asyncmy (matching production and this repo's P0 precedent),
not SQLite alone. Requires the disposable MySQL8 test container (xiao-f1ga-mysql8,
127.0.0.1:3307, root/f1ga_disposable_root_pw); tests skip cleanly if unreachable.

Pure gate-logic tests (fast lane schedule, background backoff tiers, memory bound) use
an injected fake monotonic clock instead of real sleeps -- never patch the global
time.monotonic, since asyncio's own event loop scheduling depends on it internally.
"""

import asyncio
import time
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.core.permissions import ROLE_OWNER
from app.models.base import Base
from app.models.dining import DiningParticipant, DiningSession  # noqa: F401 -- FK targets
from app.models.menu_item import MenuItem
from app.models.order import Order
from app.models.tenant import Tenant
from app.services.wxpay_recovery_gate import GateDecision, WxpayRecoveryGate

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

MYSQL_TEST_URL = (
    "mysql+asyncmy://root:f1ga_disposable_root_pw@127.0.0.1:3307/"
    "xiao_p1_wxpay_gate_test?charset=utf8mb4"
)

from sqlalchemy.dialects.mysql.asyncmy import MySQLDialect_asyncmy  # noqa: E402

MySQLDialect_asyncmy._send_false_to_ping = True

TENANT_A = "tenant-p1-gate"


class FakeClock:
    def __init__(self, start: float = 1_000_000.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _wxpay_resource_notpay() -> dict:
    return {"trade_state": "NOTPAY", "out_trade_no": "unused"}


def _wxpay_resource_success(order: Order) -> dict:
    return {
        "trade_state": "SUCCESS",
        "out_trade_no": str(order.id),
        "transaction_id": f"wx-txn-{order.id}",
        "amount": {"total": int((Decimal(str(order.total)) * 100).to_integral_value()), "currency": "CNY"},
    }


def patch_wxpay_service(*, responses: dict[int, dict | None], enabled: bool = True, counter: list | None = None):
    """Patch app.services.wxpay_service.WxPayService. `counter` (if given) records one
    entry per REAL provider call, letting tests assert exactly how many actually happened
    -- as opposed to how many times a caller merely asked the gate."""
    mock_cls = patch("app.services.wxpay_service.WxPayService")
    started = mock_cls.start()
    instance = started.return_value
    instance.enabled = enabled

    async def _query(out_trade_no: str):
        if counter is not None:
            counter.append(out_trade_no)
        return responses.get(int(out_trade_no))

    instance.query_order_by_out_trade_no = AsyncMock(side_effect=_query)
    return mock_cls


def make_owner_request(tenant_id: str) -> Request:
    req = Request(
        {
            "type": "http", "method": "GET", "path": "/api/v1/orders",
            "headers": [], "query_string": b"date_str=today",
            "server": ("testserver", 80), "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    req.state.tenant_id = tenant_id
    req.state.token_type = "merchant"
    req.state.role = ROLE_OWNER
    req.state.account_id = None
    return req


class _MySQLGateTestBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(
            MYSQL_TEST_URL,
            pool_size=20,
            max_overflow=20,
            connect_args={"init_command": "SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci"},
        )
        try:
            async with self.engine.connect():
                pass
        except OperationalError:
            await self.engine.dispose()
            self.skipTest(
                "MySQL test container not reachable at 127.0.0.1:3307 "
                "(docker start xiao-f1ga-mysql8)"
            )
            return

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self._db_patcher = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._db_patcher.start()

        self.clock = FakeClock()
        self.gate = WxpayRecoveryGate(clock=self.clock)
        self._gate_patcher = patch("app.services.wxpay_recovery_gate.recovery_gate", self.gate)
        self._gate_patcher.start()

        seed = self.SessionLocal()
        self.tenant = Tenant(
            tenant_id=TENANT_A, name="P1 Gate Restaurant", password_hash="x",
            status=True, is_open=True, payment_mode="prepay",
        )
        seed.add(self.tenant)
        self.dish = MenuItem(tenant_id=TENANT_A, name="牛肉汤", price="18.00", available=True, stock=None)
        seed.add(self.dish)
        await seed.commit()
        await seed.close()

    async def asyncTearDown(self):
        self._gate_patcher.stop()
        self._db_patcher.stop()
        await self.engine.dispose()

    async def _make_order(self, db, *, status, payment_status, created_at, total="18.00", table_no="A1"):
        order = Order(
            tenant_id=TENANT_A, table_no=table_no, status=status,
            payment_status=payment_status, payment_mode="prepay",
            total=Decimal(total), created_at=created_at,
        )
        db.add(order)
        await db.flush()
        return order


class ThirtyCallersOneOrderTest(_MySQLGateTestBase):
    """TEST A: 30 mixed-source calls against a single pending order must produce far
    fewer than 30 real provider queries, and force_fresh calls must never be silently
    swallowed by cooldown."""

    async def test_30_callers_dedup_and_force_fresh_never_skipped(self):
        db = self.SessionLocal()
        order = await self._make_order(
            db, status="pending_payment", payment_status="unpaid", created_at=datetime.utcnow(),
        )
        await db.commit()

        order_id = order.id

        async def fresh_order():
            # Every real caller re-selects fresh before touching an order -- see
            # order_lifecycle_service.py/main.py/orders.py, all fixed in this same phase
            # to never reuse an ORM object across a recovery call boundary. A prior
            # iteration's recovery attempt may have rolled back `db`, expiring `order`.
            r = await db.execute(select(Order).where(Order.id == order_id))
            return r.scalar_one()

        provider_calls: list = []
        patcher = patch_wxpay_service(responses={order_id: _wxpay_resource_notpay()}, counter=provider_calls)
        try:
            invocations = 0
            force_fresh_decisions = []
            for i in range(30):
                o = await fresh_order()
                if i % 6 == 0:
                    # Class C-style force-fresh caller mixed in periodically.
                    outcome = await self.gate.attempt_recovery(
                        o, db, source="cancel_precheck", force_fresh=True, wait_for_inflight=True,
                    )
                    force_fresh_decisions.append(outcome.decision)
                elif i % 3 == 0:
                    outcome = await self.gate.attempt_recovery(
                        o, db, source="client_order_query", fast_lane=True, wait_for_inflight=True,
                    )
                else:
                    outcome = await self.gate.attempt_recovery(o, db, source="pending_payment_background")
                invocations += 1
                self.clock.advance(0.3)
            self.clock.advance(200)  # let cooldown fully lapse before the check below
        finally:
            patcher.stop()

        self.assertEqual(invocations, 30)
        self.assertLess(len(provider_calls), 30, f"provider calls={len(provider_calls)}")
        # Every force_fresh call must have produced either a real attempt or a genuine
        # joined-in-flight result -- never SKIPPED_COOLDOWN.
        self.assertNotIn(GateDecision.SKIPPED_COOLDOWN, force_fresh_decisions)
        await db.close()


class TenConcurrentGateCallsTest(_MySQLGateTestBase):
    """TEST B: 10 concurrent gate calls for the same pending order must produce at most
    one in-flight real provider query; no MissingGreenlet, no session errors."""

    async def test_10_concurrent_same_order_single_provider_query(self):
        db = self.SessionLocal()
        order = await self._make_order(
            db, status="pending_payment", payment_status="unpaid", created_at=datetime.utcnow(),
        )
        await db.commit()

        provider_calls: list = []
        patcher = patch_wxpay_service(responses={order.id: _wxpay_resource_notpay()}, counter=provider_calls)
        try:
            async def one_call():
                call_db = self.SessionLocal()
                try:
                    return await self.gate.attempt_recovery(
                        order, call_db, source="pending_payment_background", wait_for_inflight=True,
                    )
                finally:
                    await call_db.close()

            results = await asyncio.gather(*(one_call() for _ in range(10)), return_exceptions=True)
        finally:
            patcher.stop()

        errors = [r for r in results if isinstance(r, Exception)]
        self.assertEqual(errors, [], f"concurrent gate calls raised: {errors}")
        self.assertEqual(len(provider_calls), 1, f"expected exactly 1 real provider query, got {len(provider_calls)}")
        await db.close()

    async def test_10_concurrent_get_orders_zero_provider_queries(self):
        from app.api.v1.orders import list_orders as list_orders_endpoint

        db0 = self.SessionLocal()
        await self._make_order(
            db0, status="pending_payment", payment_status="unpaid", created_at=datetime.utcnow(),
        )
        await db0.commit()
        await db0.close()

        provider_calls: list = []
        patcher = patch_wxpay_service(responses={}, counter=provider_calls)
        try:
            async def one_call():
                call_db = self.SessionLocal()
                try:
                    request = make_owner_request(TENANT_A)
                    return await list_orders_endpoint(request, date_str="today", db=call_db, response=None)
                finally:
                    await call_db.close()

            results = await asyncio.gather(*(one_call() for _ in range(10)), return_exceptions=True)
        finally:
            patcher.stop()

        errors = [r for r in results if isinstance(r, Exception)]
        self.assertEqual(errors, [], f"concurrent GET /orders raised: {errors}")
        for r in results:
            self.assertEqual(r.code, 200)
        self.assertEqual(len(provider_calls), 0, "merchant_order_query must never call WeChat")


class EventLoopResponsivenessTest(_MySQLGateTestBase):
    """TEST C: proves asyncio.to_thread actually isolates the blocking sync WeChat SDK
    call from the event loop -- exercises the REAL query_order_by_out_trade_no code path
    (not a mocked coroutine) with a genuinely slow synchronous call, and measures whether
    an unrelated heartbeat coroutine keeps progressing during it."""

    async def _run_with_blocking_sdk_call(self, *, use_to_thread: bool) -> tuple[int, float]:
        from app.services import wxpay_service as wxpay_service_module

        svc = wxpay_service_module.WxPayService.__new__(wxpay_service_module.WxPayService)
        sync_client = type("FakeSyncClient", (), {})()

        def blocking_query(out_trade_no=None):
            time.sleep(1.2)  # genuinely blocking, synchronous -- same shape as the real SDK
            return (200, '{"trade_state": "NOTPAY"}')

        sync_client.query = blocking_query
        svc._client = sync_client

        heartbeat_ticks = 0
        stop = False

        async def heartbeat():
            nonlocal heartbeat_ticks
            while not stop:
                heartbeat_ticks += 1
                await asyncio.sleep(0.05)

        async def call_sdk():
            if use_to_thread:
                return await svc.query_order_by_out_trade_no("123")
            # Simulate the pre-P1 code path: synchronous call awaited with no thread
            # offload at all.
            with patch.object(asyncio, "to_thread", new=AsyncMock(side_effect=lambda fn, *a, **k: fn(*a, **k))):
                return await svc.query_order_by_out_trade_no("123")

        hb_task = asyncio.create_task(heartbeat())
        start = time.monotonic()
        await call_sdk()
        elapsed = time.monotonic() - start
        stop = True
        await hb_task
        return heartbeat_ticks, elapsed

    async def test_event_loop_blocked_before_to_thread(self):
        ticks, elapsed = await self._run_with_blocking_sdk_call(use_to_thread=False)
        # ~1.2s blocking call with a 50ms heartbeat: if the loop were free, we'd expect
        # ~24 ticks; if frozen, essentially 0-1 (only ticks that happened to fire before
        # the blocking call began).
        self.assertLessEqual(ticks, 2, f"heartbeat ticked {ticks} times while allegedly blocked")
        self.assertGreaterEqual(elapsed, 1.1)

    async def test_event_loop_responsive_after_to_thread(self):
        ticks, elapsed = await self._run_with_blocking_sdk_call(use_to_thread=True)
        self.assertGreaterEqual(ticks, 15, f"heartbeat only ticked {ticks} times -- event loop was blocked")
        self.assertGreaterEqual(elapsed, 1.1)


class ClientFastLaneUnitTest(unittest.TestCase):
    """TEST D, pure gate logic with a fake clock -- no DB needed."""

    def test_fast_lane_schedule_immediate_2s_5s_then_standard(self):
        async def run():
            clock = FakeClock()
            gate = WxpayRecoveryGate(clock=clock)

            class FakeOrder:
                id = 42
                tenant_id = "t1"
                created_at = datetime.utcnow()

            order = FakeOrder()
            with patch("app.services.order_payment_service.OrderPaymentService") as MockSvc:
                MockSvc.return_value._recover_wxpay_order_if_paid = AsyncMock(return_value=False)

                out1 = await gate.attempt_recovery(order, db=object(), source="client_order_query", fast_lane=True)
                self.assertEqual(out1.decision, GateDecision.NOT_RECOVERED)

                clock.advance(1.0)
                out2 = await gate.attempt_recovery(order, db=object(), source="client_order_query", fast_lane=True)
                self.assertEqual(out2.decision, GateDecision.SKIPPED_COOLDOWN)

                clock.advance(1.5)  # t+2.5s
                out3 = await gate.attempt_recovery(order, db=object(), source="client_order_query", fast_lane=True)
                self.assertEqual(out3.decision, GateDecision.NOT_RECOVERED)

                clock.advance(2.9)  # t+5.4s
                out4 = await gate.attempt_recovery(order, db=object(), source="client_order_query", fast_lane=True)
                self.assertEqual(out4.decision, GateDecision.NOT_RECOVERED)

                # A simulated 6x/900ms client burst should NOT have produced 6 real
                # provider queries -- only the 3 fast-lane-scheduled ones above.
                self.assertEqual(MockSvc.return_value._recover_wxpay_order_if_paid.await_count, 3)

                clock.advance(1.0)  # t+6.4s -- 4th falls to standard cadence
                out5 = await gate.attempt_recovery(order, db=object(), source="client_order_query", fast_lane=True)
                self.assertEqual(out5.decision, GateDecision.SKIPPED_COOLDOWN)
                self.assertGreater(out5.cooldown_seconds, 50)

        asyncio.run(run())


class BackgroundBackoffUnitTest(unittest.TestCase):
    """TEST E: order-age-based progressive cooldown tiers, fake clock."""

    def test_tiers_by_order_age(self):
        async def run():
            clock = FakeClock()
            gate = WxpayRecoveryGate(clock=clock)

            with patch("app.services.order_payment_service.OrderPaymentService") as MockSvc:
                MockSvc.return_value._recover_wxpay_order_if_paid = AsyncMock(return_value=False)

                for age_minutes, expected_cooldown in ((3, 60.0), (6, 120.0), (12, 180.0)):
                    class FakeOrder:
                        id = int(age_minutes * 1000)
                        tenant_id = "t1"
                        created_at = datetime.utcnow() - timedelta(minutes=age_minutes)

                    order = FakeOrder()
                    out = await gate.attempt_recovery(order, db=object(), source="pending_payment_background")
                    self.assertEqual(out.decision, GateDecision.NOT_RECOVERED)

                    clock.advance(expected_cooldown - 5)
                    out_early = await gate.attempt_recovery(order, db=object(), source="pending_payment_background")
                    self.assertEqual(
                        out_early.decision, GateDecision.SKIPPED_COOLDOWN,
                        f"age={age_minutes}min should still be in cooldown 5s early",
                    )

                    clock.advance(10)
                    out_late = await gate.attempt_recovery(order, db=object(), source="pending_payment_background")
                    self.assertEqual(
                        out_late.decision, GateDecision.NOT_RECOVERED,
                        f"age={age_minutes}min should be eligible after {expected_cooldown}s",
                    )

        asyncio.run(run())


class PaymentSuccessDuringCooldownTest(_MySQLGateTestBase):
    """TEST F: background NOTPAY -> cooldown -> provider becomes SUCCESS -> must recover
    once the cooldown window elapses, never permanently missed."""

    async def test_success_discovered_after_cooldown_elapses(self):
        db = self.SessionLocal()
        order = await self._make_order(
            db, status="pending_payment", payment_status="unpaid",
            created_at=datetime.utcnow() - timedelta(minutes=3), total="18.00",
        )
        await db.commit()
        order_id = order.id

        async def fresh_order():
            # Every real caller re-selects fresh before touching an order -- a prior
            # gate call may have rolled back `db`, expiring the old ORM instance.
            r = await db.execute(select(Order).where(Order.id == order_id))
            return r.scalar_one()

        responses = {order_id: _wxpay_resource_notpay()}
        patcher = patch_wxpay_service(responses=responses)
        try:
            out1 = await self.gate.attempt_recovery(order, db, source="pending_payment_background")
            self.assertEqual(out1.decision, GateDecision.NOT_RECOVERED)

            # Real-world payment success arrives; webhook still lost. Re-select fresh --
            # the NOTPAY attempt above rolled back `db`, expiring the old `order`.
            responses[order_id] = _wxpay_resource_success(await fresh_order())

            self.clock.advance(55)
            o = await fresh_order()
            out_early = await self.gate.attempt_recovery(o, db, source="pending_payment_background")
            self.assertEqual(out_early.decision, GateDecision.SKIPPED_COOLDOWN)

            self.clock.advance(10)  # past the 60s tier
            o = await fresh_order()
            with patch(
                "app.services.order_print_service._print_paid_order_ticket",
                new=AsyncMock(return_value=None),
            ):
                out_recovered = await self.gate.attempt_recovery(o, db, source="pending_payment_background")
            self.assertEqual(out_recovered.decision, GateDecision.RECOVERED)
            self.assertTrue(out_recovered.recovered)
        finally:
            patcher.stop()

        verify_db = self.SessionLocal()
        try:
            refreshed = await verify_db.get(Order, order_id)
            self.assertEqual(refreshed.payment_status, "paid")
        finally:
            await verify_db.close()
        await db.close()


class CallbackDuringCooldownTest(_MySQLGateTestBase):
    """TEST G: the webhook callback path never imports or touches the gate at all -- a
    cooldown active for an order must never block/delay the callback's own payment
    success application."""

    async def test_callback_path_does_not_reference_gate(self):
        import inspect

        from app.services.order_payment_service import OrderPaymentService

        source = inspect.getsource(OrderPaymentService.wxpay_notify)
        self.assertNotIn("recovery_gate", source)
        self.assertNotIn("wxpay_recovery_gate", source)

    async def test_callback_succeeds_while_gate_cooldown_active(self):
        db = self.SessionLocal()
        order = await self._make_order(
            db, status="pending_payment", payment_status="unpaid", created_at=datetime.utcnow(), total="18.00",
        )
        await db.commit()
        order_id = order.id

        # Put the order into cooldown via a normal background NOTPAY attempt.
        patcher = patch_wxpay_service(responses={order_id: _wxpay_resource_notpay()})
        try:
            out = await self.gate.attempt_recovery(order, db, source="pending_payment_background")
            self.assertEqual(out.decision, GateDecision.NOT_RECOVERED)
        finally:
            patcher.stop()

        entry = self.gate._entries.get(order_id)
        self.assertIsNotNone(entry)
        self.assertGreater(entry.next_allowed_monotonic, self.clock())

        # Directly apply the success fact the same way the real webhook callback does --
        # the gate is never consulted on this path (confirmed structurally above). The
        # NOTPAY attempt above rolled back `db`, expiring the old `order` -- a real
        # callback would never reuse that in-memory object either, it always re-selects
        # fresh in its own request.
        from app.services.order_payment_service import OrderPaymentService

        fresh_result = await db.execute(select(Order).where(Order.id == order_id))
        fresh = fresh_result.scalar_one()

        with patch(
            "app.services.order_print_service._print_paid_order_ticket",
            new=AsyncMock(return_value=None),
        ):
            svc = OrderPaymentService(db)
            await svc._on_payment_success(fresh, payment_method="wxpay")
            await db.commit()

        verify_db = self.SessionLocal()
        try:
            refreshed = await verify_db.get(Order, order_id)
            self.assertEqual(refreshed.payment_status, "paid")
        finally:
            await verify_db.close()
        await db.close()


class StaleCancelRaceTest(_MySQLGateTestBase):
    """TEST H: T0 NOTPAY -> T1 cooldown -> T2 provider becomes SUCCESS -> T3 no callback
    -> T4 stale cleanup's force_fresh must discover SUCCESS and never cancel."""

    async def test_force_fresh_discovers_late_success_before_cancel(self):
        from app.main import _stale_order_cleanup_once

        old_created = datetime.utcnow() - timedelta(minutes=16)
        db = self.SessionLocal()
        order = await self._make_order(
            db, status="pending_payment", payment_status="unpaid", created_at=old_created, total="18.00",
        )
        await db.commit()
        await db.close()

        responses = {order.id: _wxpay_resource_notpay()}
        patcher = patch_wxpay_service(responses=responses)
        try:
            # T0: an earlier background attempt put this order into cooldown.
            probe_db = self.SessionLocal()
            out0 = await self.gate.attempt_recovery(order, probe_db, source="pending_payment_background")
            self.assertEqual(out0.decision, GateDecision.NOT_RECOVERED)
            await probe_db.close()

            # T2: real-world payment succeeds; webhook (T3) never arrives.
            responses[order.id] = _wxpay_resource_success(order)

            # T4: stale cleanup runs immediately (cooldown clock NOT advanced) -- its
            # force_fresh must bypass cooldown and see the real SUCCESS.
            with patch(
                "app.services.order_print_service._print_paid_order_ticket",
                new=AsyncMock(return_value=None),
            ):
                await _stale_order_cleanup_once()
        finally:
            patcher.stop()

        verify_db = self.SessionLocal()
        try:
            refreshed = await verify_db.get(Order, order.id)
            self.assertNotEqual(refreshed.status, "cancelled")
            self.assertEqual(refreshed.payment_status, "paid")
        finally:
            await verify_db.close()


class CancelPrecheckRaceTest(_MySQLGateTestBase):
    """TEST I: user clicks cancel while cooldown is active but the order has actually
    just succeeded -- force_fresh must prevent the erroneous cancel."""

    async def test_cancel_precheck_force_fresh_blocks_erroneous_cancel(self):
        from app.services.order_lifecycle_service import OrderLifecycleService

        db = self.SessionLocal()
        order = await self._make_order(
            db, status="pending_payment", payment_status="unpaid", created_at=datetime.utcnow(), total="18.00",
        )
        await db.commit()
        order_id = order.id

        responses = {order_id: _wxpay_resource_notpay()}
        patcher = patch_wxpay_service(responses=responses)
        try:
            out0 = await self.gate.attempt_recovery(order, db, source="pending_payment_background")
            self.assertEqual(out0.decision, GateDecision.NOT_RECOVERED)

            # NOTPAY above rolled back `db`, expiring the old `order` -- re-select fresh,
            # same as any real caller would before touching it again.
            fresh_result = await db.execute(select(Order).where(Order.id == order_id))
            responses[order_id] = _wxpay_resource_success(fresh_result.scalar_one())

            with patch(
                "app.services.order_print_service._print_paid_order_ticket",
                new=AsyncMock(return_value=None),
            ):
                resp = await OrderLifecycleService(db).cancel_order(
                    order_id, customer_id=None, participant_token=None,
                )
        finally:
            patcher.stop()

        # cancel_order requires ownership (customer_id/participant_id match) -- this
        # order has neither set, so the ownership branches are simply skipped and it
        # proceeds straight to the payment precheck + mutation. What matters here is
        # that the order is NOT left cancelled despite the pending cancel request.
        verify_db = self.SessionLocal()
        try:
            refreshed = await verify_db.get(Order, order_id)
            self.assertNotEqual(refreshed.status, "cancelled")
            self.assertEqual(refreshed.payment_status, "paid")
        finally:
            await verify_db.close()
        await db.close()


class MerchantOrdersPureReadTest(_MySQLGateTestBase):
    """TEST J: GET /orders must never call WeChat, must still run print reconciliation,
    and must return 100/100 successfully."""

    async def test_100x_zero_provider_queries_print_reconcile_still_runs(self):
        from app.api.v1.orders import list_orders as list_orders_endpoint

        db0 = self.SessionLocal()
        await self._make_order(
            db0, status="pending_payment", payment_status="unpaid", created_at=datetime.utcnow(),
        )
        await self._make_order(
            db0, status="pending", payment_status="paid", created_at=datetime.utcnow(), table_no="A2",
        )
        await db0.commit()
        await db0.close()

        provider_calls: list = []
        patcher = patch_wxpay_service(responses={}, counter=provider_calls)
        reconcile_calls: list = []

        async def _spy_reconcile(db, orders, **kwargs):
            reconcile_calls.append(len(orders))
            return 0

        try:
            with patch(
                "app.services.order_print_service.reconcile_print_orders",
                new=AsyncMock(side_effect=_spy_reconcile),
            ):
                failures = []
                for i in range(100):
                    call_db = self.SessionLocal()
                    try:
                        request = make_owner_request(TENANT_A)
                        resp = await list_orders_endpoint(request, date_str="today", db=call_db, response=None)
                        if resp.code != 200:
                            failures.append((i, resp.code))
                    finally:
                        await call_db.close()
        finally:
            patcher.stop()

        self.assertEqual(failures, [])
        self.assertEqual(len(provider_calls), 0, "GET /orders must never call WeChat")
        self.assertEqual(len(reconcile_calls), 100, "print reconciliation must still run on every call")


class MultiOrderBatchIsolationTest(_MySQLGateTestBase):
    """P1 final-checkpoint STEP 4: a rollback while recovering one order in a background
    batch must never expire, crash, or undo the outcome of a SIBLING order processed in
    the same pass. Covers both orderings (NOTPAY-then-SUCCESS and SUCCESS-then-NOTPAY)
    against the real, now per-order-isolated _stale_order_cleanup_once and
    _pending_payment_reconcile_once -- not just the gate in isolation."""

    async def _two_stale_orders(self, *, notpay_table, success_table):
        old_created = datetime.utcnow() - timedelta(minutes=16)
        db = self.SessionLocal()
        notpay_order = await self._make_order(
            db, status="pending_payment", payment_status="unpaid",
            created_at=old_created, total="18.00", table_no=notpay_table,
        )
        success_order = await self._make_order(
            db, status="pending_payment", payment_status="unpaid",
            created_at=old_created, total="18.00", table_no=success_table,
        )
        await db.commit()
        await db.close()
        return notpay_order.id, success_order.id

    async def _assert_isolated_outcome(self, notpay_id, success_id):
        verify_db = self.SessionLocal()
        try:
            notpay_refreshed = await verify_db.get(Order, notpay_id)
            success_refreshed = await verify_db.get(Order, success_id)
            # The NOTPAY order's own rollback must not have prevented ITS OWN normal
            # stale-cleanup cancellation either.
            self.assertEqual(notpay_refreshed.status, "cancelled")
            self.assertEqual(notpay_refreshed.payment_status, "unpaid")
            # The critical assertion: the sibling's real SUCCESS must survive, never
            # silently undone by the other order's rollback in a shared session.
            self.assertEqual(success_refreshed.payment_status, "paid")
            self.assertNotEqual(success_refreshed.status, "cancelled")
        finally:
            await verify_db.close()

    async def test_stale_cleanup_notpay_order_a_success_order_b(self):
        from app.main import _stale_order_cleanup_once

        notpay_id, success_id = await self._two_stale_orders(notpay_table="A", success_table="B")
        responses = {
            notpay_id: _wxpay_resource_notpay(),
            success_id: {
                "trade_state": "SUCCESS", "out_trade_no": str(success_id),
                "transaction_id": f"wx-txn-{success_id}",
                "amount": {"total": 1800, "currency": "CNY"},
            },
        }
        patcher = patch_wxpay_service(responses=responses)
        try:
            with patch(
                "app.services.order_print_service._print_paid_order_ticket",
                new=AsyncMock(return_value=None),
            ):
                await _stale_order_cleanup_once()
        finally:
            patcher.stop()

        await self._assert_isolated_outcome(notpay_id, success_id)

    async def test_stale_cleanup_success_order_a_notpay_order_b(self):
        from app.main import _stale_order_cleanup_once

        # Same scenario, roles swapped between which order is created first --
        # per-order session isolation must make batch position irrelevant.
        success_id, notpay_id = await self._two_stale_orders(notpay_table="B2", success_table="A2")
        responses = {
            notpay_id: _wxpay_resource_notpay(),
            success_id: {
                "trade_state": "SUCCESS", "out_trade_no": str(success_id),
                "transaction_id": f"wx-txn-{success_id}",
                "amount": {"total": 1800, "currency": "CNY"},
            },
        }
        patcher = patch_wxpay_service(responses=responses)
        try:
            with patch(
                "app.services.order_print_service._print_paid_order_ticket",
                new=AsyncMock(return_value=None),
            ):
                await _stale_order_cleanup_once()
        finally:
            patcher.stop()

        await self._assert_isolated_outcome(notpay_id, success_id)

    async def test_pending_payment_reconcile_notpay_and_success_same_batch(self):
        from app.main import _pending_payment_reconcile_once

        old_created = datetime.utcnow() - timedelta(seconds=100)
        db = self.SessionLocal()
        notpay_order = await self._make_order(
            db, status="pending_payment", payment_status="unpaid",
            created_at=old_created, total="18.00", table_no="C1",
        )
        success_order = await self._make_order(
            db, status="pending_payment", payment_status="unpaid",
            created_at=old_created, total="18.00", table_no="C2",
        )
        await db.commit()
        await db.close()

        responses = {
            notpay_order.id: _wxpay_resource_notpay(),
            success_order.id: {
                "trade_state": "SUCCESS", "out_trade_no": str(success_order.id),
                "transaction_id": f"wx-txn-{success_order.id}",
                "amount": {"total": 1800, "currency": "CNY"},
            },
        }
        patcher = patch_wxpay_service(responses=responses)
        try:
            with patch(
                "app.services.order_print_service._print_paid_order_ticket",
                new=AsyncMock(return_value=None),
            ):
                await _pending_payment_reconcile_once()
        finally:
            patcher.stop()

        verify_db = self.SessionLocal()
        try:
            notpay_refreshed = await verify_db.get(Order, notpay_order.id)
            success_refreshed = await verify_db.get(Order, success_order.id)
            # pending_payment_background never cancels -- the NOTPAY order just stays
            # pending_payment, unaffected either way.
            self.assertEqual(notpay_refreshed.status, "pending_payment")
            self.assertEqual(notpay_refreshed.payment_status, "unpaid")
            self.assertEqual(success_refreshed.payment_status, "paid")
        finally:
            await verify_db.close()


class ProcessRestartSemanticsTest(_MySQLGateTestBase):
    """TEST K: recreating the gate (simulating a process restart) loses cooldown state
    but causes at most one extra query, no correctness risk."""

    async def test_restart_causes_at_most_one_extra_query_no_correctness_risk(self):
        db = self.SessionLocal()
        order = await self._make_order(
            db, status="pending_payment", payment_status="unpaid", created_at=datetime.utcnow(),
        )
        await db.commit()
        order_id = order.id

        patcher = patch_wxpay_service(responses={order_id: _wxpay_resource_notpay()})
        try:
            out1 = await self.gate.attempt_recovery(order, db, source="pending_payment_background")
            self.assertEqual(out1.decision, GateDecision.NOT_RECOVERED)
            self.assertEqual(out1.attempt_count, 1)

            # Simulate a process restart: brand new gate, all state lost. A real "next
            # attempt" after a restart always comes from a fresh query (the next
            # background loop tick, the next request) -- never a reused in-memory
            # object, since the earlier NOTPAY attempt already rolled back `db`.
            fresh_result = await db.execute(select(Order).where(Order.id == order_id))
            fresh_order = fresh_result.scalar_one()
            fresh_gate = WxpayRecoveryGate(clock=self.clock)
            out2 = await fresh_gate.attempt_recovery(fresh_order, db, source="pending_payment_background")
            # Not "SKIPPED_COOLDOWN" despite the old gate having just set a cooldown --
            # the new gate has no memory of it. Exactly one fresh real query happens.
            self.assertEqual(out2.decision, GateDecision.NOT_RECOVERED)
            self.assertEqual(out2.attempt_count, 1)
        finally:
            patcher.stop()
        await db.close()


class MemoryBoundTest(unittest.TestCase):
    """TEST L: entry count stays bounded under a large number of distinct orders; TTL
    sweep reclaims stale entries."""

    def test_max_entries_enforced_and_ttl_sweep_reclaims(self):
        async def run():
            clock = FakeClock()
            gate = WxpayRecoveryGate(clock=clock, max_entries=50, ttl_seconds=100)

            with patch("app.services.order_payment_service.OrderPaymentService") as MockSvc:
                MockSvc.return_value._recover_wxpay_order_if_paid = AsyncMock(return_value=False)

                for i in range(80):
                    class FakeOrder:
                        id = i
                        tenant_id = "t1"
                        created_at = datetime.utcnow()

                    await gate.attempt_recovery(FakeOrder(), db=object(), source="pending_payment_background")

            self.assertLessEqual(gate.entry_count(), 50, "gate must never grow past max_entries")

            # TTL sweep: age everything out, confirm cleanup.
            clock.advance(1000)
            removed = gate.sweep_expired()
            self.assertGreater(removed, 0)
            self.assertEqual(gate.entry_count(), 0)

        asyncio.run(run())


class ProviderErrorTest(unittest.TestCase):
    """TEST M: a provider-side exception must clear in_flight, never leave it stuck, and
    allow a later retry."""

    def test_connect_read_timeout_clears_inflight_and_allows_retry(self):
        """Specifically a requests.exceptions.Timeout (what the scoped (5,10)s
        connect/read timeout on the recovery-query WxPayService construction would
        actually raise), not just a generic exception."""
        async def run():
            import requests

            clock = FakeClock()
            gate = WxpayRecoveryGate(clock=clock)

            class FakeOrder:
                id = 55
                tenant_id = "t1"
                created_at = datetime.utcnow()

            order = FakeOrder()
            with patch("app.services.order_payment_service.OrderPaymentService") as MockSvc:
                MockSvc.return_value._recover_wxpay_order_if_paid = AsyncMock(
                    side_effect=requests.exceptions.Timeout("simulated connect/read timeout")
                )
                out = await gate.attempt_recovery(order, db=object(), source="pending_payment_background")
                self.assertEqual(out.decision, GateDecision.PROVIDER_ERROR)

            entry = gate._entries.get(55)
            self.assertIsNotNone(entry)
            self.assertIsNone(entry.in_flight_future, "in_flight must be cleared after a timeout")

            # Background loop survival: the gate call itself must not raise past this
            # point (confirmed above -- attempt_recovery returned normally), so the
            # existing try/except in _stale_order_cleanup_loop/_pending_payment_reconcile_loop
            # is never even exercised by this path.

            # Class C retry must still be possible.
            clock.advance(200)
            with patch("app.services.order_payment_service.OrderPaymentService") as MockSvc2:
                MockSvc2.return_value._recover_wxpay_order_if_paid = AsyncMock(return_value=False)
                out2 = await gate.attempt_recovery(
                    order, db=object(), source="cancel_precheck",
                    force_fresh=True, wait_for_inflight=True,
                )
                self.assertEqual(out2.decision, GateDecision.NOT_RECOVERED)

        asyncio.run(run())

    def test_provider_exception_clears_in_flight_and_allows_retry(self):
        async def run():
            clock = FakeClock()
            gate = WxpayRecoveryGate(clock=clock)

            class FakeOrder:
                id = 7
                tenant_id = "t1"
                created_at = datetime.utcnow()

            order = FakeOrder()
            with patch("app.services.order_payment_service.OrderPaymentService") as MockSvc:
                MockSvc.return_value._recover_wxpay_order_if_paid = AsyncMock(
                    side_effect=RuntimeError("simulated provider timeout")
                )
                out = await gate.attempt_recovery(order, db=object(), source="pending_payment_background")
                self.assertEqual(out.decision, GateDecision.PROVIDER_ERROR)

            entry = gate._entries.get(order.id)
            self.assertIsNotNone(entry)
            self.assertIsNone(entry.in_flight_future, "in_flight must be cleared after a provider error")

            # A later attempt (after the error-tier cooldown) must be allowed, not stuck.
            clock.advance(200)
            with patch("app.services.order_payment_service.OrderPaymentService") as MockSvc2:
                MockSvc2.return_value._recover_wxpay_order_if_paid = AsyncMock(return_value=False)
                out2 = await gate.attempt_recovery(order, db=object(), source="pending_payment_background")
                self.assertEqual(out2.decision, GateDecision.NOT_RECOVERED)

        asyncio.run(run())


class GateCancellationSafetyTest(unittest.TestCase):
    """P1 final-checkpoint STEP 5: asyncio Task cancellation is subtler than a plain
    exception -- cancelling a task that's suspended on `await some_future` calls
    `.cancel()` on that future too (Task._fut_waiter), which would otherwise corrupt a
    SHARED future for every other awaiter. And CancelledError is a BaseException (since
    Python 3.8), so a bare `except Exception` never catches it."""

    def test_executor_cancellation_clears_inflight_and_allows_retry(self):
        async def run():
            gate = WxpayRecoveryGate()

            class FakeOrder:
                id = 1
                tenant_id = "t1"
                created_at = datetime.utcnow()

            order = FakeOrder()

            async def hangs_forever(order, source):
                await asyncio.sleep(1000)
                return False

            with patch("app.services.order_payment_service.OrderPaymentService") as MockSvc:
                MockSvc.return_value._recover_wxpay_order_if_paid = hangs_forever
                task = asyncio.create_task(
                    gate.attempt_recovery(order, db=object(), source="pending_payment_background")
                )
                await asyncio.sleep(0.05)
                entry = gate._entries.get(1)
                self.assertIsNotNone(entry)
                self.assertIsNotNone(entry.in_flight_future, "should be in-flight before cancellation")

                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

                entry = gate._entries.get(1)
                self.assertIsNone(
                    entry.in_flight_future,
                    "in_flight must be cleared even when the EXECUTOR itself is cancelled "
                    "mid-query -- without an explicit CancelledError handler, `except "
                    "Exception` never runs (CancelledError is a BaseException) and this "
                    "would be a permanently stuck lock for this order_id.",
                )

            # Retry must be possible afterward -- not permanently stuck.
            with patch("app.services.order_payment_service.OrderPaymentService") as MockSvc2:
                MockSvc2.return_value._recover_wxpay_order_if_paid = AsyncMock(return_value=False)
                out = await gate.attempt_recovery(
                    order, db=object(), source="cancel_precheck",
                    force_fresh=True, wait_for_inflight=True,
                )
                self.assertEqual(out.decision, GateDecision.NOT_RECOVERED)

        asyncio.run(run())

    def test_joiner_cancellation_does_not_corrupt_executor_or_other_joiners(self):
        async def run():
            gate = WxpayRecoveryGate()

            class FakeOrder:
                id = 2
                tenant_id = "t1"
                created_at = datetime.utcnow()

            order = FakeOrder()

            async def slow_query(order, source):
                await asyncio.sleep(0.3)
                return True

            with patch("app.services.order_payment_service.OrderPaymentService") as MockSvc:
                MockSvc.return_value._recover_wxpay_order_if_paid = slow_query
                executor_task = asyncio.create_task(
                    gate.attempt_recovery(order, db=object(), source="pending_payment_background")
                )
                await asyncio.sleep(0.05)

                # A Class C joiner starts waiting on the same in-flight future...
                joiner_task = asyncio.create_task(
                    gate.attempt_recovery(
                        order, db=object(), source="cancel_precheck",
                        force_fresh=True, wait_for_inflight=True,
                    )
                )
                await asyncio.sleep(0.05)

                # ...then gets cancelled for reasons unrelated to the recovery itself
                # (e.g. its own HTTP request timed out). Without asyncio.shield(), this
                # would cancel the SHARED future (Task.cancel() -> fut_waiter.cancel()),
                # breaking the executor's own eventual future.set_result() call and any
                # other concurrent joiner.
                joiner_task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await joiner_task

                # The executor -- and the shared future it owns -- must be completely
                # unaffected by the joiner's unrelated cancellation.
                executor_outcome = await executor_task
                self.assertEqual(executor_outcome.decision, GateDecision.RECOVERED)
                self.assertTrue(executor_outcome.recovered)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
