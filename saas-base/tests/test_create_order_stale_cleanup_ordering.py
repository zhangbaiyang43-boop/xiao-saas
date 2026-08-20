"""PROD-STABILITY-P1-01 checkpoint blocker fix: _cleanup_stale_pending_payment_orders
must run AFTER payment-mode resolution (tenant.payment_mode already extracted to plain
scalars by then) but BEFORE dining-context resolution (which acquires a SELECT
DiningSession ... FOR UPDATE row lock meant to be held continuously until this
request's own commit, for mutual exclusion with settle_table).

_cleanup_stale_pending_payment_orders calls into recovery_gate.attempt_recovery(...,
force_fresh=True), which can still reach _recover_wxpay_order_if_paid's legacy
NOTPAY/exception path and `await db.rollback()`. That rollback would release the
DiningSession row lock early and expire session_for_pickup/participant if it ran while
that lock was held -- moving cleanup earlier eliminates the exposure entirely rather
than working around it.

This file contains:
1. A source-order AST contract test (not line-number-based) preventing this ordering
   from silently regressing.
2. Real MySQL + asyncmy integration tests for the actual create_order flow across the
   scenarios the ordering fix must not break: dining-session add-on with a stale
   NOTPAY order present, the DiningSession lock/settle_table race, stale-order SUCCESS
   recovery immediately before a new order is created, no-dining-session orders, and
   table_account/staff add-on paths.
"""

import ast
import asyncio
import pathlib
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

MYSQL_TEST_URL = (
    "mysql+asyncmy://root:f1ga_disposable_root_pw@127.0.0.1:3307/"
    "xiao_p1_wxpay_gate_test?charset=utf8mb4"
)

from sqlalchemy.dialects.mysql.asyncmy import MySQLDialect_asyncmy  # noqa: E402

MySQLDialect_asyncmy._send_false_to_ping = True

TENANT_A = "tenant-create-order-ordering"


