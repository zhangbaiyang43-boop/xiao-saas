import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ORDER_MANAGE_SOURCE = (
    ROOT.parent / "admin-h5" / "src" / "views" / "OrderManage.vue"
).read_text(encoding="utf-8-sig")
POLLING_MANAGER_SOURCE = (
    ROOT.parent / "admin-h5" / "src" / "utils" / "pollingManager.js"
).read_text(encoding="utf-8-sig")
ORDERS_SOURCE = (ROOT / "app" / "api" / "v1" / "orders.py").read_text(encoding="utf-8-sig")
LIFECYCLE_SERVICE_SOURCE = (
    ROOT / "app" / "services" / "order_lifecycle_service.py"
).read_text(encoding="utf-8-sig")


def script_function_source(source: str, name: str) -> str:
    lines = source.splitlines()
    start = next(
        (idx for idx, line in enumerate(lines) if line.startswith(f"async function {name}") or line.startswith(f"function {name}")),
        None,
    )
    assert start is not None, f"{name} source not found"
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if line.startswith("async function ") or line.startswith("function ") or line.startswith("const ") or line.startswith("onMounted"):
            end = idx
            break
    return "\n".join(lines[start:end])


def py_function_source(source: str, name: str) -> str:
    lines = source.splitlines()
    start = next((idx for idx, line in enumerate(lines) if line.startswith(f"async def {name}(")), None)
    assert start is not None, f"{name} source not found"
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if line.startswith("@router.") or line.startswith("async def ") or line.startswith("class "):
            end = idx
            break
    return "\n".join(lines[start:end])


def lifecycle_method_source(name: str) -> str:
    lines = LIFECYCLE_SERVICE_SOURCE.splitlines()
    start = next(
        (idx for idx, line in enumerate(lines) if line.startswith(f"    async def {name}(")),
        None,
    )
    assert start is not None, f"{name} source not found"
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if line.startswith("    async def ") or line.startswith("    def "):
            end = idx
            break
    return "\n".join(lines[start:end])


class MerchantOrderDeliveryContractsTest(unittest.TestCase):
    def test_backend_merchant_query_returns_full_today_paid_orders(self):
        source = lifecycle_method_source("list_orders")
        self.assertIn("Order.tenant_id == tenant_id", source)
        self.assertIn("date_str == \"today\"", source)
        self.assertIn("_recover_wxpay_order_if_paid(order, self.db)", source)
        self.assertIn("serialize_order(", source)
        self.assertIn("items_by_order.get(o.id, [])", source)
        self.assertIn("checkout_requested_at=checkout_requested_by_session.get(", source)

    def test_order_page_polls_without_manual_refresh_dependency(self):
        self.assertIn("loadOrders()", ORDER_MANAGE_SOURCE)
        self.assertIn("pollingManager.start('orders:today'", ORDER_MANAGE_SOURCE)
        self.assertIn("interval: 5000", ORDER_MANAGE_SOURCE)
        self.assertIn("hiddenInterval: 30000", ORDER_MANAGE_SOURCE)
        self.assertIn("idleInterval: 30000", ORDER_MANAGE_SOURCE)

    def test_order_page_uses_independent_poll_dedupe_key(self):
        load_orders = script_function_source(ORDER_MANAGE_SOURCE, "loadOrders")
        self.assertIn("dedupeKey: 'admin:orders:today:manage'", load_orders)
        self.assertNotIn("dedupeKey: 'admin:orders:today'", load_orders)

    def test_order_page_deduplicates_by_order_id(self):
        load_orders = script_function_source(ORDER_MANAGE_SOURCE, "loadOrders")
        self.assertIn("new Map", load_orders)
        self.assertIn("String(o.id)", load_orders)
        self.assertIn("uniqueOrders.map", load_orders)

    def test_reconnect_or_visibility_change_triggers_full_reload(self):
        self.assertIn("document.addEventListener('visibilitychange', onVisibilityChange)", POLLING_MANAGER_SOURCE)
        self.assertIn("runTask(task, true)", POLLING_MANAGER_SOURCE)
        self.assertIn("task.task({ key: task.key, fromPolling: !forced, forced })", POLLING_MANAGER_SOURCE)

    def test_twenty_paid_order_simulation_delivery_window(self):
        match = re.search(r"interval:\s*(\d+)", ORDER_MANAGE_SOURCE)
        self.assertIsNotNone(match)
        poll_interval_ms = int(match.group(1))
        rows = []
        for idx in range(20):
            paid_ms = idx * 250
            first_visible_ms = ((paid_ms + poll_interval_ms - 1) // poll_interval_ms) * poll_interval_ms
            rows.append((idx + 1, paid_ms, first_visible_ms, first_visible_ms - paid_ms))
        self.assertEqual(len(rows), 20)
        self.assertLessEqual(max(row[3] for row in rows), 5000)


if __name__ == "__main__":
    unittest.main()