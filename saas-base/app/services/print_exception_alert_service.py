"""Server-side escalation of print exceptions: a paid order that the kitchen printer
may never have received must be noticed by the system, not by someone staring at a page.

NORMAL PATH IS SILENT -- an order printed (or still inside its normal retry window) never
produces a message. Only an exception does.

Layers (kept apart on purpose):

    DETECTOR     classify_order / detect_tenant_print_exceptions: find exceptions, nothing else
    AGGREGATOR   group_exceptions: one tenant -> at most one alert per group, with a count
    DEDUPE       _AlertStore + _handle_*: episode state, windows, reminder cap, recovery
    CHANNEL      SmsAlertChannel: the only thing that talks to a provider
    LOOP         run_print_alert_cycle / print_alert_loop: its own task, own sessions

Alerting never blocks fulfilment: it runs in its own asyncio task, every tenant and every
send is isolated by try/except, it never writes to an order and never calls a print
provider. UNKNOWN is alert-only here -- this module never resends anything.

State lives in Redis when available (dedupe survives restarts and is shared by workers) and
falls back to process memory otherwise; there is no new table.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from sqlalchemy import and_, or_
from sqlalchemy.future import select

from app.config import settings
from app.core.logger import logger
from app.models.order import Order
from app.services.order_print_service import (
    MAX_PRINT_RETRY_ATTEMPTS,
    PRINT_AUTO_RECOVERY_MAX_AGE_SECONDS,
    PRINT_RETRY_COOLDOWN_SECONDS,
    _get_print_meta,
    _load_print_route_and_credentials,
    _parse_dt,
)

# --- exception types -------------------------------------------------------------------
PRINT_EXHAUSTED = "PRINT_EXHAUSTED"
PRINT_UNKNOWN_STALE = "PRINT_UNKNOWN_STALE"
PRINT_NOT_ELIGIBLE_LONG = "PRINT_NOT_ELIGIBLE_LONG"
PAID_WITHOUT_PRINT_INTENT = "PAID_WITHOUT_PRINT_INTENT"
# PRINTER_SILENCE_WATCHDOG is deliberately NOT implemented: "no accepted print for a while"
# cannot be told apart from "no orders for a while" without a per-tenant baseline, and a
# false P0 at a quiet shop costs trust. Revisit with order-rate data.

P0 = "P0"
P1 = "P1"

# Alert groups: one SMS stream per (tenant, group).
GROUP_DELIVERY = "DELIVERY"  # P0: a paid order may not have reached the kitchen
GROUP_CONFIG = "CONFIG"      # P1: printing is set up but cannot work

# --- timing contract -------------------------------------------------------------------
PRINT_ALERT_SCAN_INTERVAL_SECONDS = 60
# The automatic path (3 attempts, 30s apart, plus the quarantine of an interrupted send)
# has settled well inside this; anything still unresolved after it is a real exception.
PRINT_ALERT_GRACE_SECONDS = (MAX_PRINT_RETRY_ATTEMPTS + 1) * PRINT_RETRY_COOLDOWN_SECONDS
# Same-tenant, same-group messages are at least this far apart.
PRINT_ALERT_DEDUPE_SECONDS = 10 * 60
# At most 1 alert + this many reminders per episode; then silent until it recovers.
PRINT_ALERT_MAX_REMINDERS = 3
# Remember an open episode as long as the orders in it can still be alerted on.
PRINT_ALERT_EPISODE_TTL_SECONDS = PRINT_AUTO_RECOVERY_MAX_AGE_SECONDS
# Bound the work for one tenant in one scan.
PRINT_ALERT_MAX_ORDERS_PER_TENANT = 200

_CANDIDATE_STATUSES = ("pending", "preparing", "done")
_CANDIDATE_PRINT_STATUSES = ("PENDING", "FAILED", "UNKNOWN", "NOT_ELIGIBLE")
_PHONE_RE = re.compile(r"^1\d{10}$")
_INDEX_KEY = "print_alert:index"


@dataclass(frozen=True)
class PrintException:
    tenant_id: str
    order_id: int
    type: str
    severity: str
    reason: str | None = None

    @property
    def group(self) -> str:
        return GROUP_DELIVERY if self.severity == P0 else GROUP_CONFIG


# =========================================================================================
# DETECTOR
# =========================================================================================
def printer_config_state(route: dict[str, Any], credentials: dict[str, Any]) -> str:
    """ready / partial / absent -- mirrors the provider executor's pre-flight checks in
    order_print_service (identifier + credential, plus app id for Kuaimai) without calling
    any provider.

    ``absent`` means the shop never set a printer up (a workbench-mode shop): printing is
    not expected there and nothing about printing may alert. ``partial`` means a setup was
    started and cannot work.
    """
    required = [route.get("printer_identifier"), credentials.get("credential")]
    if route.get("provider") == "kuaimai":
        required.append(credentials.get("app_id"))
    present = [bool(item) for item in required]
    if all(present):
        return "ready"
    if any(present):
        return "partial"
    return "absent"


def _attempts(meta: dict) -> int:
    return int(meta.get("attempts") or 0)


def _manual_reprint_succeeded(meta: dict) -> bool:
    events = meta.get("manual_reprints") or []
    return bool(events) and str(events[-1].get("status") or "").upper() == "SUCCESS"


def _paid_at(order: Order) -> datetime | None:
    """When the order became the kitchen's business (UTC-aware)."""
    if (getattr(order, "payment_mode", "prepay") or "prepay") == "prepay":
        return _parse_dt(getattr(order, "payment_time", None)) or _parse_dt(getattr(order, "created_at", None))
    return _parse_dt(getattr(order, "created_at", None))


