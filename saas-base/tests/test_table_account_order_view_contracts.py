import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
MENU_SOURCE = (
    ROOT / "member-mini-client" / "src" / "subpkg-order" / "pages" / "menu.vue"
).read_text(encoding="utf-8-sig")
TABLE_BILL_VIEW_SOURCE = (
    ROOT / "member-mini-client" / "src" / "subpkg-order" / "composables" / "useTableBillView.js"
).read_text(encoding="utf-8-sig")
TABLE_CHECKOUT_SOURCE = (
    ROOT / "member-mini-client" / "src" / "subpkg-order" / "composables" / "useTableCheckout.js"
).read_text(encoding="utf-8-sig")
TABLE_BILL_SHEET_SOURCE = (
    ROOT / "member-mini-client" / "src" / "subpkg-order" / "components" / "TableBillSheet.vue"
).read_text(encoding="utf-8-sig")


class TableAccountOrderViewContractsTest(unittest.TestCase):
    def test_table_account_uses_dedicated_b_version_branch(self):
        # 餐后付款结账时走的也是 settle_table 整桌一次结清（跟桌台账单同一套后端机制），
        # 所以这个聚合账单视图现在由 isSharedBillMode（table_account 或 postpay）共用，
        # 不再是 isTableAccountMode 单独把着这个分支。
        self.assertIn("import { useTableBillView } from '../composables/useTableBillView.js'", MENU_SOURCE)
        self.assertIn("import TableBillSheet from '../components/TableBillSheet.vue'", MENU_SOURCE)
        self.assertIn("} = useTableBillView({", MENU_SOURCE)
        self.assertIn('v-if="showOrders && isSharedBillMode"', MENU_SOURCE)
        self.assertIn('paymentMode.value === "table_account"', TABLE_BILL_VIEW_SOURCE)
        self.assertIn('paymentMode.value === "postpay"', TABLE_BILL_VIEW_SOURCE)
        self.assertIn("isSharedBillMode = computed(() => isTableAccountMode.value || isPostpayMode.value)", TABLE_BILL_VIEW_SOURCE)
        self.assertIn("table-account-sheet", TABLE_BILL_SHEET_SOURCE)
        self.assertIn("已点菜品", TABLE_BILL_SHEET_SOURCE)
        self.assertIn("本桌已点菜品", TABLE_BILL_SHEET_SOURCE)

    def test_table_account_aggregates_by_session_not_table_number_only(self):
        self.assertIn("tableOrderGroups", MENU_SOURCE)
        self.assertIn("const isSameDiningSessionOrder", TABLE_BILL_VIEW_SOURCE)
        self.assertIn("orderSessionId === tableSessionId.value", TABLE_BILL_VIEW_SOURCE)
        self.assertIn(".filter(isSameDiningSessionOrder)", TABLE_BILL_VIEW_SOURCE)
        self.assertNotIn("tableNo.value && order.table === tableNo.value", TABLE_BILL_VIEW_SOURCE)

    def test_postpay_shares_the_bill_view_but_has_no_clickable_checkout_button(self):
        # 结账动作在商家手里（收银台/后台"结账"按钮），餐后付款这边只提示、不提供可点的
        # "去结账"——canCheckout 必须继续只认 isTableAccountMode，不能因为共用了聚合视图
        # 就顺带让餐后付款也能自助点"去结账"。
        self.assertIn(
            'isTableAccountMode.value && tableItemCount.value > 0 && !isTableSettled.value && !tableCheckouting.value && allOrdersDone.value',
            TABLE_BILL_VIEW_SOURCE,
        )
        self.assertIn("postpayReadyToSettle", TABLE_BILL_VIEW_SOURCE)
        self.assertIn("用餐结束请到收银台或联系服务员结账", TABLE_BILL_SHEET_SOURCE)
        self.assertIn('v-else-if="postpayReadyToSettle"', TABLE_BILL_SHEET_SOURCE)
        self.assertIn('v-if="canCheckout"', TABLE_BILL_SHEET_SOURCE)

    def test_table_account_actions_do_not_use_normal_wxpay_flow(self):
        self.assertIn("import { useTableCheckout } from '../composables/useTableCheckout.js'", MENU_SOURCE)
        self.assertIn("} = useTableCheckout({", MENU_SOURCE)
        self.assertIn("const handleTableCheckout", TABLE_CHECKOUT_SOURCE)
        self.assertIn("await performTableCheckout()", TABLE_CHECKOUT_SOURCE)
        self.assertNotIn("confirmPay(", TABLE_CHECKOUT_SOURCE)
        self.assertNotIn("createWxPayOrder", TABLE_CHECKOUT_SOURCE)
        self.assertNotIn("uni.requestPayment", TABLE_CHECKOUT_SOURCE)


if __name__ == "__main__":
    unittest.main()
