"""P0 桌牌租约：占用唯一、释放、支付门禁、打印暂缓、API 合同。"""
import asyncio
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.dining import DiningSession
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.pickup_no_assignment import PickupNoAssignment
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.api.v1.orders import (
    OrderCreate,
    OrderItemIn,
    OrderPickupNoUpdate,
    create_order,
    update_order_pickup_no,
)
from app.services.order_lifecycle_service import OrderLifecycleService
from app.services.order_print_service import _print_paid_order_ticket
from app.services.pickup_no_service import PickupNoService, parse_pickup_settings, should_defer_kitchen_print
from app.services.subscribe_message_service import resolve_pickup_no
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_merchant_request(tenant_id=TENANT_A):
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
    # get_request_principal() requires role=="owner" for an account_id-less merchant
    # request (see app/middleware/auth_middleware.py:127-142, which is what a real
    # request gets from AuthMiddleware) -- this fixture predates that check.
    request.state.role = "owner"
    request.state.account_id = None
    return request


class PickupNoAssignmentsP0Test(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        for tid, mode in ((TENANT_A, "postpay"), (TENANT_B, "postpay")):
            self.db.add(
                Tenant(
                    tenant_id=tid, name=f"Shop {tid}", password_hash="x",
                    status=True, is_open=True, payment_mode=mode,
                )
            )
            self.db.add(
                TenantConfig(
                    tenant_id=tid,
                    member_rules={},
                    coupon_rules={},
                    business_info={
                        "pickup_no_enabled": True,
                        "pickup_no_count": 30,
                        "pickup_no_required_before_print": True,
                    },
                    plugin_settings={},
                )
            )
        self.dish = MenuItem(tenant_id=TENANT_A, name="Soup", price="25.00", available=True)
        self.db.add(self.dish)
        self.dish_b = MenuItem(tenant_id=TENANT_B, name="SoupB", price="25.00", available=True)
        self.db.add(self.dish_b)
        # P0-01: this suite is about pickup-number assignment behavior, not table
        # validity -- register every table_no value used across its tests, per tenant.
        for table_no in ("A05", "A01", "A02", "A20", "P1", "P2", "P3", "A09", "A10"):
            self.db.add(EntranceCode(
                id=generate_snowflake_id(),
                tenant_id=TENANT_A, name=table_no, scene=f"E0000A{table_no}",
                table_no=table_no, entry_type="table", status=1,
            ))
        self.db.add(EntranceCode(
            id=generate_snowflake_id(),
            tenant_id=TENANT_B, name="B01", scene="E0000BB01",
            table_no="B01", entry_type="table", status=1,
        ))
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _body(self, tenant=TENANT_A, table="A05", pickup_no=None, dish=None):
        d = dish or self.dish
        return OrderCreate(
            shop=tenant,
            table=table,
            items=[OrderItemIn(dish_id=d.id, name=d.name, price=float(d.price), qty=1)],
            total=float(d.price),
            pickup_no=pickup_no,
        )

    async def _insert_prepay_order(self, table="A05", *, paid=False):
        """直接落库一张 prepay 订单（代客下单在 prepay 下被业务禁止）。"""
        now = datetime.utcnow()
        session = DiningSession(
            tenant_id=TENANT_A, table_no=table, status="OPEN",
            active_key=f"{TENANT_A}:{table}", started_at=now, last_activity_at=now,
        )
        self.db.add(session)
        await self.db.flush()
        order = Order(
            tenant_id=TENANT_A,
            dining_session_id=session.id,
            table_no=table,
            total=25,
            status="pending" if paid else "pending_payment",
            payment_status="paid" if paid else "unpaid",
            payment_mode="prepay",
            source="miniprogram",
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def _insert_orphan_order(self, table="A05", *, pickup_no=None, payment_mode="postpay"):
        """无 dining_session_id 的孤儿订单——2026-08-25 P0 审计的根因场景：postpay/
        prepay 建单时客户端没带 dining_session_id，后端不拒单，订单就长期没有 session。
        """
        order = Order(
            tenant_id=TENANT_A,
            dining_session_id=None,
            table_no=table,
            total=25,
            status="preparing",
            payment_status="unpaid",
            payment_mode=payment_mode,
            pickup_no=pickup_no,
            source="miniprogram",
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def test_p0_01_same_tenant_cannot_share_pickup_no(self):
        r1 = await create_order(self._body(table="A01", pickup_no="30"), make_merchant_request(), self.db)
        self.assertEqual(r1.code, 200)
        r2 = await create_order(self._body(table="A02", pickup_no="30"), make_merchant_request(), self.db)
        self.assertEqual(r2.code, 409)
        self.assertIn("正在使用", r2.msg)

    async def test_p0_02_cross_tenant_same_number_ok(self):
        r1 = await create_order(self._body(table="A01", pickup_no="30"), make_merchant_request(TENANT_A), self.db)
        self.assertEqual(r1.code, 200)
        r2 = await create_order(
            self._body(tenant=TENANT_B, table="B01", pickup_no="30", dish=self.dish_b),
            make_merchant_request(TENANT_B),
            self.db,
        )
        self.assertEqual(r2.code, 200, r2.msg)

    async def test_p0_11_orphan_order_can_be_assigned_pickup_no(self):
        """2026-08-25 P0 修复：孤儿订单（无 dining_session_id）以前一律 422 拒绝，
        现在应该能正常占用桌牌——顾客已经在现场，不能永远发不出牌。"""
        order = await self._insert_orphan_order(table="A01")
        result = await update_order_pickup_no(
            order.id, OrderPickupNoUpdate(pickup_no="12"), make_merchant_request(), self.db
        )
        self.assertEqual(result.code, 200, result.msg)
        await self.db.refresh(order)
        self.assertEqual(order.pickup_no, "12")

    async def test_p0_12_orphan_order_conflicts_with_real_session_lease(self):
        """孤儿订单不能抢一个正被真实 session 占用的号——旧代码完全没有这层检查。"""
        r1 = await create_order(self._body(table="A01", pickup_no="7"), make_merchant_request(), self.db)
        self.assertEqual(r1.code, 200, r1.msg)
        order = await self._insert_orphan_order(table="A09")
        result = await update_order_pickup_no(
            order.id, OrderPickupNoUpdate(pickup_no="7"), make_merchant_request(), self.db
        )
        self.assertEqual(result.code, 409)
        self.assertIn("正在使用", result.msg)

    async def test_p0_13_orphan_order_conflicts_with_another_orphan_order(self):
        """两笔孤儿订单不能拿到同一个号——这条冲突以前完全没人检查。"""
        first = await self._insert_orphan_order(table="A01")
        r1 = await update_order_pickup_no(
            first.id, OrderPickupNoUpdate(pickup_no="8"), make_merchant_request(), self.db
        )
        self.assertEqual(r1.code, 200, r1.msg)

        second = await self._insert_orphan_order(table="A09")
        r2 = await update_order_pickup_no(
            second.id, OrderPickupNoUpdate(pickup_no="8"), make_merchant_request(), self.db
        )
        self.assertEqual(r2.code, 409)
        self.assertIn("正在使用", r2.msg)

    async def test_p0_14_orphan_order_can_replace_its_own_number(self):
        """孤儿订单换号：自己原来占的那个号不算冲突，能顺利换到新号。"""
        order = await self._insert_orphan_order(table="A01", pickup_no="9")
        result = await update_order_pickup_no(
            order.id, OrderPickupNoUpdate(pickup_no="9"), make_merchant_request(), self.db
        )
        self.assertEqual(result.code, 200, result.msg)
        await self.db.refresh(order)
        self.assertEqual(order.pickup_no, "9")

    async def test_p0_15_orphan_order_holding_shows_up_in_occupied_list(self):
        """选号器（PickupNoPicker.vue）靠 list_occupied 灰掉已占用号码——孤儿订单
        占用的号必须出现在这里，否则店员在界面上完全看不出这个号已经被用了。"""
        order = await self._insert_orphan_order(table="A01", pickup_no="15")
        occupied = await PickupNoService(self.db).list_occupied(TENANT_A)
        self.assertIn({"pickup_no": "15", "dining_session_id": ""}, occupied)

    async def test_p0_16_orphan_order_release_is_implicit_on_terminal_status(self):
        """孤儿订单没有租约表可释放，但一旦终态就不该再出现在 occupied 列表里——
        这条路径靠 ORDER_STATUSES_HOLDING_PICKUP 过滤活订单自然释放，不需要额外的
        释放动作，这里锁定这个行为不是巧合。"""
        order = await self._insert_orphan_order(table="A01", pickup_no="21")
        order.status = "settled"
        await self.db.commit()
        occupied = await PickupNoService(self.db).list_occupied(TENANT_A)
        self.assertNotIn({"pickup_no": "21", "dining_session_id": ""}, occupied)

    async def test_p0_04_replace_releases_old_assignment(self):
        r1 = await create_order(self._body(table="A01", pickup_no="30"), make_merchant_request(), self.db)
        oid = r1.data["id"]
        result = await update_order_pickup_no(oid, OrderPickupNoUpdate(pickup_no="29"), make_merchant_request(), self.db)
        self.assertEqual(result.code, 200, result.msg)
        rows = (await self.db.execute(select(PickupNoAssignment).where(PickupNoAssignment.tenant_id == TENANT_A))).scalars().all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].pickup_no, "29")
        order = await self.db.get(Order, int(oid))
        self.assertEqual(order.pickup_no, "29")

    async def test_p0_05_settle_releases_assignment_keeps_order_snapshot(self):
        r1 = await create_order(self._body(table="A01", pickup_no="30"), make_merchant_request(), self.db)
        order = await self.db.get(Order, int(r1.data["id"]))
        order.status = "done"
        order.payment_status = "paid"
        await self.db.commit()

        svc = OrderLifecycleService(self.db)
        svc.set_tenant_id(TENANT_A)
        settle = await svc.settle_table({"table_no": "A01", "dining_session_id": str(order.dining_session_id)}, closed_by="staff")
        self.assertEqual(settle.code, 200, settle.msg)

        rows = (await self.db.execute(select(PickupNoAssignment).where(PickupNoAssignment.tenant_id == TENANT_A))).scalars().all()
        self.assertEqual(len(rows), 0)
        await self.db.refresh(order)
        self.assertEqual(order.pickup_no, "30")
        session = await self.db.get(DiningSession, order.dining_session_id)
        self.assertIsNone(session.pickup_no)

        # 30 可被新会话占用
        r2 = await create_order(self._body(table="A01", pickup_no="30"), make_merchant_request(), self.db)
        self.assertEqual(r2.code, 200, r2.msg)

    async def test_p0_06_addon_inherits_without_second_assignment(self):
        r1 = await create_order(self._body(table="A20", pickup_no="07"), make_merchant_request(), self.db)
        self.assertEqual(r1.data["pickup_no"], "07")
        r2 = await create_order(self._body(table="A20", pickup_no=None), make_merchant_request(), self.db)
        self.assertEqual(r2.data["pickup_no"], "07")
        rows = (await self.db.execute(select(PickupNoAssignment).where(PickupNoAssignment.tenant_id == TENANT_A))).scalars().all()
        self.assertEqual(len(rows), 1)

    async def test_p0_07_prepay_unpaid_cannot_assign(self):
        order = await self._insert_prepay_order(table="P1", paid=False)
        assign = await update_order_pickup_no(
            str(order.id), OrderPickupNoUpdate(pickup_no="30"), make_merchant_request(), self.db
        )
        self.assertEqual(assign.code, 422)
        self.assertIn("尚未支付", assign.msg)

    async def test_p0_08_prepay_paid_can_assign(self):
        order = await self._insert_prepay_order(table="P2", paid=True)
        assign = await update_order_pickup_no(
            str(order.id), OrderPickupNoUpdate(pickup_no="30"), make_merchant_request(), self.db
        )
        self.assertEqual(assign.code, 200, assign.msg)

    async def test_p0_09_disabled_does_not_defer_print(self):
        settings = parse_pickup_settings({"pickup_no_enabled": False, "pickup_no_required_before_print": True})
        order = SimpleNamespace(pickup_no=None, tenant_id=TENANT_A)
        self.assertFalse(should_defer_kitchen_print(order, settings))

    async def test_p0_10_enabled_defers_print_until_pickup(self):
        settings = parse_pickup_settings({
            "pickup_no_enabled": True,
            "pickup_no_required_before_print": True,
        })
        unpaid_tag = SimpleNamespace(pickup_no=None, tenant_id=TENANT_A, payment_status="paid", payment_mode="prepay")
        self.assertTrue(should_defer_kitchen_print(unpaid_tag, settings))
        tagged = SimpleNamespace(pickup_no="30", tenant_id=TENANT_A)
        self.assertFalse(should_defer_kitchen_print(tagged, settings))

    async def test_print_skipped_waiting_pickup_no(self):
        order = await self._insert_prepay_order(table="P3", paid=True)
        result = await _print_paid_order_ticket(order, self.db, reason="payment_success")
        self.assertTrue(result.get("skipped"))
        self.assertEqual(result.get("code"), "WAITING_PICKUP_NO")

    async def test_kuaimai_render_includes_pickup_no(self):
        from app.services.kuaimai_service import build_order_template_render_data

        order = SimpleNamespace(
            id=123, table_no="A05", pickup_no="30", total=10, discount_amount=0,
            payment_method="wechat_pay", remark="", order_type="INITIAL", parent_order_id=None,
            created_at=datetime.utcnow(),
        )
        data = build_order_template_render_data(order, [], shop_name="T")
        self.assertEqual(data["table_no"], "A05")
        self.assertEqual(data["pickup_no"], "30")

    async def test_p1_01_subscribe_no_table_fallback(self):
        self.assertEqual(resolve_pickup_no(SimpleNamespace(pickup_no=None, table_no="A01")), "—")
        self.assertEqual(resolve_pickup_no(SimpleNamespace(pickup_no="30", table_no="A01")), "30")

    async def test_get_my_order_returns_pickup_no(self):
        r1 = await create_order(self._body(table="A09", pickup_no="12"), make_merchant_request(), self.db)
        order = await self.db.get(Order, int(r1.data["id"]))
        order.customer_id = 42
        await self.db.commit()
        svc = OrderLifecycleService(self.db)
        with patch.object(
            __import__("app.services.order_payment_service", fromlist=["OrderPaymentService"]).OrderPaymentService,
            "_recover_wxpay_order_if_paid",
            new=AsyncMock(return_value=False),
        ):
            resp = await svc.get_my_order(int(order.id), customer_id=42, participant_token=None)
        self.assertEqual(resp.code, 200)
        self.assertEqual(resp.data["pickup_no"], "12")

    async def test_dining_serialize_includes_pickup_no(self):
        from app.services.dining_session_service import DiningSessionService

        r1 = await create_order(self._body(table="A10", pickup_no="15"), make_merchant_request(), self.db)
        order = await self.db.get(Order, int(r1.data["id"]))
        svc = DiningSessionService(self.db)
        data = svc._serialize_order(order, [])
        self.assertEqual(data["pickup_no"], "15")


if __name__ == "__main__":
    unittest.main()
