import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.customer import Customer
from app.models.member_account import MemberAccount
from app.models.order import Order
from app.models.point_ledger import PointLedger
from app.core.plan_capabilities import CAP_COUPONS
from app.core.tenant_context import TenantContext
from app.services import order_lifecycle_service
from app.services.order_lifecycle_service import OrderLifecycleService
from app.services.order_payment_service import OrderPaymentService
from app.services.coupon_service import CouponService


class MemberValueContractSurfaceTest(unittest.TestCase):
    def test_member_value_builder_exists(self):
        self.assertTrue(
            callable(getattr(order_lifecycle_service, "build_member_value_for_order", None)),
            "P0-B1 requires one authoritative member-value builder",
        )


class _NoQuerySession:
    async def execute(self, *_args, **_kwargs):
        raise AssertionError("guest and pending reads must not query member tables")


class MemberValueEarlyStatusTest(unittest.IsolatedAsyncioTestCase):
    async def test_guest_is_not_applicable_before_or_after_payment(self):
        for payment_status in ("unpaid", "paid"):
            order = SimpleNamespace(customer_id=None, payment_status=payment_status)
            value = await order_lifecycle_service.build_member_value_for_order(_NoQuerySession(), order)
            self.assertEqual(
                value,
                {
                    "status": "not_applicable",
                    "member_savings": None,
                    "points_earned": None,
                    "points_balance": None,
                    "reward_coupon_status": "unknown",
                    "reward_coupon": None,
                },
            )

    async def test_member_unpaid_is_pending_without_member_queries(self):
        order = SimpleNamespace(customer_id=42, payment_status="unpaid")
        value = await order_lifecycle_service.build_member_value_for_order(_NoQuerySession(), order)
        self.assertEqual(
            value,
            {
                "status": "pending",
                "member_savings": None,
                "points_earned": None,
                "points_balance": None,
                "reward_coupon_status": "unknown",
                "reward_coupon": None,
            },
        )


class PaidMemberValueContractTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        TenantContext.set_tenant_id("tenant-a")

    async def asyncTearDown(self):
        TenantContext.clear()
        await self.db.close()
        await self.engine.dispose()

    async def _paid_order(
        self,
        *,
        customer_id=101,
        total="90.00",
        coupon_id=501,
        discount_amount="10.00",
        payment_mode="prepay",
        reward_snapshot=None,
    ):
        order = Order(
            tenant_id="tenant-a",
            customer_id=customer_id,
            table_no="A1",
            total=total,
            coupon_id=coupon_id,
            discount_amount=discount_amount,
            status="pending",
            payment_status="paid",
            payment_mode=payment_mode,
            reward_coupon_snapshot=reward_snapshot,
        )
        self.db.add(order)
        await self.db.flush()
        return order

    async def _account(self, customer_id=101, points_balance=190):
        account = MemberAccount(
            tenant_id="tenant-a",
            customer_id=customer_id,
            member_id=f"member-{customer_id}",
            level_code="LV1",
            level_name="普通会员",
            points_balance=points_balance,
            total_consumption=0,
            yearly_consumption=0,
            balance=0,
        )
        self.db.add(account)
        await self.db.flush()
        return account

    async def _ledger(
        self,
        order,
        *,
        event_type="consumption",
        points=90,
        ref_id=None,
        tenant_id=None,
    ):
        ledger = PointLedger(
            tenant_id=tenant_id or order.tenant_id,
            customer_id=order.customer_id,
            member_id=f"member-{order.customer_id}",
            event_type=event_type,
            points=points,
            balance_after=points,
            source_channel="STORE",
            ref_id=str(order.id) if ref_id is None else ref_id,
        )
        self.db.add(ledger)
        await self.db.flush()
        return ledger

    async def test_paid_member_uses_coupon_ledger_balance_and_reward_snapshot_authorities(self):
        reward = {"id": "coupon-9", "name": "下次券", "amount": 5, "min_amount": 30}
        order = await self._paid_order(reward_snapshot=json.dumps(reward, ensure_ascii=False))
        await self._account(points_balance=190)
        await self._ledger(order, event_type="register", points=10, ref_id="member-register")
        await self._ledger(order, event_type="consumption", points=90)
        await self._ledger(order, event_type="consumption", points=777, ref_id="another-order")

        value = await order_lifecycle_service.build_member_value_for_order(self.db, order)

        self.assertEqual(
            value,
            {
                "status": "available",
                "member_savings": 10.0,
                "points_earned": 90,
                "points_balance": 190,
                "reward_coupon_status": "issued",
                "reward_coupon": reward,
            },
        )

    async def test_ledger_actual_points_win_over_level_formula_and_balance_is_current(self):
        order = await self._paid_order(total="90.00", coupon_id=None, discount_amount=None)
        await self._account(points_balance=7)
        await self._ledger(order, points=135)

        value = await order_lifecycle_service.build_member_value_for_order(self.db, order)

        self.assertEqual(value["points_earned"], 135)
        self.assertEqual(value["points_balance"], 7)

    async def test_public_discount_is_not_member_savings_and_no_reward_is_explicit(self):
        order = await self._paid_order(
            coupon_id=None,
            discount_amount="12.00",
            reward_snapshot="null",
        )
        await self._account(points_balance=40)
        await self._ledger(order, points=90)

        value = await order_lifecycle_service.build_member_value_for_order(self.db, order)

        self.assertEqual(value["status"], "available")
        self.assertEqual(value["member_savings"], 0.0)
        self.assertEqual(value["points_earned"], 90)
        self.assertEqual(value["reward_coupon_status"], "none")
        self.assertIsNone(value["reward_coupon"])

    async def test_free_paid_member_is_available_with_zero_actual_points(self):
        order = await self._paid_order(total="0.00", discount_amount="100.00")
        await self._account(points_balance=55)

        value = await order_lifecycle_service.build_member_value_for_order(self.db, order)

        self.assertEqual(value["status"], "available")
        self.assertEqual(value["points_earned"], 0)
        self.assertEqual(value["points_balance"], 55)
        self.assertEqual(value["reward_coupon_status"], "unknown")

    async def test_missing_account_or_duplicate_order_ledgers_is_unavailable(self):
        missing_account_order = await self._paid_order(customer_id=201)
        missing = await order_lifecycle_service.build_member_value_for_order(self.db, missing_account_order)
        self.assertEqual(missing["status"], "unavailable")
        self.assertEqual(missing["reward_coupon_status"], "unknown")
        self.assertTrue(
            all(
                missing[key] is None
                for key in ("member_savings", "points_earned", "points_balance", "reward_coupon")
            )
        )

        duplicate_order = await self._paid_order(customer_id=202)
        await self._account(customer_id=202)
        await self._ledger(duplicate_order, points=90)
        await self._ledger(duplicate_order, points=90)
        with self.assertLogs("app.services.order_lifecycle_service", level="ERROR") as captured:
            duplicate = await order_lifecycle_service.build_member_value_for_order(self.db, duplicate_order)
        self.assertEqual(duplicate["status"], "unavailable")
        self.assertTrue(any("duplicate consumption ledgers" in line for line in captured.output))

    async def test_legacy_offline_null_reward_is_unknown_but_explicit_json_null_is_known_none(self):
        legacy = await self._paid_order(customer_id=301, payment_mode="postpay", reward_snapshot=None)
        await self._account(customer_id=301)
        await self._ledger(legacy, points=90)
        legacy_value = await order_lifecycle_service.build_member_value_for_order(self.db, legacy)
        self.assertEqual(legacy_value["status"], "available")
        self.assertEqual(legacy_value["reward_coupon_status"], "unknown")
        self.assertIsNone(legacy_value["reward_coupon"])

        current = await self._paid_order(customer_id=302, payment_mode="table_account", reward_snapshot="null")
        await self._account(customer_id=302)
        await self._ledger(current, points=90)
        current_value = await order_lifecycle_service.build_member_value_for_order(self.db, current)
        self.assertEqual(current_value["status"], "available")
        self.assertEqual(current_value["reward_coupon_status"], "none")
        self.assertIsNone(current_value["reward_coupon"])

    async def test_malformed_reward_snapshot_is_unavailable(self):
        order = await self._paid_order(customer_id=401, reward_snapshot="not-json")
        await self._account(customer_id=401)
        await self._ledger(order, points=90)

        value = await order_lifecycle_service.build_member_value_for_order(self.db, order)

        self.assertEqual(value["status"], "unavailable")
        self.assertEqual(value["reward_coupon_status"], "unknown")

    async def test_positive_paid_order_without_its_consumption_ledger_is_unavailable(self):
        order = await self._paid_order(customer_id=402, total="90.00", reward_snapshot="null")
        await self._account(customer_id=402)

        value = await order_lifecycle_service.build_member_value_for_order(self.db, order)

        self.assertEqual(value["status"], "unavailable")
        self.assertIsNone(value["points_earned"])
        self.assertIsNone(value["points_balance"])
        self.assertEqual(value["reward_coupon_status"], "none")

    async def test_cross_tenant_consumption_ledger_is_ignored(self):
        order = await self._paid_order(customer_id=403, total="90.00", reward_snapshot="null")
        await self._account(customer_id=403)
        await self._ledger(order, points=90, tenant_id="tenant-b")

        value = await order_lifecycle_service.build_member_value_for_order(self.db, order)

        self.assertEqual(value["status"], "unavailable")
        self.assertIsNone(value["points_earned"])

    async def test_get_my_order_exposes_member_value_after_owner_check(self):
        order = await self._paid_order(customer_id=501)
        await self._account(customer_id=501, points_balance=88)
        await self._ledger(order, points=81)

        response = await OrderLifecycleService(self.db).get_my_order(
            int(order.id), customer_id=501, participant_token=None
        )

        self.assertEqual(response.code, 200)
        self.assertEqual(response.data["member_value"]["status"], "available")
        self.assertEqual(response.data["member_value"]["points_earned"], 81)
        self.assertEqual(response.data["member_value"]["reward_coupon_status"], "unknown")

    async def test_get_my_order_rejects_cross_customer_member_value(self):
        order = await self._paid_order(customer_id=601)
        await self._account(customer_id=601)

        response = await OrderLifecycleService(self.db).get_my_order(
            int(order.id), customer_id=602, participant_token=None
        )

        self.assertEqual(response.code, 403)
        self.assertIsNone(response.data)

    async def test_get_my_order_rejects_cross_tenant_order_even_if_customer_id_matches(self):
        order = Order(
            tenant_id="tenant-b",
            customer_id=701,
            table_no="B1",
            total="10.00",
            status="pending",
            payment_status="paid",
            payment_mode="prepay",
        )
        self.db.add(order)
        self.db.add(MemberAccount(
            tenant_id="tenant-b",
            customer_id=701,
            member_id="member-b-701",
            level_code="LV1",
            level_name="普通会员",
            points_balance=0,
            total_consumption=0,
            yearly_consumption=0,
            balance=0,
        ))
        await self.db.flush()

        response = await OrderLifecycleService(self.db).get_my_order(
            int(order.id), customer_id=701, participant_token=None
        )

        self.assertEqual(response.code, 404)
        self.assertIsNone(response.data)

    async def _payment_customer_and_order(self, *, total="90.00", points_balance=0):
        customer = Customer(tenant_id="tenant-a", openid=f"wx-{total}", status=1)
        self.db.add(customer)
        await self.db.flush()
        await self._account(customer_id=int(customer.id), points_balance=points_balance)
        order = Order(
            tenant_id="tenant-a",
            customer_id=customer.id,
            table_no="P1",
            total=total,
            status="pending_payment",
            payment_status="unpaid",
            payment_mode="prepay",
        )
        self.db.add(order)
        await self.db.flush()
        return customer, order

    async def test_duplicate_payment_success_keeps_one_ledger_and_stable_reward_snapshot(self):
        customer, order = await self._payment_customer_and_order(total="90.00")
        issue_result = {
            "success_count": 1,
            "sent": [{"id": "reward-1", "expire_time": "2026-09-01T00:00:00Z"}],
            "weighted_coupon": {"name": "下次券", "amount": 5, "threshold": 30},
        }
        service = OrderPaymentService(self.db)
        with (
            patch("app.services.order_payment_service.optional_capability_enabled", new=AsyncMock(return_value=True)),
            patch.object(CouponService, "resolve_consumption_coupon_rule_type", new=AsyncMock(return_value="new_customer_coupon")),
            patch.object(CouponService, "issue_auto_coupon", new=AsyncMock(return_value=issue_result)),
            patch("app.services.payment_handoff_service.PaymentHandoffService.mark_order_paid", new=AsyncMock()),
        ):
            await service._on_payment_success(order, payment_method="wxpay")
            first_snapshot = order.reward_coupon_snapshot
            first_value = await order_lifecycle_service.build_member_value_for_order(self.db, order)
            await service._on_payment_success(order, payment_method="wxpay")
            second_value = await order_lifecycle_service.build_member_value_for_order(self.db, order)

        self.assertEqual(first_value["points_earned"], 90)
        self.assertEqual(second_value["points_earned"], 90)
        self.assertEqual(order.reward_coupon_snapshot, first_snapshot)
        self.assertEqual(second_value["reward_coupon_status"], "issued")
        self.assertEqual(second_value["reward_coupon"]["id"], "reward-1")

    async def test_free_payment_persists_explicit_no_reward_and_available_value(self):
        customer, order = await self._payment_customer_and_order(total="0.00")
        service = OrderPaymentService(self.db)
        with (
            patch("app.services.order_payment_service.optional_capability_enabled", new=AsyncMock(return_value=True)),
            patch.object(CouponService, "resolve_consumption_coupon_rule_type", new=AsyncMock(return_value="new_customer_coupon")),
            patch.object(CouponService, "issue_auto_coupon", new=AsyncMock(return_value={"success_count": 0})),
            patch("app.services.payment_handoff_service.PaymentHandoffService.mark_order_paid", new=AsyncMock()),
        ):
            await service._on_payment_success(order, payment_method="free")

        value = await order_lifecycle_service.build_member_value_for_order(self.db, order)
        self.assertEqual(order.reward_coupon_snapshot, "null")
        self.assertEqual(value["status"], "available")
        self.assertEqual(value["points_earned"], 0)
        self.assertEqual(value["reward_coupon_status"], "none")
        self.assertIsNone(value["reward_coupon"])

    async def test_prepay_no_reward_persists_explicit_json_null(self):
        customer, order = await self._payment_customer_and_order(total="90.00")
        service = OrderPaymentService(self.db)
        with (
            patch("app.services.order_payment_service.optional_capability_enabled", new=AsyncMock(return_value=True)),
            patch.object(CouponService, "resolve_consumption_coupon_rule_type", new=AsyncMock(return_value="new_customer_coupon")),
            patch.object(CouponService, "issue_auto_coupon", new=AsyncMock(return_value={"success_count": 0})),
            patch("app.services.payment_handoff_service.PaymentHandoffService.mark_order_paid", new=AsyncMock()),
        ):
            await service._on_payment_success(order, payment_method="wxpay")

        value = await order_lifecycle_service.build_member_value_for_order(self.db, order)
        self.assertEqual(order.reward_coupon_snapshot, "null")
        self.assertEqual(value["status"], "available")
        self.assertEqual(value["points_earned"], 90)
        self.assertEqual(value["reward_coupon_status"], "none")

    async def test_prepay_coupon_capability_disabled_is_known_none(self):
        customer, order = await self._payment_customer_and_order(total="90.00")
        service = OrderPaymentService(self.db)

        async def capability_enabled(_tenant_id, capability):
            return capability != CAP_COUPONS

        with (
            patch("app.services.order_payment_service.optional_capability_enabled", new=capability_enabled),
            patch("app.services.payment_handoff_service.PaymentHandoffService.mark_order_paid", new=AsyncMock()),
        ):
            await service._on_payment_success(order, payment_method="wxpay")

        value = await order_lifecycle_service.build_member_value_for_order(self.db, order)
        self.assertEqual(order.reward_coupon_snapshot, "null")
        self.assertEqual(value["status"], "available")
        self.assertEqual(value["reward_coupon_status"], "none")

    async def test_points_balance_reads_final_account_after_points_reward_deduction(self):
        customer, order = await self._payment_customer_and_order(
            total="90.00", points_balance=950
        )

        async def issue_by_rule(_service, _customer_id, rule_type, **_kwargs):
            if rule_type == "points_reward_coupon":
                return {
                    "success_count": 1,
                    "sent": [{"id": "points-reward"}],
                    "weighted_coupon": {"name": "积分券", "amount": 5, "threshold": 30},
                }
            return {"success_count": 0}

        service = OrderPaymentService(self.db)
        with (
            patch("app.services.order_payment_service.optional_capability_enabled", new=AsyncMock(return_value=True)),
            patch.object(CouponService, "resolve_consumption_coupon_rule_type", new=AsyncMock(return_value="new_customer_coupon")),
            patch.object(CouponService, "issue_auto_coupon", new=issue_by_rule),
            patch("app.services.payment_handoff_service.PaymentHandoffService.mark_order_paid", new=AsyncMock()),
        ):
            await service._on_payment_success(order, payment_method="wxpay")

        value = await order_lifecycle_service.build_member_value_for_order(self.db, order)
        self.assertEqual(value["points_earned"], 90)
        self.assertEqual(value["points_balance"], 40)
        self.assertEqual(value["reward_coupon_status"], "none")


if __name__ == "__main__":
    unittest.main()
