import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock

from app.services.dining_session_service import DiningSessionService


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *_args, **_kwargs):
        return FakeResult(self._rows)


class ParticipantOrdinalContractsTest(unittest.TestCase):
    def test_orders_within_one_session_are_numbered_by_join_order(self):
        # participant 20 加入更早，即使 id 更大，也该排第 1 号——按 joined_at 排序，
        # 不是按 id 排序。
        rows = [
            (20, 100),  # session 100，最早加入
            (5, 100),   # session 100，后加入
            (7, 200),   # session 200，独立编号
        ]
        db = FakeSession(rows)

        result = asyncio.run(DiningSessionService.get_participant_ordinals(db, "tenant-1", [100, 200]))

        self.assertEqual(result[20], 1)
        self.assertEqual(result[5], 2)
        self.assertEqual(result[7], 1)  # 不同桌各自从 1 开始编号

    def test_empty_session_list_returns_empty_map(self):
        db = FakeSession([])
        result = asyncio.run(DiningSessionService.get_participant_ordinals(db, "tenant-1", []))
        self.assertEqual(result, {})

    def test_list_session_orders_attaches_ordinal_to_serialized_order(self):
        service = DiningSessionService(db=object())
        service.get_participant_ordinals = AsyncMock()  # not used directly here
        # 直接测 _serialize_order 是否正确透传 participant_no
        from types import SimpleNamespace
        order = SimpleNamespace(
            id=1, table_no="A12", total=32.8, discount_amount=1.0, status="pending",
            merchant_note=None, payment_status="paid", payment_mode="table_account",
            payment_method="wxpay", dining_session_id=100, participant_id=5,
            order_type="dine_in", created_at=datetime(2026, 7, 29, 9, 4),
        )
        serialized = service._serialize_order(order, [], {}, participant_no=2)
        self.assertEqual(serialized["participant_no"], 2)
        self.assertEqual(serialized["participant_id"], "5")


if __name__ == "__main__":
    unittest.main()