def classify_order(
    order: Order,
    now: datetime,
    *,
    printer_state: str,
    pickup_defer: bool = False,
) -> PrintException | None:
    """Pure: decide whether one order is a print exception. ``now`` is timezone-aware UTC.

    Callers have already established that the tenant expects automatic kitchen printing
    (capability granted, printer not ``absent``).
    """
    tenant_id = str(order.tenant_id)
    order_id = int(order.id)
    meta = _get_print_meta(order)
    db_status = str(getattr(order, "print_status", "") or "").upper()

    if db_status == "SUCCESS" or meta.get("status") == "printed":
        return None
    if _manual_reprint_succeeded(meta):
        return None  # a person already got the ticket out; nothing left to escalate

    idle_since = _parse_dt(getattr(order, "updated_at", None))
    idle = (now - idle_since).total_seconds() if idle_since else 0.0
    settled_for_grace = idle >= PRINT_ALERT_GRACE_SECONDS

    initial = meta.get("initial_print") if isinstance(meta.get("initial_print"), dict) else {}
    has_intent = bool(initial and initial.get("route"))

    if printer_state == "partial":
        return PrintException(tenant_id, order_id, PRINT_NOT_ELIGIBLE_LONG, P1, "PRINTER_CONFIG_INCOMPLETE") \
            if settled_for_grace else None

    if db_status == "FAILED" and _attempts(meta) >= MAX_PRINT_RETRY_ATTEMPTS:
        return PrintException(tenant_id, order_id, PRINT_EXHAUSTED, P0, str(meta.get("last_error_code") or "") or None)

    if db_status == "UNKNOWN" or meta.get("status") == "unknown":
        return PrintException(tenant_id, order_id, PRINT_UNKNOWN_STALE, P0, str(meta.get("last_error_code") or "") or None) \
            if settled_for_grace else None

    if not has_intent and db_status == "PENDING":
        paid_at = _paid_at(order)
        if paid_at and (now - paid_at).total_seconds() >= PRINT_ALERT_GRACE_SECONDS:
            return PrintException(tenant_id, order_id, PAID_WITHOUT_PRINT_INTENT, P0, None)
        return None

    if db_status == "NOT_ELIGIBLE" and settled_for_grace:
        if pickup_defer:
            return PrintException(tenant_id, order_id, PRINT_NOT_ELIGIBLE_LONG, P1, "PICKUP_GATE")
        return PrintException(tenant_id, order_id, PRINT_NOT_ELIGIBLE_LONG, P1, str(initial.get("last_reason") or "") or None)

    if db_status == "PENDING" and has_intent and settled_for_grace:
        # An eligible intent that neither recovery path has moved in two minutes.
        return PrintException(tenant_id, order_id, PRINT_NOT_ELIGIBLE_LONG, P0, "STUCK_PENDING")

    return None