class CreateOrderSourceOrderingContractTest(unittest.TestCase):
    """AST-based (not line-number-based) guard: within create_order's own function
    body, the call to _resolve_create_order_payment_mode must appear before the call
    to _cleanup_stale_pending_payment_orders, which must appear before the call to
    _resolve_create_order_dining_context."""

    def test_payment_mode_before_cleanup_before_dining_context(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        source = (root / "app" / "api" / "v1" / "orders.py").read_text(encoding="utf-8-sig")
        tree = ast.parse(source)

        create_order_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "create_order":
                create_order_node = node
                break
        self.assertIsNotNone(create_order_node, "create_order function not found")

        target_calls = {
            "_resolve_create_order_payment_mode": None,
            "_cleanup_stale_pending_payment_orders": None,
            "_resolve_create_order_dining_context": None,
        }

        class _CallFinder(ast.NodeVisitor):
            def visit_Call(self, node):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else None
                if name in target_calls and target_calls[name] is None:
                    target_calls[name] = node.lineno
                self.generic_visit(node)

        _CallFinder().visit(create_order_node)

        missing = [name for name, line in target_calls.items() if line is None]
        self.assertEqual(missing, [], f"expected calls not found in create_order: {missing}")

        payment_mode_line = target_calls["_resolve_create_order_payment_mode"]
        cleanup_line = target_calls["_cleanup_stale_pending_payment_orders"]
        dining_context_line = target_calls["_resolve_create_order_dining_context"]

        self.assertLess(
            payment_mode_line, cleanup_line,
            "_resolve_create_order_payment_mode must be called before "
            "_cleanup_stale_pending_payment_orders (tenant.payment_mode must already be "
            "extracted to a plain scalar before the cleanup's force_fresh recovery can "
            "rollback the session)",
        )
        self.assertLess(
            cleanup_line, dining_context_line,
            "_cleanup_stale_pending_payment_orders must be called before "
            "_resolve_create_order_dining_context (which acquires a DiningSession "
            "SELECT ... FOR UPDATE row lock that must not be released early by a "
            "cleanup-triggered rollback)",
        )


def _wxpay_resource_notpay() -> dict:
    return {"trade_state": "NOTPAY", "out_trade_no": "unused"}


def _wxpay_resource_success(order_id: int, total: str) -> dict:
    return {
        "trade_state": "SUCCESS",
        "out_trade_no": str(order_id),
        "transaction_id": f"wx-txn-{order_id}",
        "amount": {"total": int((Decimal(total) * 100).to_integral_value()), "currency": "CNY"},
    }


def patch_wxpay_service(*, responses: dict[int, dict | None], enabled: bool = True):
    mock_cls = patch("app.services.wxpay_service.WxPayService")
    started = mock_cls.start()
    instance = started.return_value
    instance.enabled = enabled

    async def _query(out_trade_no: str):
        return responses.get(int(out_trade_no))

    instance.query_order_by_out_trade_no = AsyncMock(side_effect=_query)
    return mock_cls


def make_request(*, tenant_id=None, token_type=None, role=None, account_id=None):
    req = Request(
        {
            "type": "http", "method": "POST", "path": "/api/v1/orders",
            "headers": [], "query_string": b"", "server": ("testserver", 80),
            "scheme": "http", "client": ("testclient", 50000),
        }
    )
    if tenant_id is not None:
        req.state.tenant_id = tenant_id
    if token_type is not None:
        req.state.token_type = token_type
    if role is not None:
        req.state.role = role
    if account_id is not None:
        req.state.account_id = account_id
    return req


class _MySQLCreateOrderOrderingTestBase(unittest.IsolatedAsyncioTestCase):
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

        from app.models.base import Base

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self._db_patcher = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._db_patcher.start()

        from app.models.entrance_code import EntranceCode
        from app.models.menu_item import MenuItem
        from app.models.tenant import Tenant
        from app.utils.id_generator import generate_snowflake_id

        seed = self.SessionLocal()
        self.tenant = Tenant(
            tenant_id=TENANT_A, name="Ordering Fix Restaurant", password_hash="x",
            status=True, is_open=True, payment_mode="prepay",
        )
        seed.add(self.tenant)
        self.dish = MenuItem(tenant_id=TENANT_A, name="宫保鸡丁", price="28.00", available=True, stock=None)
        seed.add(self.dish)
        seed.add(EntranceCode(
            id=generate_snowflake_id(),
            tenant_id=TENANT_A, name="A12", scene="E00000000012",
            table_no="A12", entry_type="table", status=1,
        ))
        await seed.commit()
        await seed.close()

    async def asyncTearDown(self):
        self._db_patcher.stop()
        await self.engine.dispose()

    async def _make_stale_order(self, db, *, status="pending_payment", payment_status="unpaid", total="18.00"):
        from app.models.order import Order

        order = Order(
            tenant_id=TENANT_A, table_no="", status=status, payment_status=payment_status,
            payment_mode="prepay", total=Decimal(total),
            created_at=datetime.utcnow() - timedelta(minutes=20),
        )
        db.add(order)
        await db.flush()
        return order

    async def _open_dining_session_with_participant(self, db, *, table_no="A12", guest_token="guest-tok-1"):
        from app.models.dining import DiningParticipant, DiningSession
        from app.services.dining_session_service import hash_participant_token

        # A deliberate 5s-in-the-past anchor, not datetime.utcnow(): DiningSession.
        # last_activity_at / DiningParticipant.last_active_at are plain MySQL DATETIME
        # columns (no fractional-seconds precision), which truncates to whole seconds
        # on write. Anchoring "before" at utcnow() and asserting create_order's fresh
        # utcnow() mutation is strictly greater than it is flaky by construction -- both
        # calls can legitimately land in the same wall-clock second on a fast test run,
        # and after truncation they'd compare equal, not greater. A real gap makes the
        # assertion deterministic instead of racing the second boundary.
        now = datetime.utcnow() - timedelta(seconds=5)
        session = DiningSession(
            tenant_id=TENANT_A, table_no=table_no, status="OPEN",
            active_key=f"{TENANT_A}:{table_no}:{guest_token}", started_at=now, last_activity_at=now,
        )
        db.add(session)
        await db.flush()
        participant = DiningParticipant(
            tenant_id=TENANT_A, session_id=session.id,
            guest_token_hash=hash_participant_token(guest_token),
            joined_at=now, last_active_at=now,
        )
        db.add(participant)
        await db.flush()
        await db.commit()
        return session, participant

    def _order_body(self, *, dining_session_id=None, participant_token=None, table="A12"):
        from app.api.v1.orders import OrderCreate, OrderItemIn

        return OrderCreate(
            shop=TENANT_A, table=table,
            items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=28.0, qty=1)],
            total=28.0,
            dining_session_id=dining_session_id,
            participant_token=participant_token,
        )


