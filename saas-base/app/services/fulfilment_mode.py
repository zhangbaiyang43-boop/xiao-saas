"""Fulfilment mode: does this shop run the kitchen from the phone, or from the printer?

WORKBENCH (default, legacy): staff click "start" / "done" on the workbench. Table settlement
  waits for every order to be done.
PRINT_FIRST: the system prints the kitchen ticket automatically and nobody has to click
  anything for a normal order. ``pending`` is a perfectly good resting state until the table
  is settled, so it must not block settlement by itself.

The mode lives in TenantConfig.business_info["fulfilment_mode"] (no column, no migration).
Every reader goes through this module so admin, lifecycle and settlement agree on one
meaning. It fails closed: a missing, misspelled or unreadable value is WORKBENCH.

Nothing here ever turns a shop to PRINT_FIRST. The merchant settings endpoint refuses to
write the key; flipping it is a deliberate, per-shop operator action after the printer
has been proven.
"""
from __future__ import annotations

from typing import Any

FULFILMENT_MODE_KEY = "fulfilment_mode"
FULFILMENT_WORKBENCH = "WORKBENCH"
FULFILMENT_PRINT_FIRST = "PRINT_FIRST"
FULFILMENT_MODES = frozenset({FULFILMENT_WORKBENCH, FULFILMENT_PRINT_FIRST})

MANUAL_ACCEPT_DISABLED_CODE = "MANUAL_ACCEPT_DISABLED_IN_PRINT_FIRST"
POSTPAY_COLLECTION_NOT_CONFIRMED_CODE = "POSTPAY_COLLECTION_NOT_CONFIRMED"

# Orders whose bill is only collected at the till when the table is settled.
_COLLECT_AT_SETTLEMENT_MODES = frozenset({"postpay", "table_account"})


def normalize_fulfilment_mode(raw: object) -> str:
    """Exact (case-sensitive, trimmed) match or WORKBENCH. Never guesses."""
    if isinstance(raw, str) and raw.strip() in FULFILMENT_MODES:
        return raw.strip()
    return FULFILMENT_WORKBENCH


def fulfilment_mode_from_business_info(business_info: object) -> str:
    if not isinstance(business_info, dict):
        return FULFILMENT_WORKBENCH
    return normalize_fulfilment_mode(business_info.get(FULFILMENT_MODE_KEY))


def get_fulfilment_mode_from_config(config: object) -> str:
    return fulfilment_mode_from_business_info(getattr(config, "business_info", None))


def is_print_first_mode(mode_or_config: object) -> bool:
    """Accepts a mode string, a TenantConfig, or a business_info dict."""
    if isinstance(mode_or_config, str):
        return normalize_fulfilment_mode(mode_or_config) == FULFILMENT_PRINT_FIRST
    if isinstance(mode_or_config, dict):
        return fulfilment_mode_from_business_info(mode_or_config) == FULFILMENT_PRINT_FIRST
    return get_fulfilment_mode_from_config(mode_or_config) == FULFILMENT_PRINT_FIRST


async def get_fulfilment_mode(db: Any, tenant_id: str) -> str:
    """The tenant's mode, WORKBENCH on any doubt (no row, bad value, read error)."""
    from sqlalchemy import select

    from app.models.tenant_config import TenantConfig

    try:
        result = await db.execute(
            select(TenantConfig.business_info).where(TenantConfig.tenant_id == tenant_id)
        )
        return fulfilment_mode_from_business_info(result.scalar_one_or_none())
    except Exception:  # fail closed: the legacy mode is always safe
        from app.core.logger import logger

        logger.exception("fulfilment_mode read failed tenant_id=%s; falling back to WORKBENCH", tenant_id)
        return FULFILMENT_WORKBENCH


def collects_at_settlement(order: object) -> bool:
    return str(getattr(order, "payment_mode", "") or "") in _COLLECT_AT_SETTLEMENT_MODES


def print_first_pending_is_settleable(order: object, *, collection_confirmed: bool) -> bool:
    """PRINT_FIRST only: may this ``pending`` order stop blocking table settlement?

    Removing the kitchen click must not remove the cashier. A prepaid order qualifies when the
    money is really in (payment_status == paid). A postpay / table-account order is unpaid by
    definition until the till collects it, so it qualifies only when the settling cashier
    explicitly confirms collection in the settle request.
    """
    if str(getattr(order, "status", "") or "") != "pending":
        return False
    if str(getattr(order, "payment_status", "") or "") == "paid":
        return True
    return collects_at_settlement(order) and bool(collection_confirmed)


def settle_blocking_orders(
    orders: list,
    *,
    blocking_statuses: set,
    done_statuses: set,
    print_first: bool,
    collection_confirmed: bool,
) -> list:
    """Orders that keep a table from being settled.

    WORKBENCH: exactly the legacy rule. PRINT_FIRST: the same rule, except a settleable
    ``pending`` order does not block.
    """
    blockers = []
    for order in orders:
        status = order.status or ""
        legacy_block = status in blocking_statuses or status not in done_statuses
        if not legacy_block:
            continue
        if print_first and print_first_pending_is_settleable(order, collection_confirmed=collection_confirmed):
            continue
        blockers.append(order)
    return blockers