async def detect_tenant_print_exceptions(db, tenant_id: str, now: datetime) -> list[PrintException]:
    """Find print exceptions for one tenant. ``now`` is naive UTC (the DB convention).

    Quiet by construction for shops that do not use automatic printing: no KITCHEN_PRINT
    capability, or no printer configured at all, yields nothing.
    """
    from app.core.plan_capabilities import CAP_KITCHEN_PRINT
    from app.services.optional_entitlement import optional_capability_enabled
    from app.services.pickup_no_service import load_pickup_settings, should_defer_kitchen_print

    fresh_cutoff = now - timedelta(seconds=PRINT_AUTO_RECOVERY_MAX_AGE_SECONDS)
    result = await db.execute(
        select(Order)
        .where(
            Order.tenant_id == tenant_id,
            Order.status.in_(_CANDIDATE_STATUSES),
            Order.print_status.in_(_CANDIDATE_PRINT_STATUSES),
            or_(
                Order.payment_mode.in_(["postpay", "table_account"]),
                and_(Order.payment_mode == "prepay", Order.payment_status == "paid"),
            ),
            Order.created_at >= fresh_cutoff,
        )
        .order_by(Order.id.asc())
        .limit(PRINT_ALERT_MAX_ORDERS_PER_TENANT)
    )
    candidates = list(result.scalars().all())
    if not candidates:
        return []

    if not await optional_capability_enabled(tenant_id, CAP_KITCHEN_PRINT):
        return []
    route, credentials, _ = await _load_print_route_and_credentials(db, tenant_id)
    printer_state = printer_config_state(route, credentials)
    if printer_state == "absent":
        return []
    pickup_settings = await load_pickup_settings(db, tenant_id)

    aware_now = now.replace(tzinfo=timezone.utc)
    found: list[PrintException] = []
    for order in candidates:
        item = classify_order(
            order,
            aware_now,
            printer_state=printer_state,
            pickup_defer=should_defer_kitchen_print(order, pickup_settings),
        )
        if item is not None:
            found.append(item)
    return found


# =========================================================================================
# AGGREGATOR
# =========================================================================================
def group_exceptions(items: list[PrintException]) -> dict[str, list[PrintException]]:
    """One bucket per alert group; counts are distinct orders."""
    grouped: dict[str, dict[int, PrintException]] = {}
    for item in items:
        grouped.setdefault(item.group, {})[item.order_id] = item
    return {group: list(orders.values()) for group, orders in grouped.items()}


