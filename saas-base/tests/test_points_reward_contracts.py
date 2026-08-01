import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.membership_service import MembershipService, POINTS_REWARD_THRESHOLD


class FakeSession:
    def __init__(self):
        self.committed = 0
        self.refreshed = []

    async def commit(self):
        self.committed += 1

    async def refresh(self, entity):
        self.refreshed.append(entity)


def _resolve_maybe_expr(current_value, assigned):
    """_maybe_reward_points_milestone 里写的是
    `account.points_balance = MemberAccount.points_balance - N`（SQLAlchemy 类级别
    列表达式，交给数据库原子执行，跟 add_points 里已有的写法是同一个模式）。
    真实数据库会在 refresh() 时把这个表达式解析成真正的数字，这里的假账户对象
    没有数据库，用表达式自带的 operator/右值自己算一遍，模拟同样的效果。"""
    if not hasattr(assigned, "operator") or not hasattr(assigned, "right"):
        return assigned
    right_value = getattr(assigned.right, "value", assigned.right)
    return assigned.operator(current_value, right_value)


class FakeAccount:
    def __init__(self, points_balance, customer_id=1):
        self._points_balance = points_balance
        self.customer_id = customer_id

    @property
    def points_balance(self):
        return self._points_balance

    @points_balance.setter
    def points_balance(self, value):
        self._points_balance = _resolve_maybe_expr(self._points_balance, value)


def make_account(points_balance, customer_id=1):
    return FakeAccount(points_balance=points_balance, customer_id=customer_id)


class PointsRewardContractsTest(unittest.TestCase):
    def test_no_reward_when_threshold_not_crossed(self):
        service = MembershipService(FakeSession())
        service.set_tenant_id("tenant-001")
        account = make_account(points_balance=POINTS_REWARD_THRESHOLD - 1)

        with patch("app.services.coupon_service.CouponService") as MockCouponService:
            result = asyncio.run(service._maybe_reward_points_milestone(account, balance_before=0))

        MockCouponService.assert_not_called()
        self.assertIsNone(result)
        self.assertEqual(account.points_balance, POINTS_REWARD_THRESHOLD - 1)

    def test_crossing_threshold_issues_one_coupon_and_deducts_points(self):
        service = MembershipService(FakeSession())
        service.set_tenant_id("tenant-001")
        # 消费前 950 分，这一单加了 100 分，跨过 1000 门槛
        account = make_account(points_balance=1050)

        issue_result = {
            "success_count": 1,
            "sent": [{"id": "coupon-1", "expire_time": "2026-09-01T00:00:00"}],
            "weighted_coupon": {"name": "积分好礼券", "amount": 5, "threshold": 30},
        }
        fake_coupon_svc = SimpleNamespace(
            set_tenant_id=lambda tid: None,
            issue_auto_coupon=AsyncMock(return_value=issue_result),
        )

        with patch("app.services.coupon_service.CouponService", return_value=fake_coupon_svc):
            result = asyncio.run(service._maybe_reward_points_milestone(account, balance_before=950))

        fake_coupon_svc.issue_auto_coupon.assert_awaited_once_with(1, "points_reward_coupon")
        self.assertEqual(account.points_balance, 1050 - POINTS_REWARD_THRESHOLD)
        self.assertEqual(result["id"], "coupon-1")
        self.assertEqual(result["amount"], 5)
        self.assertEqual(result["min_amount"], 30)

    def test_crossing_two_thresholds_at_once_issues_two_coupons(self):
        # 一次性加了很多积分（比如活动加倍/后台手动调整），从 500 跳到 2500，
        # 跨过了两个 1000 门槛，应该发两张券、扣两倍门槛的积分。
        service = MembershipService(FakeSession())
        service.set_tenant_id("tenant-001")
        account = make_account(points_balance=2500)

        issue_result = {
            "success_count": 1,
            "sent": [{"id": "coupon-x", "expire_time": "2026-09-01T00:00:00"}],
            "weighted_coupon": {"name": "积分好礼券", "amount": 5, "threshold": 30},
        }
        fake_coupon_svc = SimpleNamespace(
            set_tenant_id=lambda tid: None,
            issue_auto_coupon=AsyncMock(return_value=issue_result),
        )

        with patch("app.services.coupon_service.CouponService", return_value=fake_coupon_svc):
            result = asyncio.run(service._maybe_reward_points_milestone(account, balance_before=500))

        self.assertEqual(fake_coupon_svc.issue_auto_coupon.await_count, 2)
        self.assertEqual(account.points_balance, 2500 - 2 * POINTS_REWARD_THRESHOLD)
        self.assertIsNotNone(result)

    def test_dedup_block_leaves_points_untouched_for_unfulfilled_portion(self):
        # 手上已经有一张未用的同类券，issue_auto_coupon 内置去重会挡住——
        # 这种情况不该扣积分，等那张用掉了、下次再攒够重新判断。
        service = MembershipService(FakeSession())
        service.set_tenant_id("tenant-001")
        account = make_account(points_balance=1050)

        issue_result = {"success_count": 0, "reason": "已持有未使用的同类券，本次不再发放", "skipped_duplicate": True}
        fake_coupon_svc = SimpleNamespace(
            set_tenant_id=lambda tid: None,
            issue_auto_coupon=AsyncMock(return_value=issue_result),
        )

        with patch("app.services.coupon_service.CouponService", return_value=fake_coupon_svc):
            result = asyncio.run(service._maybe_reward_points_milestone(account, balance_before=950))

        self.assertIsNone(result)
        self.assertEqual(account.points_balance, 1050)  # 没扣

    def test_exception_during_issuance_does_not_lose_points_or_raise(self):
        service = MembershipService(FakeSession())
        service.set_tenant_id("tenant-001")
        account = make_account(points_balance=1050)

        fake_coupon_svc = SimpleNamespace(
            set_tenant_id=lambda tid: None,
            issue_auto_coupon=AsyncMock(side_effect=RuntimeError("boom")),
        )

        with patch("app.services.coupon_service.CouponService", return_value=fake_coupon_svc):
            result = asyncio.run(service._maybe_reward_points_milestone(account, balance_before=950))

        self.assertIsNone(result)
        self.assertEqual(account.points_balance, 1050)  # 异常没吞掉积分


if __name__ == "__main__":
    unittest.main()
