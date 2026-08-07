import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.consumptions import create_consumption
from app.config import settings
from app.core.events import event_bus
from app.models.base import Base
from app.models.consumption import Consumption
from app.models.customer import Customer
from app.models.order import Order
from app.models.tenant import Tenant
from app.schemas.consumption import CreateConsumptionRequest
from app.services.coupon_service import CouponService
from app.services.order_payment_service import OrderPaymentService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


def make_merchant_request(tenant_id=TENANT_A, path="/api/v1/consumptions/"):
    req = Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    req.state.tenant_id = tenant_id
    req.state.token_type = "merchant"
    req.state.user_id = "staff-1"
    return req


class MemberCouponRuleConsistencyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._original_redis_enabled = settings.REDIS_ENABLED
        settings.REDIS_ENABLED = False

        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.tenant = Tenant(
            tenant_id=TENANT_A,
            name="Test Restaurant",
            password_hash="x",
            status=True,
            is_open=True,
        )
        self.db.add(self.tenant)
        self.customer = Customer(tenant_id=TENANT_A, openid="openid-1", status=1)
        self.db.add(self.customer)
        await self.db.commit()

        self.captured_rule_types: list[str] = []
        captured = self.captured_rule_types

        async def record_issue(_svc, customer_id, rule_type, consumption_amount=None):
            captured.append(rule_type)
            return {"success_count": 1, "source": rule_type}

        self._issue_patcher = patch.object(CouponService, "issue_auto_coupon", record_issue)
        self._issue_patcher.start()

        self._event_patcher = patch.object(event_bus, "dispatch", new=AsyncMock(return_value=[]))
        self._event_patcher.start()

    async def asyncTearDown(self):
        self._issue_patcher.stop()
        self._event_patcher.stop()
        settings.REDIS_ENABLED = self._original_redis_enabled
        await self.db.close()
        await self.engine.dispose()

    async def _pay_order_online(self, customer_id):
        order = Order(
            tenant_id=TENANT_A,
            customer_id=customer_id,
            table_no="A1",
            total="50.00",
            status="pending_payment",
            payment_status="unpaid",
            payment_mode="prepay",
        )
        self.db.add(order)
        await self.db.commit()

        svc = OrderPaymentService(self.db)
        await svc._on_payment_success(order, payment_method="wxpay")
        return order

    async def _create_manual_consumption(self, customer_id, amount="50.00"):
        payload = CreateConsumptionRequest(
            customer_id=customer_id,
            project="manual-entry",
            amount=amount,
        )
        result = await create_consumption(payload, make_merchant_request(), db=self.db)
        self.assertEqual(result.code, 200)
        return result

    async def _seed_paid_order(self, customer_id):
        order = Order(
            tenant_id=TENANT_A,
            customer_id=customer_id,
            table_no="B1",
            total="40.00",
            status="done",
            payment_status="paid",
            payment_mode="prepay",
            payment_time=datetime.utcnow().isoformat(),
        )
        self.db.add(order)
        await self.db.commit()
        return order

    async def _seed_manual_consumption(self, customer_id):
        consumption = Consumption(
            tenant_id=TENANT_A,
            customer_id=customer_id,
            project="historical-manual",
            amount="35.00",
            consume_time=datetime.utcnow(),
        )
        self.db.add(consumption)
        await self.db.commit()
        return consumption

    async def test_first_online_payment_uses_new_customer_coupon(self):
        await self._pay_order_online(self.customer.id)
        self.assertEqual(self.captured_rule_types, ["new_customer_coupon"])

    async def test_first_manual_consumption_uses_new_customer_coupon(self):
        await self._create_manual_consumption(self.customer.id)
        self.assertEqual(self.captured_rule_types, ["new_customer_coupon"])

    async def test_manual_consumption_after_paid_order_uses_consumption_coupon(self):
        await self._seed_paid_order(self.customer.id)
        await self._create_manual_consumption(self.customer.id)
        self.assertEqual(self.captured_rule_types, ["consumption_coupon"])

    async def test_online_payment_after_manual_consumption_uses_consumption_coupon(self):
        await self._seed_manual_consumption(self.customer.id)
        await self._pay_order_online(self.customer.id)
        self.assertEqual(self.captured_rule_types, ["consumption_coupon"])


if __name__ == "__main__":
    unittest.main()