# =========================================================================================
# DEDUPE STATE
# =========================================================================================
class _AlertStore:
    """Episode state + send slots. Redis when usable, process memory otherwise.

    Redis gives cross-worker, restart-proof dedupe (``claim`` is SET NX EX, so only one
    worker sends per window). The in-memory fallback is per process: with Redis down and
    several workers, each may send once per window -- noisier, never silent.
    """

    def __init__(self, now_fn=datetime.utcnow) -> None:
        self._memory: dict[str, tuple[datetime, str]] = {}
        self._now = now_fn

    async def _redis(self):
        from app.core.redis_client import get_redis

        return await get_redis()

    def _mem_get(self, key: str) -> str | None:
        item = self._memory.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at <= self._now():
            self._memory.pop(key, None)
            return None
        return value

    async def get(self, key: str) -> dict | None:
        raw: str | None = None
        client = await self._redis()
        if client is not None:
            try:
                raw = await client.get(f"{settings.CACHE_PREFIX}{key}")
            except Exception as exc:
                logger.warning(f"print alert store read fell back to memory: {exc}")
        if raw is None:
            raw = self._mem_get(key)
        if not raw:
            return None
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    async def put(self, key: str, value: dict, ttl: int) -> None:
        raw = json.dumps(value, ensure_ascii=False)
        self._memory[key] = (self._now() + timedelta(seconds=max(ttl, 1)), raw)
        client = await self._redis()
        if client is not None:
            try:
                await client.setex(f"{settings.CACHE_PREFIX}{key}", ttl, raw)
            except Exception as exc:
                logger.warning(f"print alert store write kept in memory only: {exc}")

    async def delete(self, key: str) -> None:
        self._memory.pop(key, None)
        client = await self._redis()
        if client is not None:
            try:
                await client.delete(f"{settings.CACHE_PREFIX}{key}")
            except Exception as exc:
                logger.warning(f"print alert store delete skipped: {exc}")

    async def claim(self, key: str, ttl: int) -> bool:
        """True for exactly one caller per ``ttl`` window."""
        client = await self._redis()
        if client is not None:
            try:
                return bool(await client.set(f"{settings.CACHE_PREFIX}{key}", "1", nx=True, ex=ttl))
            except Exception as exc:
                logger.warning(f"print alert claim fell back to memory: {exc}")
        if self._mem_get(key) is not None:
            return False
        self._memory[key] = (self._now() + timedelta(seconds=max(ttl, 1)), "1")
        return True

    async def bump(self, key: str, ttl: int) -> int:
        """Increment a counter and return the new value (daily SMS budget)."""
        current = 0
        raw = self._mem_get(key)
        if raw and raw.isdigit():
            current = int(raw)
        client = await self._redis()
        if client is not None:
            try:
                value = int(await client.incr(f"{settings.CACHE_PREFIX}{key}"))
                if value == 1:
                    await client.expire(f"{settings.CACHE_PREFIX}{key}", ttl)
                self._memory[key] = (self._now() + timedelta(seconds=max(ttl, 1)), str(value))
                return value
            except Exception as exc:
                logger.warning(f"print alert counter fell back to memory: {exc}")
        value = current + 1
        self._memory[key] = (self._now() + timedelta(seconds=max(ttl, 1)), str(value))
        return value


def _episode_key(tenant_id: str, group: str) -> str:
    return f"print_alert:episode:{tenant_id}:{group}"


def _slot_key(tenant_id: str, group: str) -> str:
    return f"print_alert:slot:{tenant_id}:{group}"


# =========================================================================================
# CHANNEL
# =========================================================================================
class AlertChannel(Protocol):
    async def send_alert(self, tenant_id: str, phone: str | None, group: str, count: int) -> bool: ...

    async def send_recovered(self, tenant_id: str, phone: str | None, group: str) -> bool: ...


