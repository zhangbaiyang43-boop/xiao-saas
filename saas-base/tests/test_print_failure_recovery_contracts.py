import asyncio
import importlib.util
import json
import pathlib
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "app" / "api" / "v1" / "orders.py"
PRINT_SERVICE_PATH = ROOT / "app" / "services" / "order_print_service.py"
LIFECYCLE_SERVICE_PATH = ROOT / "app" / "services" / "order_lifecycle_service.py"


class FakeColumn:
    def __eq__(self, other):
        return ("eq", other)


class FakeTenant:
    tenant_id = FakeColumn()

    def __init__(self):
        self.tenant_id = "tenant_1"
        self.name = "Test Shop"
        self.feieyun_sn = ""
        self.feieyun_key = ""


class FakeTenantConfig:
    tenant_id = FakeColumn()

    def __init__(self):
        self.business_info = {
            "printer_provider": "kuaimai",
            "kuaimai_printer": {
                "app_id": "app_1",
                "app_secret": "secret_1",
                "sn": "KM001",
                "order_template_id": "1634998374",
            },
        }


class FakeOrder:
    id = FakeColumn()
    tenant_id = FakeColumn()

    def __init__(self):
        self.id = 10001
        self.tenant_id = "tenant_1"
        self.table_no = "A01"
        self.phone = "15900000000"
        self.total = 15
        self.status = "pending"
        self.payment_status = "paid"
        self.payment_mode = "prepay"
        self.payment_method = "wxpay"
        self.payment_time = "2026-07-16T10:00:00+00:00"
        self.discount_amount = 0
        self.remark = "no spicy"
        self.merchant_note = None
        self.customer_id = 1
        self.coupon_id = None
        self.created_at = datetime(2026, 7, 16, 9, 59, tzinfo=timezone.utc)
        self.dining_session_id = None
        self.participant_id = None
        self.order_type = None
        self.parent_order_id = None
        self.source = "miniprogram"
        self.print_status = "PENDING"
        self.printed_at = None
        self.pickup_no = None


class FakeOrderItem:
    order_id = FakeColumn()

    def __init__(self, name="Beef Soup", qty=1, price=15):
        self.order_id = 10001
        self.dish_id = 1
        self.name = name
        self.qty = qty
        self.price = price


class FakeQuery:
    def __init__(self, model):
        self.model = model

    def where(self, *args):
        return self

    def order_by(self, *args):
        return self


    def with_for_update(self):
        return self

class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeResult:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows if rows is not None else ([] if row is None else [row])

    def scalar_one_or_none(self):
        return self.row

    def scalars(self):
        return FakeScalarResult(self.rows)


class FakeDB:
    def __init__(self, order, config=None, items=None):
        self.order = order
        self.tenant = FakeTenant()
        self.config = config or FakeTenantConfig()
        self.items = items or [FakeOrderItem()]
        self.commit_count = 0
        self.refresh_count = 0

    async def execute(self, query):
        if query.model is FakeTenant:
            return FakeResult(self.tenant)
        if query.model is FakeTenantConfig:
            return FakeResult(self.config)
        if query.model is FakeOrderItem:
            return FakeResult(rows=self.items)
        if query.model is FakeOrder:
            return FakeResult(self.order, [self.order])
        raise AssertionError(f"unexpected query model: {query.model}")

    async def commit(self):
        self.commit_count += 1

    async def flush(self):
        pass

    async def refresh(self, obj):
        self.refresh_count += 1


class KuaimaiPrintError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code
        self.status_code = 502


class KuaimaiStub:
    calls = 0
    outcomes = []
    validate_error = ""

    @classmethod
    def reset(cls):
        cls.calls = 0
        cls.outcomes = []
        cls.validate_error = ""

    @staticmethod
    def build_order_template_render_data(order, order_items, shop_name=""):
        return {
            "shop_name": shop_name,
            "order_no": str(order.id),
            "table_no": order.table_no,
            "total_amount": "15.00",
            "pay_amount": "15.00",
            "pay_type": "微信支付",
            "items": [{"goods_name": order_items[0].name, "quantity": order_items[0].qty, "quantity_text": "×1", "item_amount": "15.00", "item_amount_text": "15.00"}],
        }

    @classmethod
    def validate_order_template_render_data(cls, render_data, order=None):
        if cls.validate_error:
            return False, cls.validate_error
        return True, ""

    @classmethod
    async def print_template_order(cls, *args):
        cls.calls += 1
        outcome = cls.outcomes.pop(0) if cls.outcomes else {"success": True, "provider_task_id": f"task_{cls.calls}"}
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def fake_select(model):
    return FakeQuery(model)


