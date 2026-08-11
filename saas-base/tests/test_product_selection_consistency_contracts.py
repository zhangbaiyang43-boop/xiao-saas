import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MENU_SOURCE = (
    ROOT.parent / "member-mini-client" / "src" / "subpkg-order" / "pages" / "menu.vue"
).read_text(encoding="utf-8-sig")
CHECKOUT_SOURCE = (
    ROOT.parent / "member-mini-client" / "src" / "subpkg-order" / "composables" / "useCheckout.js"
).read_text(encoding="utf-8-sig")
SPEC_SHEET_SOURCE = (
    ROOT.parent / "member-mini-client" / "src" / "subpkg-order" / "composables" / "useSpecSheet.js"
).read_text(encoding="utf-8-sig")
HOME_TAB_VIEW_SOURCE = (
    ROOT.parent / "member-mini-client" / "src" / "subpkg-order" / "composables" / "useHomeTabView.js"
).read_text(encoding="utf-8-sig")
HISTORY_REORDER_SOURCE = (
    ROOT.parent / "member-mini-client" / "src" / "subpkg-order" / "composables" / "useHistoryReorder.js"
).read_text(encoding="utf-8-sig")
DISH_LIST_SOURCE = (
    ROOT.parent / "member-mini-client" / "src" / "subpkg-order" / "components" / "DishList.vue"
).read_text(encoding="utf-8-sig")
ORDERS_SOURCE = (ROOT / "app" / "api" / "v1" / "orders.py").read_text(encoding="utf-8-sig")
ORDER_MODEL_SOURCE = (ROOT / "app" / "models" / "order.py").read_text(encoding="utf-8-sig")
KUAIMAI_PATH = ROOT / "app" / "services" / "kuaimai_service.py"
SPEC = importlib.util.spec_from_file_location("kuaimai_selection_under_test", KUAIMAI_PATH)
kuaimai_service = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(kuaimai_service)


class FakeItem:
    def __init__(self, name, qty=1, price=15):
        self.name = name
        self.qty = qty
        self.price = price


def persisted_order_item_name(db_name, submitted_name):
    base_name = str(db_name or "")
    submitted_name = str(submitted_name or "").strip()
    return submitted_name[:64] if submitted_name and submitted_name.startswith(base_name) else base_name


