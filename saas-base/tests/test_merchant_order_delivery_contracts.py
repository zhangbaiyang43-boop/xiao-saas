import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ORDER_MANAGE_SOURCE = (
    ROOT.parent / "admin-h5" / "src" / "views" / "OrderManage.vue"
).read_text(encoding="utf-8-sig")
WORKBENCH_CORE_SOURCE = (
    ROOT.parent / "admin-h5" / "src" / "composables" / "workbenchSyncCore.js"
).read_text(encoding="utf-8-sig")
USE_WORKBENCH_SYNC_SOURCE = (
    ROOT.parent / "admin-h5" / "src" / "composables" / "useWorkbenchSync.js"
).read_text(encoding="utf-8-sig")
ORDERS_SOURCE = (ROOT / "app" / "api" / "v1" / "orders.py").read_text(encoding="utf-8-sig")
LIFECYCLE_SERVICE_SOURCE = (
    ROOT / "app" / "services" / "order_lifecycle_service.py"
).read_text(encoding="utf-8-sig")


def script_function_source(source: str, name: str) -> str:
    lines = source.splitlines()
    start = next(
        (
            idx
            for idx, line in enumerate(lines)
            if line.startswith(f"async function {name}")
            or line.startswith(f"function {name}")
            or line.startswith(f"export function {name}")
        ),
        None,
    )
    assert start is not None, f"{name} source not found"
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if line.startswith("async function ") or line.startswith("function ") or line.startswith("export function ") or line.startswith("const ") or line.startswith("onMounted"):
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
        # P0-MISSING-GREENLET: print reconciliation runs on an isolated `recon_db`
        # session (not self.db) so its commit/rollback can never expire the ORM objects
        # this read path is about to serialize -- see order_lifecycle_service.py for the
        # full rationale. P1-WXPAY-RECOVERY-GATE (MERCHANT_PROVIDER_QUERY=REMOVE): GET
        # /orders no longer calls WeChat at all -- pending_payment_background already
        # covers every pending_payment order on the same cadence this page's own polling
        # used to provide.
        source = lifecycle_method_source("list_orders")
        self.assertIn("Order.tenant_id == tenant_id", source)
        self.assertIn("resolve_merchant_list_date(date_str)", source)
        self.assertIn("date_mode == \"live\"", source)
        self.assertNotIn("_recover_wxpay_order_if_paid(", source)
        self.assertIn("reconcile_print_orders(", source)
        self.assertIn("recon_db, recon_orders, trigger=", source)
        self.assertIn("serialize_order(", source)
        self.assertIn("items_by_order.get(o.id or 0, [])", source)
        self.assertIn("checkout_requested_at=checkout_requested_by_session.get(", source)

    def test_order_page_polls_without_manual_refresh_dependency(self):
        self.assertIn("getOwnerOrderChanges", ORDER_MANAGE_SOURCE)
        self.assertIn("useWorkbenchSync", ORDER_MANAGE_SOURCE)
        self.assertNotIn("pollingManager.start('orders:today'", ORDER_MANAGE_SOURCE)
        self.assertIn("WORKBENCH_SYNC_INTERVAL_MS = 5000", WORKBENCH_CORE_SOURCE)
        self.assertIn("WORKBENCH_FULL_RECONCILE_INTERVAL_MS = 60000", WORKBENCH_CORE_SOURCE)

    def test_order_page_uses_independent_poll_dedupe_key(self):
        full = script_function_source(ORDER_MANAGE_SOURCE, "fetchOwnerFull")
        delta = script_function_source(ORDER_MANAGE_SOURCE, "fetchOwnerChanges")
        self.assertIn("dedupeKey: 'admin:orders:today:manage'", full)
        self.assertIn("dedupeKey: 'admin:orders:today:changes'", delta)
        self.assertNotEqual(full, delta)

    def test_order_page_deduplicates_by_order_id(self):
        owner_map = script_function_source(ORDER_MANAGE_SOURCE, "mapOwnerOrders")
        apply_delta = script_function_source(WORKBENCH_CORE_SOURCE, "applyWorkbenchDelta")
        self.assertIn("new Map", owner_map)
        self.assertIn("String(o.id)", owner_map)
        self.assertIn("map.set(String(o.id), o)", apply_delta)
        self.assertIn("map.set(sid, keep[0])", apply_delta)

    def test_reconnect_or_visibility_change_triggers_full_reload(self):
        self.assertIn("document.addEventListener('visibilitychange', onVisibility)", USE_WORKBENCH_SYNC_SOURCE)
        self.assertIn("window.addEventListener('pageshow', onPageShow)", USE_WORKBENCH_SYNC_SOURCE)
        self.assertIn("window.addEventListener('online', onOnline)", USE_WORKBENCH_SYNC_SOURCE)
        self.assertIn("core.syncNow()", USE_WORKBENCH_SYNC_SOURCE)

    def test_twenty_paid_order_simulation_delivery_window(self):
        script = ROOT.parent / "admin-h5" / "scripts" / "test-p0-08-acceptance.mjs"
        completed = subprocess.run(
            ["node", str(script)],
            cwd=ROOT.parent / "admin-h5",
            check=True,
            capture_output=True,
            text=True,
        )
        metrics = dict(
            line.split("=", 1)
            for line in completed.stdout.splitlines()
            if "=" in line
        )
        self.assertEqual(int(metrics["DEVICE_A_VISIBLE"]), 20)
        self.assertEqual(int(metrics["DEVICE_B_VISIBLE"]), 20)
        self.assertEqual(int(metrics["DEVICE_A_MISSING"]), 0)
        self.assertEqual(int(metrics["DEVICE_B_MISSING"]), 0)
        self.assertEqual(int(metrics["DUPLICATE_ROWS_A"]), 0)
        self.assertEqual(int(metrics["DUPLICATE_ROWS_B"]), 0)
        self.assertLessEqual(int(metrics["VISIBILITY_P95_MS"]), 5000)


if __name__ == "__main__":
    unittest.main()
