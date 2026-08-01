import asyncio
import unittest
from datetime import datetime

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.dining import DiningParticipant, DiningSession
from app.models.order import Order, OrderItem
from app.services.dining_session_service import (
    DiningSessionService,
    hash_participant_token,
    make_client_id,
)
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


class TableAccountDetailTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.service = DiningSessionService(self.db)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_session(self, tenant_id="tenant-a", table_no="A12"):
        now = datetime.utcnow()
        session = DiningSession(
            tenant_id=tenant_id,
            table_no=table_no,
            status="OPEN",
            active_key=f"{tenant_id}:{table_no}",
            started_at=now,
            last_activity_at=now,
        )
        self.db.add(session)
        await self.db.flush()

        raw_token = f"guest-token-{tenant_id}-{table_no}"
        participant = DiningParticipant(
            tenant_id=tenant_id,
            session_id=session.id,
            client_id=make_client_id(),
            guest_token_hash=hash_participant_token(raw_token),
            joined_at=now,
            last_active_at=now,
        )
        self.db.add(participant)
        await self.db.flush()
        await self.db.commit()
        return session, raw_token

    async def _make_order(self, session, tenant_id, status, payment_status, total, items, payment_mode="table_account"):
        order = Order(
            tenant_id=tenant_id,
            dining_session_id=session.id,
            table_no=session.table_no,
            total=total,
            status=status,
            payment_status=payment_status,
            payment_mode=payment_mode,
        )
        self.db.add(order)
        await self.db.flush()
        for name, price, qty in items:
            self.db.add(OrderItem(id=generate_snowflake_id(), order_id=order.id, name=name, price=price, qty=qty))
        await self.db.commit()
        return order

    async def test_open_session_with_two_unpaid_sub_orders_returns_five_items_and_correct_total(self):
        session, token = await self._make_session()
        await self._make_order(
            session, TENANT_A, status="pending", payment_status="unpaid",
            total="32.80", items=[("凉拌冻肉", "16.40", 2)],
        )
        await self._make_order(
            session, TENANT_A, status="preparing", payment_status="unpaid",
            total="76.40", items=[("宫保鸡丁", "25.00", 2), ("米饭", "13.20", 1)],
        )

        result = await self.service.list_session_orders(
            tenant_id=TENANT_A, dining_session_id=session.id, participant_token=token,
        )

        self.assertEqual(len(result["orders"]), 2)
        self.assertEqual(result["item_count"], 5)
        self.assertEqual(result["table_total"], "109.20")
        for order in result["orders"]:
            self.assertEqual(order["payment_mode"], "table_account")
            self.assertTrue(len(order["items"]) > 0)

    async def test_confirmed_and_preparing_orders_are_returned_not_only_paid(self):
        session, token = await self._make_session()
        await self._make_order(
            session, TENANT_A, status="preparing", payment_status="unpaid",
            total="10.00", items=[("A", "10.00", 1)],
        )
        await self._make_order(
            session, TENANT_A, status="pending", payment_status="paid",
            total="20.00", items=[("B", "20.00", 1)],
        )

        result = await self.service.list_session_orders(
            tenant_id=TENANT_A, dining_session_id=session.id, participant_token=token,
        )
        statuses = {o["status"] for o in result["orders"]}
        self.assertEqual(statuses, {"preparing", "pending"})
        self.assertEqual(result["item_count"], 2)
        self.assertEqual(result["table_total"], "30.00")

    async def test_cancelled_order_is_returned_but_excluded_from_total_and_count(self):
        session, token = await self._make_session()
        await self._make_order(
            session, TENANT_A, status="pending", payment_status="unpaid",
            total="10.00", items=[("A", "10.00", 1)],
        )
        await self._make_order(
            session, TENANT_A, status="cancelled", payment_status="unpaid",
            total="99.00", items=[("Cancelled dish", "99.00", 3)],
        )

        result = await self.service.list_session_orders(
            tenant_id=TENANT_A, dining_session_id=session.id, participant_token=token,
        )
        self.assertEqual(len(result["orders"]), 2)
        self.assertEqual(result["item_count"], 1)
        self.assertEqual(result["table_total"], "10.00")

    async def test_different_customer_in_same_session_can_still_see_table_bill(self):
        session, _token = await self._make_session()
        now = datetime.utcnow()
        other_participant = DiningParticipant(
            tenant_id=TENANT_A,
            session_id=session.id,
            customer_id=555,
            joined_at=now,
            last_active_at=now,
        )
        self.db.add(other_participant)
        await self.db.commit()
        await self._make_order(
            session, TENANT_A, status="pending", payment_status="unpaid",
            total="15.00", items=[("A", "15.00", 1)],
        )

        result = await self.service.list_session_orders(
            tenant_id=TENANT_A, dining_session_id=session.id, customer_id=555,
        )
        self.assertEqual(result["item_count"], 1)
        self.assertEqual(result["table_total"], "15.00")

    async def test_different_table_session_does_not_leak_into_this_one(self):
        session, token = await self._make_session(table_no="A12")
        other_session, _other_token = await self._make_session(table_no="B7")
        await self._make_order(
            session, TENANT_A, status="pending", payment_status="unpaid",
            total="10.00", items=[("A", "10.00", 1)],
        )
        await self._make_order(
            other_session, TENANT_A, status="pending", payment_status="unpaid",
            total="500.00", items=[("Other table dish", "500.00", 9)],
        )

        result = await self.service.list_session_orders(
            tenant_id=TENANT_A, dining_session_id=session.id, participant_token=token,
        )
        self.assertEqual(result["item_count"], 1)
        self.assertEqual(result["table_total"], "10.00")

    async def test_different_tenant_does_not_leak_into_this_session(self):
        session, token = await self._make_session(tenant_id=TENANT_A)
        await self._make_order(
            session, TENANT_A, status="pending", payment_status="unpaid",
            total="10.00", items=[("A", "10.00", 1)],
        )

        result = await self.service.list_session_orders(
            tenant_id=TENANT_B, dining_session_id=session.id, participant_token=token,
        )
        self.assertEqual(result["orders"], [])
        self.assertEqual(result["item_count"], 0)
        self.assertEqual(result["table_total"], "0.00")

    async def test_session_not_found_returns_empty_not_error(self):
        # 会话真的不存在时也要走 identity_mismatch=True 这条路——客户端没法区分
        # "这一桌真的没人点单"和"传的会话号本身就是错的"，两种都该提示重新建立
        # 本桌身份（见 dining_session_service.py:232 的说明），不是裸的空结果。
        result = await self.service.list_session_orders(
            tenant_id=TENANT_A, dining_session_id=999999, participant_token="nope",
        )
        self.assertEqual(
            result,
            {"orders": [], "table_total": "0.00", "item_count": 0, "identity_mismatch": True},
        )

    async def test_participant_count_reflects_second_join_even_before_anyone_orders(self):
        # "客如云同款"提示功能就是靠这个场景撑起来的：第一个人还在点餐、什么都没提交，
        # 第二个人扫码加入——这时候 orders 表里还是空的，必须在"没有订单"提前返回之前
        # 就把人数算出来，不然这个场景永远检测不到人数变化。
        session, token = await self._make_session()
        self.assertEqual(
            (await self.service.list_session_orders(
                tenant_id=TENANT_A, dining_session_id=session.id, participant_token=token,
            ))["participant_count"],
            1,
        )

        now = datetime.utcnow()
        self.db.add(DiningParticipant(
            tenant_id=TENANT_A, session_id=session.id, customer_id=888,
            joined_at=now, last_active_at=now,
        ))
        await self.db.commit()

        result = await self.service.list_session_orders(
            tenant_id=TENANT_A, dining_session_id=session.id, participant_token=token,
        )
        self.assertEqual(result["participant_count"], 2)
        self.assertEqual(result["orders"], [])  # 没人下单，但人数已经能看到变化了

    async def test_participant_count_stays_correct_once_orders_exist(self):
        session, token = await self._make_session()
        now = datetime.utcnow()
        self.db.add(DiningParticipant(
            tenant_id=TENANT_A, session_id=session.id, customer_id=999,
            joined_at=now, last_active_at=now,
        ))
        await self.db.commit()
        await self._make_order(
            session, TENANT_A, status="pending", payment_status="unpaid",
            total="10.00", items=[("A", "10.00", 1)],
        )

        result = await self.service.list_session_orders(
            tenant_id=TENANT_A, dining_session_id=session.id, participant_token=token,
        )
        self.assertEqual(result["participant_count"], 2)
        self.assertEqual(len(result["orders"]), 1)


if __name__ == "__main__":
    unittest.main()
