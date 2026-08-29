import asyncio
from datetime import datetime, timedelta
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import create_demo_launch_code
from app.models.base import Base
from app.models.dining import DiningSession
from app.models.entrance_code import EntranceCode
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.services.demo_session_service import (
    DemoActionDeniedError,
    DemoInvalidLaunchError,
    DemoOrderNotFoundError,
    DemoPoolFullError,
    DemoRateLimitedError,
    DemoSessionService,
    DemoUnavailableError,
    enforce_demo_start_limit,
)
from app.utils.id_generator import generate_snowflake_id


if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class FakePipeline:
    def __init__(self, values=None, failure: Exception | None = None):
        self.values = values or [1, True, 1, True]
        self.failure = failure
        self.commands = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def incr(self, key: str):
        self.commands.append(("incr", key))
        return self

    def expire(self, key: str, ttl: int):
        self.commands.append(("expire", key, ttl))
        return self

    async def execute(self):
        if self.failure:
            raise self.failure
        return self.values


class FakeRedis:
    def __init__(self, pipeline: FakePipeline):
        self._pipeline = pipeline

    def pipeline(self, *, transaction: bool):
        if not transaction:
            raise AssertionError("Demo rate limit must use an atomic pipeline")
        return self._pipeline


class DemoStartRateLimitTest(unittest.IsolatedAsyncioTestCase):
    @patch("app.services.demo_session_service.settings.REDIS_ENABLED", False)
    async def test_disabled_redis_fails_closed(self):
        with self.assertRaises(DemoUnavailableError):
            await enforce_demo_start_limit("127.0.0.1", "launch-secret")

    @patch("app.services.demo_session_service.settings.REDIS_ENABLED", True)
    @patch("app.services.demo_session_service.settings.DEMO_START_IP_LIMIT_PER_MINUTE", 5)
    @patch("app.services.demo_session_service.settings.DEMO_START_CODE_LIMIT_PER_MINUTE", 20)
    async def test_limit_counters_do_not_store_raw_launch_code(self):
        pipeline = FakePipeline(values=[1, True, 1, True])

        with patch(
            "app.services.demo_session_service.redis_client", FakeRedis(pipeline)
        ):
            await enforce_demo_start_limit("127.0.0.1", "launch-secret")

        keys = [command[1] for command in pipeline.commands if command[0] == "incr"]
        self.assertEqual(len(keys), 2)
        self.assertTrue(all("launch-secret" not in key for key in keys))

    @patch("app.services.demo_session_service.settings.REDIS_ENABLED", True)
    @patch("app.services.demo_session_service.settings.DEMO_START_IP_LIMIT_PER_MINUTE", 5)
    @patch("app.services.demo_session_service.settings.DEMO_START_CODE_LIMIT_PER_MINUTE", 20)
    async def test_exceeded_counter_is_rejected(self):
        pipeline = FakePipeline(values=[6, True, 1, True])

        with patch(
            "app.services.demo_session_service.redis_client", FakeRedis(pipeline)
        ):
            with self.assertRaises(DemoRateLimitedError):
                await enforce_demo_start_limit("127.0.0.1", "launch-secret")

    @patch("app.services.demo_session_service.settings.REDIS_ENABLED", True)
    async def test_redis_error_fails_closed(self):
        pipeline = FakePipeline(failure=ConnectionError("redis unavailable"))

        with patch(
            "app.services.demo_session_service.redis_client", FakeRedis(pipeline)
        ):
            with self.assertRaises(DemoUnavailableError):
                await enforce_demo_start_limit("127.0.0.1", "launch-secret")


class DemoSessionAllocationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.db = session_factory()

        self.settings_patch = patch.multiple(
            "app.services.demo_session_service.settings",
            DEMO_TENANT_ID="demo-tenant",
            DEMO_SESSION_MINUTES=30,
            DEMO_TABLE_POOL_SIZE=20,
        )
        self.settings_patch.start()
        self.limit_patch = patch(
            "app.services.demo_session_service.enforce_demo_start_limit",
            new_callable=AsyncMock,
        )
        self.mock_limit = self.limit_patch.start()
        self.token_patch = patch(
            "app.services.demo_session_service.create_demo_session_token",
            return_value="scoped-demo-token",
        )
        self.mock_token = self.token_patch.start()

        self.db.add(
            Tenant(
                tenant_id="demo-tenant",
                name="开心点单体验店",
                password_hash="x",
                status=True,
                is_open=True,
                payment_mode="postpay",
            )
        )
        self.add_demo_code("DEMO-01", "/static/entrance-codes/demo-01.png")
        self.add_demo_code("DEMO-02", "/static/entrance-codes/demo-02.png")
        await self.db.commit()

        self.launch_code = create_demo_launch_code(expires_delta=timedelta(minutes=5))
        self.service = DemoSessionService(self.db)

    async def asyncTearDown(self):
        self.token_patch.stop()
        self.limit_patch.stop()
        self.settings_patch.stop()
        await self.db.close()
        await self.engine.dispose()

    def add_demo_code(self, table_no: str, image_url: str) -> None:
        code_id = generate_snowflake_id()
        self.db.add(
            EntranceCode(
                id=code_id,
                tenant_id="demo-tenant",
                name=table_no,
                channel="DEMO",
                scene=f"D{code_id}"[:32],
                image_url=image_url,
                table_no=table_no,
                entry_type="table",
                status=1,
            )
        )

    async def test_start_allocates_open_session_and_returns_table_code(self):
        result = await self.service.start_session(self.launch_code, "127.0.0.1")

        self.assertEqual(result["tableNo"], "DEMO-01")
        self.assertEqual(
            result["customerCodeImageUrl"], "/static/entrance-codes/demo-01.png"
        )
        self.assertEqual(result["shopName"], "开心点单体验店")
        self.assertEqual(result["demoToken"], "scoped-demo-token")
        self.assertTrue(result["diningSessionId"])
        self.mock_limit.assert_awaited_once_with("127.0.0.1", self.launch_code)

    async def test_two_active_starts_use_different_tables(self):
        first = await self.service.start_session(self.launch_code, "127.0.0.1")
        second = await self.service.start_session(self.launch_code, "127.0.0.2")

        self.assertNotEqual(first["tableNo"], second["tableNo"])

    async def test_pool_full_raises_without_reusing_an_open_table(self):
        await self.service.start_session(self.launch_code, "127.0.0.1")
        await self.service.start_session(self.launch_code, "127.0.0.2")

        with self.assertRaises(DemoPoolFullError):
            await self.service.start_session(self.launch_code, "127.0.0.3")

    async def test_expired_open_session_is_closed_before_reuse(self):
        stale_time = datetime.utcnow() - timedelta(minutes=31)
        stale = DiningSession(
            tenant_id="demo-tenant",
            table_no="DEMO-01",
            status="OPEN",
            active_key="demo-tenant:DEMO-01",
            started_at=stale_time,
            last_activity_at=stale_time,
        )
        self.db.add(stale)
        await self.db.commit()

        result = await self.service.start_session(self.launch_code, "127.0.0.1")

        await self.db.refresh(stale)
        self.assertEqual(stale.status, "EXPIRED")
        self.assertIsNone(stale.active_key)
        self.assertEqual(result["tableNo"], "DEMO-01")
        self.assertNotEqual(result["diningSessionId"], str(stale.id))

    async def test_invalid_launch_code_is_rejected_before_allocation(self):
        with self.assertRaises(DemoInvalidLaunchError):
            await self.service.start_session("not-a-token", "127.0.0.1")

        self.mock_limit.assert_not_awaited()

    @patch("app.services.demo_session_service.settings.DEMO_TENANT_ID", "")
    async def test_empty_demo_tenant_disables_allocation(self):
        with self.assertRaises(DemoUnavailableError):
            await self.service.start_session(self.launch_code, "127.0.0.1")


class DemoOrderScopeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.db = session_factory()
        self.db.add_all(
            [
                Tenant(
                    tenant_id="demo-tenant",
                    name="开心点单体验店",
                    password_hash="x",
                    status=True,
                    is_open=True,
                    payment_mode="postpay",
                ),
                Tenant(
                    tenant_id="other-tenant",
                    name="其他门店",
                    password_hash="x",
                    status=True,
                    is_open=True,
                    payment_mode="postpay",
                ),
            ]
        )
        now = datetime.utcnow()
        self.session_a = DiningSession(
            tenant_id="demo-tenant",
            table_no="DEMO-01",
            status="OPEN",
            active_key="demo-tenant:DEMO-01",
            started_at=now,
            last_activity_at=now,
        )
        self.session_b = DiningSession(
            tenant_id="demo-tenant",
            table_no="DEMO-02",
            status="OPEN",
            active_key="demo-tenant:DEMO-02",
            started_at=now,
            last_activity_at=now,
        )
        self.other_session = DiningSession(
            tenant_id="other-tenant",
            table_no="OTHER-01",
            status="OPEN",
            active_key="other-tenant:OTHER-01",
            started_at=now,
            last_activity_at=now,
        )
        self.db.add_all([self.session_a, self.session_b, self.other_session])
        await self.db.flush()

        self.order_a = self.make_order(
            tenant_id="demo-tenant",
            session=self.session_a,
            phone="13800000000",
            wx_transaction_id="wx-secret-a",
        )
        self.order_b = self.make_order(
            tenant_id="demo-tenant",
            session=self.session_b,
            phone="13900000000",
            wx_transaction_id="wx-secret-b",
        )
        self.other_order = self.make_order(
            tenant_id="other-tenant",
            session=self.other_session,
            phone="13700000000",
            wx_transaction_id="wx-secret-other",
        )
        self.db.add_all([self.order_a, self.order_b, self.other_order])
        await self.db.flush()
        self.db.add_all(
            [
                OrderItem(
                    id=generate_snowflake_id(),
                    order_id=self.order_a.id,
                    name="招牌牛肉饭",
                    price="28.00",
                    qty=2,
                    item_remark="少辣",
                ),
                OrderItem(
                    id=generate_snowflake_id(),
                    order_id=self.order_b.id,
                    name="酸辣粉",
                    price="18.00",
                    qty=1,
                ),
            ]
        )
        await self.db.commit()
        self.service = DemoSessionService(self.db)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    @staticmethod
    def make_order(
        *, tenant_id: str, session: DiningSession, phone: str, wx_transaction_id: str
    ) -> Order:
        return Order(
            tenant_id=tenant_id,
            table_no=session.table_no,
            dining_session_id=session.id,
            status="pending",
            payment_status="unpaid",
            payment_mode="postpay",
            total="56.00",
            remark="不要香菜",
            phone=phone,
            wx_transaction_id=wx_transaction_id,
        )

    async def test_snapshot_returns_only_token_session_and_no_pii(self):
        data = await self.service.get_session_snapshot(
            "demo-tenant", self.session_a.id
        )

        self.assertEqual(data["diningSessionId"], str(self.session_a.id))
        self.assertEqual(data["tableNo"], "DEMO-01")
        self.assertEqual(
            [order["orderId"] for order in data["orders"]], [str(self.order_a.id)]
        )
        self.assertEqual(
            data["orders"][0]["items"],
            [{"name": "招牌牛肉饭", "quantity": 2, "remark": "少辣"}],
        )
        forbidden = {
            "phone",
            "openid",
            "customerId",
            "transactionId",
            "paymentTransactionId",
            "paymentStatus",
        }
        self.assertTrue(forbidden.isdisjoint(data["orders"][0]))
        self.assertNotIn("13800000000", str(data))
        self.assertNotIn("wx-secret-a", str(data))

    async def test_cross_session_status_update_looks_not_found(self):
        with self.assertRaises(DemoOrderNotFoundError):
            await self.service.update_order_status(
                tenant_id="demo-tenant",
                dining_session_id=self.session_a.id,
                order_id=self.order_b.id,
                status="preparing",
            )

    async def test_only_pending_preparing_done_transitions_are_exposed(self):
        preparing = await self.service.update_order_status(
            tenant_id="demo-tenant",
            dining_session_id=self.session_a.id,
            order_id=self.order_a.id,
            status="preparing",
        )
        done = await self.service.update_order_status(
            tenant_id="demo-tenant",
            dining_session_id=self.session_a.id,
            order_id=self.order_a.id,
            status="done",
        )

        self.assertEqual(preparing["status"], "preparing")
        self.assertEqual(done["status"], "done")
        with self.assertRaises(DemoActionDeniedError):
            await self.service.update_order_status(
                tenant_id="demo-tenant",
                dining_session_id=self.session_a.id,
                order_id=self.order_a.id,
                status="settled",
            )

    async def test_serve_is_scoped_and_idempotent(self):
        self.order_a.status = "done"
        await self.db.commit()

        first = await self.service.serve_order(
            tenant_id="demo-tenant",
            dining_session_id=self.session_a.id,
            order_id=self.order_a.id,
        )
        second = await self.service.serve_order(
            tenant_id="demo-tenant",
            dining_session_id=self.session_a.id,
            order_id=self.order_a.id,
        )

        self.assertTrue(first["servedAt"])
        self.assertEqual(second["servedAt"], first["servedAt"])

    async def test_cross_tenant_order_looks_not_found(self):
        with self.assertRaises(DemoOrderNotFoundError):
            await self.service.serve_order(
                tenant_id="demo-tenant",
                dining_session_id=self.session_a.id,
                order_id=self.other_order.id,
            )


if __name__ == "__main__":
    unittest.main()
