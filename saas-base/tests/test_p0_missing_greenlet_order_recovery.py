"""P0 PROD-STABILITY-P0-01: MissingGreenlet crash in GET /api/v1/orders and in
_stale_order_cleanup_once, both traced back to the same root cause: payment recovery
(_recover_wxpay_order_if_paid) can call `await session.rollback()` on a session that
still holds ORM objects the caller needs afterward. SQLAlchemy's rollback() always
expires every object in the session's identity map -- unconditionally, independent of
`expire_on_commit` -- so any later bare attribute access on those objects attempts an
implicit lazy reload with no active greenlet and raises MissingGreenlet.

These tests run against real MySQL + asyncmy (matching production), not SQLite, per the
P0 audit requirement -- the point of this suite is to prove the fix holds against the
same driver production actually crashed on, not just that SQLAlchemy's ORM-level
expiry mechanics work in the abstract.

Requires the disposable MySQL8 test container (xiao-f1ga-mysql8, 127.0.0.1:3307,
root/f1ga_disposable_root_pw) to be running; tests skip cleanly if it isn't reachable.
"""

import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.core.permissions import ROLE_OWNER
from app.models.base import Base
from app.models.dining import DiningParticipant, DiningSession  # noqa: F401 -- FK targets, must register on Base
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

MYSQL_TEST_URL = (
    "mysql+asyncmy://root:f1ga_disposable_root_pw@127.0.0.1:3307/"
    "xiao_p0_missing_greenlet_test?charset=utf8mb4"
)

# Same asyncmy/pymysql ping-signature workaround app/core/database.py applies for its
# own engine -- needed independently here since this test builds its own engine.
from sqlalchemy.dialects.mysql.asyncmy import MySQLDialect_asyncmy  # noqa: E402

MySQLDialect_asyncmy._send_false_to_ping = True

TENANT_A = "tenant-p0-greenlet"


def _wxpay_resource_notpay() -> dict:
    """A resource WeChat returns for a genuinely still-unpaid order. Truthy (so it
    passes the `if not pay_resource: return False` early-out) but trade_state !=
    SUCCESS, so _validate_confirmed_wx_payment raises PaymentFactError -- which is
    exactly the exception-then-rollback path production hit repeatedly for
    order_id=7495790502218960896."""
    return {"trade_state": "NOTPAY", "out_trade_no": "unused"}


def _wxpay_resource_success(order: Order) -> dict:
    return {
        "trade_state": "SUCCESS",
        "out_trade_no": str(order.id),
        "transaction_id": f"wx-txn-{order.id}",
        "amount": {"total": int((Decimal(str(order.total)) * 100).to_integral_value()), "currency": "CNY"},
    }


def patch_wxpay_service(*, responses: dict[int, dict | None], enabled: bool = True):
    """Patch app.services.wxpay_service.WxPayService so _recover_wxpay_order_if_paid's
    `WxPayService(tenant)` construction returns a mock whose query_order_by_out_trade_no
    resolves per out_trade_no (== str(order.id)) from `responses`. Missing keys -> None
    (order not found / no resource -> _recover_wxpay_order_if_paid returns False with no
    rollback, the pre-existing safe path)."""
    mock_cls = patch("app.services.wxpay_service.WxPayService")
    started = mock_cls.start()
    instance = started.return_value
    instance.enabled = enabled

    async def _query(out_trade_no: str):
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


class _MySQLGreenletTestBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(
            MYSQL_TEST_URL,
            pool_size=20,
            max_overflow=20,
            connect_args={"init_command": "SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci"},
        )
        try:
            async with self.engine.connect() as conn:
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

        seed = self.SessionLocal()
        self.tenant = Tenant(
            tenant_id=TENANT_A, name="P0 Greenlet Restaurant", password_hash="x",
            status=True, is_open=True, payment_mode="prepay",
        )
        seed.add(self.tenant)
        self.dish = MenuItem(tenant_id=TENANT_A, name="牛肉汤", price="18.00", available=True, stock=None)
        seed.add(self.dish)
        await seed.commit()
        await seed.close()

    async def asyncTearDown(self):
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


