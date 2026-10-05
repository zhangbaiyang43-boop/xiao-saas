"""P0-PRINT-02: print recovery must not be starved by rows that cannot make progress.

The recovery query is oldest-first with a global LIMIT, and a skipped row never
changes updated_at or print_status. Rows that can never progress (retry budget
spent, KITCHEN_PRINT not granted) therefore used to pin the head of the query
and hide every newer PENDING/FAILED order behind them -- across tenants.

Contract under test: such rows are examined once per cycle, the scan moves on,
proven-stuck rows are remembered by the loop-owned memo, and nothing else about
the recovery contract (UNKNOWN, stale SENDING, SUCCESS, per-cycle provider
budget) changes.

The request-driven path (reconcile_print_orders, used by the workbench and the
order list) had the same flaw -- it truncated its input to the batch limit
*before* deciding whether anything needed doing -- and now shares the
recoverability rules (_auto_recovery_disposition) with the background loop.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import re
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.base import Base
from app.models.order import Order
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.services import order_print_service
from app.services.order_print_service import (
    MAX_PRINT_RETRY_ATTEMPTS,
    PRINT_AUTO_RECOVERY_MAX_AGE_SECONDS,
    PRINT_RECONCILE_BATCH_LIMIT,
    PRINT_RETRY_COOLDOWN_SECONDS,
    PRINT_SENDING_STALE_SECONDS,
    _RecoveryScanMemo,
    _auto_recovery_disposition,
    _get_print_meta,
    _set_print_meta,
    _sync_legacy_initial_fields,
    reconcile_print_orders,
    recover_pending_print_orders_once,
)
from app.services.subscription_service import STATUS_TRIAL

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
DINING_SESSION_SERVICE = ROOT / "app" / "services" / "dining_session_service.py"

TENANT_A = "tenant-print02-a"
TENANT_B = "tenant-print02-b"
ROUTE = {
    "provider": "feieyun",
    "printer_identifier": "SN001",
    "template_or_route_mode": "text",
    "copies": 1,
}
PROVIDER_PATH = "app.services.order_print_service._execute_provider_with_frozen_route"
CAPABILITY_PATH = "app.services.optional_entitlement.optional_capability_enabled"


def _initial(order: Order) -> dict:
    return _get_print_meta(order).get("initial_print") or {}


class RecoveryQueueStarvationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._original_redis_enabled = settings.REDIS_ENABLED
        settings.REDIS_ENABLED = False

        self._db_file = f"{tempfile.gettempdir()}/p0_print_02_{uuid.uuid4().hex}.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_file}")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self._session_patch = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._session_patch.start()

        self.provider = AsyncMock(return_value="task-print02")
        self._provider_patch = patch(PROVIDER_PATH, self.provider)
        self._provider_patch.start()

        now = datetime.utcnow()
        self.db.add_all([
            Plan(code="FREE", name="免费版", is_active=True, price_month_cents=0, price_year_cents=0, sort_order=0),
            Plan(code="STANDARD", name="普通版", is_active=True, price_month_cents=5900, price_year_cents=60900, sort_order=1),
            Plan(code="PRO", name="专业版", is_active=True, price_month_cents=9900, price_year_cents=102200, sort_order=2),
        ])
        await self.db.flush()
        pro = (await self.db.execute(select(Plan).where(Plan.code == "PRO"))).scalar_one()
        for tid in (TENANT_A, TENANT_B):
            self.db.add(Tenant(
                tenant_id=tid, name=f"Shop {tid}", password_hash="x", status=True, is_open=True,
                payment_mode="prepay", feieyun_sn="SN001", feieyun_key="KEY001",
            ))
            self.db.add(Subscription(
                tenant_id=tid, plan_id=pro.id, status=STATUS_TRIAL,
                trial_started_at=now, trial_ends_at=now + timedelta(days=30),
            ))
        await self.db.commit()

    async def asyncTearDown(self):
        self._provider_patch.stop()
        self._session_patch.stop()
        settings.REDIS_ENABLED = self._original_redis_enabled
        await self.db.close()
        await self.engine.dispose()
        try:
            os.remove(self._db_file)
        except OSError:
            pass

    async def _make_order(
        self,
        tenant_id: str,
        *,
        print_status: str,
        attempts: int = 0,
        last_attempt_age_s: int | None = None,
        updated_age_s: int = 120,
        created_age_s: int = 0,
        paid_age_s: int = 120,
    ) -> Order:
        """Paid prepay order with a frozen-route print intent in ``print_status``."""
        now = datetime.utcnow()
        order = Order(
            tenant_id=tenant_id,
            table_no="A1",
            total="20.00",
            status="pending",
            payment_mode="prepay",
            payment_status="paid",
            payment_time=(now - timedelta(seconds=paid_age_s)).isoformat(),
            source="miniprogram",
            print_status=print_status,
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)

        last_attempt_at = (
            (datetime.utcnow() - timedelta(seconds=last_attempt_age_s)).isoformat()
            if last_attempt_age_s is not None
            else None
        )
        meta = {
            "version": 2,
            "initial_print": {
                "status": print_status,
                "attempts": attempts,
                "last_attempt_at": last_attempt_at,
                "eligible_at": now.isoformat(),
                "route": dict(ROUTE),
            },
            "manual_reprint_count": 0,
            "manual_reprints": [],
        }
        _sync_legacy_initial_fields(meta)
        _set_print_meta(order, meta)
        await self.db.commit()
        await self.db.execute(
            update(Order)
            .where(Order.id == order.id)
            .values(
                updated_at=now - timedelta(seconds=updated_age_s),
                created_at=now - timedelta(seconds=created_age_s),
            )
        )
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def _make_exhausted_failed(self, tenant_id: str, count: int) -> list[Order]:
        # Older updated_at than anything else so they sit at the head of the query.
        return [
            await self._make_order(
                tenant_id,
                print_status="FAILED",
                attempts=MAX_PRINT_RETRY_ATTEMPTS,
                last_attempt_age_s=PRINT_RETRY_COOLDOWN_SECONDS + 600,
                updated_age_s=3600 + idx,
            )
            for idx in range(count)
        ]

    # ------------------------------------------------------------------ 1 / 8
    async def test_exhausted_failed_rows_do_not_starve_newer_pending_across_tenants(self):
        zombies = await self._make_exhausted_failed(TENANT_A, PRINT_RECONCILE_BATCH_LIMIT + 1)
        newer = await self._make_order(TENANT_B, print_status="PENDING")

        handled = await recover_pending_print_orders_once(self.db)

        await self.db.refresh(newer)
        self.assertEqual(handled, 1)
        self.assertEqual(self.provider.await_count, 1)
        self.assertEqual(newer.print_status, "SUCCESS")
        for zombie in zombies:
            await self.db.refresh(zombie)
            self.assertEqual(zombie.print_status, "FAILED")
            self.assertEqual(int(_initial(zombie).get("attempts") or 0), MAX_PRINT_RETRY_ATTEMPTS)

    # ------------------------------------------------------------------ 2
    async def test_recoverable_failed_row_is_still_retried(self):
        order = await self._make_order(
            TENANT_A,
            print_status="FAILED",
            attempts=1,
            last_attempt_age_s=PRINT_RETRY_COOLDOWN_SECONDS + 45,
            updated_age_s=PRINT_RETRY_COOLDOWN_SECONDS + 45,
        )

        handled = await recover_pending_print_orders_once(self.db)

        await self.db.refresh(order)
        self.assertEqual(handled, 1)
        self.assertEqual(self.provider.await_count, 1)
        self.assertEqual(order.print_status, "SUCCESS")
        self.assertEqual(int(_initial(order).get("attempts") or 0), 2)

    # ------------------------------------------------------------------ 3
    async def test_exhausted_failed_rows_never_reach_the_provider(self):
        zombies = await self._make_exhausted_failed(TENANT_A, 3)

        handled = await recover_pending_print_orders_once(self.db)

        self.assertEqual(handled, 0)
        self.provider.assert_not_awaited()
        for zombie in zombies:
            await self.db.refresh(zombie)
            self.assertEqual(zombie.print_status, "FAILED")

    async def test_memo_stops_re_examining_rows_proven_stuck(self):
        await self._make_exhausted_failed(TENANT_A, 3)
        guard = MagicMock(wraps=_auto_recovery_disposition)

        with patch.object(order_print_service, "_auto_recovery_disposition", guard):
            memo = _RecoveryScanMemo()
            await recover_pending_print_orders_once(self.db, memo=memo)
            after_first = guard.call_count
            await recover_pending_print_orders_once(self.db, memo=memo)
            after_second = guard.call_count
            await recover_pending_print_orders_once(self.db)  # no memo: examines again
            after_unmemoed = guard.call_count

        self.assertEqual(after_first, 3)
        self.assertEqual(after_second, after_first)
        self.assertEqual(after_unmemoed, after_first + 3)
        self.provider.assert_not_awaited()

    async def test_provider_path_stuck_code_is_memoized_per_order(self):
        # Defence in depth: a row that slips past the guard but is refused with a
        # permanent code by the claim is still remembered.
        await self._make_order(TENANT_A, print_status="PENDING")
        stuck = AsyncMock(return_value={"success": False, "skipped": True, "code": "PRINT_RETRY_LIMIT"})

        with patch.object(order_print_service, "_print_paid_order_ticket", stuck):
            memo = _RecoveryScanMemo()
            await recover_pending_print_orders_once(self.db, memo=memo)
            await recover_pending_print_orders_once(self.db, memo=memo)

        self.assertEqual(stuck.await_count, 1)

    # ------------------------------------------------------------------ 4
    async def test_stale_sending_is_still_quarantined_behind_zombies_and_past_the_age_window(self):
        await self._make_exhausted_failed(TENANT_A, PRINT_RECONCILE_BATCH_LIMIT + 1)
        sending = await self._make_order(
            TENANT_B,
            print_status="SENDING",
            attempts=1,
            last_attempt_age_s=PRINT_SENDING_STALE_SECONDS + 90,
            updated_age_s=PRINT_SENDING_STALE_SECONDS + 90,
            created_age_s=PRINT_AUTO_RECOVERY_MAX_AGE_SECONDS + 3600,
        )

        handled = await recover_pending_print_orders_once(self.db)

        await self.db.refresh(sending)
        self.assertEqual(handled, 1)
        self.assertEqual(sending.print_status, "UNKNOWN")
        self.assertEqual(_initial(sending).get("last_error_code"), "STALE_SENDING")
        self.provider.assert_not_awaited()

    # ------------------------------------------------------------------ 5 / 6
    async def test_unknown_and_success_rows_are_not_recovery_candidates(self):
        unknown = await self._make_order(
            TENANT_A, print_status="UNKNOWN", attempts=1, last_attempt_age_s=600, updated_age_s=600,
        )
        success = await self._make_order(
            TENANT_A, print_status="SUCCESS", attempts=1, last_attempt_age_s=600, updated_age_s=600,
        )

        handled = await recover_pending_print_orders_once(self.db)

        self.assertEqual(handled, 0)
        self.provider.assert_not_awaited()
        await self.db.refresh(unknown)
        await self.db.refresh(success)
        self.assertEqual(unknown.print_status, "UNKNOWN")
        self.assertEqual(success.print_status, "SUCCESS")

    # ------------------------------------------------------------------ 7
    async def test_rows_older_than_the_window_are_not_auto_recovered(self):
        too_old = PRINT_AUTO_RECOVERY_MAX_AGE_SECONDS + 3600
        old_pending = await self._make_order(TENANT_A, print_status="PENDING", created_age_s=too_old)
        old_failed = await self._make_order(
            TENANT_A,
            print_status="FAILED",
            attempts=1,
            last_attempt_age_s=PRINT_RETRY_COOLDOWN_SECONDS + 45,
            updated_age_s=PRINT_RETRY_COOLDOWN_SECONDS + 45,
            created_age_s=too_old,
        )
        fresh = await self._make_order(TENANT_B, print_status="PENDING")

        handled = await recover_pending_print_orders_once(self.db)

        self.assertEqual(handled, 1)
        self.assertEqual(self.provider.await_count, 1)
        await self.db.refresh(old_pending)
        await self.db.refresh(old_failed)
        await self.db.refresh(fresh)
        self.assertEqual(old_pending.print_status, "PENDING")
        self.assertEqual(old_failed.print_status, "FAILED")
        self.assertEqual(fresh.print_status, "SUCCESS")

    def test_auto_recovery_window_equals_dining_session_expiry(self):
        match = re.search(r"^SESSION_EXPIRE_HOURS\s*=\s*(\d+)", DINING_SESSION_SERVICE.read_text(encoding="utf-8"), re.M)
        self.assertIsNotNone(match)
        self.assertEqual(PRINT_AUTO_RECOVERY_MAX_AGE_SECONDS, int(match.group(1)) * 3600)

    # ------------------------------------------------------------------ capability
    async def test_capability_disabled_tenant_does_not_starve_other_tenants(self):
        for _ in range(PRINT_RECONCILE_BATCH_LIMIT + 1):
            await self._make_order(TENANT_A, print_status="PENDING", updated_age_s=3600)
        newer = await self._make_order(TENANT_B, print_status="PENDING")
        capability = AsyncMock(side_effect=lambda tenant_id, capability_key: tenant_id != TENANT_A)

        with patch(CAPABILITY_PATH, capability):
            memo = _RecoveryScanMemo()
            handled = await recover_pending_print_orders_once(self.db, memo=memo)
            a_checks_first = [c.args[0] for c in capability.await_args_list].count(TENANT_A)
            await recover_pending_print_orders_once(self.db, memo=memo)
            a_checks_second = [c.args[0] for c in capability.await_args_list].count(TENANT_A)

        await self.db.refresh(newer)
        self.assertEqual(handled, 1)
        self.assertEqual(newer.print_status, "SUCCESS")
        self.assertEqual(self.provider.await_count, 1)
        self.assertGreater(a_checks_first, 0)
        self.assertEqual(a_checks_second, a_checks_first)

    async def test_capability_disabled_rows_stay_pending_and_recover_after_the_recheck(self):
        order = await self._make_order(TENANT_A, print_status="PENDING")
        capability = AsyncMock(side_effect=[False, True])

        with patch(CAPABILITY_PATH, capability):
            memo = _RecoveryScanMemo()
            first = await recover_pending_print_orders_once(self.db, memo=memo)
            await self.db.refresh(order)
            self.assertEqual(first, 0)
            self.assertEqual(order.print_status, "PENDING")

            # Entitlement came back; the tenant memo entry has expired.
            memo._tenant_until.clear()
            second = await recover_pending_print_orders_once(self.db, memo=memo)

        await self.db.refresh(order)
        self.assertEqual(second, 1)
        self.assertEqual(order.print_status, "SUCCESS")

    # ------------------------------------------------------------------ secondary path (S1-S7)
    async def test_s1_reconcile_is_not_starved_by_exhausted_failed_rows(self):
        zombies = await self._make_exhausted_failed(TENANT_A, PRINT_RECONCILE_BATCH_LIMIT + 1)
        recoverable = await self._make_order(TENANT_A, print_status="PENDING")

        attempted = await reconcile_print_orders(self.db, [*zombies, recoverable], trigger="reconcile")

        await self.db.refresh(recoverable)
        self.assertEqual(attempted, 1)
        self.assertEqual(self.provider.await_count, 1)
        self.assertEqual(recoverable.print_status, "SUCCESS")

    async def test_s1b_reconcile_is_not_starved_by_already_printed_orders(self):
        # The common workbench shape: many printed orders ahead of the one that needs help.
        printed = [
            await self._make_order(TENANT_A, print_status="SUCCESS", attempts=1, last_attempt_age_s=600)
            for _ in range(PRINT_RECONCILE_BATCH_LIMIT + 1)
        ]
        recoverable = await self._make_order(TENANT_A, print_status="PENDING")

        attempted = await reconcile_print_orders(self.db, [*printed, recoverable], trigger="reconcile")

        self.assertEqual(attempted, 1)
        self.assertEqual(self.provider.await_count, 1)

    async def test_s2_reconcile_never_sends_exhausted_failed_rows(self):
        zombies = await self._make_exhausted_failed(TENANT_A, 3)

        attempted = await reconcile_print_orders(self.db, zombies, trigger="reconcile")

        self.assertEqual(attempted, 0)
        self.provider.assert_not_awaited()

    async def test_s3_reconcile_still_retries_recoverable_failed(self):
        order = await self._make_order(
            TENANT_A,
            print_status="FAILED",
            attempts=1,
            last_attempt_age_s=PRINT_RETRY_COOLDOWN_SECONDS + 45,
        )

        attempted = await reconcile_print_orders(self.db, [order], trigger="reconcile")

        await self.db.refresh(order)
        self.assertEqual(attempted, 1)
        self.assertEqual(self.provider.await_count, 1)
        self.assertEqual(order.print_status, "SUCCESS")
        self.assertEqual(int(_initial(order).get("attempts") or 0), 2)

    async def test_s4_reconcile_quarantines_stale_sending_without_the_provider(self):
        sending = await self._make_order(
            TENANT_A,
            print_status="SENDING",
            attempts=1,
            last_attempt_age_s=PRINT_SENDING_STALE_SECONDS + 90,
            created_age_s=PRINT_AUTO_RECOVERY_MAX_AGE_SECONDS + 3600,
        )

        attempted = await reconcile_print_orders(self.db, [sending], trigger="reconcile")

        await self.db.refresh(sending)
        self.assertEqual(attempted, 1)
        self.assertEqual(sending.print_status, "UNKNOWN")
        self.assertEqual(_initial(sending).get("last_error_code"), "STALE_SENDING")
        self.provider.assert_not_awaited()

    async def test_s4b_reconcile_leaves_a_fresh_sending_claim_alone(self):
        sending = await self._make_order(
            TENANT_A, print_status="SENDING", attempts=1, last_attempt_age_s=1,
        )

        attempted = await reconcile_print_orders(self.db, [sending], trigger="reconcile")

        await self.db.refresh(sending)
        self.assertEqual(attempted, 0)
        self.assertEqual(sending.print_status, "SENDING")
        self.provider.assert_not_awaited()

    async def test_s5_reconcile_never_touches_unknown(self):
        unknown = await self._make_order(
            TENANT_A, print_status="UNKNOWN", attempts=1, last_attempt_age_s=600,
        )

        attempted = await reconcile_print_orders(self.db, [unknown], trigger="reconcile")

        await self.db.refresh(unknown)
        self.assertEqual(attempted, 0)
        self.assertEqual(unknown.print_status, "UNKNOWN")
        self.provider.assert_not_awaited()

    async def test_s6_reconcile_does_not_auto_print_rows_outside_the_window(self):
        too_old = PRINT_AUTO_RECOVERY_MAX_AGE_SECONDS + 3600
        old_pending = await self._make_order(TENANT_A, print_status="PENDING", created_age_s=too_old)
        old_failed = await self._make_order(
            TENANT_A,
            print_status="FAILED",
            attempts=1,
            last_attempt_age_s=PRINT_RETRY_COOLDOWN_SECONDS + 45,
            created_age_s=too_old,
        )
        fresh = await self._make_order(TENANT_A, print_status="PENDING")

        attempted = await reconcile_print_orders(self.db, [old_pending, old_failed, fresh], trigger="reconcile")

        self.assertEqual(attempted, 1)
        self.assertEqual(self.provider.await_count, 1)
        await self.db.refresh(old_pending)
        await self.db.refresh(old_failed)
        await self.db.refresh(fresh)
        # Still visible to staff as PENDING / FAILED -- only the automatic print is withheld.
        self.assertEqual(old_pending.print_status, "PENDING")
        self.assertEqual(old_failed.print_status, "FAILED")
        self.assertEqual(fresh.print_status, "SUCCESS")

    async def test_s7_both_recovery_paths_agree_on_the_same_inputs(self):
        too_old = PRINT_AUTO_RECOVERY_MAX_AGE_SECONDS + 3600
        retry_after = PRINT_RETRY_COOLDOWN_SECONDS + 45
        cases = {
            "pending_fresh": dict(print_status="PENDING"),
            "pending_too_old": dict(print_status="PENDING", created_age_s=too_old),
            "failed_retryable": dict(print_status="FAILED", attempts=1, last_attempt_age_s=retry_after, updated_age_s=retry_after),
            "failed_exhausted": dict(print_status="FAILED", attempts=MAX_PRINT_RETRY_ATTEMPTS, last_attempt_age_s=retry_after, updated_age_s=retry_after),
            "failed_too_old": dict(print_status="FAILED", attempts=1, last_attempt_age_s=retry_after, updated_age_s=retry_after, created_age_s=too_old),
            "unknown": dict(print_status="UNKNOWN", attempts=1, last_attempt_age_s=600, updated_age_s=600),
            "success": dict(print_status="SUCCESS", attempts=1, last_attempt_age_s=600, updated_age_s=600),
            "sending_stale": dict(
                print_status="SENDING", attempts=1,
                last_attempt_age_s=PRINT_SENDING_STALE_SECONDS + 90, updated_age_s=PRINT_SENDING_STALE_SECONDS + 90,
                created_age_s=too_old,
            ),
        }
        request_path = {name: await self._make_order(TENANT_A, **kw) for name, kw in cases.items()}
        loop_path = {name: await self._make_order(TENANT_B, **kw) for name, kw in cases.items()}

        # The request path first; then the loop, with tenant A denied so it only sees B.
        await reconcile_print_orders(self.db, list(request_path.values()), trigger="reconcile")
        sent_by_request_path = {c.args[0].id for c in self.provider.await_args_list}
        self.provider.reset_mock()
        with patch(CAPABILITY_PATH, AsyncMock(side_effect=lambda tenant_id, capability_key: tenant_id != TENANT_A)):
            await recover_pending_print_orders_once(self.db)
        sent_by_loop = {c.args[0].id for c in self.provider.await_args_list}

        for name in cases:
            await self.db.refresh(request_path[name])
            await self.db.refresh(loop_path[name])
            self.assertEqual(
                request_path[name].print_status, loop_path[name].print_status, f"final status differs for {name}",
            )
            self.assertEqual(
                request_path[name].id in sent_by_request_path,
                loop_path[name].id in sent_by_loop,
                f"provider use differs for {name}",
            )
        self.assertEqual(request_path["pending_fresh"].print_status, "SUCCESS")
        self.assertEqual(request_path["failed_retryable"].print_status, "SUCCESS")
        self.assertEqual(request_path["sending_stale"].print_status, "UNKNOWN")
        self.assertEqual(len(sent_by_request_path), 2)

    def test_s7b_shared_rules_for_the_disposition_helper(self):
        from datetime import timezone

        def order(**kw):
            row = Order(tenant_id=TENANT_A, status="pending", payment_mode="prepay", payment_status="paid")
            row.print_status = kw.get("print_status", "PENDING")
            row.created_at = datetime.utcnow() - timedelta(seconds=kw.get("created_age_s", 0))
            meta = {"version": 2, "initial_print": {
                "status": row.print_status, "attempts": kw.get("attempts", 0), "route": dict(ROUTE),
            }}
            _sync_legacy_initial_fields(meta)
            _set_print_meta(row, meta)
            return row

        now = datetime.now(timezone.utc)
        self.assertEqual(_auto_recovery_disposition(order(), now), "RETRY")
        self.assertEqual(_auto_recovery_disposition(order(print_status="FAILED", attempts=1), now), "RETRY")
        self.assertEqual(
            _auto_recovery_disposition(order(print_status="FAILED", attempts=MAX_PRINT_RETRY_ATTEMPTS), now), "SKIP",
        )
        self.assertEqual(_auto_recovery_disposition(order(print_status="UNKNOWN", attempts=1), now), "SKIP")
        self.assertEqual(_auto_recovery_disposition(order(print_status="SUCCESS", attempts=1), now), "SKIP")
        self.assertEqual(_auto_recovery_disposition(order(print_status="SENDING", attempts=1), now), "QUARANTINE")
        self.assertEqual(
            _auto_recovery_disposition(order(created_age_s=PRINT_AUTO_RECOVERY_MAX_AGE_SECONDS + 60), now), "SKIP",
        )
        # SENDING is exempt from the age window: quarantine never calls the provider.
        self.assertEqual(
            _auto_recovery_disposition(
                order(print_status="SENDING", attempts=1, created_age_s=PRINT_AUTO_RECOVERY_MAX_AGE_SECONDS + 60), now,
            ),
            "QUARANTINE",
        )

    # ------------------------------------------------------------------ budget / wiring
    async def test_provider_attempts_stay_capped_per_cycle(self):
        for idx in range(PRINT_RECONCILE_BATCH_LIMIT + 2):
            await self._make_order(TENANT_A, print_status="PENDING", updated_age_s=120 + idx)

        first = await recover_pending_print_orders_once(self.db)
        self.assertEqual(first, PRINT_RECONCILE_BATCH_LIMIT)
        self.assertEqual(self.provider.await_count, PRINT_RECONCILE_BATCH_LIMIT)

        second = await recover_pending_print_orders_once(self.db)
        self.assertEqual(second, 2)
        self.assertEqual(self.provider.await_count, PRINT_RECONCILE_BATCH_LIMIT + 2)

    def test_recovery_loop_owns_one_memo_for_its_lifetime(self):
        source = inspect.getsource(order_print_service.print_recovery_loop)
        self.assertIn("_RecoveryScanMemo()", source)
        self.assertIn("recover_pending_print_orders_once(memo=memo)", source)
        self.assertLess(source.index("_RecoveryScanMemo()"), source.index("while True"))


if __name__ == "__main__":
    unittest.main()
