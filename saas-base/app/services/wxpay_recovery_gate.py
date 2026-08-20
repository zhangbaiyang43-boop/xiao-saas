"""P1-WXPAY-RECOVERY-GATE: single shared, in-process cadence gate for WeChat payment
recovery queries. See PROD-STABILITY-P1-01 Phase 1/2 for the forensic audit and
architecture decision this implements (Option D Hybrid).

Problem this solves: _recover_wxpay_order_if_paid (order_payment_service.py) had no
per-order cooldown/backoff/in-flight protection. Up to 7 independent call sites could
each fire an unbounded, uncoordinated real WeChat query for the same still-unpaid order --
production evidence showed the same order_id repeatedly queried by
merchant_order_query/pending_payment_background/stale_order_background within seconds of
each other. This module is the single shared entry point all recovery callers now go
through; it decides WHETHER a real provider query happens, never HOW payment success is
validated or applied -- _recover_wxpay_order_if_paid itself is untouched (same bool
contract, same commit/rollback/side-effect logic, same existing test coverage).

Design constraints carried over from the architecture decision:
- time.monotonic() for all cooldown-spacing arithmetic (never wall-clock datetime) --
  a system clock adjustment must not corrupt cooldown spacing.
- order AGE (which backoff tier applies) is inherently wall-clock (order.created_at),
  which is unavoidable and unrelated to the monotonic-spacing concern above.
- exactly one real provider query in flight per order_id at any instant; every other
  concurrent caller either skips or joins that same in-flight result, never duplicates it.
- destructive callers (about to cancel/reject a pending_payment order) can force a fresh
  query that bypasses cooldown, but MUST still join an already-in-flight query rather than
  firing a redundant second one -- an in-flight query, by definition, started before "now",
  so its result is always fresh enough for a decision being made "now".
- bounded memory: TTL + max-entry cap, cleanup piggybacked on existing infra (no new
  background thread/task).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from app.core.logger import logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.order import Order


class GateDecision(str, Enum):
    RECOVERED = "recovered"
    NOT_RECOVERED = "not_recovered"
    SKIPPED_COOLDOWN = "skipped_cooldown"
    JOINED_IN_FLIGHT = "joined_in_flight"
    PROVIDER_ERROR = "provider_error"


@dataclass(frozen=True)
class RecoveryOutcome:
    """Richer result the gate returns. `recovered` alone preserves the exact bool
    semantics _recover_wxpay_order_if_paid already had, so callers that only care about
    "did this order just get recovered" can keep using outcome.recovered unchanged."""

    decision: GateDecision
    recovered: bool
    attempt_count: int
    cooldown_seconds: Optional[float] = None
    trade_state: Optional[str] = None


# Backoff tiers, keyed by order age in seconds. Grounded in the existing, code-verified
# constants: STALE_ORDER_CLEANUP_TIMEOUT_MINUTES=15 (app/main.py) and
# PENDING_PAYMENT_TIMEOUT_MINUTES=15 (app/api/v1/orders.py) are the longest pending_payment
# lifecycle in the system; PENDING_PAYMENT_RECONCILE_INTERVAL_SECONDS=60 (app/main.py) is
# the background loop's own native tick. See PROD-STABILITY-P1-01 Phase 2 BACKOFF POLICY.
_TIER_2_5_MIN_COOLDOWN = 60.0
_TIER_5_10_MIN_COOLDOWN = 120.0
_TIER_10_PLUS_MIN_COOLDOWN = 180.0

# Client fast-lane window: member-mini-client's waitForBackendPaymentConfirmation polls
# every 900ms up to 6 times (~5.4s), with a possible follow-on attachPaymentReward chain
# (~11s worst case) -- see Phase 1 audit. 15s gives comfortable margin over the observed
# burst without bleeding into the 2-5min standard tier's own territory.
_FAST_LANE_WINDOW_SECONDS = 15.0
_FAST_LANE_DELAYS = (0.0, 2.0, 5.0)  # delay since FIRST attempt, indexed by attempt_count

# Memory bound. TTL derivation: 15min stale-cutoff + 5min worst-case additional wait for
# the stale-cleanup loop's own 300s tick interval to actually reach and cancel the order
# = 20min. Not a round-number guess -- see PROD-STABILITY-P1-01 Phase 3 MEMORY BOUND.
DEFAULT_MAX_ENTRIES = 5000
DEFAULT_TTL_SECONDS = 20 * 60


@dataclass
class _GateEntry:
    next_allowed_monotonic: float = 0.0
    attempt_count: int = 0
    first_attempt_monotonic: Optional[float] = None
    last_attempt_monotonic: Optional[float] = None
    last_result: Optional[bool] = None
    last_trade_state: Optional[str] = None
    in_flight_future: Optional["asyncio.Future[bool]"] = None
    # Set explicitly by the owning gate at creation time (using its own clock), not via a
    # dataclass default_factory -- default_factory has no access to a test-injected fake
    # clock, only the real time.monotonic.
    created_monotonic: float = 0.0
    touched_monotonic: float = 0.0


def _cooldown_for_age(order_age_seconds: float) -> float:
    if order_age_seconds < 5 * 60:
        return _TIER_2_5_MIN_COOLDOWN
    if order_age_seconds < 10 * 60:
        return _TIER_5_10_MIN_COOLDOWN
    return _TIER_10_PLUS_MIN_COOLDOWN


class WxpayRecoveryGate:
    """Process-wide shared cadence gate. One instance is meant to live for the life of
    the process (see `recovery_gate` singleton below); tests construct their own instance
    (optionally with an injected fake `clock`) and patch the module-level reference for
    isolation, matching this repo's established AsyncSessionLocal-patching test pattern.

    clock: defaults to time.monotonic. Never patch the global time.monotonic in tests
    instead -- asyncio's own event loop scheduling (asyncio.sleep, Future timeouts, etc.)
    relies on time.monotonic() internally, so a global patch would corrupt the event
    loop's own timing, not just this gate's. Inject a fake clock here instead.
    """

    def __init__(
        self,
        *,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock=time.monotonic,
    ):
        self._entries: dict[int, _GateEntry] = {}
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._clock = clock

    def _get_or_create(self, order_id: int) -> _GateEntry:
        entry = self._entries.get(order_id)
        if entry is None:
            if len(self._entries) >= self._max_entries:
                self._sweep(force_count=1)
            entry = _GateEntry(created_monotonic=self._clock())
            self._entries[order_id] = entry
        entry.touched_monotonic = self._clock()
        return entry

    def forget(self, order_id: int) -> None:
        """Drop an order's gate state -- callers should call this once they observe the
        order reach a terminal state (paid/cancelled/rejected) outside a gate-mediated
        call (e.g. the webhook callback path, which never goes through this gate)."""
        self._entries.pop(order_id, None)

    def sweep_expired(self) -> int:
        """Periodic cleanup. Intended to be piggybacked on an already-running background
        loop tick (e.g. _stale_order_cleanup_loop) -- never spawn a dedicated task/thread
        for this. Returns the number of entries removed."""
        return self._sweep(force_count=0)

    def _sweep(self, *, force_count: int) -> int:
        now = self._clock()
        removed = 0
        # TTL-expired entries with no in-flight query are always safe to drop.
        expired_ids = [
            oid
            for oid, e in self._entries.items()
            if e.in_flight_future is None and (now - e.touched_monotonic) > self._ttl_seconds
        ]
        for oid in expired_ids:
            del self._entries[oid]
            removed += 1
        if removed >= force_count:
            return removed
        # Backstop for the max-entries cap: evict oldest-touched, non-in-flight entries
        # until we've freed at least `force_count` more slots.
        candidates = sorted(
            (e for e in self._entries.values() if e.in_flight_future is None),
            key=lambda e: e.touched_monotonic,
        )
        for entry in candidates:
            if removed >= force_count:
                break
            for oid, e in list(self._entries.items()):
                if e is entry:
                    del self._entries[oid]
                    removed += 1
                    break
        return removed

    def entry_count(self) -> int:
        return len(self._entries)

    async def attempt_recovery(
        self,
        order: "Order",
        db: "AsyncSession",
        *,
        source: str,
        force_fresh: bool = False,
        wait_for_inflight: bool = False,
        fast_lane: bool = False,
    ) -> RecoveryOutcome:
        """Single shared entry point every recovery caller must go through.

        force_fresh: bypass cooldown (never bypasses in-flight dedup -- joins instead of
          duplicating). Required for any destructive pre-cancel/pre-reject check.
        wait_for_inflight: if a query is already in flight for this order, await its
          result instead of returning immediately without one. force_fresh implies this.
        fast_lane: apply the short post-payment-attempt schedule (client_order_query only)
          instead of the standard progressive background cadence, while the order is still
          within _FAST_LANE_WINDOW_SECONDS of creation.
        """
        from app.services.order_payment_service import OrderPaymentService

        # P0-MISSING-GREENLET: capture everything this function will ever need as plain
        # scalars BEFORE calling into recovery, and never read an `order` attribute again
        # after that call. _recover_wxpay_order_if_paid may rollback `db` (e.g. WeChat
        # reports the order still unpaid), and SQLAlchemy's rollback() unconditionally
        # expires every object in the session's identity map regardless of
        # expire_on_commit -- so `order` itself would come out of that call expired for
        # any caller that loaded it from the same `db`. A bare attribute read afterward
        # (even just for a log line) would then attempt an implicit lazy reload with no
        # active greenlet -> MissingGreenlet. This is the exact P0 failure mode; the gate
        # must not reintroduce it.
        order_id = order.id
        order_tenant_id = order.tenant_id
        order_age_seconds = (
            max((datetime.utcnow() - order.created_at).total_seconds(), 0.0) if order.created_at else 0.0
        )

        now = self._clock()
        entry = self._get_or_create(order_id)

        if entry.in_flight_future is not None:
            if force_fresh or wait_for_inflight:
                # asyncio.shield: if THIS joiner's own outer task gets cancelled (e.g.
                # its HTTP request times out) while awaiting, a bare `await
                # entry.in_flight_future` would propagate that cancellation onto the
                # SHARED future itself (Task.cancel() cancels whatever Future the task
                # is currently suspended on) -- corrupting the outcome for every OTHER
                # caller also awaiting that same future, and breaking the executor's own
                # eventual future.set_result() call. shield() lets this joiner's own
                # cancellation propagate normally to ITS caller without touching the
                # shared future other joiners (and the executor) still depend on.
                recovered = await asyncio.shield(entry.in_flight_future)
                logger.debug(
                    "[WXPAY_RECOVERY_JOINED_IN_FLIGHT] order_id=%s tenant_id=%s source=%s attempt=%s",
                    order_id, order_tenant_id, source, entry.attempt_count,
                )
                return RecoveryOutcome(
                    GateDecision.JOINED_IN_FLIGHT, recovered=recovered,
                    attempt_count=entry.attempt_count, trade_state=entry.last_trade_state,
                )
            logger.debug(
                "[WXPAY_RECOVERY_JOINED_IN_FLIGHT] order_id=%s tenant_id=%s source=%s attempt=%s no_wait=true",
                order_id, order_tenant_id, source, entry.attempt_count,
            )
            return RecoveryOutcome(
                GateDecision.JOINED_IN_FLIGHT, recovered=False, attempt_count=entry.attempt_count,
            )

        if not force_fresh and now < entry.next_allowed_monotonic:
            cooldown_remaining = entry.next_allowed_monotonic - now
            logger.debug(
                "[WXPAY_RECOVERY_SKIPPED_COOLDOWN] order_id=%s tenant_id=%s source=%s attempt=%s "
                "next_allowed_in_seconds=%.1f",
                order_id, order_tenant_id, source, entry.attempt_count, cooldown_remaining,
            )
            return RecoveryOutcome(
                GateDecision.SKIPPED_COOLDOWN, recovered=False, attempt_count=entry.attempt_count,
                cooldown_seconds=cooldown_remaining,
            )

        loop = asyncio.get_running_loop()
        future: "asyncio.Future[bool]" = loop.create_future()
        entry.in_flight_future = future
        logger.info(
            "[WXPAY_RECOVERY_ATTEMPT] order_id=%s tenant_id=%s source=%s attempt=%s order_age_seconds=%.0f",
            order_id, order_tenant_id, source, entry.attempt_count + 1, order_age_seconds,
        )
        try:
            payment_svc = OrderPaymentService(db)
            recovered = await payment_svc._recover_wxpay_order_if_paid(order, source=source)
        except asyncio.CancelledError:
            # The executor itself was cancelled mid-query (e.g. the owning request was
            # torn down, or the process is shutting down) -- NOT one of the shielded
            # joiners above, this is genuinely OUR OWN await being interrupted. Without
            # this handler, `except Exception` below would not catch it (CancelledError
            # is a BaseException, not an Exception, since Python 3.8), and
            # in_flight_future would be left permanently set -- every future caller for
            # this order_id would see JOINED_IN_FLIGHT forever and never query again.
            # Resolve the future (so any shielded joiners get a definitive answer instead
            # of hanging), clear in_flight, apply a normal cooldown so a cancellation
            # storm can't cause an immediate retry storm, then propagate the cancellation
            # to whatever actually owns it.
            if not future.done():
                future.set_result(False)
            entry.in_flight_future = None
            entry.attempt_count += 1
            entry.last_attempt_monotonic = now
            entry.next_allowed_monotonic = now + _cooldown_for_age(order_age_seconds)
            raise
        except Exception:
            # _recover_wxpay_order_if_paid already catches everything internally and
            # never raises in practice -- this is a defensive backstop for the gate's own
            # bookkeeping, not a signal path for WeChat-side errors (which the core
            # already absorbs into a plain False before this call returns). Must never
            # leave in_flight_future unresolved/never leave the entry stuck.
            logger.warning(
                "[WXPAY_RECOVERY_PROVIDER_ERROR] order_id=%s tenant_id=%s source=%s attempt=%s",
                order_id, order_tenant_id, source, entry.attempt_count + 1,
            )
            if not future.done():
                future.set_result(False)
            entry.in_flight_future = None
            entry.attempt_count += 1
            entry.last_attempt_monotonic = now
            entry.next_allowed_monotonic = now + _cooldown_for_age(order_age_seconds)
            return RecoveryOutcome(
                GateDecision.PROVIDER_ERROR, recovered=False, attempt_count=entry.attempt_count,
            )

        entry.attempt_count += 1
        if entry.first_attempt_monotonic is None:
            entry.first_attempt_monotonic = now
        entry.last_attempt_monotonic = now
        entry.last_result = recovered
        entry.in_flight_future = None
        if not future.done():
            future.set_result(recovered)

        if recovered:
            logger.info(
                "[WXPAY_RECOVERY_SUCCESS] order_id=%s tenant_id=%s source=%s attempt=%s",
                order_id, order_tenant_id, source, entry.attempt_count,
            )
            self.forget(order_id)
            return RecoveryOutcome(GateDecision.RECOVERED, recovered=True, attempt_count=entry.attempt_count)

        next_delay = self._next_delay(entry, order_age_seconds, fast_lane=fast_lane)
        entry.next_allowed_monotonic = now + next_delay
        logger.debug(
            "[WXPAY_RECOVERY_NOT_RECOVERED] order_id=%s tenant_id=%s source=%s attempt=%s "
            "cooldown_seconds=%.1f",
            order_id, order_tenant_id, source, entry.attempt_count, next_delay,
        )
        return RecoveryOutcome(GateDecision.NOT_RECOVERED, recovered=False, attempt_count=entry.attempt_count)

    def _next_delay(self, entry: _GateEntry, order_age_seconds: float, *, fast_lane: bool) -> float:
        # _FAST_LANE_DELAYS[k] is when attempt (k+1) becomes eligible, measured from the
        # FIRST attempt in this burst: attempt 1 immediate, attempt 2 at +2s, attempt 3 at
        # +5s. Called right after attempt_count'th attempt just completed -- so once
        # attempt_count reaches len(_FAST_LANE_DELAYS) (3 scheduled fast-lane attempts
        # exhausted), fall through to the standard cadence rather than recomputing an
        # already-elapsed fast-lane target (which would otherwise produce a zero/negative
        # cooldown and defeat throttling entirely).
        if (
            fast_lane
            and order_age_seconds < _FAST_LANE_WINDOW_SECONDS
            and entry.attempt_count < len(_FAST_LANE_DELAYS)
        ):
            anchor = entry.first_attempt_monotonic if entry.first_attempt_monotonic is not None else self._clock()
            target = anchor + _FAST_LANE_DELAYS[entry.attempt_count]
            remaining = target - self._clock()
            if remaining > 0:
                return remaining
        return _cooldown_for_age(order_age_seconds)


# Process-wide singleton. Tests patch this module attribute (or construct their own
# WxpayRecoveryGate and monkeypatch the reference) for isolation between test cases --
# mirrors this repo's established app.core.database.AsyncSessionLocal patching pattern.
recovery_gate = WxpayRecoveryGate()
