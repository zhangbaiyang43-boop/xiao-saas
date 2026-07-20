import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ORDERS_SOURCE = (ROOT / "app" / "api" / "v1" / "orders.py").read_text(encoding="utf-8-sig")


def py_function_source(source: str, name: str) -> str:
    lines = source.splitlines()
    start = next((idx for idx, line in enumerate(lines) if line.startswith(f"async def {name}(")), None)
    assert start is not None, f"{name} source not found"
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if line.startswith("@router.") or line.startswith("async def ") or line.startswith("class "):
            end = idx
            break
    return "\n".join(lines[start:end])


def simulate_search(orders, tenant_id, *, order_no="", order_tail="", table_no="", keyword="", status="", page=1, page_size=20):
    rows = [o for o in orders if o["tenant_id"] == tenant_id]
    if order_no:
        rows = [o for o in rows if str(o["id"]) == str(order_no) if str(order_no).isdigit()]
    if order_tail:
        rows = [o for o in rows if str(o["id"]).endswith(str(order_tail))]
    if table_no:
        rows = [o for o in rows if o["table_no"] == table_no]
    if status:
        rows = [o for o in rows if o["status"] == status]
    if keyword:
        kw = str(keyword)
        rows = [
            o for o in rows
            if o["table_no"] == kw
            or kw in o["table_no"]
            or str(o["id"]).endswith(kw)
            or (kw.isdigit() and str(o["id"]) == kw)
        ]
    total = len(rows)
    start = (page - 1) * page_size
    return rows[start:start + page_size], total


class MerchantOrderLookupContractsTest(unittest.TestCase):
    def test_backend_accepts_order_lookup_parameters(self):
        source = py_function_source(ORDERS_SOURCE, "list_orders")
        for param in ["keyword", "order_no", "order_tail", "tail_no", "table_no", "status", "page", "page_size"]:
            self.assertIn(f"{param}: Optional", source)
        self.assertIn("Order.tenant_id == tenant_id", source)
        self.assertIn("cast(Order.id, String)", source)
        self.assertIn("Order.table_no == normalized_table", source)
        self.assertIn("Order.status == normalized_status", source)
        self.assertIn("select(func.count()).select_from", source)
        self.assertIn('"items": rows', source)
        self.assertIn('"total": total or 0', source)

    def test_full_order_no_tail_table_pagination_and_tenant_isolation_with_ten_orders(self):
        orders = [
            {"id": 202607160001, "tenant_id": "tenant_a", "table_no": "A01", "status": "pending"},
            {"id": 202607160002, "tenant_id": "tenant_a", "table_no": "A02", "status": "preparing"},
            {"id": 202607160102, "tenant_id": "tenant_a", "table_no": "A02", "status": "done"},
            {"id": 202607160202, "tenant_id": "tenant_a", "table_no": "B01", "status": "pending"},
            {"id": 202607161202, "tenant_id": "tenant_a", "table_no": "B02", "status": "pending"},
            {"id": 202607162202, "tenant_id": "tenant_a", "table_no": "C01", "status": "settled"},
            {"id": 202607163202, "tenant_id": "tenant_a", "table_no": "C02", "status": "cancelled"},
            {"id": 202607160001, "tenant_id": "tenant_b", "table_no": "A01", "status": "pending"},
            {"id": 202607160202, "tenant_id": "tenant_b", "table_no": "B01", "status": "pending"},
            {"id": 202607169999, "tenant_id": "tenant_b", "table_no": "Z09", "status": "done"},
        ]

        full, total = simulate_search(orders, "tenant_a", order_no="202607160001")
        self.assertEqual(total, 1)
        self.assertEqual(full[0]["tenant_id"], "tenant_a")
        self.assertEqual(full[0]["id"], 202607160001)

        tail, total = simulate_search(orders, "tenant_a", order_tail="202")
        self.assertEqual(total, 4)
        self.assertEqual({o["id"] for o in tail}, {202607160202, 202607161202, 202607162202, 202607163202})
        self.assertTrue(all(o["tenant_id"] == "tenant_a" for o in tail))

        table, total = simulate_search(orders, "tenant_a", table_no="A02")
        self.assertEqual(total, 2)
        self.assertEqual({o["status"] for o in table}, {"preparing", "done"})

        page_rows, total = simulate_search(orders, "tenant_a", page=2, page_size=3)
        self.assertEqual(total, 7)
        self.assertEqual(len(page_rows), 3)
        self.assertTrue(all(o["tenant_id"] == "tenant_a" for o in page_rows))

    def test_status_text_is_exposed_for_merchant_display(self):
        self.assertIn("ORDER_STATUS_TEXT", ORDERS_SOURCE)
        self.assertIn('"status_text": ORDER_STATUS_TEXT.get(order.status, order.status)', ORDERS_SOURCE)
        for text in ["待支付", "等待接单", "制作中", "已上餐", "已完成", "已取消"]:
            self.assertIn(text, ORDERS_SOURCE)

    def test_default_order_list_response_remains_backward_compatible(self):
        source = py_function_source(ORDERS_SOURCE, "list_orders")
        self.assertIn("if wants_pagination:", source)
        self.assertRegex(source, re.compile(r"return success_response\(data=rows\)"))


if __name__ == "__main__":
    unittest.main()