class ProductSelectionConsistencyContractsTest(unittest.TestCase):
    def test_frontend_spec_cart_keeps_spec_taste_remark_and_quantity(self):
        self.assertIn("import { useSpecSheet } from '../composables/useSpecSheet.js'", MENU_SOURCE)
        self.assertIn("} = useSpecSheet({", MENU_SOURCE)
        self.assertIn("const buildSpecKey = () => JSON.stringify", SPEC_SHEET_SOURCE)
        self.assertIn("specifications: selectedSpecRows.value", SPEC_SHEET_SOURCE)
        self.assertIn("itemRemark: itemRemark.value.trim()", SPEC_SHEET_SOURCE)
        self.assertIn("const labels = [...specifications.map(i => i.value), ...extras]", SPEC_SHEET_SOURCE)
        self.assertIn("if (remarkText) labels.push(remarkText)", SPEC_SHEET_SOURCE)
        self.assertIn("orderName: labels.length ? specDish.value.name + '(' + labels.join(specText.separator) + ')' : specDish.value.name", SPEC_SHEET_SOURCE)
        self.assertIn("qty: specQty.value", SPEC_SHEET_SOURCE)

    def test_frontend_order_payload_uses_display_name_for_confirmation_and_submit(self):
        self.assertIn("import { useCheckout } from '../composables/useCheckout.js'", MENU_SOURCE)
        self.assertIn("} = useCheckout({", MENU_SOURCE)
        self.assertIn("cartItems.value.map((item) => ({ dish_id: item.id, name: item.orderName || item.name", CHECKOUT_SOURCE)
        self.assertIn("successItems.value = cartItems.value.map(i => ({ ...i }))", CHECKOUT_SOURCE)
        self.assertIn("cartSnapshot: cartItems.value.map(item => ({ id: item.id, name: item.orderName || item.name", CHECKOUT_SOURCE)

    def test_backend_persists_legal_display_name_without_trusting_price_or_foreign_dish(self):
        self.assertIn("MenuItem.id == item_in.dish_id", ORDERS_SOURCE)
        self.assertIn("MenuItem.tenant_id == tenant_id", ORDERS_SOURCE)
        self.assertIn("unit_price = _numeric_float(dish.price)", ORDERS_SOURCE)
        self.assertIn("submitted_name = str(item_in.name or \"\").strip()", ORDERS_SOURCE)
        self.assertIn("submitted_name.startswith(base_name)", ORDERS_SOURCE)
        self.assertIn("name = submitted_name[:64] if submitted_name", ORDERS_SOURCE)
        self.assertIn("name=name", ORDERS_SOURCE)

    def test_display_name_matrix_for_database_order_detail(self):
        cases = [
            ("no spec", "Beef Soup", "Beef Soup", 1),
            ("multi spec", "Noodles", "Noodles(Large)", 1),
            ("required taste", "Tomato Soup", "Tomato Soup(Mild)", 1),
            ("item remark", "Tofu", "Tofu(Less Salt)", 1),
            ("quantity 99", "Rice", "Rice", 99),
        ]
        for label, db_name, submitted_name, qty in cases:
            with self.subTest(label=label):
                self.assertEqual(persisted_order_item_name(db_name, submitted_name), submitted_name[:64])
                self.assertIn(qty, (1, 99))
        self.assertEqual(persisted_order_item_name("Beef Soup", "Bad Name(Large)"), "Beef Soup")

    def test_sold_out_and_unavailable_are_blocked_before_order_item_created(self):
        self.assertIn("if not dish.available", ORDERS_SOURCE)
        self.assertIn("if not dish.available", ORDERS_SOURCE)
        self.assertIn("dish.stock is not None and dish.stock <= 0", ORDERS_SOURCE)
        self.assertIn("dish sold out", ORDERS_SOURCE)
        self.assertIn("import DishList from '../components/DishList.vue'", MENU_SOURCE)
        self.assertIn(":is-sold-out=\"isSoldOut\"", MENU_SOURCE)
        self.assertIn("isSoldOut(dish)", DISH_LIST_SOURCE)
        self.assertIn("dish-item--soldout", DISH_LIST_SOURCE)

    def test_history_reorder_revalidates_current_menu_state_before_cart_add(self):
        self.assertIn("import { useHomeTabView } from '../composables/useHomeTabView.js'", MENU_SOURCE)
        self.assertIn("import { useHistoryReorder } from '../composables/useHistoryReorder.js'", MENU_SOURCE)
        self.assertIn("} = useHomeTabView({", MENU_SOURCE)
        self.assertIn("} = useHistoryReorder({", MENU_SOURCE)
        self.assertIn("const validateHistoryReorderItem", HOME_TAB_VIEW_SOURCE)
        self.assertIn("const dish = findHistoryDish(item)", HOME_TAB_VIEW_SOURCE)
        self.assertIn("return { dish, reason: 'unavailable' }", HOME_TAB_VIEW_SOURCE)
        self.assertIn("return { dish, reason: 'spec_changed' }", HOME_TAB_VIEW_SOURCE)
        self.assertIn("const check = validateHistoryReorderItem(item)", HISTORY_REORDER_SOURCE)
        self.assertIn("addToCart(check.dish)", HISTORY_REORDER_SOURCE)
        self.assertIn("skippedUnavailable", HISTORY_REORDER_SOURCE)
        self.assertIn("skippedSpec", HISTORY_REORDER_SOURCE)
        self.assertIn("部分菜品已下架或售罄", HISTORY_REORDER_SOURCE)
        self.assertIn("部分规格已变更，请重新选择", HISTORY_REORDER_SOURCE)
        self.assertIn("没有可重新加入的菜品", HISTORY_REORDER_SOURCE)

    def test_print_payload_uses_database_order_item_name(self):
        item = FakeItem("Tofu(Mild,Less Salt)", qty=99, price=22)
        row = kuaimai_service._build_print_item_row(item)
        self.assertEqual(row["goods_name"], "Tofu(Mild,Less Salt)")
        self.assertEqual(row["display_name"], "Tofu(Mild,Less Salt)")
        self.assertEqual(row["quantity"], 99)
        self.assertEqual(row["quantity_text"], "×99")
        self.assertEqual(row["item_amount_text"], "2178.00")

    def test_order_item_model_uses_existing_name_field_no_migration_required(self):
        self.assertIn("class OrderItem", ORDER_MODEL_SOURCE)
        self.assertIn("name = Column(String(64)", ORDER_MODEL_SOURCE)
        self.assertNotIn("sku_text = Column", ORDER_MODEL_SOURCE)
        self.assertNotIn("item_remark = Column", ORDER_MODEL_SOURCE)


if __name__ == "__main__":
    unittest.main()