class ListOrders100xNoMissingGreenletTest(_MySQLGreenletTestBase):
    """Core repro: a still-unpaid prepay order in the list makes WeChat return NOTPAY
    on every recovery attempt, which (pre-fix) rolled back the shared session and
    expired the entire `orders` list -- crashing GET /orders on the very next
    attribute read. Drives the real router-level `list_orders` endpoint function 100
    times against MySQL + asyncmy and requires 100/100 clean successes."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        db = self.SessionLocal()
        self.pending_order = await self._make_order(
            db, status="pending_payment", payment_status="unpaid",
            created_at=datetime.utcnow(),
        )
        await self._make_order(
            db, status="done", payment_status="paid", created_at=datetime.utcnow(), table_no="A2",
        )
        await db.commit()
        await db.close()

        self.wxpay_patcher = patch_wxpay_service(responses={self.pending_order.id: _wxpay_resource_notpay()})

    async def asyncTearDown(self):
        self.wxpay_patcher.stop()
        await super().asyncTearDown()

    async def test_100_consecutive_get_orders_no_500_no_missing_greenlet(self):
        from app.api.v1.orders import list_orders as list_orders_endpoint

        failures = []
        for i in range(100):
            db = self.SessionLocal()
            try:
                request = make_owner_request(TENANT_A)
                resp = await list_orders_endpoint(
                    request, date_str="today", db=db, response=None,
                )
                if getattr(resp, "code", None) != 200:
                    failures.append((i, f"non-200 code={getattr(resp, 'code', None)}"))
                elif not resp.data or len(resp.data) < 2:
                    failures.append((i, f"unexpected data={resp.data}"))
            except Exception as exc:  # noqa: BLE001 -- we want to see MissingGreenlet by name if it happens
                failures.append((i, f"{type(exc).__name__}: {exc}"))
            finally:
                await db.close()

        self.assertEqual(failures, [], f"{len(failures)}/100 iterations failed: {failures[:5]}")


class ListOrdersConcurrencyTest(_MySQLGreenletTestBase):
    """10 concurrent GET /orders requests, each with its own session (mirroring 10
    real concurrent HTTP requests each getting a fresh dependency-injected session).
    Must not MissingGreenlet, must not hit 'session is already closed', and must not
    exhaust the connection pool."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        db = self.SessionLocal()
        self.pending_order = await self._make_order(
            db, status="pending_payment", payment_status="unpaid",
            created_at=datetime.utcnow(),
        )
        await db.commit()
        await db.close()
        self.wxpay_patcher = patch_wxpay_service(responses={self.pending_order.id: _wxpay_resource_notpay()})

    async def asyncTearDown(self):
        self.wxpay_patcher.stop()
        await super().asyncTearDown()

    async def test_10_concurrent_list_orders_no_crash_no_leak(self):
        from app.api.v1.orders import list_orders as list_orders_endpoint

        async def one_call():
            db = self.SessionLocal()
            try:
                request = make_owner_request(TENANT_A)
                return await list_orders_endpoint(request, date_str="today", db=db, response=None)
            finally:
                await db.close()

        results = await asyncio.gather(*(one_call() for _ in range(10)), return_exceptions=True)
        errors = [r for r in results if isinstance(r, Exception)]
        self.assertEqual(errors, [], f"concurrent calls raised: {errors}")
        for r in results:
            self.assertEqual(r.code, 200)


class ReconcilePrintOrdersFailureIsolationTest(_MySQLGreenletTestBase):
    """P0 objective 1/5: an internal failure inside the best-effort print-reconcile
    pass must never fail GET /orders, and must not be silently swallowed -- it has to
    surface as a structured warning/error log."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        db = self.SessionLocal()
        await self._make_order(
            db, status="pending", payment_status="paid", created_at=datetime.utcnow(),
        )
        await db.commit()
        await db.close()

    async def test_reconcile_exception_logged_but_list_orders_still_succeeds(self):
        from app.api.v1.orders import list_orders as list_orders_endpoint

        with patch(
            "app.services.order_print_service.reconcile_print_orders",
            new=AsyncMock(side_effect=RuntimeError("simulated print provider meltdown")),
        ), patch("app.core.logger.logger") as mock_logger:
            request = make_owner_request(TENANT_A)
            db = self.SessionLocal()
            try:
                resp = await list_orders_endpoint(request, date_str="today", db=db, response=None)
            finally:
                await db.close()

        self.assertEqual(resp.code, 200)
        self.assertEqual(len(resp.data), 1)
        mock_logger.exception.assert_called()
        logged_msg = mock_logger.exception.call_args[0][0]
        self.assertIn("list_orders", logged_msg)


class WxpayRecoveryAuthorityUnchangedTest(_MySQLGreenletTestBase):
    """P0 objective: fixing the session-isolation bug must not change WXPAY money
    authority. A genuinely-paid order recovered through the new isolated-session path
    inside list_orders must still transition to paid/pending, exactly as before."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        db = self.SessionLocal()
        self.paid_order = await self._make_order(
            db, status="pending_payment", payment_status="unpaid",
            created_at=datetime.utcnow(), total="18.00",
        )
        await db.commit()
        await db.close()
        self.wxpay_patcher = patch_wxpay_service(
            responses={self.paid_order.id: _wxpay_resource_success(self.paid_order)}
        )

    async def asyncTearDown(self):
        self.wxpay_patcher.stop()
        await super().asyncTearDown()

    async def test_successful_recovery_still_flips_order_to_paid(self):
        from app.api.v1.orders import list_orders as list_orders_endpoint

        with patch(
            "app.services.order_print_service._print_paid_order_ticket",
            new=AsyncMock(return_value=None),
        ):
            request = make_owner_request(TENANT_A)
            db = self.SessionLocal()
            try:
                resp = await list_orders_endpoint(request, date_str="today", db=db, response=None)
            finally:
                await db.close()
        self.assertEqual(resp.code, 200)

        verify_db = self.SessionLocal()
        try:
            refreshed = await verify_db.get(Order, self.paid_order.id)
            self.assertEqual(refreshed.payment_status, "paid")
            self.assertEqual(refreshed.status, "pending")
            self.assertEqual(refreshed.wx_transaction_id, f"wx-txn-{self.paid_order.id}")
        finally:
            await verify_db.close()


