"""P0-13 finding 02: defense-in-depth hardening for coupon redemption. The
Coupon row's own tenant_id was already the authority gating cross-tenant use
(confirmed safe in Phase A), but the CouponTemplate row referenced by
coupon.template_id was never independently re-verified to belong to the same
tenant as the order. This closes that gap so a future issuance bug (or a
hand-crafted coupon whose Coupon row was somehow mis-tenanted) can't silently
apply another tenant's discount rule -- it's not exploitable via any real
issuance path today, which is exactly why this is hardening, not a fix for an
active incident.

Also pins the existing control-green boundary (finding 01's resolution):
CouponTemplate.status is confirmed ISSUANCE_ONLY semantics (admin UI literally
labels status==1 "上架"/listed and status!=1 "下架"/delisted; the only backend
check of template.status anywhere in the codebase lives inside
send_coupons_with_result, the issuance path, with message "优惠券不存在或未上架").
A disabled template's already-issued, still-valid coupons must therefore
continue to redeem normally -- adding a redemption-time status gate would
create a NEW asset-safety incident (retroactively invalidating coupons
customers already legitimately hold), which is exactly what this file also
proves does NOT happen.
"""

import asyncio
import unittest
from datetime import datetime, timedelta

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import OrderItem
from app.models.tenant import Tenant
from app.api.v1.orders import create_order, OrderCreate, OrderItemIn
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


TENANT_A = "p0-13-tenant-a"
TENANT_B = "p0-13-tenant-b"
TABLE = "T20"


def make_request(customer_id):
    req = Request(
        {
            "type": "http", "method": "POST", "path": "/api/v1/orders",
            "headers": [], "query_string": b"",
            "server": ("testserver", 80), "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    req.state.customer_id = customer_id
    return req


class TemplateTenantHardeningTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        for tenant_id in (TENANT_A, TENANT_B):
            self.db.add(Tenant(
                tenant_id=tenant_id, name="Test Restaurant", password_hash="x",
                status=True, is_open=True, payment_mode="postpay",
            ))
        self.dish = MenuItem(tenant_id=TENANT_A, name="宫保鸡丁", price="100.00", available=True)
        self.db.add(self.dish)
        self.db.add(EntranceCode(
            id=generate_snowflake_id(),
            tenant_id=TENANT_A, name=TABLE, scene=f"E{TENANT_A}",
            table_no=TABLE, entry_type="table", status=1,
        ))
        await self.db.flush()

        # Template genuinely belongs to Tenant B.
        self.template_b = CouponTemplate(
            tenant_id=TENANT_B, name="B's 20 off", type="FIXED", value="20.00",
            min_amount="0.00", total_stock=100, used_stock=1,
            start_time=datetime.utcnow() - timedelta(days=1),
            end_time=datetime.utcnow() + timedelta(days=30), status=1,
        )
        self.db.add(self.template_b)
        await self.db.flush()

        # Mis-tenanted coupon: the Coupon row itself claims Tenant A (so the
        # existing Coupon.tenant_id check alone would let it through), but its
        # template_id points at Tenant B's template -- this is the exact case
        # the Coupon.tenant_id check alone cannot catch.
        self.coupon = Coupon(
            tenant_id=TENANT_A, template_id=self.template_b.id, customer_id=8001,
            code=f"CODE-{generate_snowflake_id()}", status="UNUSED",
            expire_time=datetime.utcnow() + timedelta(days=1),
        )
        self.db.add(self.coupon)
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _body(self, coupon_id):
        return OrderCreate(
            shop=TENANT_A, table=TABLE,
            items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=100.0, qty=1)],
            total=100.0, coupon_id=coupon_id, request_id="R-TEMPLATE-TENANT",
        )

    async def test_mismatched_template_tenant_is_denied(self):
        result = await create_order(self._body(self.coupon.id), make_request(8001), db=self.db)
        self.assertEqual(result.code, 400)
        # Minimal disclosure: same generic message as "template missing",
        # never reveals which tenant the template actually belongs to.
        self.assertEqual(result.msg, "优惠券规则不存在")

        await self.db.refresh(self.coupon)
        self.assertEqual(self.coupon.status, "UNUSED")  # untouched, not consumed by the failed attempt

    async def test_matching_template_tenant_still_succeeds(self):
        template_a = CouponTemplate(
            tenant_id=TENANT_A, name="A's 20 off", type="FIXED", value="20.00",
            min_amount="0.00", total_stock=100, used_stock=1,
            start_time=datetime.utcnow() - timedelta(days=1),
            end_time=datetime.utcnow() + timedelta(days=30), status=1,
        )
        self.db.add(template_a)
        await self.db.flush()
        coupon_a = Coupon(
            tenant_id=TENANT_A, template_id=template_a.id, customer_id=8002,
            code=f"CODE-{generate_snowflake_id()}", status="UNUSED",
            expire_time=datetime.utcnow() + timedelta(days=1),
        )
        self.db.add(coupon_a)
        await self.db.commit()

        result = await create_order(
            OrderCreate(
                shop=TENANT_A, table=TABLE,
                items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=100.0, qty=1)],
                total=100.0, coupon_id=coupon_a.id, request_id="R-MATCH",
            ),
            make_request(8002), db=self.db,
        )
        self.assertEqual(result.code, 200, result.msg)
        self.assertEqual(result.data["discount_amount"], 20.0)
        await self.db.refresh(coupon_a)
        self.assertEqual(coupon_a.status, "LOCKED")

    # ---- P0-13-01 control green: disabled template does not invalidate an already-issued, still-valid coupon ----
    async def test_disabled_template_does_not_block_redemption_of_already_issued_coupon(self):
        template_a = CouponTemplate(
            tenant_id=TENANT_A, name="A's soon-to-be-delisted coupon", type="FIXED", value="15.00",
            min_amount="0.00", total_stock=100, used_stock=1,
            start_time=datetime.utcnow() - timedelta(days=1),
            end_time=datetime.utcnow() + timedelta(days=30),
            status=0,  # merchant has delisted the template ("下架") -- stops NEW issuance only
        )
        self.db.add(template_a)
        await self.db.flush()
        coupon_a = Coupon(
            tenant_id=TENANT_A, template_id=template_a.id, customer_id=8003,
            code=f"CODE-{generate_snowflake_id()}", status="UNUSED",
            expire_time=datetime.utcnow() + timedelta(days=1),
        )
        self.db.add(coupon_a)
        await self.db.commit()

        result = await create_order(
            OrderCreate(
                shop=TENANT_A, table=TABLE,
                items=[OrderItemIn(dish_id=self.dish.id, name=self.dish.name, price=100.0, qty=1)],
                total=100.0, coupon_id=coupon_a.id, request_id="R-DELISTED-STILL-REDEEMABLE",
            ),
            make_request(8003), db=self.db,
        )
        self.assertEqual(result.code, 200, result.msg)
        self.assertEqual(result.data["discount_amount"], 15.0)


if __name__ == "__main__":
    unittest.main()