class SmsAlertChannel:
    """SMS to the shop owner's login phone (Tenant.phone). The message carries a count and
    nothing else: no order ids, amounts, customer data, error text or secrets."""

    def __init__(self, store: _AlertStore, sms=None) -> None:
        from app.services.tencent_sms_service import TencentSmsService

        self._store = store
        self._sms = sms or TencentSmsService()

    async def _send(self, tenant_id: str, phone: str | None, template_id: str, params: list[str], kind: str) -> bool:
        from app.services.tencent_sms_service import mask_phone

        if not phone or not _PHONE_RE.match(str(phone)):
            logger.warning("PRINT_ALERT_UNDELIVERABLE tenant_id=%s kind=%s reason=no_valid_owner_phone", tenant_id, kind)
            return False
        if not self._sms.is_template_configured(template_id):
            logger.warning("PRINT_ALERT_UNDELIVERABLE tenant_id=%s kind=%s reason=sms_template_not_configured", tenant_id, kind)
            return False
        day = datetime.utcnow().strftime("%Y%m%d")
        used = await self._store.bump(f"print_alert:sms_daily:{day}:{phone}", 86400)
        if used > settings.PRINT_ALERT_SMS_DAILY_LIMIT:
            logger.warning(
                "PRINT_ALERT_UNDELIVERABLE tenant_id=%s kind=%s reason=daily_limit phone=%s",
                tenant_id, kind, mask_phone(str(phone)),
            )
            return False
        status = await self._sms.send_template_notice(str(phone), template_id, params)
        if not status.ok:
            logger.error(
                "PRINT_ALERT_SEND_FAILED tenant_id=%s kind=%s provider_code=%s phone=%s",
                tenant_id, kind, status.provider_code, mask_phone(str(phone)),
            )
        return bool(status.ok)

    async def send_alert(self, tenant_id: str, phone: str | None, group: str, count: int) -> bool:
        return await self._send(
            tenant_id, phone, settings.TENCENT_SMS_PRINT_ALERT_TEMPLATE_ID, [str(int(count))], f"alert:{group}",
        )

    async def send_recovered(self, tenant_id: str, phone: str | None, group: str) -> bool:
        return await self._send(
            tenant_id, phone, settings.TENCENT_SMS_PRINT_RECOVERED_TEMPLATE_ID, [], f"recovered:{group}",
        )


# =========================================================================================
# ORCHESTRATION
# =========================================================================================
@dataclass
class CycleReport:
    tenants_scanned: int = 0
    alerts_sent: int = 0
    reminders_sent: int = 0
    recoveries_sent: int = 0
    suppressed: int = 0
    failures: int = 0
    open_groups: list[tuple[str, str]] = field(default_factory=list)


async def _owner_phone(db, tenant_id: str) -> str | None:
    from app.models.tenant import Tenant

    result = await db.execute(select(Tenant.phone).where(Tenant.tenant_id == tenant_id))
    return result.scalar_one_or_none()


