import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MAIN_SOURCE = (ROOT / "app" / "main.py").read_text(encoding="utf-8-sig")
API_SOURCE = (ROOT / "app" / "api" / "v1" / "merchant_system.py")
DASHBOARD_SOURCE = (
    ROOT.parent / "admin-h5" / "src" / "views" / "Dashboard.vue"
).read_text(encoding="utf-8-sig")
ADMIN_API_SOURCE = (
    ROOT.parent / "admin-h5" / "src" / "api" / "index.js"
).read_text(encoding="utf-8-sig")


class MerchantSystemStatusContractsTest(unittest.TestCase):
    def test_backend_exposes_readonly_merchant_system_status(self):
        self.assertTrue(API_SOURCE.exists())
        source = API_SOURCE.read_text(encoding="utf-8-sig")
        self.assertIn('router = APIRouter(prefix="/api/v1/merchant"', source)
        self.assertIn('@router.get("/system-status"', source)
        self.assertIn('"api": "ok"', source)
        self.assertIn('"database": database_status', source)
        self.assertIn('"order": order_status', source)
        self.assertIn('"payment": payment_status', source)
        self.assertIn('"printer": printer_status', source)
        self.assertIn('"checked_at":', source)
        self.assertIn('"message": message', source)
        self.assertNotIn('httpx', source)
        self.assertNotIn('requests.', source)

    def test_backend_router_is_registered(self):
        self.assertIn('from app.api.v1.merchant_system import router as merchant_system_router', MAIN_SOURCE)
        self.assertIn('app.include_router(merchant_system_router)', MAIN_SOURCE)

    def test_admin_dashboard_fetches_status_but_only_surfaces_actionable_printer_state(self):
        self.assertIn("getMerchantSystemStatus", ADMIN_API_SOURCE)
        self.assertIn("request.get('/v1/merchant/system-status')", ADMIN_API_SOURCE)
        self.assertIn("getMerchantSystemStatus", DASHBOARD_SOURCE)
        self.assertIn("printerActionable", DASHBOARD_SOURCE)
        self.assertIn("systemStatus.value.printer", DASHBOARD_SOURCE)
        self.assertIn("systemStatusCheckedLabel", DASHBOARD_SOURCE)
        self.assertIn("最近检测", DASHBOARD_SOURCE)
        self.assertIn("打印服务异常，请检查打印机或手动处理订单", DASHBOARD_SOURCE)
        self.assertNotIn("systemStatusItems", DASHBOARD_SOURCE)
        self.assertNotIn("系统状态获取失败，请稍后刷新", DASHBOARD_SOURCE)

        load_system_status_source = DASHBOARD_SOURCE.split(
            "async function loadSystemStatus()", 1
        )[1].split("async function loadTableCouponActivity()", 1)[0]
        self.assertIn("getMerchantSystemStatus", load_system_status_source)
        self.assertNotIn("message.error", load_system_status_source)
        self.assertNotIn("系统状态获取失败，请稍后刷新", load_system_status_source)

        todo_items_source = DASHBOARD_SOURCE.split("const todoItems = computed", 1)[1].split(
            "async function loadSystemStatus()", 1
        )[0]
        self.assertIn("printerActionable.value", todo_items_source)


if __name__ == "__main__":
    unittest.main()
