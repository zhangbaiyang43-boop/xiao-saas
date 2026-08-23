"""P1-03: order status_text never leaks the technical token."""
from __future__ import annotations

import unittest

from app.api.v1.orders import (
    ORDER_STATUS_TEXT,
    UNKNOWN_ORDER_STATUS_TEXT,
    order_status_text,
)


class OrderStatusTextTest(unittest.TestCase):
    def test_required_mapping(self):
        self.assertEqual(order_status_text("pending_payment"), "待支付")
        self.assertEqual(order_status_text("pending"), "待接单")
        self.assertEqual(order_status_text("preparing"), "制作中")
        self.assertEqual(order_status_text("done"), "已上餐")
        self.assertEqual(order_status_text("settled"), "已结账")
        self.assertEqual(order_status_text("cancelled"), "已取消")
        self.assertEqual(order_status_text("rejected"), "已拒单")

    def test_unknown_status_is_chinese_not_token(self):
        self.assertEqual(order_status_text("not_a_real_status"), UNKNOWN_ORDER_STATUS_TEXT)
        self.assertEqual(order_status_text(""), UNKNOWN_ORDER_STATUS_TEXT)
        self.assertEqual(order_status_text(None), UNKNOWN_ORDER_STATUS_TEXT)
        self.assertNotEqual(order_status_text("pending_payment"), "pending_payment")
        self.assertFalse(order_status_text("abc_xyz").isascii() and "_" in order_status_text("abc_xyz"))

    def test_canonical_map_has_no_english_values(self):
        for key, text in ORDER_STATUS_TEXT.items():
            self.assertNotEqual(text, key)
            self.assertFalse(text.isascii())
