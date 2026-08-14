import asyncio
import importlib.util
import pathlib
import sys
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "app" / "api" / "v1" / "orders.py"
PAYMENT_SERVICE_PATH = ROOT / "app" / "services" / "order_payment_service.py"


class FakeColumn:
    def __eq__(self, other):
        return ("eq", other)

    def isnot(self, other):
        return ("isnot", other)


class FakeTenant:
    tenant_id = FakeColumn()
    wx_pay_enabled = FakeColumn()
    wx_mchid = FakeColumn()

    def __init__(self):
        self.tenant_id = "tenant_1"


class FakeOrder:
    id = FakeColumn()
    tenant_id = FakeColumn()

    def __init__(self):
        self.id = 10001
        self.tenant_id = "tenant_1"
        self.status = "pending_payment"
        self.payment_status = "unpaid"
        self.payment_method = None
        self.payment_mode = "prepay"
        self.total = 28
        self.wx_transaction_id = None


class FakeQuery:
    def __init__(self, model):
        self.model = model
        self.locked = False

    def where(self, *args):
        return self

    def with_for_update(self):
        self.locked = True
        return self


def fake_select(model):
    return FakeQuery(model)


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeResult:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or ([] if row is None else [row])

    def scalar_one_or_none(self):
        return self.row

    def scalars(self):
        return FakeScalarResult(self.rows)


class FakeDB:
    def __init__(self, tenant, order):
        self.tenant = tenant
        self.order = order
        self.order_lock_count = 0
        self.order_query_count = 0
        self.commit_count = 0

    async def execute(self, query):
        if query.model is FakeTenant:
            return FakeResult(self.tenant, [self.tenant])
        if query.model is FakeOrder:
            self.order_query_count += 1
            if query.locked:
                self.order_lock_count += 1
            return FakeResult(self.order)
        raise AssertionError(f"unexpected query model: {query.model}")

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        return None


class FakeRequest:
    headers = {"wechatpay-signature": "valid"}
    query_params = {"tenant_id": "tenant_1"}

    async def body(self):
        return b'{"same":"legal callback payload"}'


class FakeWxPayService:
    enabled = True

    def __init__(self, tenant):
        self.tenant = tenant

    def verify_notify(self, headers, raw_body):
        return {
            "out_trade_no": "10001",
            "transaction_id": "4200000000000000001",
            "trade_state": "SUCCESS",
            "amount": {"total": 2800, "currency": "CNY"},
        }


_ORIGINAL_MODULES = {}


def restore_stubs():
    """撤销 install_stubs() 对 sys.modules 的替换，避免 app.services.coupon_service
    这类真实模块被永久换成假模块，污染同一个 pytest 进程里跑在后面的其它测试文件。"""
    for name, original in _ORIGINAL_MODULES.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


def install_stubs():
    global _ORIGINAL_MODULES

    async def _noop_async(*args, **kwargs):
        return None

    async def _zero_async(*args, **kwargs):
        return 0

    modules = {
        "app": types.ModuleType("app"),
        "app.api": types.ModuleType("app.api"),
        "app.api.v1": types.ModuleType("app.api.v1"),
        "app.config": types.ModuleType("app.config"),
        "app.core": types.ModuleType("app.core"),
        "app.core.database": types.ModuleType("app.core.database"),
        "app.core.logger": types.ModuleType("app.core.logger"),
        "app.core.response": types.ModuleType("app.core.response"),
        "app.core.tenant_context": types.ModuleType("app.core.tenant_context"),
        "app.core.platform_rules": types.ModuleType("app.core.platform_rules"),
        "app.models": types.ModuleType("app.models"),
        "app.models.order": types.ModuleType("app.models.order"),
        "app.models.tenant": types.ModuleType("app.models.tenant"),
        "app.services": types.ModuleType("app.services"),
        "app.services.consumption_service": types.ModuleType("app.services.consumption_service"),
        "app.services.coupon_service": types.ModuleType("app.services.coupon_service"),
        "app.services.order_lifecycle_service": types.ModuleType("app.services.order_lifecycle_service"),
        "app.services.order_payment_service": types.ModuleType("app.services.order_payment_service"),
        "app.services.order_print_service": types.ModuleType("app.services.order_print_service"),
        "app.services.order_stock_service": types.ModuleType("app.services.order_stock_service"),
        "app.services.base_service": types.ModuleType("app.services.base_service"),
        "app.services.wxpay_service": types.ModuleType("app.services.wxpay_service"),
    }
    _ORIGINAL_MODULES = {name: sys.modules.get(name) for name in modules}
    for name, module in modules.items():
        sys.modules[name] = module

    modules["app.config"].settings = types.SimpleNamespace(H5_ORDER_BASE_URL="https://example.com", DEBUG=False)
    modules["app.core.database"].get_db = lambda: None
    modules["app.core.logger"].logger = types.SimpleNamespace(warning=lambda *a, **k: None, info=lambda *a, **k: None, error=lambda *a, **k: None)
    import importlib.util

    response_spec = importlib.util.spec_from_file_location(
        "app.core.response", ROOT / "app" / "core" / "response.py"
    )
    assert response_spec and response_spec.loader
    real_response = importlib.util.module_from_spec(response_spec)
    response_spec.loader.exec_module(real_response)
    modules["app.core.response"] = real_response
    sys.modules["app.core.response"] = real_response
    modules["app.core.tenant_context"].TenantContext = types.SimpleNamespace(set_tenant_id=lambda tenant_id: None)
    modules["app.core.platform_rules"].cap_discount_amount = lambda discount, total: discount
    modules["app.models.order"].Order = FakeOrder
    modules["app.models.order"].OrderItem = type("FakeOrderItem", (), {})
    modules["app.models.tenant"].Tenant = FakeTenant
    modules["app.services.coupon_service"].CouponService = type("CouponService", (), {})
    modules["app.services.coupon_service"]._mark_order_coupon_used_if_locked = _noop_async
    modules["app.services.coupon_service"]._set_order_coupon_status_if_locked = _noop_async
    modules["app.services.coupon_service"]._unlock_order_coupon_if_locked = _noop_async
    modules["app.services.consumption_service"]._record_order_consumption = _noop_async
    modules["app.services.order_lifecycle_service"].OrderLifecycleService = type("OrderLifecycleService", (), {})
    modules["app.services.order_payment_service"].OrderPaymentService = type(
        "OrderPaymentService",
        (),
        {
            "__init__": lambda self, db: setattr(self, "db", db),
            "_on_payment_success": _noop_async,
            "_recover_wxpay_order_if_paid": _noop_async,
        },
    )
    modules["app.services.order_stock_service"]._restore_order_stock = _noop_async
    modules["app.services.base_service"].BaseService = type(
        "BaseService",
        (),
        {"__init__": lambda self, db: setattr(self, "db", db)},
    )
    modules["app.services.order_print_service"].MAX_PRINT_RETRY_ATTEMPTS = 3
    modules["app.services.order_print_service"]._compose_merchant_note_with_print_meta = lambda note, meta: note
    modules["app.services.order_print_service"]._get_print_meta = lambda order: {}
    modules["app.services.order_print_service"]._print_paid_order_ticket = _noop_async
    modules["app.services.order_print_service"]._print_paid_order_ticket_background = _noop_async
    modules["app.services.order_print_service"]._serialize_print_meta = lambda order: {}
    modules["app.services.order_print_service"]._spawn_background_print_task = lambda *args, **kwargs: None
    modules["app.services.order_print_service"]._split_merchant_note_and_print_meta = lambda note: (note, {})
    modules["app.services.order_print_service"].build_staff_print_summary = lambda order, defer_kitchen_print=False: {
        "print_status": None,
        "print_status_label": "",
        "print_attempts": 0,
        "print_issue": None,
        "can_reprint": True,
    }
    modules["app.services.order_print_service"].can_reprint_order = lambda order, print_type="kitchen": (True, None)
    modules["app.services.order_print_service"].reconcile_print_orders = _zero_async
    modules["app.services.order_print_service"].supports_independent_print_session = lambda db: False
    modules["app.services.wxpay_service"].WxPayService = FakeWxPayService


