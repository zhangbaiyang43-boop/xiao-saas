"""Merchant staff Role → Permission mapping (code-defined for V1).

Business APIs must authorize via Permission, not Role string checks.
Future DB-backed role_permissions can replace ROLE_PERMISSIONS without changing guards.
"""

from __future__ import annotations

from typing import Iterable

ROLE_OWNER = "owner"
ROLE_WAITER = "waiter"
ROLE_KITCHEN = "kitchen"

STAFF_ROLES = (ROLE_WAITER, ROLE_KITCHEN)
ALL_ROLES = (ROLE_OWNER, ROLE_WAITER, ROLE_KITCHEN)

# Atomic permissions mapped to real merchant actions
PERM_ORDER_VIEW_FULFILLMENT = "order.view_fulfillment"
PERM_ORDER_ACCEPT = "order.accept"  # pending → preparing
PERM_ORDER_COMPLETE = "order.complete"  # preparing → done
PERM_ORDER_REJECT = "order.reject"

PERM_TABLE_VIEW = "table.view"

PERM_PICKUP_VIEW = "pickup.view"
PERM_PICKUP_ASSIGN = "pickup.assign"
PERM_PICKUP_CHANGE = "pickup.change"

PERM_KITCHEN_VIEW = "kitchen.view"
PERM_KITCHEN_PRINT_REPRINT = "kitchen.print_reprint"

PERM_FINANCE_VIEW = "finance.view"
PERM_FINANCE_SETTLE = "finance.settle"
PERM_FINANCE_REFUND = "finance.refund"

PERM_MEMBER_VIEW = "member.view"
PERM_MEMBER_MANAGE = "member.manage"

PERM_MARKETING_VIEW = "marketing.view"
PERM_MARKETING_MANAGE = "marketing.manage"

PERM_SETTINGS_STORE = "settings.store"
PERM_SETTINGS_PAYMENT = "settings.payment"
PERM_SETTINGS_PRINTER = "settings.printer"

PERM_STAFF_VIEW = "staff.view"
PERM_STAFF_MANAGE = "staff.manage"

PERM_WILDCARD = "*"

WAITER_PERMISSIONS = frozenset(
    {
        PERM_ORDER_VIEW_FULFILLMENT,
        PERM_ORDER_ACCEPT,
        PERM_TABLE_VIEW,
        PERM_PICKUP_VIEW,
        PERM_PICKUP_ASSIGN,
        PERM_PICKUP_CHANGE,
    }
)

KITCHEN_PERMISSIONS = frozenset(
    {
        PERM_KITCHEN_VIEW,
        PERM_ORDER_VIEW_FULFILLMENT,
        PERM_ORDER_ACCEPT,
        PERM_ORDER_COMPLETE,
        PERM_KITCHEN_PRINT_REPRINT,
        PERM_PICKUP_VIEW,  # see plate number only; no assign/change
    }
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    ROLE_OWNER: frozenset({PERM_WILDCARD}),
    ROLE_WAITER: WAITER_PERMISSIONS,
    ROLE_KITCHEN: KITCHEN_PERMISSIONS,
}


def normalize_role(role: str | None) -> str:
    value = (role or ROLE_OWNER).strip().lower()
    if value not in ALL_ROLES:
        return ROLE_OWNER
    return value


def permissions_for_role(role: str | None) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(normalize_role(role), frozenset())


def has_permission(role: str | None, permission: str) -> bool:
    perms = permissions_for_role(role)
    if PERM_WILDCARD in perms:
        return True
    return permission in perms


def has_any_permission(role: str | None, permissions: Iterable[str]) -> bool:
    return any(has_permission(role, p) for p in permissions)


def permission_list(role: str | None) -> list[str]:
    perms = permissions_for_role(role)
    if PERM_WILDCARD in perms:
        return [PERM_WILDCARD]
    return sorted(perms)


# Map order status transitions → required permission
ORDER_STATUS_PERMISSIONS = {
    "preparing": PERM_ORDER_ACCEPT,
    "done": PERM_ORDER_COMPLETE,
    "settled": PERM_FINANCE_SETTLE,
    "rejected": PERM_ORDER_REJECT,
    "cancelled": PERM_FINANCE_REFUND,
}