class NotpayStaleCreateOrderTest(_MySQLCreateOrderOrderingTestBase):
    """REQUIRED MYSQL TEST 1: a stale NOTPAY order present at create_order time must
    not crash the request, and the dining-session add-on must still succeed with the
    participant/session activity mutations correctly persisted."""

    async def test_create_order_add_on_survives_notpay_stale_cleanup(self):
        from app.api.v1.orders import create_order

        db = self.SessionLocal()
        session, participant = await self._open_dining_session_with_participant(db)
        stale = await self._make_stale_order(db)
        await db.commit()
        await db.close()

        patcher = patch_wxpay_service(responses={stale.id: _wxpay_resource_notpay()})
        try:
            request_db = self.SessionLocal()
            try:
                result = await create_order(
                    self._order_body(dining_session_id=session.id, participant_token="guest-tok-1"),
                    make_request(),
                    db=request_db,
                )
            finally:
                await request_db.close()
        finally:
            patcher.stop()

        self.assertEqual(result.code, 200, f"create_order failed: {result.msg}")
        self.assertEqual(str(result.data["dining_session_id"]), str(session.id))
        self.assertEqual(str(result.data["participant_id"]), str(participant.id))

        verify_db = self.SessionLocal()
        try:
            from app.models.dining import DiningParticipant, DiningSession

            refreshed_participant = await verify_db.get(DiningParticipant, participant.id)
            refreshed_session = await verify_db.get(DiningSession, session.id)
            self.assertGreater(refreshed_participant.last_active_at, participant.last_active_at)
            self.assertGreater(refreshed_session.last_activity_at, session.last_activity_at)
        finally:
            await verify_db.close()


class DiningSessionLockRaceTest(_MySQLCreateOrderOrderingTestBase):
    """REQUIRED MYSQL TEST 2 (most important): the DiningSession row lock acquired by
    create_order's dining-context resolution must be held continuously until this
    request's own commit -- a concurrent settle_table-equivalent lock attempt on the
    same row must block until create_order finishes, never sneak in early because a
    stale-cleanup-triggered rollback released the lock prematurely."""

    async def test_lock_held_until_create_order_commits_even_with_stale_notpay_present(self):
        import app.api.v1.orders as orders_module
        from app.api.v1.orders import create_order
        from app.models.dining import DiningSession

        db = self.SessionLocal()
        session, participant = await self._open_dining_session_with_participant(db)
        stale = await self._make_stale_order(db)
        await db.commit()
        await db.close()

        barrier_reached = asyncio.Event()
        release_barrier = asyncio.Event()
        original_apply_coupon = orders_module._apply_create_order_coupon

        async def delayed_apply_coupon(*args, **kwargs):
            # Runs AFTER _resolve_create_order_dining_context has already acquired the
            # DiningSession FOR UPDATE lock, and AFTER cleanup (now positioned before
            # dining-context resolution) has already run to completion -- exactly the
            # window where the lock must still be held.
            result = await original_apply_coupon(*args, **kwargs)
            barrier_reached.set()
            await release_barrier.wait()
            return result

        patcher = patch_wxpay_service(responses={stale.id: _wxpay_resource_notpay()})
        try:
            with patch.object(orders_module, "_apply_create_order_coupon", side_effect=delayed_apply_coupon):
                request_db = self.SessionLocal()
                task_a = asyncio.create_task(
                    create_order(
                        self._order_body(dining_session_id=session.id, participant_token="guest-tok-1"),
                        make_request(),
                        db=request_db,
                    )
                )
                await asyncio.wait_for(barrier_reached.wait(), timeout=10)

                # Task B: settle_table-equivalent -- lock the SAME DiningSession row via
                # a completely separate connection/session.
                lock_b_acquired = asyncio.Event()

                async def task_b_lock_attempt():
                    b_db = self.SessionLocal()
                    try:
                        await b_db.execute(
                            select(DiningSession).where(DiningSession.id == session.id).with_for_update()
                        )
                        lock_b_acquired.set()
                        await b_db.commit()
                    finally:
                        await b_db.close()

                task_b = asyncio.create_task(task_b_lock_attempt())
                await asyncio.sleep(0.5)
                self.assertFalse(
                    lock_b_acquired.is_set(),
                    "Task B acquired the DiningSession row lock BEFORE Task A "
                    "committed -- the lock was released early (exactly the bug this "
                    "ordering fix prevents: stale cleanup must never run between lock "
                    "acquisition and commit).",
                )

                release_barrier.set()
                result_a = await asyncio.wait_for(task_a, timeout=10)
                await asyncio.wait_for(task_b, timeout=10)
        finally:
            patcher.stop()
            await request_db.close()

        self.assertEqual(result_a.code, 200, f"create_order failed: {result_a.msg}")
        self.assertTrue(lock_b_acquired.is_set(), "Task B should acquire the lock after Task A commits")


