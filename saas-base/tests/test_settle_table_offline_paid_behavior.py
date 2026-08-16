import asyncio
import unittest
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.dining import DiningSession
from app.models.order import Order, OrderItem
from app.models.consumption import Consumption
from app.models.customer import Customer
from app.models.member_account import MemberAccount
from app.models.point_ledger import PointLedger
from app.api.v1.orders import settle_table
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT = "tenant-settle-behavior"


class FakeRequest:
    def __init__(self, **state):
        if state.get("token_type") == "merchant":
            state.setdefault("role", "owner")
            state.setdefault("account_id", None)
        self.state = SimpleNamespace(**state)


class SettleTableOfflinePaidBehaviorTest(unittest.IsolatedAsyncioTestCase):
    """真正跑一遍 settle_table（而不是只断言源码字符串），因为这个 bug 恰恰是
    "每个函数单独看都对，拼起来才错"——source-string 合同测试完全测不出来。"""

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_open_session(self, table_no):
        now = datetime.utcnow()
        session = DiningSession(
            tenant_id=TENANT,
            table_no=table_no,
            status="OPEN",
            active_key=f"{TENANT}:{table_no}",
            started_at=now,
            last_activity_at=now,
        )
        self.db.add(session)
        await self.db.flush()
        await self.db.commit()
        return session

    async def _make_order(self, session, payment_mode, status="done", payment_status="unpaid", total="20.00"):
        order = Order(
            tenant_id=TENANT,
            dining_session_id=session.id,
            table_no=session.table_no,
            total=total,
            status=status,
            payment_status=payment_status,
            payment_mode=payment_mode,
        )
        self.db.add(order)
        await self.db.flush()
        self.db.add(OrderItem(id=generate_snowflake_id(), order_id=order.id, name="菜品", price=total, qty=1))
        await self.db.commit()
        return order

    async def _make_customer(self, phone="13900000001", openid="openid-settle"):
        customer = Customer(
            tenant_id=TENANT,
            openid=openid,
            phone=phone,
            name="会员顾客",
            status=1,
        )
        self.db.add(customer)
        await self.db.flush()
        await self.db.commit()
        return customer
    async def test_postpay_order_settled_via_table_settle_gets_marked_offline_paid(self):
        # 小程序下单时不分付款模式都会建 dining_session，商家后台桌台视图也不分模式都会把订单
        # 分组进同一个"结账"按钮，所以餐后付款订单实际上也是走 settle_table 结账——
        # 这条路径必须把它标记为线下已付款，否则会出现"已结账但显示未支付"的黑洞订单。
        session = await self._make_open_session("A1")
        order = await self._make_order(session, payment_mode="postpay")

        request = FakeRequest(tenant_id=TENANT, token_type="merchant", user_id="u1")
        res = await settle_table({"table_no": "A1", "dining_session_id": str(session.id)}, request, self.db)

        self.assertEqual(res.code, 200)
        await self.db.refresh(order)
        self.assertEqual(order.status, "settled")
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.payment_method, "offline")

    async def test_table_account_order_settled_via_table_settle_still_marked_offline_paid(self):
        session = await self._make_open_session("B2")
        order = await self._make_order(session, payment_mode="table_account")

        request = FakeRequest(tenant_id=TENANT, token_type="merchant", user_id="u1")
        await settle_table({"table_no": "B2", "dining_session_id": str(session.id)}, request, self.db)

        await self.db.refresh(order)
        self.assertEqual(order.status, "settled")
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.payment_method, "offline")

    async def test_prepay_order_advances_to_settled_without_being_touched_by_offline_paid_marking(self):
        # 先付后厨的订单到 done 时早就已经 payment_status=="paid" 了。settlement_orders 必须
        # 照样把它推进到 settled（否则这一桌永远清不掉、消费记录也永远不会生成），但
        # _mark_order_offline_paid 只认 table_account/postpay，不应该碰它、也不应该覆盖已有的 payment_method。
        session = await self._make_open_session("C3")
        order = await self._make_order(session, payment_mode="prepay", payment_status="paid")

        request = FakeRequest(tenant_id=TENANT, token_type="merchant", user_id="u1")
        res = await settle_table({"table_no": "C3", "dining_session_id": str(session.id)}, request, self.db)

        self.assertEqual(res.code, 200)
        self.assertEqual(res.data["settled_count"], 1)
        self.assertEqual(res.data["paid_synced_count"], 0)
        await self.db.refresh(order)
        self.assertEqual(order.status, "settled")
        self.assertEqual(order.payment_status, "paid")
        self.assertIsNone(order.payment_method)

    async def test_settled_prepay_order_gets_a_consumption_record_for_logged_in_customer(self):
        # _record_order_consumption 只在订单真正推进到 settled 时触发；先付后厨的订单如果
        # 一直卡在 done，顾客端"消费记录"页就永远看不到这笔——这里验证登录顾客确实能拿到记录。
        from sqlalchemy.future import select as sa_select

        session = await self._make_open_session("D4")
        order = await self._make_order(session, payment_mode="prepay", payment_status="paid")
        order.customer_id = 8888
        await self.db.commit()

        request = FakeRequest(tenant_id=TENANT, token_type="merchant", user_id="u1")
        await settle_table({"table_no": "D4", "dining_session_id": str(session.id)}, request, self.db)

        result = await self.db.execute(
            sa_select(Consumption).where(Consumption.customer_id == 8888)
        )
        self.assertIsNotNone(result.scalar_one_or_none())

    async def test_postpay_table_settle_records_member_assets_once(self):
        from sqlalchemy.future import select as sa_select

        customer = await self._make_customer()
        session = await self._make_open_session("E5")
        order = await self._make_order(session, payment_mode="postpay", total="20.00")
        order.customer_id = customer.id
        await self.db.commit()

        request = FakeRequest(tenant_id=TENANT, token_type="merchant", user_id="u1")
        await settle_table({"table_no": "E5", "dining_session_id": str(session.id)}, request, self.db)

        account_result = await self.db.execute(
            sa_select(MemberAccount).where(
                MemberAccount.tenant_id == TENANT,
                MemberAccount.customer_id == customer.id,
            )
        )
        account = account_result.scalar_one_or_none()
        self.assertIsNotNone(account)
        self.assertEqual(str(account.total_consumption), "20.00")
        self.assertEqual(str(account.yearly_consumption), "20.00")
        self.assertEqual(account.points_balance, 20)

        ledger_result = await self.db.execute(
            sa_select(PointLedger).where(
                PointLedger.tenant_id == TENANT,
                PointLedger.customer_id == customer.id,
                PointLedger.event_type == "consumption",
                PointLedger.ref_id == str(order.id),
            )
        )
        self.assertEqual(len(ledger_result.scalars().all()), 1)

    async def test_table_account_settle_records_member_assets_once(self):
        from sqlalchemy.future import select as sa_select

        customer = await self._make_customer(phone="13900000002", openid="openid-table-account")
        session = await self._make_open_session("F6")
        order = await self._make_order(session, payment_mode="table_account", total="30.00")
        order.customer_id = customer.id
        await self.db.commit()

        request = FakeRequest(tenant_id=TENANT, token_type="merchant", user_id="u1")
        await settle_table({"table_no": "F6", "dining_session_id": str(session.id)}, request, self.db)

        account_result = await self.db.execute(
            sa_select(MemberAccount).where(
                MemberAccount.tenant_id == TENANT,
                MemberAccount.customer_id == customer.id,
            )
        )
        account = account_result.scalar_one_or_none()
        self.assertIsNotNone(account)
        self.assertEqual(str(account.total_consumption), "30.00")
        self.assertEqual(str(account.yearly_consumption), "30.00")
        self.assertEqual(account.points_balance, 30)

        ledger_result = await self.db.execute(
            sa_select(PointLedger).where(
                PointLedger.tenant_id == TENANT,
                PointLedger.customer_id == customer.id,
                PointLedger.event_type == "consumption",
                PointLedger.ref_id == str(order.id),
            )
        )
        self.assertEqual(len(ledger_result.scalars().all()), 1)


if __name__ == "__main__":
    unittest.main()