class StaleOrderCleanupOnceNoMissingGreenletTest(_MySQLGreenletTestBase):
    """Link B: _stale_order_cleanup_once must not MissingGreenlet across pending
    (fresh, untouched), expired/stale (triggers the rollback path), paid, and
    cancelled orders."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        old = datetime.utcnow() - timedelta(minutes=30)
        db = self.SessionLocal()
        self.fresh_pending = await self._make_order(
            db, status="pending_payment", payment_status="unpaid",
            created_at=datetime.utcnow(), table_no="P1",
        )
        self.stale_notpay = await self._make_order(
            db, status="pending_payment", payment_status="unpaid",
            created_at=old, table_no="P2",
        )
        self.already_paid = await self._make_order(
            db, status="settled", payment_status="paid", created_at=old, table_no="P3",
        )
        self.already_cancelled = await self._make_order(
            db, status="cancelled", payment_status="unpaid", created_at=old, table_no="P4",
        )
        await db.commit()
        await db.close()

        self.wxpay_patcher = patch_wxpay_service(
            responses={self.stale_notpay.id: _wxpay_resource_notpay()}
        )

    async def asyncTearDown(self):
        self.wxpay_patcher.stop()
        await super().asyncTearDown()

    async def test_stale_cleanup_once_all_states_no_crash(self):
        from app.main import _stale_order_cleanup_once

        # Ran under the same patched AsyncSessionLocal as asyncSetUp installed.
        await _stale_order_cleanup_once()

        verify_db = self.SessionLocal()
        try:
            fresh = await verify_db.get(Order, self.fresh_pending.id)
            stale = await verify_db.get(Order, self.stale_notpay.id)
            paid = await verify_db.get(Order, self.already_paid.id)
            cancelled = await verify_db.get(Order, self.already_cancelled.id)

            # Not yet past the timeout threshold -- untouched.
            self.assertEqual(fresh.status, "pending_payment")
            # Recovery attempted, WeChat said still unpaid (rollback fired internally,
            # pre-fix this alone crashed the whole loop iteration) -- cancelled by the
            # normal stale-cleanup mutation that runs right after.
            self.assertEqual(stale.status, "cancelled")
            self.assertIsNotNone(stale.terminated_at)
            # Already-terminal orders are excluded by the query filter -- untouched.
            self.assertEqual(paid.status, "settled")
            self.assertEqual(cancelled.status, "cancelled")
        finally:
            await verify_db.close()

    async def test_stale_cleanup_once_runs_five_consecutive_iterations_no_crash(self):
        """Objective 3: the background loop runs this repeatedly and must never
        MissingGreenlet on any iteration, including ones after the stale order has
        already been cancelled (recovery is attempted again on next pass only if a
        fresh stale order exists; here we just prove repeated invocation is safe)."""
        from app.main import _stale_order_cleanup_once

        for i in range(5):
            try:
                await _stale_order_cleanup_once()
            except Exception as exc:  # noqa: BLE001
                self.fail(f"iteration {i} raised {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    unittest.main()