class SuccessStaleRecoveryThenCreateOrderTest(_MySQLCreateOrderOrderingTestBase):
    """REQUIRED MYSQL TEST 3: a stale order that turns out to have actually succeeded
    must be recovered by the cleanup pass (which may internally commit), and
    create_order must still go on to acquire the DiningSession lock and create the new
    order normally afterward."""

    async def test_success_recovery_then_new_order_created_normally(self):
        from app.api.v1.orders import create_order
        from app.models.order import Order

        db = self.SessionLocal()
        session, participant = await self._open_dining_session_with_participant(db)
        stale = await self._make_stale_order(db)
        await db.commit()
        await db.close()

        patcher = patch_wxpay_service(
            responses={stale.id: _wxpay_resource_success(stale.id, "18.00")}
        )
        try:
            with patch(
                "app.services.order_print_service._print_paid_order_ticket",
                new=AsyncMock(return_value=None),
            ):
                request_db = self.SessionLocal()
                try:
                    result = await create_order(
                        self._order_body(dining_session_id=session.id, participant_token="guest-tok-1"),
                        make_request(),
                        db=request_db,
                    )
                finally:
                    await request_db.close()
        finally:
            patcher.stop()

        self.assertEqual(result.code, 200, f"create_order failed: {result.msg}")

        verify_db = self.SessionLocal()
        try:
            refreshed_stale = await verify_db.get(Order, stale.id)
            self.assertEqual(refreshed_stale.payment_status, "paid")
            new_order_id = int(result.data["id"])
            new_order = await verify_db.get(Order, new_order_id)
            self.assertIsNotNone(new_order)
            self.assertEqual(str(new_order.dining_session_id), str(session.id))
        finally:
            await verify_db.close()


class NoDiningSessionCreateOrderTest(_MySQLCreateOrderOrderingTestBase):
    """REQUIRED TEST 4: anonymous/prepay orders with no dining_session_id at all must
    be completely unaffected by the ordering change."""

    async def test_anonymous_prepay_order_unaffected_by_ordering_change(self):
        from app.api.v1.orders import create_order

        db = self.SessionLocal()
        stale = await self._make_stale_order(db)
        await db.commit()
        await db.close()

        patcher = patch_wxpay_service(responses={stale.id: _wxpay_resource_notpay()})
        try:
            request_db = self.SessionLocal()
            try:
                result = await create_order(
                    self._order_body(dining_session_id=None, participant_token=None, table=""),
                    make_request(),
                    db=request_db,
                )
            finally:
                await request_db.close()
        finally:
            patcher.stop()

        self.assertEqual(result.code, 200, f"create_order failed: {result.msg}")
        self.assertIsNone(result.data.get("dining_session_id"))


class TableAccountAndStaffAddOnTest(_MySQLCreateOrderOrderingTestBase):
    """REQUIRED TEST 5: table_account customer add-on and staff-assisted add-on must
    both still work -- payment-mode resolution before cleanup, dining-session
    resolution after cleanup, business behavior otherwise unchanged."""

    async def test_table_account_customer_add_on(self):
        from app.api.v1.orders import create_order
        from app.models.entrance_code import EntranceCode
        from app.utils.id_generator import generate_snowflake_id

        db = self.SessionLocal()
        # A zone_type="full" EntranceCode makes _resolve_create_order_payment_mode
        # resolve payment_mode to "table_account" for this table.
        db.add(EntranceCode(
            id=generate_snowflake_id(),
            tenant_id=TENANT_A, name="B7", scene="E00000000099",
            table_no="B7", entry_type="table", status=1, zone_type="full",
        ))
        session, participant = await self._open_dining_session_with_participant(db, table_no="B7", guest_token="guest-tok-2")
        stale = await self._make_stale_order(db)
        await db.commit()
        await db.close()

        patcher = patch_wxpay_service(responses={stale.id: _wxpay_resource_notpay()})
        try:
            request_db = self.SessionLocal()
            try:
                result = await create_order(
                    self._order_body(dining_session_id=session.id, participant_token="guest-tok-2", table="B7"),
                    make_request(),
                    db=request_db,
                )
            finally:
                await request_db.close()
        finally:
            patcher.stop()

        self.assertEqual(result.code, 200, f"create_order failed: {result.msg}")
        self.assertEqual(result.data.get("payment_mode"), "table_account")

    async def test_staff_assisted_add_on(self):
        from app.api.v1.orders import create_order

        db = self.SessionLocal()
        stale = await self._make_stale_order(db)
        await db.commit()
        await db.close()

        patcher = patch_wxpay_service(responses={stale.id: _wxpay_resource_notpay()})
        try:
            request_db = self.SessionLocal()
            try:
                result = await create_order(
                    self._order_body(dining_session_id=None, participant_token=None, table="A12"),
                    make_request(tenant_id=TENANT_A, token_type="merchant"),
                    db=request_db,
                )
            finally:
                await request_db.close()
        finally:
            patcher.stop()

        self.assertEqual(result.code, 200, f"create_order failed: {result.msg}")
        self.assertIsNotNone(result.data.get("dining_session_id"))