async def _noop_async(*args, **kwargs):
    return None


_ORIGINAL_MODULES = {}


def restore_stubs():
    """Restore stubbed modules after loading the isolated orders module."""
    for name, original in _ORIGINAL_MODULES.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


async def _fake_load_pickup_settings(db, tenant_id):
    return {"enabled": False, "required_before_print": False}


def _fake_should_defer_kitchen_print(order, settings):
    if not settings.get("enabled") or not settings.get("required_before_print"):
        return False
    return not getattr(order, "pickup_no", None)


def install_stubs():
    global _ORIGINAL_MODULES
    modules = {
        "app": types.ModuleType("app"),
        "app.api": types.ModuleType("app.api"),
        "app.api.v1": types.ModuleType("app.api.v1"),
        "app.config": types.ModuleType("app.config"),
        "app.core": types.ModuleType("app.core"),
        "app.core.database": types.ModuleType("app.core.database"),
        "app.core.logger": types.ModuleType("app.core.logger"),
        "app.core.platform_rules": types.ModuleType("app.core.platform_rules"),
        "app.core.response": types.ModuleType("app.core.response"),
        "app.core.tenant_context": types.ModuleType("app.core.tenant_context"),
        "app.models": types.ModuleType("app.models"),
        "app.models.order": types.ModuleType("app.models.order"),
        "app.models.tenant": types.ModuleType("app.models.tenant"),
        "app.models.tenant_config": types.ModuleType("app.models.tenant_config"),
        "app.services": types.ModuleType("app.services"),
        "app.services.coupon_service": types.ModuleType("app.services.coupon_service"),
        "app.services.consumption_service": types.ModuleType("app.services.consumption_service"),
        "app.services.feieyun_service": types.ModuleType("app.services.feieyun_service"),
        "app.services.kuaimai_service": types.ModuleType("app.services.kuaimai_service"),
        "app.services.order_lifecycle_service": types.ModuleType("app.services.order_lifecycle_service"),
        "app.services.order_payment_service": types.ModuleType("app.services.order_payment_service"),
        "app.services.order_stock_service": types.ModuleType("app.services.order_stock_service"),
        "app.services.pickup_no_service": types.ModuleType("app.services.pickup_no_service"),
    }
    _ORIGINAL_MODULES = {name: sys.modules.get(name) for name in modules}
    for name, module in modules.items():
        sys.modules[name] = module

    modules["app.config"].settings = types.SimpleNamespace(DEBUG=False)
    modules["app.core.database"].get_db = lambda: None
    modules["app.core.logger"].logger = types.SimpleNamespace(warning=lambda *a, **k: None, info=lambda *a, **k: None, error=lambda *a, **k: None)
    modules["app.core.platform_rules"].cap_discount_amount = lambda discount, total: discount
    modules["app.core.response"].error_response = lambda code=-1, msg="error", data=None: {"code": code, "msg": msg, "data": data}
    modules["app.core.response"].success_response = lambda data=None, msg="ok": {"code": 200, "msg": msg, "data": data}

    _RespT = TypeVar("_RespT")

    class FakeRespVo(BaseModel, Generic[_RespT]):
        # Mirrors app.core.response.RespVo's shape so FastAPI can build a real
        # response field from `-> ApiResponse` (= RespVo[Any]) return annotations
        # when orders.py is exec'd in isolation here.
        code: int = 200
        msg: str = "ok"
        data: Optional[_RespT] = None

    modules["app.core.response"].RespVo = FakeRespVo
    modules["app.core.tenant_context"].TenantContext = types.SimpleNamespace(set_tenant_id=lambda tenant_id: None)
    modules["app.models.order"].Order = FakeOrder
    modules["app.models.order"].OrderItem = FakeOrderItem
    modules["app.models.tenant"].Tenant = FakeTenant
    modules["app.models.tenant_config"].TenantConfig = FakeTenantConfig
    modules["app.services.coupon_service"].CouponService = type("CouponService", (), {})
    modules["app.services.coupon_service"]._set_order_coupon_status_if_locked = _noop_async
    modules["app.services.coupon_service"]._unlock_order_coupon_if_locked = _noop_async
    modules["app.services.coupon_service"]._mark_order_coupon_used_if_locked = _noop_async
    modules["app.services.consumption_service"]._record_order_consumption = _noop_async
    modules["app.services.order_stock_service"]._restore_order_stock = _noop_async
    modules["app.services.order_lifecycle_service"].OrderLifecycleService = type("OrderLifecycleService", (), {})
    class FakeOrderPaymentService:
        def __init__(self, db):
            self.db = db

        _on_payment_success = _noop_async
        _recover_wxpay_order_if_paid = _noop_async
        mock_pay_order = _noop_async
        create_wxpay_order = _noop_async
        wxpay_notify = _noop_async
        _apply_paid_order_member_assets_once = _noop_async
        _refund_order_payment = _noop_async
        _refund_orphaned_wxpay_payment = _noop_async

    modules["app.services.order_payment_service"].OrderPaymentService = FakeOrderPaymentService
    modules["app.services.feieyun_service"].build_order_ticket = lambda order, order_items: "ticket"
    modules["app.services.feieyun_service"].print_order = lambda *args: True
    modules["app.services.kuaimai_service"].KUAIMAI_ORDER_TEMPLATE_ID = "1634998374"
    modules["app.services.kuaimai_service"].KuaimaiPrintError = KuaimaiPrintError
    modules["app.services.kuaimai_service"].build_order_template_render_data = KuaimaiStub.build_order_template_render_data
    modules["app.services.kuaimai_service"].validate_order_template_render_data = KuaimaiStub.validate_order_template_render_data
    modules["app.services.kuaimai_service"].print_template_order = KuaimaiStub.print_template_order
    modules["app.services.pickup_no_service"].load_pickup_settings = _fake_load_pickup_settings
    modules["app.services.pickup_no_service"].should_defer_kitchen_print = _fake_should_defer_kitchen_print
    modules["app.services.pickup_no_service"].can_assign_pickup_no = lambda *a, **k: False
    modules["app.services.pickup_no_service"].parse_pickup_settings = lambda *a, **k: {
        "enabled": False,
        "required_before_print": False,
    }


