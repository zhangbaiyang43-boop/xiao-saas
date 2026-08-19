import asyncio
import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
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
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.schemas.consumption import CreateConsumptionRequest
from app.services.coupon_service import CouponService
from app.services.order_payment_service import OrderPaymentService
from app.services.subscription_service import STATUS_ACTIVE, SubscriptionService

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

        # A real file-backed SQLite DB, not :memory: -- see
        # tests/test_optional_side_effect_wiring.py for why: a nested
        # optional_capability_enabled() session mid-transaction can spuriously
        # roll back this session's pending writes under :memory:, a
        # SQLite/aiosqlite test-only artifact absent on any real DB.
        self._db_file = f"{tempfile.gettempdir()}/f1fd1a_member_coupon_{uuid.uuid4().hex}.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_file}")
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
        # Phase F1F-C: manual consumption creation (POST /api/v1/consumptions/)
        # is now gated behind CUSTOMER_CONSUMPTION (PRO). This file predates
        # subscription-awareness and tests coupon auto-issue rule selection,
        # unrelated to plan tier -- give TENANT_A a real PRO baseline so the
        # manual-consumption call under test keeps succeeding.
        self.db.add_all(
            [
                Plan(code="FREE", name="免费版", is_active=True, price_month_cents=0, price_year_cents=0, sort_order=0),
                Plan(code="STANDARD", name="普通版", is_active=True, price_month_cents=5900, price_year_cents=60900, sort_order=1),
                Plan(code="PRO", name="专业版", is_active=True, price_month_cents=9900, price_year_cents=102200, sort_order=2),
            ]
        )
        await self.db.commit()

        pro_plan = await SubscriptionService(self.db).get_plan_by_code("PRO")
        now = datetime.utcnow()
        self.db.add(Subscription(
            tenant_id=TENANT_A, plan_id=pro_plan.id, status=STATUS_ACTIVE,
            started_at=now, ends_at=now + timedelta(days=30),
        ))
        await self.db.commit()

        # Phase F1F-D1A: order_payment_service.py now calls
        # optional_capability_enabled() inside _on_payment_success, which opens
        # its own AsyncSessionLocal() session -- point that factory at this
        # test's own in-memory engine instead of the real production DB.
        self._session_patch = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._session_patch.start()

        self.captured_rule_types: list[str] = []
        captured = self.captured_rule_types

        async def record_issue(
            _svc,
            customer_id,
            rule_type,
            consumption_amount=None,
            auto_commit=True,
        ):
            captured.append(rule_type)
            return {"success_count": 1, "source": rule_type}

        self._issue_patcher = patch.object(CouponService, "issue_auto_coupon", record_issue)
        self._issue_patcher.start()

        self._event_patcher = patch.object(event_bus, "dispatch", new=AsyncMock(return_value=[]))
        self._event_patcher.start()

    async def asyncTearDown(self):
        self._issue_patcher.stop()
        self._event_patcher.stop()
        self._session_patch.stop()
        settings.REDIS_ENABLED = self._original_redis_enabled
        await self.db.close()
        await self.engine.dispose()
        try:
            os.remove(self._db_file)
        except OSError:
            pass

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
