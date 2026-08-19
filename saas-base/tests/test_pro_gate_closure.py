"""Phase F1F-CX — PRO interactive contract closure.

Closes two gaps left by F1F-C, both discovered by re-reading the frozen
contract against real source rather than adding new capabilities:

1. POST /coupons/{id}/recall (single-coupon manual recall) was left ungated
   in F1F-C on the assumption it might be an order-correction path. Source
   reverify here confirms CouponService.recall_coupon has exactly one call
   site (this route), only touches UNUSED coupons, and is never reached by
   the cancel-unlock/refund-rollback helpers in coupon_service.py. It is a
   merchant-proactive marketing/administrative action -- gated under
   COUPONS, same as batch recall.

2. customers.py's create/update/status/restore/delete/merge/identities
   mutations were left ungated in F1F-C (only list/detail/timeline/logs
   were gated). The frozen CUSTOMER_CONSUMPTION contract requires all
   merchant CRM actions, not just reads, to be PRO-gated. Source reverify
   confirms CustomerService.create_customer is also called directly by
   member.py's login_or_create (customer self-registration) -- a
   completely separate system-core path that does not go through this
   route and is therefore unaffected by gating the route.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.v1.coupons import recall_coupon
from app.api.v1.customers import (
    create_customer,
    delete_customer,
    get_customer,
    get_customer_identities,
    merge_customers,
    restore_customer,
    update_customer,
    update_customer_status,
)
from app.core.tenant_context import TenantContext
from app.models.base import Base
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.schemas.coupon import RecallCouponRequest
from app.schemas.customer import (
    CreateCustomerRequest,
    MergeCustomerRequest,
    UpdateCustomerRequest,
    UpdateCustomerStatusRequest,
)
from app.services.subscription_service import STATUS_ACTIVE, SubscriptionService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@event.listens_for(Plan, "before_insert")
def _assign_plan_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Subscription, "before_insert")
def _assign_subscription_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Tenant, "before_insert")
def _assign_tenant_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Customer, "before_insert")
def _assign_customer_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(CouponTemplate, "before_insert")
def _assign_template_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


@event.listens_for(Coupon, "before_insert")
def _assign_coupon_id(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_request(*, tenant_id=None, method="GET", path="/x"):
    request = Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [(b"authorization", b"Bearer dummy")] if tenant_id else [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    if tenant_id is not None:
        request.state.tenant_id = tenant_id
        request.state.token_type = "merchant"
    return request


TENANT_FREE = "tenant-f1fcx-free"
TENANT_STANDARD = "tenant-f1fcx-standard"
TENANT_PRO = "tenant-f1fcx-pro"


class BaseClosureTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add_all(
            [
                Tenant(tenant_id=TENANT_FREE, name="Free Tenant", password_hash="x", status=True),
                Tenant(tenant_id=TENANT_STANDARD, name="Standard Tenant", password_hash="x", status=True),
                Tenant(tenant_id=TENANT_PRO, name="Pro Tenant", password_hash="x", status=True),
                Plan(code="FREE", name="免费版", is_active=True, price_month_cents=0, price_year_cents=0, sort_order=0),
                Plan(code="STANDARD", name="普通版", is_active=True, price_month_cents=5900, price_year_cents=60900, sort_order=1),
                Plan(code="PRO", name="专业版", is_active=True, price_month_cents=9900, price_year_cents=102200, sort_order=2),
            ]
        )
        await self.db.commit()
        self.subscription_service = SubscriptionService(self.db)
        await self._activate(TENANT_STANDARD, "STANDARD")
        await self._activate(TENANT_PRO, "PRO")

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _activate(self, tenant_id: str, plan_code: str, *, ends_delta=timedelta(days=30)):
        plan = await self.subscription_service.get_plan_by_code(plan_code)
        now = datetime.utcnow()
        sub = Subscription(
            tenant_id=tenant_id, plan_id=plan.id, status=STATUS_ACTIVE,
            started_at=now, ends_at=now + ends_delta,
        )
        self.db.add(sub)
        await self.db.commit()
        await self.db.refresh(sub)
        return sub


# ---------------------------------------------------------------------------
# PHASE 1 -- manual coupon recall
# ---------------------------------------------------------------------------

class ManualCouponRecallGateTest(BaseClosureTest):
    async def _seed_unused_coupon(self, tenant_id: str) -> Coupon:
        customer = Customer(tenant_id=tenant_id, openid=f"op-{tenant_id}", name="张三", status=1)
        self.db.add(customer)
        await self.db.commit()
        await self.db.refresh(customer)

        template = CouponTemplate(
            tenant_id=tenant_id, name="满10减2", type="FIXED", value=2, min_amount=10,
            total_stock=100, used_stock=1,
            start_time=datetime.utcnow(), end_time=datetime.utcnow() + timedelta(days=30), status=1,
        )
        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)

        coupon = Coupon(
            tenant_id=tenant_id, template_id=template.id, customer_id=customer.id,
            code=f"CODE-{tenant_id}", status="UNUSED", expire_time=datetime.utcnow() + timedelta(days=30),
        )
        self.db.add(coupon)
        await self.db.commit()
        await self.db.refresh(coupon)
        return coupon

    async def test_manual_recall_non_pro_denied_no_mutation(self):
        coupon = await self._seed_unused_coupon(TENANT_STANDARD)
        TenantContext.set_tenant_id(TENANT_STANDARD)
        try:
            resp = await recall_coupon(
                coupon.id, RecallCouponRequest(reason="测试收回"), db=self.db,
            )
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 403)
        self.assertEqual(resp.data["error_code"], "PLAN_CAPABILITY_REQUIRED")
        self.assertEqual(resp.data["capability"], "COUPONS")

        result = await self.db.execute(select(Coupon).where(Coupon.id == coupon.id))
        refreshed = result.scalar_one()
        self.assertEqual(refreshed.status, "UNUSED", "denied recall must never mutate coupon status")
        self.assertIsNone(refreshed.revoke_time)

    async def test_manual_recall_pro_allowed(self):
        coupon = await self._seed_unused_coupon(TENANT_PRO)
        TenantContext.set_tenant_id(TENANT_PRO)
        try:
            resp = await recall_coupon(
                coupon.id, RecallCouponRequest(reason="测试收回"), db=self.db,
            )
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 200)

        result = await self.db.execute(select(Coupon).where(Coupon.id == coupon.id))
        refreshed = result.scalar_one()
        self.assertEqual(refreshed.status, "REVOKED")


# ---------------------------------------------------------------------------
# PHASE 3/4 -- CUSTOMER_CONSUMPTION CRM mutation completeness
# ---------------------------------------------------------------------------

class CustomerCrmMutationGateTest(BaseClosureTest):
    async def _seed_customer(self, tenant_id: str, *, name="老客户", phone="13800000001", tags=None) -> Customer:
        customer = Customer(
            tenant_id=tenant_id, openid=f"op-{tenant_id}-{name}", name=name, phone=phone,
            tags=tags or [], status=1,
        )
        self.db.add(customer)
        await self.db.commit()
        await self.db.refresh(customer)
        return customer

    async def test_customer_create_non_pro_denied(self):
        TenantContext.set_tenant_id(TENANT_STANDARD)
        try:
            resp = await create_customer(
                CreateCustomerRequest(openid="new-op", name="新客户"),
                make_request(tenant_id=TENANT_STANDARD, method="POST", path="/api/v1/customers"),
                db=self.db,
            )
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 403)
        self.assertEqual(resp.data["capability"], "CUSTOMER_CONSUMPTION")

        result = await self.db.execute(select(Customer).where(Customer.tenant_id == TENANT_STANDARD))
        self.assertEqual(len(result.scalars().all()), 0, "denied create must not insert a Customer row")

    async def test_customer_update_non_pro_denied_no_mutation(self):
        """PHASE 4: a normal mutation."""
        customer = await self._seed_customer(TENANT_STANDARD, name="原名字", phone="13800000002")
        TenantContext.set_tenant_id(TENANT_STANDARD)
        try:
            resp = await update_customer(
                customer.id, UpdateCustomerRequest(name="改名字"),
                make_request(tenant_id=TENANT_STANDARD, method="PUT", path=f"/api/v1/customers/{customer.id}"),
                db=self.db,
            )
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 403)
        self.assertEqual(resp.data["capability"], "CUSTOMER_CONSUMPTION")

        result = await self.db.execute(select(Customer).where(Customer.id == customer.id))
        refreshed = result.scalar_one()
        self.assertEqual(refreshed.name, "原名字", "denied update must never mutate the Customer row")

    async def test_customer_update_pro_allowed(self):
        customer = await self._seed_customer(TENANT_PRO, name="原名字", phone="13800000003")
        TenantContext.set_tenant_id(TENANT_PRO)
        try:
            resp = await update_customer(
                customer.id, UpdateCustomerRequest(name="改名字"),
                make_request(tenant_id=TENANT_PRO, method="PUT", path=f"/api/v1/customers/{customer.id}"),
                db=self.db,
            )
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 200)

    async def test_customer_merge_non_pro_denied_no_mutation(self):
        """PHASE 4: a tag/identity/merge-class mutation."""
        source = await self._seed_customer(TENANT_STANDARD, name="重复客户", phone="13800000004")
        target = await self._seed_customer(TENANT_STANDARD, name="保留客户", phone="13800000005")
        TenantContext.set_tenant_id(TENANT_STANDARD)
        try:
            resp = await merge_customers(
                MergeCustomerRequest(source_customer_id=source.id, target_customer_id=target.id),
                make_request(tenant_id=TENANT_STANDARD, method="POST", path="/api/v1/customers/merge"),
                db=self.db,
            )
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 403)
        self.assertEqual(resp.data["capability"], "CUSTOMER_CONSUMPTION")

        result = await self.db.execute(select(Customer).where(Customer.tenant_id == TENANT_STANDARD))
        rows = result.scalars().all()
        self.assertEqual(len(rows), 2, "denied merge must not delete/merge either Customer row")
        self.assertTrue(all(row.status == 1 for row in rows))

    async def test_customer_status_mutation_non_pro_denied(self):
        customer = await self._seed_customer(TENANT_STANDARD)
        TenantContext.set_tenant_id(TENANT_STANDARD)
        try:
            resp = await update_customer_status(
                customer.id, UpdateCustomerStatusRequest(status=0),
                make_request(tenant_id=TENANT_STANDARD, method="PUT", path=f"/api/v1/customers/{customer.id}/status"),
                db=self.db,
            )
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 403)
        result = await self.db.execute(select(Customer).where(Customer.id == customer.id))
        self.assertEqual(result.scalar_one().status, 1, "denied status change must not mutate the row")

    async def test_customer_restore_non_pro_denied(self):
        customer = await self._seed_customer(TENANT_STANDARD)
        customer.status = 0
        await self.db.commit()
        TenantContext.set_tenant_id(TENANT_STANDARD)
        try:
            resp = await restore_customer(
                customer.id,
                make_request(tenant_id=TENANT_STANDARD, method="POST", path=f"/api/v1/customers/{customer.id}/restore"),
                db=self.db,
            )
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 403)
        result = await self.db.execute(select(Customer).where(Customer.id == customer.id))
        self.assertEqual(result.scalar_one().status, 0, "denied restore must not mutate the row")

    async def test_customer_delete_non_pro_denied(self):
        customer = await self._seed_customer(TENANT_STANDARD)
        TenantContext.set_tenant_id(TENANT_STANDARD)
        try:
            resp = await delete_customer(
                customer.id,
                make_request(tenant_id=TENANT_STANDARD, method="DELETE", path=f"/api/v1/customers/{customer.id}"),
                db=self.db,
            )
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 403)
        result = await self.db.execute(select(Customer).where(Customer.id == customer.id))
        self.assertEqual(result.scalar_one().status, 1, "denied delete must not mutate the row")

    async def test_customer_identities_non_pro_denied(self):
        customer = await self._seed_customer(TENANT_STANDARD)
        TenantContext.set_tenant_id(TENANT_STANDARD)
        try:
            resp = await get_customer_identities(customer.id, db=self.db)
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 403)
        self.assertEqual(resp.data["capability"], "CUSTOMER_CONSUMPTION")


# ---------------------------------------------------------------------------
# PHASE 5 -- downgrade / re-upgrade data preservation for CRM access
# ---------------------------------------------------------------------------

class CustomerCrmDowngradeReupgradeTest(BaseClosureTest):
    async def test_customer_crm_access_preserved_after_downgrade_and_reupgrade(self):
        customer = Customer(
            tenant_id=TENANT_PRO, openid="op-hist", name="老客户", phone="13800009999",
            tags=["vip", "常客"], status=1,
        )
        self.db.add(customer)
        await self.db.commit()
        await self.db.refresh(customer)

        TenantContext.set_tenant_id(TENANT_PRO)
        try:
            resp = await get_customer(customer.id, db=self.db)
        finally:
            TenantContext.clear()
        self.assertEqual(resp.code, 200, "sanity: readable while PRO")
        self.assertEqual(resp.data["tags"], ["vip", "常客"])

        # Downgrade: expire the PRO subscription.
        result = await self.db.execute(select(Subscription).where(Subscription.tenant_id == TENANT_PRO))
        sub = result.scalars().first()
        sub.ends_at = datetime.utcnow() - timedelta(seconds=1)
        await self.db.commit()

        TenantContext.set_tenant_id(TENANT_PRO)
        try:
            denied = await get_customer(customer.id, db=self.db)
        finally:
            TenantContext.clear()
        self.assertEqual(denied.code, 403)

        # Data preserved: row untouched by the downgrade.
        result = await self.db.execute(select(Customer).where(Customer.id == customer.id))
        preserved = result.scalar_one()
        self.assertEqual(preserved.tags, ["vip", "常客"])
        self.assertEqual(preserved.status, 1)

        # Re-upgrade: same tenant, new unexpired PRO subscription.
        await self._activate(TENANT_PRO, "PRO", ends_delta=timedelta(days=30))

        TenantContext.set_tenant_id(TENANT_PRO)
        try:
            restored = await get_customer(customer.id, db=self.db)
        finally:
            TenantContext.clear()
        self.assertEqual(restored.code, 200)
        self.assertEqual(restored.data["tags"], ["vip", "常客"])
        self.assertEqual(restored.data["id"], str(customer.id))


if __name__ == "__main__":
    unittest.main()
