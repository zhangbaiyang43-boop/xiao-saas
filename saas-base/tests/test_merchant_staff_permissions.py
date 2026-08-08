"""Merchant staff Role → Permission matrix + route default-deny contracts."""
import unittest

from app.core.merchant_auth import require_order_status_permission, staff_route_allowed
from app.core.permissions import (
    PERM_FINANCE_REFUND,
    PERM_FINANCE_SETTLE,
    PERM_KITCHEN_PRINT_REPRINT,
    PERM_MEMBER_MANAGE,
    PERM_ORDER_ACCEPT,
    PERM_ORDER_ASSISTED_ADD,
    PERM_ORDER_COMPLETE,
    PERM_ORDER_SERVE,
    PERM_ORDER_VIEW_FULFILLMENT,
    PERM_PICKUP_ASSIGN,
    PERM_PICKUP_CHANGE,
    PERM_PICKUP_VIEW,
    PERM_SETTINGS_PAYMENT,
    PERM_STAFF_MANAGE,
    PERM_TABLE_VIEW,
    ROLE_FRONTDESK,
    ROLE_KITCHEN,
    ROLE_OWNER,
    ROLE_WAITER,
    has_permission,
    permission_list,
    staff_home_path,
)
from app.api.v1.orders import serialize_fulfillment_order


class _Item:
    def __init__(self, name, qty):
        self.name = name
        self.qty = qty


class _Order:
    def __init__(self):
        self.id = 1234567890123456789
        self.status = "pending"
        self.table_no = "A05"
        self.pickup_no = "08"
        self.created_at = None
        self.remark = "少辣"
        self.staff_note = ""
        self.dining_session_id = 1
        self.order_type = "dine_in"
        self.phone = "13800000000"
        self.total = 99.5
        self.customer_id = 42


