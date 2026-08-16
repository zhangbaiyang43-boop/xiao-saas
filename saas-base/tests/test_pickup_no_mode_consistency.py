"""桌牌：配置落库、can_assign_pickup_no 合同、拒单释放、order.payment_mode 覆盖租户模式。"""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.orders import (
    OrderCreate,
    OrderItemIn,
    OrderStatusUpdate,
    create_order,
    serialize_order,
)
from app.api.v1.tenant import serialize_settings
from app.models.base import Base
from app.models.dining import DiningSession
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.pickup_no_assignment import PickupNoAssignment
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.services.order_lifecycle_service import OrderLifecycleService
from app.services.pickup_no_service import (
    PickupNoService,
    can_assign_pickup_no,
    parse_pickup_settings,
)
from app.services.tenant_service import TenantService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT = "tenant-mode"


def close_background_print_coroutine(coroutine):
    coroutine.close()


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_merchant_request(tenant_id=TENANT):
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/orders",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    request.state.tenant_id = tenant_id
    request.state.token_type = "merchant"
    return request


class PickupNoModeConsistencyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add(
            Tenant(
                tenant_id=TENANT, name="Mode Shop", password_hash="x",
                status=True, is_open=True, payment_mode="table_account",
            )
        )
        self.db.add(
            TenantConfig(
                tenant_id=TENANT,
                member_rules={},
                coupon_rules={},
                business_info={
                    "pickup_no_enabled": False,
                    "pickup_no_count": 30,
                    "pickup_no_required_before_print": True,
                },
                plugin_settings={},
            )
        )
        self.dish = MenuItem(tenant_id=TENANT, name="Soup", price="25.00", available=True)
        self.db.add(self.dish)
        # P0-01: this suite is about pickup-number mode consistency, not table
        # validity -- register every table_no value used across its tests
        # (R01 default plus R1-R5 overrides in individual tests).
        for table_no in ("R01", "R1", "R2", "R3", "R4", "R5"):
            self.db.add(EntranceCode(
                id=generate_snowflake_id(),
                tenant_id=TENANT, name=table_no, scene=f"E0000000{table_no}",
                table_no=table_no, entry_type="table", status=1,
            ))
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _enable_pickup(self, **patch):
        config = (
            await self.db.execute(select(TenantConfig).where(TenantConfig.tenant_id == TENANT))
        ).scalar_one()
        tenant = (
            await self.db.execute(select(Tenant).where(Tenant.tenant_id == TENANT))
        ).scalar_one()
        info = {
            "pickup_no_enabled": True,
            "pickup_no_count": 30,
            "pickup_no_required_before_print": True,
            **patch,
        }
        svc = TenantService(self.db)
        await svc.update_tenant_settings(tenant, config, business_info=info)
        await self.db.refresh(config)
        return tenant, config

    def _settings(self, enabled=True):
        return parse_pickup_settings({
            "pickup_no_enabled": enabled,
            "pickup_no_count": 30,
            "pickup_no_required_before_print": True,
        })

    def _session(self, status="OPEN"):
        return SimpleNamespace(id=1, status=status, tenant_id=TENANT)

    # ---------- CONFIG ----------
    async def test_config_01_enable_persists_to_db_and_profile(self):
        tenant, config = await self._enable_pickup(pickup_no_enabled=True)
        self.assertTrue(config.business_info.get("pickup_no_enabled"))
        data = serialize_settings(tenant, config)
        self.assertTrue(data["business_info"]["pickup_no_enabled"])
        flat = {**data["profile"], **(data["business_info"] or {})}
        self.assertTrue(flat["pickup_no_enabled"])

    async def test_config_02_count_persists(self):
        tenant, config = await self._enable_pickup(pickup_no_count=30)
        self.assertEqual(int(config.business_info.get("pickup_no_count")), 30)
        flat = {**(serialize_settings(tenant, config)["business_info"] or {})}
        self.assertEqual(int(flat["pickup_no_count"]), 30)

    async def test_config_03_required_before_print_persists(self):
        tenant, config = await self._enable_pickup(pickup_no_required_before_print=True)
        self.assertTrue(config.business_info.get("pickup_no_required_before_print"))
        flat = {**(serialize_settings(tenant, config)["business_info"] or {})}
        self.assertTrue(flat["pickup_no_required_before_print"])

    # ---------- can_assign contract ----------
    def test_prepay_01_unpaid_false(self):
        order = SimpleNamespace(
            pickup_no=None, status="pending_payment", payment_status="unpaid", payment_mode="prepay",
        )
        self.assertFalse(can_assign_pickup_no(order, self._settings(), self._session()))

    def test_prepay_02_paid_pending_true(self):
        order = SimpleNamespace(
            pickup_no=None, status="pending", payment_status="paid", payment_mode="prepay",
        )
        self.assertTrue(can_assign_pickup_no(order, self._settings(), self._session()))

    def test_postpay_01_unpaid_pending_true(self):
        order = SimpleNamespace(
            pickup_no=None, status="pending", payment_status="unpaid", payment_mode="postpay",
        )
        self.assertTrue(can_assign_pickup_no(order, self._settings(), self._session()))

    def test_postpay_02_unpaid_preparing_true(self):
        order = SimpleNamespace(
            pickup_no=None, status="preparing", payment_status="unpaid", payment_mode="postpay",
        )
        self.assertTrue(can_assign_pickup_no(order, self._settings(), self._session()))

    def test_table_01_open_unpaid_pending_true(self):
        order = SimpleNamespace(
            pickup_no=None, status="pending", payment_status="unpaid", payment_mode="table_account",
        )
        self.assertTrue(can_assign_pickup_no(order, self._settings(), self._session("OPEN")))

    def test_table_02_open_unpaid_preparing_true(self):
        order = SimpleNamespace(
            pickup_no=None, status="preparing", payment_status="unpaid", payment_mode="table_account",
        )
        self.assertTrue(can_assign_pickup_no(order, self._settings(), self._session("OPEN")))

    def test_table_03_closed_false(self):
        order = SimpleNamespace(
            pickup_no=None, status="pending", payment_status="unpaid", payment_mode="table_account",
        )
        self.assertFalse(can_assign_pickup_no(order, self._settings(), self._session("CLOSED")))

    def test_common_01_disabled_false_all_modes(self):
        for mode in ("prepay", "postpay", "table_account"):
            order = SimpleNamespace(
                pickup_no=None, status="pending", payment_status="paid", payment_mode=mode,
            )
            self.assertFalse(can_assign_pickup_no(order, self._settings(False), self._session()))

    def test_common_02_cancelled_false(self):
        order = SimpleNamespace(
            pickup_no=None, status="cancelled", payment_status="unpaid", payment_mode="postpay",
        )
        self.assertFalse(can_assign_pickup_no(order, self._settings(), self._session()))

    def test_common_03_rejected_false(self):
        order = SimpleNamespace(
            pickup_no=None, status="rejected", payment_status="unpaid", payment_mode="postpay",
        )
        self.assertFalse(can_assign_pickup_no(order, self._settings(), self._session()))

    def test_common_04_settled_false(self):
        order = SimpleNamespace(
            pickup_no=None, status="settled", payment_status="paid", payment_mode="prepay",
        )
        self.assertFalse(can_assign_pickup_no(order, self._settings(), self._session()))

    def test_order_mode_overrides_tenant_table_account_to_prepay(self):
        """Tenant=table_account，但订单 payment_mode=prepay unpaid → false。"""
        order = SimpleNamespace(
            pickup_no=None, status="pending", payment_status="unpaid", payment_mode="prepay",
        )
        self.assertFalse(can_assign_pickup_no(order, self._settings(), self._session()))

    def test_order_mode_overrides_tenant_prepay_to_table_account(self):
        order = SimpleNamespace(
            pickup_no=None, status="pending", payment_status="unpaid", payment_mode="table_account",
        )
        self.assertTrue(can_assign_pickup_no(order, self._settings(), self._session("OPEN")))

    def test_serialize_order_includes_can_assign(self):
        order = SimpleNamespace(
            id=1, table_no="A1", phone=None, total=10, status="pending", remark=None,
            coupon_id=None, discount_amount=None, payment_status="unpaid", payment_mode="postpay",
            payment_method=None, dining_session_id=9, participant_id=None, order_type=None,
            parent_order_id=None, source="miniprogram", staff_note=None, pickup_no=None,
            created_at=None, merchant_note=None, print_status=None, printed_at=None,
        )
        data = serialize_order(
            order, [], pickup_settings=self._settings(True), dining_session=self._session("OPEN"),
        )
        self.assertTrue(data["can_assign_pickup_no"])

    # ---------- RELEASE ----------
    async def _create_enabled_postpay_order(self, table="R01", pickup_no="17"):
        await self._enable_pickup()
        tenant = (
            await self.db.execute(select(Tenant).where(Tenant.tenant_id == TENANT))
        ).scalar_one()
        tenant.payment_mode = "postpay"
        await self.db.commit()
        body = OrderCreate(
            shop=TENANT,
            table=table,
            items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=25, qty=1)],
            total=25,
            pickup_no=pickup_no,
        )
        with patch(
            "app.api.v1.orders._spawn_background_print_task",
            side_effect=close_background_print_coroutine,
        ):
            res = await create_order(body, make_merchant_request(), self.db)
        self.assertEqual(res.code, 200, res.msg)
        return await self.db.get(Order, int(res.data["id"]))

    async def test_release_01_reject_sole_order_frees_assignment(self):
        order = await self._create_enabled_postpay_order(table="R1", pickup_no="19")
        svc = OrderLifecycleService(self.db)
        svc.set_tenant_id(TENANT)
        result = await svc.update_order_status(order.id, OrderStatusUpdate(status="rejected"))
        self.assertEqual(result.code, 200, result.msg)
        rows = (
            await self.db.execute(select(PickupNoAssignment).where(PickupNoAssignment.tenant_id == TENANT))
        ).scalars().all()
        self.assertEqual(len(rows), 0)
        await self.db.refresh(order)
        self.assertEqual(order.pickup_no, "19")  # 历史快照保留

    async def test_release_02_cancel_one_keeps_when_sibling_active(self):
        order_a = await self._create_enabled_postpay_order(table="R2", pickup_no="17")
        body = OrderCreate(
            shop=TENANT,
            table="R2",
            items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=25, qty=1)],
            total=25,
        )
        with patch(
            "app.api.v1.orders._spawn_background_print_task",
            side_effect=close_background_print_coroutine,
        ):
            res_b = await create_order(body, make_merchant_request(), self.db)
        self.assertEqual(res_b.code, 200, res_b.msg)
        order_b = await self.db.get(Order, int(res_b.data["id"]))
        order_b.status = "preparing"
        await self.db.commit()

        svc = OrderLifecycleService(self.db)
        svc.set_tenant_id(TENANT)
        result = await svc.update_order_status(order_a.id, OrderStatusUpdate(status="cancelled"))
        self.assertEqual(result.code, 200, result.msg)
        rows = (
            await self.db.execute(select(PickupNoAssignment).where(PickupNoAssignment.tenant_id == TENANT))
        ).scalars().all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].pickup_no, "17")

    async def test_release_03_all_terminal_releases(self):
        order_a = await self._create_enabled_postpay_order(table="R3", pickup_no="18")
        body = OrderCreate(
            shop=TENANT,
            table="R3",
            items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=25, qty=1)],
            total=25,
        )
        with patch(
            "app.api.v1.orders._spawn_background_print_task",
            side_effect=close_background_print_coroutine,
        ):
            res_b = await create_order(body, make_merchant_request(), self.db)
        order_b = await self.db.get(Order, int(res_b.data["id"]))

        svc = OrderLifecycleService(self.db)
        svc.set_tenant_id(TENANT)
        await svc.update_order_status(order_a.id, OrderStatusUpdate(status="cancelled"))
        await svc.update_order_status(order_b.id, OrderStatusUpdate(status="rejected"))
        rows = (
            await self.db.execute(select(PickupNoAssignment).where(PickupNoAssignment.tenant_id == TENANT))
        ).scalars().all()
        self.assertEqual(len(rows), 0)

    async def test_release_04_settle_still_releases(self):
        order = await self._create_enabled_postpay_order(table="R4", pickup_no="20")
        order.status = "done"
        order.payment_status = "paid"
        await self.db.commit()
        svc = OrderLifecycleService(self.db)
        svc.set_tenant_id(TENANT)
        settle = await svc.settle_table({"table_no": "R4", "dining_session_id": str(order.dining_session_id)}, closed_by="staff")
        self.assertEqual(settle.code, 200, settle.msg)
        rows = (
            await self.db.execute(select(PickupNoAssignment).where(PickupNoAssignment.tenant_id == TENANT))
        ).scalars().all()
        self.assertEqual(len(rows), 0)

    async def test_release_05_double_release_idempotent(self):
        order = await self._create_enabled_postpay_order(table="R5", pickup_no="21")
        session = await self.db.get(DiningSession, order.dining_session_id)
        svc = PickupNoService(self.db)
        await svc.release_session_assignment(TENANT, session, clear_session_field=True)
        await svc.release_session_assignment(TENANT, session, clear_session_field=True)
        await self.db.commit()
        rows = (
            await self.db.execute(select(PickupNoAssignment).where(PickupNoAssignment.tenant_id == TENANT))
        ).scalars().all()
        self.assertEqual(len(rows), 0)


if __name__ == "__main__":
    unittest.main()
