import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ORDERS_SOURCE = (ROOT / "app" / "api" / "v1" / "orders.py").read_text(encoding="utf-8-sig")
PAYMENT_SERVICE_SOURCE = (
    ROOT / "app" / "services" / "order_payment_service.py"
).read_text(encoding="utf-8-sig")


def function_source(name: str, *, source: str | None = None) -> str:
    text = source if source is not None else ORDERS_SOURCE
    lines = text.splitlines()
    start = next(
        (idx for idx, line in enumerate(lines) if line.startswith(f"async def {name}(")),
        None,
    )
    assert start is not None, f"{name} source not found"
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if line.startswith("@router.") or line.startswith("class ") or line.startswith("async def "):
            end = idx
            break
    return "\n".join(lines[start:end])


class OrderAmountSecurityContractsTest(unittest.TestCase):
    def test_menu_item_price_is_loaded_from_server_with_tenant_scope(self):
        source = function_source("create_order")
        self.assertIn("MenuItem.tenant_id == tenant_id", source)
        self.assertIn("unit_price = float(dish.price)", source)
        self.assertLess(source.index("unit_price = float(dish.price)"), source.index("real_total += unit_price * item_in.qty"))

    def test_invalid_quantity_and_missing_dish_id_are_rejected_before_total_calculation(self):
        source = function_source("create_order")
        self.assertIn("if item_in.qty <= 0", source)
        self.assertIn("商品数量必须大于0", source)
        self.assertIn("缺少菜品ID", source)
        self.assertLess(source.index("if item_in.qty <= 0"), source.index("real_total += unit_price * item_in.qty"))

    def test_invalid_coupon_is_rejected_instead_of_silently_ignored(self):
        source = function_source("create_order")
        self.assertIn("if body.coupon_id:", source)
        self.assertIn("优惠券不可用或已失效", source)
        self.assertIn("优惠券规则不存在", source)
        self.assertIn("未达到优惠券使用门槛", source)
        self.assertIn("if real_total < min_amount", source)
        self.assertLess(source.index("if real_total < min_amount"), source.index("coupon.status = \"LOCKED\""))

    def test_client_total_discount_and_pay_amount_are_not_part_of_order_create_schema(self):
        schema_start = ORDERS_SOURCE.index("class OrderCreate")
        schema_end = ORDERS_SOURCE.index("def serialize_order")
        schema = ORDERS_SOURCE[schema_start:schema_end]
        self.assertIn("total: float", schema)
        self.assertNotIn("discount_amount", schema)
        self.assertNotIn("pay_amount", schema)

    def test_wxpay_amount_uses_server_order_total(self):
        source = function_source("create_wxpay_order", source=PAYMENT_SERVICE_SOURCE)
        self.assertIn("pay_amount = float(order.total)", source)
        self.assertIn("amount_fen = max(1, round(pay_amount * 100))", source)
        self.assertLess(source.index("pay_amount = float(order.total)"), source.index("create_jsapi_order"))


if __name__ == "__main__":
    unittest.main()