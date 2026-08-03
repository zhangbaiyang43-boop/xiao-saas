import unittest
from types import SimpleNamespace

from app.services.feieyun_service import build_order_ticket


class FeieyunTicketIncludesItemsTest(unittest.TestCase):
    """build_order_ticket used to read order.items, which the Order model has never had
    (no relationship/column by that name) -- every feieyun-printed ticket silently came out
    with zero item lines, no matter what was actually ordered. Regression coverage for the
    fix: the ticket must be built from the OrderItem rows passed in explicitly."""

    def _order(self, **overrides):
        defaults = dict(id=123456789, table_no="A7", source="miniprogram", remark="", total=45.5)
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def _item(self, name, qty, price):
        return SimpleNamespace(name=name, qty=qty, price=price)

    def test_ticket_lists_every_order_item_with_name_qty_and_price(self):
        order = self._order()
        items = [
            self._item("宫保鸡丁", 2, 28.0),
            self._item("米饭", 3, 3.0),
        ]

        ticket = build_order_ticket(order, items)

        self.assertIn("宫保鸡丁", ticket)
        self.assertIn("x2", ticket)
        self.assertIn("¥28.0", ticket)
        self.assertIn("米饭", ticket)
        self.assertIn("x3", ticket)
        self.assertIn("¥3.0", ticket)

    def test_empty_item_list_produces_no_item_lines_but_does_not_crash(self):
        order = self._order()
        ticket = build_order_ticket(order, [])
        self.assertIn("合计：¥45.50", ticket)

    def test_none_item_list_is_tolerated(self):
        order = self._order()
        ticket = build_order_ticket(order, None)
        self.assertIn("合计：¥45.50", ticket)

    def test_pickup_no_is_printed_when_set(self):
        order = self._order(pickup_no="07")
        ticket = build_order_ticket(order, [])
        self.assertIn("取餐号：07", ticket)

    def test_no_pickup_no_line_when_not_assigned_yet(self):
        order = self._order()
        ticket = build_order_ticket(order, [])
        self.assertNotIn("取餐号", ticket)


if __name__ == "__main__":
    unittest.main()