class MerchantStaffPermissionsTest(unittest.TestCase):
    def test_owner_has_wildcard(self):
        self.assertTrue(has_permission(ROLE_OWNER, PERM_FINANCE_SETTLE))
        self.assertTrue(has_permission(ROLE_OWNER, PERM_STAFF_MANAGE))
        self.assertEqual(permission_list(ROLE_OWNER), ["*"])

    def test_frontdesk_matrix(self):
        self.assertTrue(has_permission(ROLE_FRONTDESK, PERM_ORDER_VIEW_FULFILLMENT))
        self.assertTrue(has_permission(ROLE_FRONTDESK, PERM_ORDER_ASSISTED_ADD))
        self.assertTrue(has_permission(ROLE_FRONTDESK, PERM_TABLE_VIEW))
        self.assertTrue(has_permission(ROLE_FRONTDESK, PERM_PICKUP_VIEW))
        self.assertTrue(has_permission(ROLE_FRONTDESK, PERM_PICKUP_ASSIGN))
        self.assertTrue(has_permission(ROLE_FRONTDESK, PERM_PICKUP_CHANGE))
        self.assertFalse(has_permission(ROLE_FRONTDESK, PERM_ORDER_ACCEPT))
        self.assertFalse(has_permission(ROLE_FRONTDESK, PERM_ORDER_COMPLETE))
        self.assertFalse(has_permission(ROLE_FRONTDESK, PERM_KITCHEN_PRINT_REPRINT))
        self.assertFalse(has_permission(ROLE_FRONTDESK, PERM_FINANCE_SETTLE))
        self.assertFalse(has_permission(ROLE_FRONTDESK, PERM_MEMBER_MANAGE))
        self.assertFalse(has_permission(ROLE_FRONTDESK, PERM_STAFF_MANAGE))

    def test_waiter_matrix(self):
        self.assertTrue(has_permission(ROLE_WAITER, PERM_ORDER_VIEW_FULFILLMENT))
        self.assertTrue(has_permission(ROLE_WAITER, PERM_ORDER_SERVE))
        self.assertTrue(has_permission(ROLE_WAITER, PERM_ORDER_ASSISTED_ADD))
        self.assertTrue(has_permission(ROLE_WAITER, PERM_TABLE_VIEW))
        self.assertTrue(has_permission(ROLE_WAITER, PERM_PICKUP_VIEW))
        self.assertFalse(has_permission(ROLE_WAITER, PERM_ORDER_ACCEPT))
        self.assertFalse(has_permission(ROLE_WAITER, PERM_PICKUP_ASSIGN))
        self.assertFalse(has_permission(ROLE_WAITER, PERM_PICKUP_CHANGE))
        self.assertFalse(has_permission(ROLE_WAITER, PERM_ORDER_COMPLETE))
        self.assertFalse(has_permission(ROLE_WAITER, PERM_FINANCE_SETTLE))
        self.assertFalse(has_permission(ROLE_WAITER, PERM_FINANCE_REFUND))
        self.assertFalse(has_permission(ROLE_WAITER, PERM_MEMBER_MANAGE))
        self.assertFalse(has_permission(ROLE_WAITER, PERM_SETTINGS_PAYMENT))
        self.assertFalse(has_permission(ROLE_WAITER, PERM_STAFF_MANAGE))
        self.assertFalse(has_permission(ROLE_WAITER, PERM_KITCHEN_PRINT_REPRINT))
        self.assertFalse(has_permission(ROLE_FRONTDESK, PERM_ORDER_SERVE))
        self.assertFalse(has_permission(ROLE_KITCHEN, PERM_ORDER_SERVE))
        self.assertTrue(has_permission(ROLE_OWNER, PERM_ORDER_SERVE))

    def test_kitchen_matrix(self):
        self.assertTrue(has_permission(ROLE_KITCHEN, PERM_ORDER_ACCEPT))
        self.assertTrue(has_permission(ROLE_KITCHEN, PERM_ORDER_COMPLETE))
        self.assertTrue(has_permission(ROLE_KITCHEN, PERM_KITCHEN_PRINT_REPRINT))
        self.assertTrue(has_permission(ROLE_KITCHEN, PERM_PICKUP_VIEW))
        self.assertFalse(has_permission(ROLE_KITCHEN, PERM_ORDER_ASSISTED_ADD))
        self.assertFalse(has_permission(ROLE_KITCHEN, PERM_PICKUP_ASSIGN))
        self.assertFalse(has_permission(ROLE_KITCHEN, PERM_PICKUP_CHANGE))
        self.assertFalse(has_permission(ROLE_KITCHEN, PERM_FINANCE_SETTLE))
        self.assertFalse(has_permission(ROLE_KITCHEN, PERM_STAFF_MANAGE))
        self.assertFalse(has_permission(ROLE_KITCHEN, PERM_MEMBER_MANAGE))

    def test_staff_home_paths(self):
        self.assertEqual(staff_home_path(ROLE_FRONTDESK), "/frontdesk")
        self.assertEqual(staff_home_path(ROLE_WAITER), "/waiter")
        self.assertEqual(staff_home_path(ROLE_KITCHEN), "/kitchen")
        self.assertEqual(staff_home_path("owner"), "/")
        self.assertEqual(staff_home_path("cashier"), "/")

    def test_order_status_permission_mapping(self):
        self.assertFalse(require_order_status_permission("preparing", ROLE_WAITER))
        self.assertFalse(require_order_status_permission("preparing", ROLE_FRONTDESK))
        self.assertTrue(require_order_status_permission("preparing", ROLE_KITCHEN))
        self.assertFalse(require_order_status_permission("done", ROLE_WAITER))
        self.assertFalse(require_order_status_permission("done", ROLE_FRONTDESK))
        self.assertTrue(require_order_status_permission("done", ROLE_KITCHEN))
        self.assertFalse(require_order_status_permission("settled", ROLE_WAITER))
        self.assertFalse(require_order_status_permission("settled", ROLE_KITCHEN))
        self.assertTrue(require_order_status_permission("settled", ROLE_OWNER))

    def test_staff_route_default_deny(self):
        self.assertTrue(staff_route_allowed("GET", "/api/v1/orders/workbench", ROLE_WAITER))
        self.assertTrue(staff_route_allowed("GET", "/api/v1/orders/workbench", ROLE_FRONTDESK))
        self.assertTrue(staff_route_allowed("GET", "/api/v1/orders/workbench/changes", ROLE_WAITER))
        self.assertTrue(staff_route_allowed("GET", "/api/v1/orders/workbench/changes", ROLE_FRONTDESK))
        self.assertTrue(staff_route_allowed("GET", "/api/v1/orders/workbench/changes", ROLE_KITCHEN))
        self.assertFalse(staff_route_allowed("PATCH", "/api/v1/orders/123/status", ROLE_WAITER))
        self.assertFalse(staff_route_allowed("PATCH", "/api/v1/orders/123/status", ROLE_FRONTDESK))
        self.assertTrue(staff_route_allowed("PATCH", "/api/v1/orders/123/status", ROLE_KITCHEN))
        self.assertFalse(staff_route_allowed("PATCH", "/api/v1/orders/123/pickup-no", ROLE_WAITER))
        self.assertTrue(staff_route_allowed("PATCH", "/api/v1/orders/123/pickup-no", ROLE_FRONTDESK))
        self.assertFalse(staff_route_allowed("PATCH", "/api/v1/orders/123/pickup-no", ROLE_KITCHEN))
        self.assertTrue(staff_route_allowed("POST", "/api/v1/orders/123/serve", ROLE_WAITER))
        self.assertFalse(staff_route_allowed("POST", "/api/v1/orders/123/serve", ROLE_FRONTDESK))
        self.assertFalse(staff_route_allowed("POST", "/api/v1/orders/123/serve", ROLE_KITCHEN))
        self.assertTrue(staff_route_allowed("POST", "/api/v1/orders", ROLE_WAITER))
        self.assertTrue(staff_route_allowed("POST", "/api/v1/orders", ROLE_FRONTDESK))
        self.assertFalse(staff_route_allowed("POST", "/api/v1/orders", ROLE_KITCHEN))
        self.assertTrue(staff_route_allowed("GET", "/api/v1/menu/items", ROLE_WAITER))
        self.assertTrue(staff_route_allowed("GET", "/api/v1/dining-sessions/active", ROLE_FRONTDESK))
        self.assertFalse(staff_route_allowed("GET", "/api/v1/dining-sessions/active", ROLE_KITCHEN))
        self.assertTrue(staff_route_allowed("POST", "/api/v1/orders/123/reprint", ROLE_KITCHEN))
        self.assertFalse(staff_route_allowed("POST", "/api/v1/orders/123/reprint", ROLE_FRONTDESK))
        self.assertFalse(staff_route_allowed("POST", "/api/v1/orders/settle-table", ROLE_WAITER))
        self.assertFalse(staff_route_allowed("POST", "/api/v1/orders/settle-table", ROLE_FRONTDESK))
        self.assertFalse(staff_route_allowed("GET", "/api/v1/orders", ROLE_WAITER))
        self.assertFalse(staff_route_allowed("GET", "/api/v1/customers/", ROLE_WAITER))
        self.assertFalse(staff_route_allowed("GET", "/api/v1/tenant/settings", ROLE_KITCHEN))
        self.assertFalse(staff_route_allowed("GET", "/api/v1/merchant-accounts", ROLE_WAITER))
        self.assertFalse(staff_route_allowed("GET", "/api/v1/merchant-accounts", ROLE_FRONTDESK))
        self.assertTrue(staff_route_allowed("GET", "/api/v1/merchant-accounts", ROLE_OWNER))
        self.assertTrue(staff_route_allowed("GET", "/api/v1/orders", ROLE_OWNER))

    def test_fulfillment_dto_strips_sensitive_fields(self):
        payload = serialize_fulfillment_order(_Order(), [_Item("牛肉汤", 2)], can_assign_pickup=False)
        self.assertNotIn("phone", payload)
        self.assertNotIn("total", payload)
        self.assertNotIn("customer_id", payload)
        self.assertNotIn("payment_status", payload)
        self.assertNotIn("payment_method", payload)
        self.assertNotIn("discount_amount", payload)
        self.assertEqual(payload["table_no"], "A05")
        self.assertEqual(payload["pickup_no"], "08")
        self.assertEqual(payload["items"][0]["name"], "牛肉汤")
        self.assertNotIn("price", payload["items"][0])


if __name__ == "__main__":
    unittest.main()
