import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ORDERS_SOURCE = (ROOT / "app" / "api" / "v1" / "orders.py").read_text(encoding="utf-8-sig")
LIFECYCLE_SERVICE_SOURCE = (
    ROOT / "app" / "services" / "order_lifecycle_service.py"
).read_text(encoding="utf-8-sig")
MENU_SOURCE = (
    ROOT.parent / "member-mini-client" / "src" / "subpkg-order" / "pages" / "menu.vue"
).read_text(encoding="utf-8-sig")
ORDER_MANAGE_SOURCE = (
    ROOT.parent / "admin-h5" / "src" / "views" / "OrderManage.vue"
).read_text(encoding="utf-8-sig")


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


class OrderStateMachineContractsTest(unittest.TestCase):
    def test_backend_declares_existing_status_machine_without_new_statuses(self):
        self.assertIn("ORDER_ALLOWED_TRANSITIONS", ORDERS_SOURCE)
        self.assertRegex(ORDERS_SOURCE, r'"pending"\s*:\s*\{"preparing", "rejected", "cancelled"\}')
        self.assertRegex(ORDERS_SOURCE, r'"preparing"\s*:\s*\{"done"\}')
        self.assertRegex(ORDERS_SOURCE, r'"done"\s*:\s*\{"settled"\}')
        self.assertIn('"pending_payment"', ORDERS_SOURCE)
        self.assertNotIn('"accepted"', ORDERS_SOURCE)
        self.assertNotIn('"cooking"', ORDERS_SOURCE)

    def test_status_update_is_tenant_scoped_idempotent_and_blocks_reverse_flow(self):
        source = lifecycle_method_source("update_order_status")
        self.assertIn("Order.tenant_id == tenant_id", source)
        self.assertIn("current_status == body.status", source)
        self.assertIn('"idempotent": True', source)
        self.assertIn("ORDER_ALLOWED_TRANSITIONS.get(current_status, set())", source)
        self.assertIn("code=409", source)
        self.assertIn("illegal status transition", source)

    def test_status_update_records_terminal_timestamps_once(self):
        source = lifecycle_method_source("update_order_status")
        self.assertIn('body.status == "done"', source)
        self.assertIn("served_at", source)
        self.assertIn('body.status == "settled"', source)
        self.assertIn("completed_at", source)

    def test_table_settlement_only_settles_done_orders(self):
        source = lifecycle_method_source("settle_table")
        self.assertIn("Order.dining_session_id == active_session.id", source)
        self.assertIn("TABLE_CLOSE_BLOCKING_STATUSES", source)
        self.assertIn("TABLE_CLOSE_DONE_STATUSES", source)
        self.assertIn('code=409', source)
        self.assertIn('msg="本桌还有未完成的订单，无法结账"', source)
        self.assertIn('settlement_orders = [', source)
        self.assertIn('o.status == "done"', source)
        # 不能再按 payment_status=="unpaid" 过滤 settlement_orders：先付后厨的订单到 done 时
        # 已经是 paid 了，按 unpaid 过滤会把它们永远漏在 done，见 test_settle_table_offline_paid_behavior.py。
        self.assertNotIn('o.status == "done" and getattr(o, "payment_status", None) == "unpaid"', source)
        self.assertIn('for o in settlement_orders:', source)
        self.assertIn('active_session.status = "CLOSED"', source)
        self.assertIn("active_session.active_key = None", source)
        self.assertIn('o.status = "settled"', source)

    def test_consumer_and_merchant_status_text_cover_backend_states(self):
        self.assertIn("pending: '", MENU_SOURCE)
        self.assertIn("preparing: '", MENU_SOURCE)
        self.assertIn("done: '", MENU_SOURCE)
        self.assertIn("settled: '", MENU_SOURCE)
        self.assertIn("function statusLabel(s)", ORDER_MANAGE_SOURCE)
        self.assertIn("pending:", ORDER_MANAGE_SOURCE)
        self.assertIn("preparing:", ORDER_MANAGE_SOURCE)
        self.assertIn("done:", ORDER_MANAGE_SOURCE)
        self.assertIn("settled:", ORDER_MANAGE_SOURCE)

    def test_consumer_status_rendering_uses_backend_status_without_fake_progression(self):
        self.assertIn("if (['paid', 'pending'].includes(status)) return 'pending'", MENU_SOURCE)
        self.assertIn("if (['accepted', 'preparing', 'cooking'].includes(status)) return 'preparing'", MENU_SOURCE)
        self.assertIn("if (['done', 'completed'].includes(status)) return 'done'", MENU_SOURCE)
        self.assertIn("if (status === 'settled') return 'settled'", MENU_SOURCE)
        self.assertNotIn("return 'accepted'", MENU_SOURCE)
        self.assertNotIn("return 'cooking'", MENU_SOURCE)
        self.assertNotIn("return 'completed'", MENU_SOURCE)
        self.assertIn("const order = ['pending', 'preparing', 'done', 'settled']", MENU_SOURCE)
        self.assertIn("['settled', 'cancelled', 'rejected'].includes(newStatus)", MENU_SOURCE)
        self.assertIn("!['settled', 'cancelled', 'rejected'].includes(normalizeOrderStatus(o.status))", MENU_SOURCE)

    def test_merchant_actions_follow_forward_sequence(self):
        self.assertIn("updateOrderStatus(order.id, 'preparing')", ORDER_MANAGE_SOURCE)
        self.assertIn("updateOrderStatus(order.id, 'done')", ORDER_MANAGE_SOURCE)
        self.assertIn("settleTable(settlingTable.value.tableNo)", ORDER_MANAGE_SOURCE)
        self.assertNotRegex(ORDER_MANAGE_SOURCE, re.compile(r"updateOrderStatus\([^)]*,\s*'pending'\)"))


if __name__ == "__main__":
    unittest.main()