def load_orders_module():
    install_stubs()
    print_spec = importlib.util.spec_from_file_location(
        "order_print_service_under_test",
        PRINT_SERVICE_PATH,
    )
    print_module = importlib.util.module_from_spec(print_spec)
    assert print_spec.loader is not None
    _ORIGINAL_MODULES["app.services.order_print_service"] = sys.modules.get("app.services.order_print_service")
    sys.modules["app.services.order_print_service"] = print_module
    print_spec.loader.exec_module(print_module)
    print_module.select = fake_select

    spec = importlib.util.spec_from_file_location("orders_print_recovery_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.select = fake_select
    return module


def load_print_module_only():
    install_stubs()
    print_spec = importlib.util.spec_from_file_location(
        "order_print_service_phase4b_under_test",
        PRINT_SERVICE_PATH,
    )
    print_module = importlib.util.module_from_spec(print_spec)
    assert print_spec.loader is not None
    _ORIGINAL_MODULES["app.services.order_print_service"] = sys.modules.get("app.services.order_print_service")
    sys.modules["app.services.order_print_service"] = print_module
    print_spec.loader.exec_module(print_module)
    print_module.select = fake_select
    return print_module


class PrintFailureRecoveryContractsTest(unittest.TestCase):
    def setUp(self):
        self.addCleanup(restore_stubs)
        KuaimaiStub.reset()
        self.module = load_orders_module()

    def test_offline_failure_keeps_order_paid_and_records_unknown_print_task(self):
        order = FakeOrder()
        db = FakeDB(order)
        KuaimaiStub.outcomes = [KuaimaiPrintError("printer offline", "KUAIMAI_CONNECTION_ERROR")]

        result = asyncio.run(self.module._print_paid_order_ticket(order, db, reason="payment_success"))
        data = self.module.serialize_order(order, db.items)

        self.assertFalse(result["success"])
        self.assertEqual(order.status, "pending")
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(data["print_status"], "unknown")
        self.assertEqual(data["print_attempts"], 1)
        self.assertEqual(data["print_error_code"], "KUAIMAI_CONNECTION_ERROR")
        self.assertFalse(data["print_manual_reprint"])

    def test_timeout_failure_records_unknown_not_failed(self):
        order = FakeOrder()
        db = FakeDB(order)
        KuaimaiStub.outcomes = [KuaimaiPrintError("timeout", "KUAIMAI_TIMEOUT")]

        result = asyncio.run(self.module._print_paid_order_ticket(order, db, reason="payment_success"))
        data = self.module.serialize_order(order, db.items)

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(data["print_status"], "unknown")
        self.assertEqual(data["print_error_code"], "KUAIMAI_TIMEOUT")
        self.assertEqual(data["print_attempts"], 1)
        self.assertNotEqual(data["print_status"], "failed")

    def test_template_error_does_not_send_provider_request(self):
        order = FakeOrder()
        db = FakeDB(order)
        KuaimaiStub.validate_error = "PRINT_ITEMS_PAYLOAD_INVALID"

        result = asyncio.run(self.module._print_paid_order_ticket(order, db, reason="payment_success"))
        data = self.module.serialize_order(order, db.items)

        self.assertFalse(result["success"])
        self.assertEqual(KuaimaiStub.calls, 0)
        self.assertEqual(data["print_status"], "failed")
        self.assertEqual(data["print_error_code"], "PRINT_ITEMS_PAYLOAD_INVALID")

    def test_recovery_retry_prints_once_then_auto_skip_prevents_duplicate(self):
        order = FakeOrder()
        db = FakeDB(order)
        KuaimaiStub.outcomes = [KuaimaiPrintError("rejected", "KUAIMAI_BUSINESS_ERROR")]
        asyncio.run(self.module._print_paid_order_ticket(order, db, reason="payment_success"))
        note, meta = self.module._split_merchant_note_and_print_meta(order.merchant_note)
        old_attempt = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        meta["last_attempt_at"] = old_attempt
        meta["initial_print"]["last_attempt_at"] = old_attempt
        order.merchant_note = self.module._compose_merchant_note_with_print_meta(note, meta)

        KuaimaiStub.outcomes = [{"success": True, "provider_task_id": "task_recovered"}]
        recovered = asyncio.run(self.module._print_paid_order_ticket(order, db, reason="merchant_list_recovery"))
        skipped = asyncio.run(self.module._print_paid_order_ticket(order, db, reason="merchant_list_recovery"))
        data = self.module.serialize_order(order, db.items)

        self.assertTrue(recovered["success"])
        self.assertTrue(skipped["skipped"])
        self.assertEqual(KuaimaiStub.calls, 2)
        self.assertEqual(data["print_status"], "printed")
        self.assertEqual(data["print_attempts"], 2)
        self.assertEqual(data["print_provider_task_id"], "task_recovered")

    def test_success_print_status_skips_provider_request_even_without_meta(self):
        order = FakeOrder()
        order.print_status = "SUCCESS"
        order.printed_at = "2026-07-16T10:01:00+00:00"
        db = FakeDB(order)

        result = asyncio.run(self.module._print_paid_order_ticket(order, db, reason="payment_success"))

        self.assertTrue(result["success"])
        self.assertTrue(result["skipped"])
        self.assertEqual(KuaimaiStub.calls, 0)
        self.assertEqual(result["status"], "printed")

    def test_manual_reprint_is_allowed_and_marked_after_printed(self):
        order = FakeOrder()
        db = FakeDB(order)
        KuaimaiStub.outcomes = [{"success": True, "provider_task_id": "task_first"}]
        asyncio.run(self.module._print_paid_order_ticket(order, db, reason="payment_success"))

        KuaimaiStub.outcomes = [{"success": True, "provider_task_id": "task_manual"}]
        result = asyncio.run(self.module._print_paid_order_ticket(order, db, manual=True, reason="manual_reprint"))
        data = self.module.serialize_order(order, db.items)

        self.assertTrue(result["success"])
        self.assertEqual(KuaimaiStub.calls, 2)
        self.assertEqual(data["print_status"], "printed")
        self.assertEqual(data["print_attempts"], 1)
        self.assertTrue(data["print_manual_reprint"])
        self.assertEqual(data["print_provider_task_id"], "task_first")

    def _feieyun_db(self):
        order = FakeOrder()
        config = FakeTenantConfig()
        config.business_info = {}  # no printer_provider -> falls through to the feieyun branch
        db = FakeDB(order, config=config)
        db.tenant.feieyun_sn = "SN001"
        db.tenant.feieyun_key = "KEY001"
        return order, db

    def test_feieyun_definite_failure_is_marked_failed(self):
        order, db = self._feieyun_db()

        async def fake_print_order(*args, **kwargs):
            return "failed"

        sys.modules["app.services.feieyun_service"].print_order = fake_print_order

        result = asyncio.run(self.module._print_paid_order_ticket(order, db, reason="payment_success"))
        data = self.module.serialize_order(order, db.items)

        self.assertFalse(result["success"])
        self.assertEqual(data["print_status"], "failed")

    def test_feieyun_timeout_result_is_marked_unknown_not_failed(self):
        # P1-3: feieyun's API has no idempotency/external-order-id support (confirmed against
        # its open-platform docs), so a request that times out could have actually printed.
        # Treating that the same as a definite failure would let the merchant-list auto-retry
        # (which only fires on status=="failed") reprint a ticket that already went out.
        order, db = self._feieyun_db()

        async def fake_print_order(*args, **kwargs):
            return "unknown"

        sys.modules["app.services.feieyun_service"].print_order = fake_print_order

        result = asyncio.run(self.module._print_paid_order_ticket(order, db, reason="payment_success"))
        data = self.module.serialize_order(order, db.items)

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(data["print_status"], "unknown")
        self.assertNotEqual(data["print_status"], "failed")  # must not be auto-retry eligible

    def test_manual_reprint_records_operator_and_timestamp(self):
        order, db = self._feieyun_db()

        async def fake_print_order(*args, **kwargs):
            return "success"

        sys.modules["app.services.feieyun_service"].print_order = fake_print_order

        asyncio.run(
            self.module._print_paid_order_ticket(
                order,
                db,
                manual=True,
                reason="manual_reprint",
                operator="42",
                operator_role="kitchen",
            )
        )
        data = self.module.serialize_order(order, db.items)
        _, meta = self.module._split_merchant_note_and_print_meta(order.merchant_note)

        self.assertEqual(data["print_manual_reprint_by"], "42")
        self.assertIsNotNone(data["print_manual_reprint_at"])
        self.assertEqual(meta.get("manual_reprint_role"), "kitchen")

    def test_list_orders_contains_recovery_trigger(self):
        lifecycle_source = LIFECYCLE_SERVICE_PATH.read_text(encoding="utf-8-sig")
        orders_source = MODULE_PATH.read_text(encoding="utf-8-sig")
        self.assertIn("reconcile_print_orders", lifecycle_source)
        self.assertIn('trigger="merchant_list_recovery"', lifecycle_source)
        self.assertIn("reconcile_print_orders", orders_source)
        self.assertIn('@router.post("/orders/{order_id}/reprint")', orders_source)


class PrintPhase4BContractsTest(unittest.TestCase):
    def setUp(self):
        self.addCleanup(restore_stubs)
        KuaimaiStub.reset()
        self.print_mod = load_print_module_only()

    def test_evaluate_eligibility_helpers(self):
        cancelled = FakeOrder()
        cancelled.status = "cancelled"
        self.assertEqual(
            self.print_mod.evaluate_print_eligibility(cancelled)["code"],
            "NOT_PRINTABLE",
        )

        success = FakeOrder()
        success.print_status = "SUCCESS"
        self.assertEqual(
            self.print_mod.evaluate_print_eligibility(success)["code"],
            "ALREADY_SUCCESS",
        )
        self.assertEqual(
            self.print_mod.evaluate_print_eligibility(success, manual=True)["code"],
            "ELIGIBLE",
        )

        waiting = FakeOrder()
        self.assertEqual(
            self.print_mod.evaluate_print_eligibility(waiting, defer_kitchen_print=True)["code"],
            "WAITING_PICKUP_NO",
        )

        unpaid_prepay = FakeOrder()
        unpaid_prepay.payment_status = "unpaid"
        self.assertEqual(
            self.print_mod.evaluate_print_eligibility(unpaid_prepay)["code"],
            "NOT_YET_PAYABLE",
        )

        unpaid_postpay = FakeOrder()
        unpaid_postpay.payment_mode = "postpay"
        unpaid_postpay.payment_status = "unpaid"
        self.assertEqual(
            self.print_mod.evaluate_print_eligibility(unpaid_postpay)["code"],
            "ELIGIBLE",
        )

    def test_note_merge_preserves_merchant_note_text(self):
        order = FakeOrder()
        order.merchant_note = "少辣加葱"
        db = FakeDB(order)
        KuaimaiStub.outcomes = [KuaimaiPrintError("offline", "KUAIMAI_CONNECTION_ERROR")]

        asyncio.run(self.print_mod._print_paid_order_ticket(order, db, reason="payment_success"))
        note, meta = self.print_mod._split_merchant_note_and_print_meta(order.merchant_note)

        self.assertEqual(note, "少辣加葱")
        self.assertEqual(meta.get("status"), "unknown")
        self.assertIn("last_attempt_at", meta)
        self.assertTrue(order.merchant_note.startswith("少辣加葱"))

    def test_reconcile_retries_failed_unpaid_postpay(self):
        order = FakeOrder()
        order.payment_mode = "postpay"
        order.payment_status = "unpaid"
        order.print_status = "FAILED"
        order.merchant_note = (
            "note"
            + self.print_mod.PRINT_META_MARKER
            + json.dumps(
                {
                    "status": "failed",
                    "attempts": 1,
                    "last_attempt_at": (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat(),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        db = FakeDB(order)
        KuaimaiStub.outcomes = [{"success": True, "provider_task_id": "postpay_retry"}]

        attempted = asyncio.run(
            self.print_mod.reconcile_print_orders(db, [order], trigger="merchant_list_recovery")
        )
        self.assertEqual(attempted, 1)
        self.assertEqual(KuaimaiStub.calls, 1)
        self.assertEqual(order.print_status, "SUCCESS")

    def test_reconcile_never_auto_retries_unknown(self):
        order = FakeOrder()
        order.print_status = "UNKNOWN"
        order.merchant_note = (
            "x"
            + self.print_mod.PRINT_META_MARKER
            + json.dumps(
                {
                    "status": "unknown",
                    "attempts": 1,
                    "last_attempt_at": (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat(),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        db = FakeDB(order)

        attempted = asyncio.run(self.print_mod.reconcile_print_orders(db, [order], trigger="reconcile"))
        self.assertEqual(attempted, 0)
        self.assertEqual(KuaimaiStub.calls, 0)

    def test_reconcile_grace_skips_never_attempted(self):
        order = FakeOrder()
        order.created_at = datetime.now(timezone.utc)
        order.payment_time = datetime.now(timezone.utc).isoformat()
        order.print_status = "PENDING"
        db = FakeDB(order)

        attempted = asyncio.run(self.print_mod.reconcile_print_orders(db, [order], trigger="reconcile"))
        self.assertEqual(attempted, 0)
        self.assertEqual(KuaimaiStub.calls, 0)

    def test_reconcile_prints_never_attempted_after_grace(self):
        order = FakeOrder()
        past = datetime.now(timezone.utc) - timedelta(seconds=60)
        order.created_at = past
        order.payment_time = past.isoformat()
        order.print_status = "PENDING"
        db = FakeDB(order)
        KuaimaiStub.outcomes = [{"success": True, "provider_task_id": "grace_print"}]

        attempted = asyncio.run(self.print_mod.reconcile_print_orders(db, [order], trigger="reconcile"))
        self.assertEqual(attempted, 1)
        self.assertEqual(KuaimaiStub.calls, 1)
        self.assertEqual(order.print_status, "SUCCESS")

    def test_build_staff_print_summary_safe_fields_only(self):
        order = FakeOrder()
        order.print_status = "FAILED"
        order.merchant_note = (
            "secret note"
            + self.print_mod.PRINT_META_MARKER
            + json.dumps({"status": "failed", "attempts": 2, "last_error": "boom", "app_secret": "x"})
        )
        summary = self.print_mod.build_staff_print_summary(order)
        self.assertEqual(summary["print_status"], "FAILED")
        self.assertEqual(summary["print_status_label"], "打印失败")
        self.assertEqual(summary["print_issue"], "failed")
        self.assertEqual(summary["print_attempts"], 2)
        self.assertTrue(summary["can_reprint"])
        self.assertNotIn("last_error", summary)
        self.assertNotIn("app_secret", summary)
        self.assertNotIn("merchant_note", summary)

        waiting = self.print_mod.build_staff_print_summary(order, defer_kitchen_print=True)
        # failed takes precedence over waiting
        self.assertEqual(waiting["print_issue"], "failed")

        pending = FakeOrder()
        pending.print_status = "PENDING"
        wait_summary = self.print_mod.build_staff_print_summary(pending, defer_kitchen_print=True)
        self.assertEqual(wait_summary["print_issue"], "waiting_pickup")
        self.assertEqual(wait_summary["print_status_label"], "等待桌牌后打印")

    def test_a50_exactly_fifty_eligible_orders_print_once_each(self):
        modes = ["prepay"] * 15 + ["postpay"] * 15 + ["table_account"] * 20
        successes = 0
        intents = 0
        for index, mode in enumerate(modes, start=1):
            order = FakeOrder()
            order.id = 20000 + index
            order.payment_mode = mode
            order.payment_status = "paid" if mode == "prepay" else "unpaid"
            db = FakeDB(order)
            result = asyncio.run(
                self.print_mod._print_paid_order_ticket(order, db, reason="a50_all_success")
            )
            _, meta = self.print_mod._split_merchant_note_and_print_meta(order.merchant_note)
            intents += int(bool(meta.get("initial_print")))
            successes += int(result.get("success") is True)

        self.assertEqual(len(modes), 50)
        self.assertEqual(intents, 50)
        self.assertEqual(KuaimaiStub.calls, 50)
        self.assertEqual(successes, 50)

    def test_provider_success_result_is_committed_after_sending_claim(self):
        order = FakeOrder()
        db = FakeDB(order)

        result = asyncio.run(
            self.print_mod._print_paid_order_ticket(order, db, reason="durability_contract")
        )

        self.assertTrue(result["success"])
        self.assertGreaterEqual(db.commit_count, 2)
        self.assertEqual(order.print_status, "SUCCESS")

    def test_stale_sending_becomes_unknown_without_provider_call(self):
        order = FakeOrder()
        old_attempt = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        order.print_status = "SENDING"
        order.merchant_note = self.print_mod._compose_merchant_note_with_print_meta(
            None,
            {
                "version": 2,
                "initial_print": {
                    "status": "SENDING",
                    "attempts": 1,
                    "last_attempt_at": old_attempt,
                    "route": {"provider": "kuaimai", "printer_identifier": "KM001"},
                },
            },
        )
        db = FakeDB(order)

        changed = asyncio.run(
            self.print_mod._quarantine_stale_sending(
                db,
                order_id=order.id,
                tenant_id=order.tenant_id,
                allow_provider_call=False,
            )
        )

        self.assertTrue(changed)
        self.assertEqual(order.print_status, "UNKNOWN")
        self.assertEqual(KuaimaiStub.calls, 0)

    def test_manual_failure_preserves_initial_success_fact(self):
        order = FakeOrder()
        db = FakeDB(order)
        KuaimaiStub.outcomes = [{"success": True, "provider_task_id": "initial-task"}]
        asyncio.run(self.print_mod._print_paid_order_ticket(order, db, reason="initial"))
        initial_printed_at = order.printed_at

        KuaimaiStub.outcomes = [KuaimaiPrintError("rejected", "KUAIMAI_BUSINESS_ERROR")]
        result = asyncio.run(
            self.print_mod._print_paid_order_ticket(
                order,
                db,
                manual=True,
                reason="manual_reprint",
                operator="42",
                operator_role="kitchen",
            )
        )
        _, meta = self.print_mod._split_merchant_note_and_print_meta(order.merchant_note)

        self.assertFalse(result["success"])
        self.assertEqual(order.print_status, "SUCCESS")
        self.assertEqual(order.printed_at, initial_printed_at)
        self.assertEqual(meta["initial_print"]["status"], "SUCCESS")
        self.assertEqual(meta["initial_print"]["attempts"], 1)
        self.assertEqual(meta["initial_print"]["provider_task_id"], "initial-task")
        self.assertEqual(meta["manual_reprints"][-1]["status"], "FAILED")

    def test_frozen_route_never_falls_back_to_new_printer(self):
        order = FakeOrder()
        db = FakeDB(order)
        asyncio.run(
            self.print_mod.ensure_initial_print_intent(
                order,
                db,
                eligible=True,
                reason="order_created",
            )
        )
        db.config.business_info["kuaimai_printer"]["sn"] = "KM999"

        result = asyncio.run(
            self.print_mod._print_paid_order_ticket(order, db, reason="route_contract")
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["code"], "PRINT_ROUTE_UNAVAILABLE")
        self.assertEqual(KuaimaiStub.calls, 0)

    def test_option_a_capacity_guard_preserves_note_without_truncation(self):
        note = chr(0x10FFFF) * self.print_mod.MERCHANT_NOTE_MAX_CHARS
        composed = self.print_mod._compose_merchant_note_with_print_meta(
            note,
            {"version": 2, "initial_print": {"status": "PENDING"}},
        )
        parsed_note, _ = self.print_mod._split_merchant_note_and_print_meta(composed)
        self.assertEqual(parsed_note, note)

        with self.assertRaisesRegex(ValueError, "MERCHANT_NOTE_TOO_LONG"):
            self.print_mod._compose_merchant_note_with_print_meta(note + "x", {"version": 2})
        with self.assertRaisesRegex(ValueError, "PRINT_META_CAPACITY_EXCEEDED"):
            self.print_mod._compose_merchant_note_with_print_meta(
                "note",
                {"oversized": chr(0x10FFFF) * 20000},
            )

    def test_route_snapshot_contains_no_credentials(self):
        order = FakeOrder()
        db = FakeDB(order)

        asyncio.run(
            self.print_mod.ensure_initial_print_intent(
                order,
                db,
                eligible=True,
                reason="route_secret_contract",
            )
        )

        self.assertNotIn("secret_1", order.merchant_note)
        self.assertNotIn("app_secret", order.merchant_note)
        _, meta = self.print_mod._split_merchant_note_and_print_meta(order.merchant_note)
        self.assertEqual(meta["initial_print"]["route"]["printer_identifier"], "KM001")

    def test_manual_history_retains_five_and_keeps_cumulative_count(self):
        order = FakeOrder()
        db = FakeDB(order)
        asyncio.run(self.print_mod._print_paid_order_ticket(order, db, reason="initial"))

        for index in range(10):
            asyncio.run(
                self.print_mod._print_paid_order_ticket(
                    order,
                    db,
                    manual=True,
                    reason=f"manual_{index}",
                    operator=str(index),
                    operator_role="kitchen",
                )
            )
        _, meta = self.print_mod._split_merchant_note_and_print_meta(order.merchant_note)

        self.assertEqual(meta["initial_print"]["attempts"], 1)
        self.assertEqual(meta["manual_reprint_count"], 10)
        self.assertEqual(len(meta["manual_reprints"]), 5)


if __name__ == "__main__":
    unittest.main()
