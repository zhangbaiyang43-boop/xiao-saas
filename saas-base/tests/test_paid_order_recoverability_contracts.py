import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ORDERS_SOURCE = (ROOT / "app" / "api" / "v1" / "orders.py").read_text(encoding="utf-8-sig")
PAYMENT_SERVICE_SOURCE = (
    ROOT / "app" / "services" / "order_payment_service.py"
).read_text(encoding="utf-8-sig")
LIFECYCLE_SERVICE_SOURCE = (
    ROOT / "app" / "services" / "order_lifecycle_service.py"
).read_text(encoding="utf-8-sig")
WXPAY_SOURCE = (ROOT / "app" / "services" / "wxpay_service.py").read_text(encoding="utf-8-sig")


def function_source(name: str, *, source: str | None = None) -> str:
    text = source if source is not None else ORDERS_SOURCE
    lines = text.splitlines()
    start = next(
        (
            idx
            for idx, line in enumerate(lines)
            if line.startswith(f"async def {name}(") or line.startswith(f"    async def {name}(")
        ),
        None,
    )
    assert start is not None, f"{name} source not found"
    is_class_method = lines[start].startswith("    async def")
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if is_class_method:
            if line.startswith("    async def ") or line.startswith("    def "):
                end = idx
                break
        elif line.startswith("@router.") or line.startswith("class ") or line.startswith("async def "):
            end = idx
            break
    return "\n".join(lines[start:end])


def class_method_source(name: str) -> str:
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


class PaidOrderRecoverabilityContractsTest(unittest.TestCase):
    def test_order_is_created_before_payment_request(self):
        create_order_source = function_source("_persist_create_order_and_build_response")
        create_pay_source = function_source("create_wxpay_order", source=PAYMENT_SERVICE_SOURCE)
        resolve_source = function_source("_resolve_create_order_payment_mode")
        self.assertIn('payment_mode = payment_mode if payment_mode in ("prepay", "postpay", "table_account") else "prepay"', resolve_source)
        self.assertIn('status="pending" if payment_mode in ("postpay", "table_account") else "pending_payment"', create_order_source)
        self.assertIn('payment_status="unpaid"', create_order_source)
        self.assertIn('"need_payment": payment_mode == "prepay"', create_order_source)
        self.assertIn('"next_action": build_order_next_action(payment_mode)', create_order_source)
        self.assertIn('getattr(order, "payment_mode", "prepay") != "prepay"', create_pay_source)
        self.assertIn('"PAYMENT_NOT_REQUIRED"', create_pay_source)
        self.assertIn("out_trade_no=str(order.id)", create_pay_source)

    def test_wxpay_service_can_query_order_for_callback_loss_recovery(self):
        self.assertIn("async def query_order_by_out_trade_no", WXPAY_SOURCE)
        self.assertIn("trade_state", PAYMENT_SERVICE_SOURCE)
        self.assertIn("WXPAY_ORDER_RECOVERED", PAYMENT_SERVICE_SOURCE)

    def test_consumer_order_query_recovers_paid_pending_payment_order(self):
        get_my_order_source = class_method_source("get_my_order")
        self.assertIn("payment_svc._recover_wxpay_order_if_paid(order, source=", get_my_order_source)
        self.assertIn('"payment_status": order.payment_status', get_my_order_source)

    def test_merchant_order_query_recovers_paid_pending_payment_orders(self):
        list_orders_source = class_method_source("list_orders")
        self.assertIn('if order.status == "pending_payment"', list_orders_source)
        self.assertIn("payment_svc._recover_wxpay_order_if_paid(order, source=", list_orders_source)
        self.assertIn("await self.db.commit()", list_orders_source)

    def test_recovery_reuses_normal_payment_success_side_effect_path(self):
        recover_source = function_source("_recover_wxpay_order_if_paid", source=PAYMENT_SERVICE_SOURCE)
        self.assertIn("query_order_by_out_trade_no", recover_source)
        self.assertIn("_apply_confirmed_wx_payment", recover_source)
        self.assertIn("with_for_update()", recover_source)
        apply_source = function_source("_apply_confirmed_wx_payment", source=PAYMENT_SERVICE_SOURCE)
        self.assertIn("_validate_confirmed_wx_payment", apply_source)
        self.assertIn("_on_payment_success", apply_source)


if __name__ == "__main__":
    unittest.main()
