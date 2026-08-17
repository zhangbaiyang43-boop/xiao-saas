"""Plan -> Capability policy (Phase F1F-A, F1F0/F1F0-A frozen contract,
docs/saas-subscription-audit.md).

Pure policy only: no SQLAlchemy, no AsyncSession, no SubscriptionService, no
DB model, no FastAPI. Capability *resolution* (which plan a tenant actually
has right now) lives in app/services/entitlement_service.py; this module
only answers "what capabilities does each plan tier include" and "which
plan codes include a given capability" -- two static questions with no I/O.

V1 has exactly three tiers and no runtime parent-lookup recursion --
FREE_CAPABILITIES / STANDARD_CAPABILITIES / PRO_CAPABILITIES are each
constructed as a complete, final set at module-import time (FREE union
STANDARD-additions union PRO-additions), so FREE subset STANDARD subset PRO
holds by construction, not by convention.
"""

from __future__ import annotations

PLAN_CODE_FREE = "FREE"
PLAN_CODE_STANDARD = "STANDARD"
PLAN_CODE_PRO = "PRO"

PLAN_CODES_IN_ORDER = (PLAN_CODE_FREE, PLAN_CODE_STANDARD, PLAN_CODE_PRO)

# Capability keys -- stable strings. Never spell these out as bare literals
# anywhere else; import the constant.
CAP_SCAN_ORDERING = "SCAN_ORDERING"
CAP_MENU_BASIC = "MENU_BASIC"
CAP_ORDER_MANAGEMENT = "ORDER_MANAGEMENT"
CAP_WECHAT_PAYMENT = "WECHAT_PAYMENT"
CAP_TABLE_MANAGEMENT = "TABLE_MANAGEMENT"
CAP_MENU_ADVANCED_TOOLS = "MENU_ADVANCED_TOOLS"
CAP_KITCHEN_PRINT = "KITCHEN_PRINT"
CAP_STAFF_MANAGEMENT = "STAFF_MANAGEMENT"
CAP_MEMBERSHIP = "MEMBERSHIP"
CAP_POINTS = "POINTS"
CAP_MEMBER_LEVELS = "MEMBER_LEVELS"
CAP_COUPONS = "COUPONS"
CAP_MARKETING_AUTOMATION = "MARKETING_AUTOMATION"
CAP_CUSTOMER_CONSUMPTION = "CUSTOMER_CONSUMPTION"
CAP_CHANNEL_ENTRY = "CHANNEL_ENTRY"
CAP_DISTRIBUTION_REFERRAL = "DISTRIBUTION_REFERRAL"

# Independent enumeration of every defined capability -- deliberately NOT
# derived from PLAN_CAPABILITIES/PRO_CAPABILITIES below, so the test that
# asserts PLAN_CAPABILITIES[PRO] == ALL_CAPABILITIES is a real structural
# check (matrix actually covers every defined key), not a tautology.
ALL_CAPABILITIES = frozenset({
    CAP_SCAN_ORDERING,
    CAP_MENU_BASIC,
    CAP_ORDER_MANAGEMENT,
    CAP_WECHAT_PAYMENT,
    CAP_TABLE_MANAGEMENT,
    CAP_MENU_ADVANCED_TOOLS,
    CAP_KITCHEN_PRINT,
    CAP_STAFF_MANAGEMENT,
    CAP_MEMBERSHIP,
    CAP_POINTS,
    CAP_MEMBER_LEVELS,
    CAP_COUPONS,
    CAP_MARKETING_AUTOMATION,
    CAP_CUSTOMER_CONSUMPTION,
    CAP_CHANNEL_ENTRY,
    CAP_DISTRIBUTION_REFERRAL,
})

_STANDARD_ADDITIONAL_CAPABILITIES = frozenset({
    CAP_MENU_ADVANCED_TOOLS,
    CAP_KITCHEN_PRINT,
    CAP_STAFF_MANAGEMENT,
})

_PRO_ADDITIONAL_CAPABILITIES = frozenset({
    CAP_MEMBERSHIP,
    CAP_POINTS,
    CAP_MEMBER_LEVELS,
    CAP_COUPONS,
    CAP_MARKETING_AUTOMATION,
    CAP_CUSTOMER_CONSUMPTION,
    CAP_CHANNEL_ENTRY,
    CAP_DISTRIBUTION_REFERRAL,
})

FREE_CAPABILITIES = frozenset({
    CAP_SCAN_ORDERING,
    CAP_MENU_BASIC,
    CAP_ORDER_MANAGEMENT,
    CAP_WECHAT_PAYMENT,
    CAP_TABLE_MANAGEMENT,
})

# Constructed as complete final sets at import time -- not a runtime parent
# lookup -- so FREE < STANDARD < PRO holds structurally.
STANDARD_CAPABILITIES = frozenset(FREE_CAPABILITIES | _STANDARD_ADDITIONAL_CAPABILITIES)
PRO_CAPABILITIES = frozenset(STANDARD_CAPABILITIES | _PRO_ADDITIONAL_CAPABILITIES)

PLAN_CAPABILITIES = {
    PLAN_CODE_FREE: FREE_CAPABILITIES,
    PLAN_CODE_STANDARD: STANDARD_CAPABILITIES,
    PLAN_CODE_PRO: PRO_CAPABILITIES,
}


def plans_requiring(capability: str) -> tuple[str, ...]:
    """Plan codes (FREE, STANDARD, PRO order) that include `capability`.

    Raises ValueError for an unrecognized capability key -- a typo'd
    constant is a development-time configuration error, never a merchant
    business outcome, so this must fail loud rather than silently return an
    empty tuple a caller could misread as "no plan grants this."
    """
    if capability not in ALL_CAPABILITIES:
        raise ValueError(f"unknown capability: {capability!r}")
    return tuple(
        plan_code for plan_code in PLAN_CODES_IN_ORDER
        if capability in PLAN_CAPABILITIES[plan_code]
    )