def load_orders_module():
    install_stubs()
    payment_spec = importlib.util.spec_from_file_location(
        "order_payment_service_under_test",
        PAYMENT_SERVICE_PATH,
    )
    payment_module = importlib.util.module_from_spec(payment_spec)
    assert payment_spec.loader is not None
    sys.modules["app.services.order_payment_service"] = payment_module
    payment_spec.loader.exec_module(payment_module)
    payment_module.select = fake_select

    spec = importlib.util.spec_from_file_location("orders_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.select = fake_select
    _ORIGINAL_MODULES["app.api.v1.orders"] = sys.modules.get("app.api.v1.orders")
    sys.modules["app.api.v1.orders"] = module
    return module


class WxPayNotifyIdempotencyTest(unittest.TestCase):
    def tearDown(self):
        restore_stubs()

    def test_same_success_callback_three_times_runs_side_effects_once(self):
        module = load_orders_module()
        tenant = FakeTenant()
        order = FakeOrder()
        db = FakeDB(tenant, order)
        side_effects = {
            "payment_updates": 0,
            "coupon_writeoffs": 0,
            "points_changes": 0,
            "print_jobs": 0,
        }

        async def fake_on_payment_success(self, order_obj, payment_method="wxpay"):
            side_effects["payment_updates"] += 1
            side_effects["coupon_writeoffs"] += 1
            side_effects["points_changes"] += 1
            order_obj.payment_status = "paid"
            order_obj.payment_method = payment_method
            order_obj.status = "pending"
            return None, 0

        payment_module = sys.modules["app.services.order_payment_service"]
        payment_module.OrderPaymentService._on_payment_success = fake_on_payment_success

        async def fake_claim(self, order_obj, transaction_id):
            if order_obj.wx_transaction_id == transaction_id:
                return "duplicate"
            order_obj.wx_transaction_id = transaction_id
            return "bound"

        async def fake_post_commit(self, order_obj):
            side_effects["print_jobs"] += 1

        payment_module.OrderPaymentService._claim_wx_transaction = fake_claim
        payment_module.OrderPaymentService._run_post_commit_payment_effects = fake_post_commit

        results = [
            asyncio.run(module.wxpay_notify(FakeRequest(), db))
            for _ in range(3)
        ]

        self.assertEqual(results, [{"code": "SUCCESS", "message": "ok"}] * 3)
        self.assertEqual(order.status, "pending")
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(db.order_query_count, 3)
        self.assertEqual(db.order_lock_count, 3)
        self.assertEqual(db.commit_count, 1)
        self.assertEqual(side_effects["payment_updates"], 1)
        self.assertEqual(side_effects["coupon_writeoffs"], 1)
        self.assertEqual(side_effects["points_changes"], 1)
        self.assertEqual(side_effects["print_jobs"], 1)


if __name__ == "__main__":
    unittest.main()
