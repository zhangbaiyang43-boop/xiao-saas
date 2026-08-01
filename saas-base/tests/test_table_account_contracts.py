import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
DINING_SERVICE_SOURCE = (ROOT / "app" / "services" / "dining_session_service.py").read_text(encoding="utf-8-sig")
DINING_ROUTER_SOURCE = (ROOT / "app" / "api" / "v1" / "dining_sessions.py").read_text(encoding="utf-8-sig")


def function_source(source: str, name: str) -> str:
    lines = source.splitlines()
    start = next(
        (idx for idx, line in enumerate(lines) if line.strip().startswith(f"async def {name}(") or line.strip().startswith(f"def {name}(")),
        None,
    )
    assert start is not None, f"{name} source not found"
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if not line.strip():
            continue
        line_indent = len(line) - len(line.lstrip())
        if line_indent <= indent and (line.strip().startswith("async def ") or line.strip().startswith("def ") or line.strip().startswith("@")):
            end = idx
            break
    return "\n".join(lines[start:end])


class TableAccountContractsTest(unittest.TestCase):
    def test_serializer_includes_payment_mode_so_frontend_filter_can_match(self):
        serialize_source = function_source(DINING_SERVICE_SOURCE, "_serialize_order")
        self.assertIn('"payment_mode": order.payment_mode', serialize_source)

    def test_session_order_query_does_not_filter_by_payment_status_or_order_status(self):
        list_source = function_source(DINING_SERVICE_SOURCE, "list_session_orders")
        # 桌台账单必须以 tenant_id + dining_session_id 为主条件，不能按 payment_status 过滤，
        # 否则 table_account 用餐期间的 unpaid 子订单会被整桌漏掉。
        self.assertIn("Order.tenant_id == tenant_id", list_source)
        self.assertIn("Order.dining_session_id == dining_session_id", list_source)
        self.assertNotIn('Order.payment_status ==', list_source)
        self.assertNotIn('Order.status ==', list_source)

    def test_table_total_and_item_count_are_computed_backend_side_with_decimal(self):
        list_source = function_source(DINING_SERVICE_SOURCE, "list_session_orders")
        self.assertIn("Decimal(str(order.total or 0))", list_source)
        self.assertIn('order.payment_mode in ("table_account", "postpay")', list_source)
        self.assertIn('order.status not in ("cancelled", "rejected")', list_source)
        self.assertIn('"table_total"', list_source)
        self.assertIn('"item_count"', list_source)

    def test_router_forwards_table_total_and_item_count_to_frontend_contract(self):
        route_source = function_source(DINING_ROUTER_SOURCE, "list_current_dining_orders")
        self.assertIn('"orders": result["orders"]', route_source)
        self.assertIn('"table_total": result["table_total"]', route_source)
        self.assertIn('"item_count": result["item_count"]', route_source)


if __name__ == "__main__":
    unittest.main()
