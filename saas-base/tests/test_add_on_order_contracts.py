import importlib.util
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ORDER_SOURCE = (ROOT / "app" / "api" / "v1" / "orders.py").read_text(encoding="utf-8-sig")
KUAIMAI_PATH = ROOT / "app" / "services" / "kuaimai_service.py"
SPEC = importlib.util.spec_from_file_location("kuaimai_add_on_under_test", KUAIMAI_PATH)
kuaimai_service = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(kuaimai_service)


class FakeOrder:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id")
        self.tenant_id = kwargs.get("tenant_id", "tenant_1")
        self.customer_id = kwargs.get("customer_id", 1)
        self.dining_session_id = kwargs.get("dining_session_id", 9001)
        self.participant_id = kwargs.get("participant_id", 7001)
        self.order_type = kwargs.get("order_type")
        self.parent_order_id = kwargs.get("parent_order_id")
        self.table_no = kwargs.get("table_no", "A01")
        self.phone = kwargs.get("phone", "15900000000")
        self.total = kwargs.get("total", 15)
        self.status = kwargs.get("status", "pending")
        self.payment_status = kwargs.get("payment_status", "paid")
        self.payment_method = kwargs.get("payment_method", "wxpay")
        self.payment_time = kwargs.get("payment_time", "2026-07-16T10:00:00+00:00")
        self.remark = kwargs.get("remark", "")
        self.merchant_note = kwargs.get("merchant_note")
        self.coupon_id = kwargs.get("coupon_id")
        self.discount_amount = kwargs.get("discount_amount", 0)
        self.served_at = None
        self.completed_at = None
        self.source = "miniprogram"
        self.created_at = None


class FakeItem:
    def __init__(self, name, qty, price):
        self.dish_id = 1
        self.order_id = None
        self.name = name
        self.qty = qty
        self.price = price


class AddOnOrderContractsTest(unittest.TestCase):
    def test_model_already_has_add_on_fields_no_migration_required(self):
        model_source = (ROOT / "app" / "models" / "order.py").read_text(encoding="utf-8-sig")
        self.assertIn("dining_session_id", model_source)
        self.assertIn("participant_id", model_source)
        self.assertIn("order_type", model_source)
        self.assertIn("parent_order_id", model_source)

    def test_create_order_marks_second_paid_session_order_as_add_on(self):
        self.assertIn('order_type = "ADD_ON" if parent_order else "INITIAL"', ORDER_SOURCE)
        self.assertIn('parent_order_id = parent_order.id if parent_order else None', ORDER_SOURCE)
        self.assertIn('Order.dining_session_id == session.id', ORDER_SOURCE)
        self.assertIn('Order.payment_status == "paid"', ORDER_SOURCE)
        self.assertIn('participant_id=dining_participant_id', ORDER_SOURCE)

    def test_first_and_add_on_orders_are_separate_and_parent_amount_unchanged(self):
        first = FakeOrder(id=10001, order_type="INITIAL", parent_order_id=None, total=15)
        first_items = [FakeItem("牛肉汤", 1, 15)]
        original_total = first.total
        original_items = [(i.name, i.qty, i.price) for i in first_items]

        add_on = FakeOrder(id=10002, order_type="ADD_ON", parent_order_id=first.id, total=6)
        add_on_items = [FakeItem("米饭", 2, 3)]

        self.assertNotEqual(str(first.id), str(add_on.id))
        self.assertEqual(first.dining_session_id, add_on.dining_session_id)
        self.assertEqual(first.participant_id, add_on.participant_id)
        self.assertEqual(add_on.order_type, "ADD_ON")
        self.assertEqual(add_on.parent_order_id, first.id)
        self.assertEqual(first.total, original_total)
        self.assertEqual([(i.name, i.qty, i.price) for i in first_items], original_items)
        self.assertEqual(add_on.total, 6)
        self.assertEqual([(i.name, i.qty) for i in add_on_items], [("米饭", 2)])

    def test_merchant_serialization_exposes_add_on_label(self):
        spec = importlib.util.spec_from_file_location("orders_source_text", ROOT / "app" / "api" / "v1" / "orders.py")
        self.assertIn("ORDER_TYPE_TEXT", ORDER_SOURCE)
        self.assertIn('"ADD_ON": "加菜单"', ORDER_SOURCE)
        self.assertIn('"order_type_text": ORDER_TYPE_TEXT.get', ORDER_SOURCE)

    def test_kuaimai_payload_marks_add_on_ticket_and_keeps_items_separate(self):
        add_on = FakeOrder(id=10002, order_type="ADD_ON", parent_order_id=10001, total=6)
        add_on_items = [FakeItem("米饭", 2, 3)]

        render_data = kuaimai_service.build_order_template_render_data(add_on, add_on_items, shop_name="味来餐厅")
        payload = kuaimai_service.build_template_print_payload(
            app_id="123456",
            app_secret="abc",
            sn="KM110h45932",
            template_id="1634998374",
            render_data=render_data,
            timestamp="2020-10-10 15:29:29",
        )
        final_render_data = json.loads(payload["renderData"])

        self.assertEqual(final_render_data["order_no"], "10002")
        self.assertEqual(final_render_data["parent_order_id"], "10001")
        self.assertEqual(final_render_data["order_type"], "ADD_ON")
        self.assertEqual(final_render_data["order_type_text"], "加菜单")
        self.assertEqual(len(final_render_data["items"]), 1)
        self.assertEqual(final_render_data["items"][0]["goods_name"], "米饭")
        self.assertEqual(final_render_data["items"][0]["quantity_text"], "×2")
        self.assertEqual(final_render_data["items"][0]["item_amount_text"], "6.00")
        self.assertEqual(final_render_data["点餐订单"][0]["order_type_text"], "加菜单")


if __name__ == "__main__":
    unittest.main()