async def _printed_since(db, tenant_id: str, since: datetime) -> bool:
    """Evidence that printing actually works again: an order whose kitchen ticket was
    accepted after the episode began."""
    result = await db.execute(
        select(Order.id)
        .where(Order.tenant_id == tenant_id, Order.print_status == "SUCCESS", Order.printed_at >= since)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _handle_open(
    db, store: _AlertStore, channel: AlertChannel, report: CycleReport,
    tenant_id: str, group: str, count: int, now: datetime,
) -> None:
    key = _episode_key(tenant_id, group)
    state = await store.get(key) or {
        "first_at": now.isoformat(), "last_sent_at": None, "sent": 0, "reminders": 0,
    }
    report.open_groups.append((tenant_id, group))

    reminders_left = int(state.get("reminders", 0)) < PRINT_ALERT_MAX_REMINDERS
    never_delivered = int(state.get("sent", 0)) == 0
    if not never_delivered and not reminders_left:
        await store.put(key, state, PRINT_ALERT_EPISODE_TTL_SECONDS)
        report.suppressed += 1
        return

    # One attempt per window per tenant+group, claimed before sending so a failing channel
    # is retried once per window instead of every scan, and workers do not double-send.
    if not await store.claim(_slot_key(tenant_id, group), PRINT_ALERT_DEDUPE_SECONDS):
        await store.put(key, state, PRINT_ALERT_EPISODE_TTL_SECONDS)
        report.suppressed += 1
        return

    ok = await channel.send_alert(tenant_id, await _owner_phone(db, tenant_id), group, count)
    if ok:
        if never_delivered:
            report.alerts_sent += 1
        else:
            state["reminders"] = int(state.get("reminders", 0)) + 1
            report.reminders_sent += 1
        state["sent"] = int(state.get("sent", 0)) + 1
        state["last_sent_at"] = now.isoformat()
    logger.error(
        "PRINT_ALERT_OPEN tenant_id=%s group=%s orders=%s delivered=%s sent=%s",
        tenant_id, group, count, ok, state.get("sent", 0),
    )
    await store.put(key, state, PRINT_ALERT_EPISODE_TTL_SECONDS)


async def _handle_clear(
    db, store: _AlertStore, channel: AlertChannel, report: CycleReport,
    tenant_id: str, group: str, state: dict,
) -> None:
    """The group has no exceptions left. Say so only if we said there was one AND there is
    proof printing works again; otherwise close quietly."""
    key = _episode_key(tenant_id, group)
    if int(state.get("sent", 0)) >= 1:
        first_at = _parse_dt(state.get("first_at"))
        since = first_at.replace(tzinfo=None) if first_at else datetime.utcnow() - timedelta(hours=1)
        if await _printed_since(db, tenant_id, since):
            if await channel.send_recovered(tenant_id, await _owner_phone(db, tenant_id), group):
                report.recoveries_sent += 1
            logger.warning("PRINT_ALERT_RECOVERED tenant_id=%s group=%s", tenant_id, group)
        else:
            logger.warning("PRINT_ALERT_CLOSED_WITHOUT_EVIDENCE tenant_id=%s group=%s", tenant_id, group)
    await store.delete(key)


async def _scan_tenants(db, store: _AlertStore, now: datetime) -> list[str]:
    fresh_cutoff = now - timedelta(seconds=PRINT_AUTO_RECOVERY_MAX_AGE_SECONDS)
    result = await db.execute(
        select(Order.tenant_id)
        .where(
            Order.status.in_(_CANDIDATE_STATUSES),
            Order.print_status.in_(_CANDIDATE_PRINT_STATUSES),
            Order.created_at >= fresh_cutoff,
        )
        .distinct()
    )
    tenants = {str(item) for item in result.scalars().all() if item}
    index = await store.get(_INDEX_KEY) or {}
    tenants.update(str(item) for item in (index.get("tenants") or []))
    return sorted(tenants)


async def run_print_alert_cycle(
    db_factory,
    *,
    store: _AlertStore,
    channel: AlertChannel,
    now: datetime | None = None,
) -> CycleReport:
    """One scan. Never raises: a failing tenant or channel is logged and skipped."""
    now = now or datetime.utcnow()
    report = CycleReport()
    try:
        async with db_factory() as db:
            tenants = await _scan_tenants(db, store, now)
            for tenant_id in tenants:
                report.tenants_scanned += 1
                try:
                    items = await detect_tenant_print_exceptions(db, tenant_id, now)
                    grouped = group_exceptions(items)
                    for group in (GROUP_DELIVERY, GROUP_CONFIG):
                        state = await store.get(_episode_key(tenant_id, group))
                        if grouped.get(group):
                            await _handle_open(
                                db, store, channel, report, tenant_id, group, len(grouped[group]), now,
                            )
                        elif state is not None:
                            await _handle_clear(db, store, channel, report, tenant_id, group, state)
                except Exception as exc:  # one tenant must not stop the others
                    report.failures += 1
                    logger.warning("PRINT_ALERT_TENANT_FAILED tenant_id=%s error=%s", tenant_id, exc)
            open_tenants = sorted({tenant for tenant, _ in report.open_groups})
            await store.put(_INDEX_KEY, {"tenants": open_tenants}, PRINT_ALERT_EPISODE_TTL_SECONDS)
    except Exception as exc:
        report.failures += 1
        logger.warning("PRINT_ALERT_CYCLE_FAILED error=%s", exc)
    return report


async def print_alert_loop() -> None:
    from app.core.database import AsyncSessionLocal

    store = _AlertStore()
    channel = SmsAlertChannel(store)
    while True:
        try:
            await run_print_alert_cycle(AsyncSessionLocal, store=store, channel=channel)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # run_print_alert_cycle already swallows; belt and braces
            logger.warning("[PRINT_ALERT_LOOP_FAILED] error=%s", exc)
        await asyncio.sleep(PRINT_ALERT_SCAN_INTERVAL_SECONDS)
