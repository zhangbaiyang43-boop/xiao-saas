import asyncio
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.statistics_service import StatisticsService, TABLE_NEW_CUSTOMER_ALERT_THRESHOLD


class FakeResult:
    """跟 test_coupon_loop_contracts.py 里的 FakeSession 同一个思路：只假出
    db.execute(...).all() 这一步需要的返回值，不用连真数据库。"""

    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, results):
        # table_coupon_activity 依次跑三条查询：今日已支付订单 -> 这些客户各自的首单时间
        # -> 这些 dining_session 对应的桌号。按调用顺序把结果一个个吐出去。
        self._results = list(results)

    async def execute(self, *_args, **_kwargs):
        return self._results.pop(0)


class TableCouponActivityContractsTest(unittest.TestCase):
    def _run(self, today_orders, first_paid_rows, table_no_rows):
        service = StatisticsService(FakeSession([
            FakeResult(today_orders),
            FakeResult(first_paid_rows),
            FakeResult(table_no_rows),
        ]))
        service.set_tenant_id("tenant-001")
        return asyncio.run(service.table_coupon_activity(datetime(2026, 7, 29)))

    def test_table_with_many_same_day_first_orders_gets_flagged(self):
        # 桌 A12：4 个客户，每个人的"首单"都恰好是今天这一条 —— 应该被标记
        today_orders = [
            SimpleNamespace(dining_session_id=100, customer_id=1, created_at=datetime(2026, 7, 29, 9, 0)),
            SimpleNamespace(dining_session_id=100, customer_id=2, created_at=datetime(2026, 7, 29, 9, 1)),
            SimpleNamespace(dining_session_id=100, customer_id=3, created_at=datetime(2026, 7, 29, 9, 2)),
            SimpleNamespace(dining_session_id=100, customer_id=4, created_at=datetime(2026, 7, 29, 9, 3)),
        ]
        first_paid_rows = [
            (1, datetime(2026, 7, 29, 9, 0)),
            (2, datetime(2026, 7, 29, 9, 1)),
            (3, datetime(2026, 7, 29, 9, 2)),
            (4, datetime(2026, 7, 29, 9, 3)),
        ]
        table_no_rows = [(100, "A12")]

        result = self._run(today_orders, first_paid_rows, table_no_rows)

        self.assertEqual(result["threshold"], TABLE_NEW_CUSTOMER_ALERT_THRESHOLD)
        self.assertEqual(len(result["tables"]), 1)
        table = result["tables"][0]
        self.assertEqual(table["table_no"], "A12")
        self.assertEqual(table["new_customer_count"], 4)
        self.assertEqual(table["customer_count"], 4)
        self.assertTrue(table["flagged"])

    def test_returning_customer_reordering_today_is_not_counted_as_new(self):
        # 桌 B03：客户 5 是老客（首单是昨天），今天只是回来又点了一单，
        # 不该被算进"今天这一桌的新客数"里，哪怕他今天确实也下单支付了。
        today_orders = [
            SimpleNamespace(dining_session_id=200, customer_id=5, created_at=datetime(2026, 7, 29, 12, 0)),
            SimpleNamespace(dining_session_id=200, customer_id=6, created_at=datetime(2026, 7, 29, 12, 1)),
        ]
        first_paid_rows = [
            (5, datetime(2026, 7, 20, 18, 0)),  # 首单是很多天前，今天只是老客回购
            (6, datetime(2026, 7, 29, 12, 1)),  # 首单就是今天
        ]
        table_no_rows = [(200, "B03")]

        result = self._run(today_orders, first_paid_rows, table_no_rows)

        table = result["tables"][0]
        self.assertEqual(table["order_count"], 2)
        self.assertEqual(table["customer_count"], 2)
        self.assertEqual(table["new_customer_count"], 1)
        self.assertFalse(table["flagged"])

    def test_no_orders_today_returns_empty_table_list(self):
        result = self._run([], [], [])
        self.assertEqual(result["tables"], [])
        self.assertEqual(result["threshold"], TABLE_NEW_CUSTOMER_ALERT_THRESHOLD)

    def test_tables_sorted_by_new_customer_count_descending(self):
        today_orders = [
            SimpleNamespace(dining_session_id=100, customer_id=1, created_at=datetime(2026, 7, 29, 9, 0)),
            SimpleNamespace(dining_session_id=200, customer_id=2, created_at=datetime(2026, 7, 29, 9, 0)),
            SimpleNamespace(dining_session_id=200, customer_id=3, created_at=datetime(2026, 7, 29, 9, 1)),
        ]
        first_paid_rows = [
            (1, datetime(2026, 7, 29, 9, 0)),
            (2, datetime(2026, 7, 29, 9, 0)),
            (3, datetime(2026, 7, 29, 9, 1)),
        ]
        table_no_rows = [(100, "A01"), (200, "A02")]

        result = self._run(today_orders, first_paid_rows, table_no_rows)

        self.assertEqual([t["table_no"] for t in result["tables"]], ["A02", "A01"])


if __name__ == "__main__":
    unittest.main()
