import asyncio
import importlib.util
import pathlib
import sys
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "app" / "api" / "v1" / "orders.py"


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

    def __init__(self):
        self.id = 10001
        self.tenant_id = "tenant_1"
        self.status = "pending_payment"
        self.payment_status = "unpaid"
        self.payment_method = None


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
        }


def install_stubs():
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
        "app.models": types.ModuleType("app.models"),
        "app.models.order": types.ModuleType("app.models.order"),
        "app.models.tenant": types.ModuleType("app.models.tenant"),
        "app.services": types.ModuleType("app.services"),
        "app.services.coupon_service": types.ModuleType("app.services.coupon_service"),
        "app.services.wxpay_service": types.ModuleType("app.services.wxpay_service"),
    }
    for name, module in modules.items():
        sys.modules[name] = module

    modules["app.config"].settings = types.SimpleNamespace(H5_ORDER_BASE_URL="https://example.com", DEBUG=False)
    modules["app.core.database"].get_db = lambda: None
    modules["app.core.logger"].logger = types.SimpleNamespace(warning=lambda *a, **k: None, info=lambda *a, **k: None, error=lambda *a, **k: None)
    modules["app.core.response"].error_response = lambda code=-1, msg="error", data=None: {"code": code, "msg": msg, "data": data}
    modules["app.core.response"].success_response = lambda data=None, msg="ok": {"code": 200, "msg": msg, "data": data}
    modules["app.core.tenant_context"].TenantContext = types.SimpleNamespace(set_tenant_id=lambda tenant_id: None)
    modules["app.models.order"].Order = FakeOrder
    modules["app.models.order"].OrderItem = type("FakeOrderItem", (), {})
    modules["app.models.tenant"].Tenant = FakeTenant
    modules["app.services.coupon_service"].CouponService = type("CouponService", (), {})
    modules["app.services.wxpay_service"].WxPayService = FakeWxPayService


def load_orders_module():
    install_stubs()
    spec = importlib.util.spec_from_file_location("orders_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.select = fake_select
    return module


class WxPayNotifyIdempotencyTest(unittest.TestCase):
    def test_same_success_callback_three_times_runs_side_effects_once(self):
        module = load_orders_module()
        tenant = FakeTenant()
        order = FakeOrder()
        db = FakeDB(tenant, order)
        side_effects = {
            "payment_updates": 0,
            "coupon_writeoffs": 0,
            "points_changes": 0,
            "balance_changes": 0,
            "print_jobs": 0,
        }

        async def fake_on_payment_success(order_obj, db_obj, use_balance=False, payment_method="wxpay"):
            side_effects["payment_updates"] += 1
            side_effects["coupon_writeoffs"] += 1
            side_effects["points_changes"] += 1
            side_effects["print_jobs"] += 1
            if use_balance:
                side_effects["balance_changes"] += 1
            order_obj.payment_status = "paid"
            order_obj.payment_method = payment_method
            order_obj.status = "pending"
            return None, 0

        module._on_payment_success = fake_on_payment_success

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
        self.assertEqual(side_effects["balance_changes"], 0)
        self.assertEqual(side_effects["print_jobs"], 1)


if __name__ == "__main__":
    unittest.main()
