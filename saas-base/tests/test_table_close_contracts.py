import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ORDERS_SOURCE = (ROOT / "app" / "api" / "v1" / "orders.py").read_text(encoding="utf-8-sig")
DINING_SOURCE = (ROOT / "app" / "services" / "dining_session_service.py").read_text(encoding="utf-8-sig")
DINING_API_SOURCE = (ROOT / "app" / "api" / "v1" / "dining_sessions.py").read_text(encoding="utf-8-sig")
MENU_SOURCE = (
    ROOT.parent / "member-mini-client" / "src" / "subpkg-order" / "pages" / "menu.vue"
).read_text(encoding="utf-8-sig")
DINING_UTIL_SOURCE = (
    ROOT.parent / "member-mini-client" / "src" / "utils" / "dining.js"
).read_text(encoding="utf-8-sig")
ORDER_MODEL_SOURCE = (ROOT / "app" / "models" / "order.py").read_text(encoding="utf-8-sig")
DINING_MODEL_SOURCE = (ROOT / "app" / "models" / "dining.py").read_text(encoding="utf-8-sig")


TABLE_CLOSE_BLOCKING_STATUSES = {
    "pending_payment",
    "pending",
    "preparing",
    "refunding",
    "refund_pending",
    "refund_requested",
}
TABLE_CLOSE_DONE_STATUSES = {"done", "settled", "cancelled", "rejected"}


def can_close_table_session(statuses):
    blocking = [
        status
        for status in statuses
        if status in TABLE_CLOSE_BLOCKING_STATUSES or status not in TABLE_CLOSE_DONE_STATUSES
    ]
    return len(blocking) == 0, blocking


class TableCloseContractsTest(unittest.TestCase):
    def test_models_already_support_session_close_without_migration(self):
        self.assertIn("dining_session_id", ORDER_MODEL_SOURCE)
        self.assertIn("status", DINING_MODEL_SOURCE)
        self.assertIn("active_key", DINING_MODEL_SOURCE)
        self.assertIn("closed_at", DINING_MODEL_SOURCE)
        self.assertIn("closed_by", DINING_MODEL_SOURCE)

    def test_settle_table_locks_and_closes_current_open_session_only(self):
        self.assertIn("TABLE_CLOSE_BLOCKING_STATUSES", ORDERS_SOURCE)
        self.assertIn("TABLE_CLOSE_DONE_STATUSES", ORDERS_SOURCE)
        self.assertIn('DiningSession.status == "OPEN"', ORDERS_SOURCE)
        self.assertIn(".with_for_update()", ORDERS_SOURCE)
        self.assertIn("Order.dining_session_id == active_session.id", ORDERS_SOURCE)
        self.assertIn('active_session.status = "CLOSED"', ORDERS_SOURCE)
        self.assertIn("active_session.active_key = None", ORDERS_SOURCE)

    def test_closed_session_cannot_receive_add_on_order(self):
        self.assertIn('DiningSession.status == "OPEN"', ORDERS_SOURCE)
        self.assertIn("body.dining_session_id", ORDERS_SOURCE)
        self.assertIn("DiningSession.id == int(body.dining_session_id)", ORDERS_SOURCE)
        self.assertIn("return error_response(code=400", ORDERS_SOURCE)

    def test_current_orders_response_exposes_session_closed_state(self):
        self.assertIn("get_session_status", DINING_SOURCE)
        self.assertIn('"session_status": session_status', DINING_API_SOURCE)
        self.assertIn('"closed": session_status in ("CLOSED", "EXPIRED")', DINING_API_SOURCE)

    def test_consumer_page_blocks_add_on_after_session_closed(self):
        self.assertIn("const tableSessionClosed = ref(false)", MENU_SOURCE)
        self.assertIn("res.data?.closed === true", MENU_SOURCE)
        self.assertIn("['CLOSED', 'EXPIRED'].includes(sessionStatus)", MENU_SOURCE)
        self.assertIn("!storeClosed.value && !tableSessionClosed.value", MENU_SOURCE)
        self.assertIn("if (tableSessionClosed.value && !force) return false", MENU_SOURCE)
        self.assertIn("if (!sessionReady || tableSessionClosed.value)", MENU_SOURCE)
        self.assertIn("tableSessionClosed ?", MENU_SOURCE)
        self.assertIn("\\u91cd\\u65b0\\u626b\\u7801", MENU_SOURCE)

    def test_next_table_scan_forces_new_session_after_closed_page_state(self):
        # 本桌身份的建立/缓存判断收敛到 utils/dining.js 的 resolveDiningIdentity 共享实现
        # （entry/index.vue 和 menu.vue 都走这一份，不再各自维护），menu.vue 的
        # ensureDiningSession 只是薄封装，负责把结果同步进组件自己的响应式状态。
        #
        # onLoad 里这个调用不再传 force:true（P0 性能修复：entry 页扫码进来时已经
        # force 刷新过一次并写进缓存，menu.vue 不用再重复打一次一模一样的请求）——
        # 重新扫一张不同的桌码时之所以还能正确建立新会话，靠的不是这个 force 参数，
        # 是 resolveDiningIdentity 里的 staleForOtherTable 判断：缓存记录的桌号跟
        # 当前桌号对不上就自动判定缓存不可信、发起真实请求，这条判断在上面已经断言过。
        self.assertIn("const ensureDiningSession = async (force = false)", MENU_SOURCE)
        self.assertIn("resolveDiningIdentity", MENU_SOURCE)
        self.assertIn(
            "if (!force && !staleForOtherTable && cachedSessionId && cachedToken)",
            DINING_UTIL_SOURCE,
        )
        self.assertIn("tableSessionClosed.value = false", MENU_SOURCE)
        self.assertIn("await this.ensureDiningSession(false)", MENU_SOURCE)
        self.assertNotIn("if (!tableSessionClosed.value && sessionStatus === 'OPEN') tableSessionClosedNotice", MENU_SOURCE)

    def test_next_table_scan_creates_new_session_after_active_key_cleared(self):
        self.assertIn('active_key = f"{tenant_id}:{table_no}"', DINING_SOURCE)
        self.assertIn("DiningSession.active_key == active_key", DINING_SOURCE)
        self.assertIn('status="OPEN"', DINING_SOURCE)
        self.assertIn("active_key=active_key", DINING_SOURCE)

    def test_pending_payment_blocks_close(self):
        ok, blocking = can_close_table_session(["pending_payment"])
        self.assertFalse(ok)
        self.assertEqual(blocking, ["pending_payment"])

    def test_paid_waiting_accept_blocks_close(self):
        ok, blocking = can_close_table_session(["pending"])
        self.assertFalse(ok)
        self.assertEqual(blocking, ["pending"])

    def test_preparing_blocks_close(self):
        ok, blocking = can_close_table_session(["preparing"])
        self.assertFalse(ok)
        self.assertEqual(blocking, ["preparing"])

    def test_refunding_blocks_close(self):
        for status in ("refunding", "refund_pending", "refund_requested"):
            with self.subTest(status=status):
                ok, blocking = can_close_table_session([status])
                self.assertFalse(ok)
                self.assertEqual(blocking, [status])

    def test_all_finished_orders_can_close(self):
        ok, blocking = can_close_table_session(["done", "settled", "cancelled", "rejected"])
        self.assertTrue(ok)
        self.assertEqual(blocking, [])


if __name__ == "__main__":
    unittest.main()