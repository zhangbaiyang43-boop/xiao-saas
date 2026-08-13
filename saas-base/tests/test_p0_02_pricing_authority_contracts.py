"""P0-02: menu display data vs. final transaction data consistency.

Audit finding (see conversation report): the create_order path already recomputes
dish price, spec/extra surcharges, quantity, coupon discount, and payment/print/
admin amounts entirely from server-side data (MenuItem, TenantConfig.business_info
["menu_item_specs"], Coupon/CouponTemplate, the persisted Order/OrderItem rows) --
client-submitted price/unit_price/subtotal/total/addon_price fields are read by
Pydantic but never used in any amount computation (confirmed by exhaustive grep).
Most of these tests therefore PASS as pre-existing regression proof, not because
a fix landed here. The one genuine behavior change in this pass is TEST 04: the
system previously had no stale-price detection at all (silently created the order
at the current server price with no signal to the client) -- this suite proves
the new PRICE_CHANGED rejection contract.
"""

import asyncio
import unittest
from datetime import datetime

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.coupon import Coupon
from app.models.coupon_template import CouponTemplate
from app.models.customer import Customer
from app.models.dining import DiningSession
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.api.v1.orders import create_order, OrderCreate, OrderItemIn, OrderItemSpecIn, list_orders
from app.services.dining_session_service import DiningSessionService
from app.services.order_lifecycle_service import OrderLifecycleService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


def make_request(path="/api/v1/orders"):
    return Request(
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


def make_owner_request(tenant_id=TENANT_A):
    req = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/orders",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    req.state.tenant_id = tenant_id
    req.state.token_type = "merchant"
    req.state.role = "owner"
    req.state.account_id = None
    return req


class PricingAuthorityTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.db.add_all([
            Tenant(tenant_id=TENANT_A, name="Restaurant A", password_hash="x",
                   status=True, is_open=True, payment_mode="postpay"),
            Tenant(tenant_id=TENANT_B, name="Restaurant B", password_hash="x",
                   status=True, is_open=True, payment_mode="postpay"),
        ])
        await self.db.flush()

        # Dish A: 28.00, spec group "份量" (小份 +0 / 大份 +10), extra "加蛋" +2.00
        self.dish_a = MenuItem(tenant_id=TENANT_A, name="宫保鸡丁", price="28.00", available=True)
        # Dish B: 38.00, its own, differently-priced spec group of the same names
        self.dish_b = MenuItem(tenant_id=TENANT_A, name="水煮牛肉", price="38.00", available=True)
        self.db.add_all([self.dish_a, self.dish_b])
        await self.db.flush()

        self.db.add(TenantConfig(
            tenant_id=TENANT_A,
            member_rules={}, coupon_rules={}, plugin_settings={},
            business_info={
                "menu_item_specs": {
                    str(self.dish_a.id): [
                        {"name": "份量", "type": "single", "options": [
                            {"name": "小份", "price_delta": 0},
                            {"name": "大份", "price_delta": 10},
                        ]},
                        {"name": "加料", "type": "multi", "options": [
                            {"name": "加蛋", "price_delta": 2},
                        ]},
                    ],
                    str(self.dish_b.id): [
                        # Same group/option *names* as dish A, different price --
                        # this is exactly the cross-dish attack surface: if the
                        # server ever looked up specs by name alone without
                        # scoping to the submitted dish_id, this would let an
                        # attacker pay dish A's cheaper delta for dish B.
                        {"name": "份量", "type": "single", "options": [
                            {"name": "小份", "price_delta": 0},
                            {"name": "大份", "price_delta": 999},
                        ]},
                    ],
                },
            },
        ))
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _order_body(self, *, shop=TENANT_A, table="", items, total=1.0, dining_session_id=None,
                     participant_token=None, coupon_id=None, request_id=None):
        return OrderCreate(
            shop=shop, table=table, items=items, total=total,
            dining_session_id=dining_session_id, participant_token=participant_token,
            coupon_id=coupon_id, request_id=request_id,
        )

    async def _order_count(self):
        return len((await self.db.execute(select(Order))).scalars().all())

    async def _get_order_items(self, order_id):
        return (await self.db.execute(select(OrderItem).where(OrderItem.order_id == order_id))).scalars().all()

    # ---- TEST 01: client tampers dish price ----
    async def test_01_client_price_tamper_is_rejected_never_silently_undercharged(self):
        # Under the chosen contract (Option B, see report), the server can't tell
        # "attacker set price=0.01" apart from "page went stale" -- both are the
        # same signal (client price disagrees with server price) and get the
        # same safe treatment: reject, never silently create the order at
        # *either* the client's number or a silently-substituted server number.
        # This is the task's own explicitly-permitted alternative outcome for
        # this exact case ("...或者按照选定 stale-price 合同明确拒绝").
        body = self._order_body(items=[
            OrderItemIn(dish_id=self.dish_a.id, name="宫保鸡丁", price=0.01, qty=1),
        ], total=0.01)
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 400)
        self.assertEqual(await self._order_count(), 0)

    # ---- TEST 02: client tampers total (item prices correct, isolating that
    # `total` specifically -- not just any client-submitted number -- is inert) ----
    async def test_02_client_total_tamper_does_not_affect_order_total(self):
        body = self._order_body(items=[
            OrderItemIn(dish_id=self.dish_a.id, name="宫保鸡丁", price=28, qty=1),
            OrderItemIn(dish_id=self.dish_b.id, name="水煮牛肉", price=38, qty=1),
        ], total=1.0)
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200)
        self.assertEqual(result.data["total"], 66.0)  # 28 + 38, not body.total's 1.0

    # ---- TEST 03: qty x price ----
    async def test_03_quantity_multiplies_server_price_correctly(self):
        body = self._order_body(items=[
            OrderItemIn(dish_id=self.dish_a.id, name="宫保鸡丁", price=28, qty=10),
        ], total=280)
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200)
        self.assertEqual(result.data["total"], 280.0)

    # ---- TEST 04: stale base price -- the new behavior this pass adds ----
    async def test_04_stale_displayed_price_is_rejected_not_silently_charged(self):
        # Client's page loaded when dish A was (hypothetically) 24.00; server is
        # now authoritatively 28.00. Client still sends its stale displayed price.
        body = self._order_body(items=[
            OrderItemIn(dish_id=self.dish_a.id, name="宫保鸡丁", price=24.00, qty=1),
        ], total=24.00)
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 400)
        self.assertIn("价格", result.msg or "")
        self.assertEqual(await self._order_count(), 0)

    async def test_04b_matching_displayed_price_still_succeeds(self):
        body = self._order_body(items=[
            OrderItemIn(dish_id=self.dish_a.id, name="宫保鸡丁", price=28.00, qty=1),
        ], total=28.00)
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200)

    # ---- TEST 05: item offline ----
    async def test_05_offline_dish_is_rejected(self):
        self.dish_a.available = False
        await self.db.commit()
        body = self._order_body(items=[
            OrderItemIn(dish_id=self.dish_a.id, name="宫保鸡丁", price=28, qty=1),
        ], total=28)
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 400)
        self.assertEqual(await self._order_count(), 0)

    # ---- TEST 06: sold out ----
    async def test_06_sold_out_dish_is_rejected(self):
        self.dish_a.stock = 0
        await self.db.commit()
        body = self._order_body(items=[
            OrderItemIn(dish_id=self.dish_a.id, name="宫保鸡丁", price=28, qty=1),
        ], total=28)
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 400)
        self.assertEqual(await self._order_count(), 0)
        # case 2.8 / 10: message must be actionable Chinese, not a raw English
        # preamble a customer can't read (the interpolated dish name is always
        # Chinese, so a weaker "not fully ASCII" check would pass even with an
        # English prefix like "dish sold out: 宫保鸡丁" -- assert the literal
        # English strings are gone, not just that *some* Chinese appears).
        self.assertNotIn("dish sold out", result.msg or "")
        self.assertNotIn("dish stock not enough", result.msg or "")

    async def test_06b_insufficient_stock_message_is_chinese(self):
        self.dish_a.stock = 1
        await self.db.commit()
        body = self._order_body(items=[
            OrderItemIn(dish_id=self.dish_a.id, name="宫保鸡丁", price=28, qty=5),
        ], total=140)
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 400)
        self.assertEqual(await self._order_count(), 0)
        self.assertNotIn("dish stock not enough", result.msg or "")

    # ---- TEST 07: spec price ----
    async def test_07_spec_price_uses_server_delta_not_client_price(self):
        # A real client (useSpecSheet.js's specUnitPrice) always sends the full
        # base+delta price for a spec'd line, never the bare base price -- 38,
        # matching what the server independently computes from its own delta.
        body = self._order_body(items=[
            OrderItemIn(
                dish_id=self.dish_a.id, name="宫保鸡丁", price=38, qty=1,
                specifications=[OrderItemSpecIn(group="份量", value="大份")],
            ),
        ], total=28)  # total still wrong/irrelevant -- proves that field is inert
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200)
        self.assertEqual(result.data["total"], 38.0)  # 28 + 10 delta

    # ---- TEST 08: cross-dish spec attack ----
    async def test_08_cross_dish_spec_value_is_rejected(self):
        # Dish A has no "大份"=999 option -- only dish B does. Submitting dish A
        # with a spec value that doesn't exist in *A's own* configured groups
        # must be rejected, not silently resolved against dish B's pricing.
        body = self._order_body(items=[
            OrderItemIn(
                dish_id=self.dish_a.id, name="宫保鸡丁", price=28, qty=1,
                specifications=[OrderItemSpecIn(group="份量", value="超大份-only-on-B")],
            ),
        ], total=28)
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 400)
        self.assertEqual(await self._order_count(), 0)

    async def test_08b_same_option_name_different_dish_uses_that_dishs_own_price(self):
        # Both dishes have a "份量"/"大份" option, but at different deltas (10 vs
        # 999). Submitting dish A must always use dish A's own delta (10), proving
        # the lookup is dish-scoped, not name-only.
        body = self._order_body(items=[
            OrderItemIn(
                dish_id=self.dish_a.id, name="宫保鸡丁", price=38, qty=1,
                specifications=[OrderItemSpecIn(group="份量", value="大份")],
            ),
        ], total=28)
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200)
        self.assertEqual(result.data["total"], 38.0)  # NOT 28 + 999

    # ---- TEST 09: addon price ----
    async def test_09_addon_price_uses_server_delta_regardless_of_client_addon_price(self):
        body = self._order_body(items=[
            OrderItemIn(
                dish_id=self.dish_a.id, name="宫保鸡丁", price=30, qty=1,
                extras=["加蛋"],
            ),
        ], total=28)  # total wrong/irrelevant; price=30 matches real 28+2 delta
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200)
        self.assertEqual(result.data["total"], 30.0)  # 28 + 2

    # ---- TEST 10: cross-dish addon ----
    async def test_10_cross_dish_addon_is_rejected(self):
        body = self._order_body(items=[
            OrderItemIn(
                dish_id=self.dish_b.id, name="水煮牛肉", price=38, qty=1,
                extras=["加蛋"],  # only configured on dish A
            ),
        ], total=38)
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 400)
        self.assertEqual(await self._order_count(), 0)

    # ---- TEST 11: invalid qty ----
    async def test_11_zero_and_negative_quantity_are_rejected(self):
        for bad_qty in (0, -1):
            body = self._order_body(items=[
                OrderItemIn(dish_id=self.dish_a.id, name="宫保鸡丁", price=28, qty=bad_qty),
            ], total=28)
            result = await create_order(body, make_request(), db=self.db)
            self.assertEqual(result.code, 400, f"qty={bad_qty} must be rejected")
        self.assertEqual(await self._order_count(), 0)

    def test_11b_non_integer_quantity_is_rejected_at_the_schema_layer(self):
        with self.assertRaises(Exception):
            OrderItemIn(dish_id=self.dish_a.id, name="宫保鸡丁", price=28, qty=1.5)

    # ---- TEST 12: Decimal precision ----
    async def test_12_amount_accumulation_has_no_float_drift(self):
        # 19.90 * 7 in raw IEEE754 float is 139.29999999999998, not 139.30 --
        # a classic case this test is designed to catch if it ever regresses.
        dish = MenuItem(tenant_id=TENANT_A, name="米线", price="19.90", available=True)
        self.db.add(dish)
        await self.db.commit()
        body = self._order_body(items=[
            OrderItemIn(dish_id=dish.id, name="米线", price=19.90, qty=7),
        ], total=139.30)
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200)
        self.assertEqual(result.data["total"], 139.30)
        order = (await self.db.execute(select(Order).where(Order.id == int(result.data["id"])))).scalar_one()
        self.assertEqual(str(order.total), "139.30")

    # ---- TEST 13: WeChat amount source (already covered structurally by
    # test_order_amount_security_contracts.py / test_order_payment_security.py;
    # this is the end-to-end DB-level companion) ----
    async def test_13_order_persists_authoritative_total_independent_of_client_input(self):
        body = self._order_body(items=[
            OrderItemIn(dish_id=self.dish_a.id, name="宫保鸡丁", price=28, qty=2),
            OrderItemIn(dish_id=self.dish_b.id, name="水煮牛肉", price=38, qty=1),
        ], total=0.01)  # only body.total is tampered; item prices are honest
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200)
        order = (await self.db.execute(select(Order).where(Order.id == int(result.data["id"])))).scalar_one()
        # This is exactly what create_wxpay_order reads (see order_payment_service.py:561);
        # amount_fen = max(1, round(pay_amount * 100)) is computed from this value only.
        self.assertEqual(float(order.total), 94.0)  # 28*2 + 38
        expected_fen = max(1, round(float(order.total) * 100))
        self.assertEqual(expected_fen, 9400)

    # ---- TEST 14: print amount source ----
    async def test_14_print_render_data_reads_persisted_order_not_client_payload(self):
        from app.services.kuaimai_service import build_order_template_render_data

        body = self._order_body(items=[
            OrderItemIn(dish_id=self.dish_a.id, name="宫保鸡丁", price=28, qty=1),
        ], total=0.01)  # only body.total is tampered
        result = await create_order(body, make_request(), db=self.db)
        order = (await self.db.execute(select(Order).where(Order.id == int(result.data["id"])))).scalar_one()
        items = await self._get_order_items(order.id)
        render = build_order_template_render_data(order, items, shop_name="Restaurant A")
        self.assertEqual(render["pay_amount"], "28.00")
        self.assertEqual(render["total_amount"], "28.00")

    # ---- TEST 15: Admin display consistency ----
    async def test_15_admin_order_list_amount_matches_db_order_total(self):
        body = self._order_body(items=[
            OrderItemIn(dish_id=self.dish_a.id, name="宫保鸡丁", price=28, qty=2),
        ], total=0.01)  # only body.total is tampered
        result = await create_order(body, make_request(), db=self.db)
        db_total = float((await self.db.execute(
            select(Order.total).where(Order.id == int(result.data["id"]))
        )).scalar_one())

        admin_result = await list_orders(make_owner_request(), date_str="today", db=self.db)
        admin_order = next(o for o in admin_result.data if o["id"] == str(result.data["id"]))
        self.assertEqual(float(admin_order["total"]), db_total)
        self.assertEqual(db_total, 56.0)

    # ---- TEST 16/17/18: three payment modes share the same item pricing authority ----
    async def _assert_same_priced_order_total_for_mode(self, payment_mode, *, needs_session=False):
        self.tenant_mode = Tenant(
            tenant_id=f"tenant-mode-{payment_mode}", name="Mode Shop", password_hash="x",
            status=True, is_open=True, payment_mode=payment_mode,
        )
        self.db.add(self.tenant_mode)
        dish = MenuItem(tenant_id=self.tenant_mode.tenant_id, name="宫保鸡丁", price="28.00", available=True)
        self.db.add(dish)
        await self.db.commit()

        dining_session_id = None
        participant_token = None
        if needs_session:
            self.db.add(EntranceCode(
                id=generate_snowflake_id(),
                tenant_id=self.tenant_mode.tenant_id, name="A01", scene=f"E{self.tenant_mode.tenant_id}A01",
                table_no="A01", entry_type="table", status=1,
            ))
            await self.db.commit()
            identity = await DiningSessionService(self.db).resolve_session(
                tenant_id=self.tenant_mode.tenant_id, table_no="A01", client_id="dc_test",
            )
            await self.db.commit()
            dining_session_id = int(identity["dining_session_id"])
            participant_token = identity["participant_token"]

        body = OrderCreate(
            shop=self.tenant_mode.tenant_id, table="A01" if needs_session else "",
            items=[OrderItemIn(dish_id=dish.id, name="宫保鸡丁", price=28, qty=2)],
            total=0.01,  # only body.total is tampered
            dining_session_id=dining_session_id, participant_token=participant_token,
        )
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200, f"{payment_mode}: {result.msg}")
        self.assertEqual(result.data["total"], 56.0, f"{payment_mode} did not use server price authority")

    async def test_16_prepay_uses_server_price_authority(self):
        await self._assert_same_priced_order_total_for_mode("prepay")

    async def test_17_postpay_uses_server_price_authority(self):
        await self._assert_same_priced_order_total_for_mode("postpay")

    async def test_18_table_account_uses_server_price_authority(self):
        await self._assert_same_priced_order_total_for_mode("table_account", needs_session=True)

    # ---- Arithmetic proof scenario (task's own worked example: 28x2 + 38x1 + 2x3 = 100) ----
    async def test_19_arithmetic_proof_scenario(self):
        # This schema always attaches an addon as a per-unit delta on a real dish
        # line (OrderItemIn.dish_id is mandatory, extras/specifications modify
        # that dish's own price) -- there is no standalone "addon SKU" concept.
        # To reproduce the task's literal "加料 ¥2 x3" as an independent ¥6
        # component (not bundled onto dish A or B's own price), give it its own
        # zero-price carrier dish with only the addon configured, matching this
        # system's real schema instead of inventing one.
        addon_carrier = MenuItem(tenant_id=TENANT_A, name="加料", price="0.00", available=True)
        self.db.add(addon_carrier)
        await self.db.flush()
        config = (await self.db.execute(
            select(TenantConfig).where(TenantConfig.tenant_id == TENANT_A)
        )).scalar_one()
        specs = dict(config.business_info.get("menu_item_specs") or {})
        specs[str(addon_carrier.id)] = [
            {"name": "加料", "type": "multi", "options": [{"name": "加蛋", "price_delta": 2}]},
        ]
        config.business_info = {**config.business_info, "menu_item_specs": specs}
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(config, "business_info")
        await self.db.commit()

        result = await create_order(self._order_body(items=[
            OrderItemIn(dish_id=self.dish_a.id, name="宫保鸡丁", price=28, qty=2),
            OrderItemIn(dish_id=self.dish_b.id, name="水煮牛肉", price=38, qty=1),
            OrderItemIn(dish_id=addon_carrier.id, name="加料", price=2.0, qty=3, extras=["加蛋"]),
        ], total=1.0), make_request(), db=self.db)  # only body.total is tampered
        self.assertEqual(result.code, 200)
        # 28*2 + 38*1 + 2*3 = 56 + 38 + 6 = 100.00, exactly the task's worked example.
        self.assertEqual(result.data["total"], 100.0)
        order_id = int(result.data["id"])
        order = (await self.db.execute(select(Order).where(Order.id == order_id))).scalar_one()
        self.assertEqual(str(order.total), "100.00")

        # Payment amount: what create_wxpay_order would compute (order.total is
        # its only input -- see order_payment_service.py:561,605).
        expected_fen = max(1, round(float(order.total) * 100))
        self.assertEqual(expected_fen, 10000)

        # Admin amount: same shared serializer, same DB row.
        admin_result = await list_orders(make_owner_request(), date_str="today", db=self.db)
        admin_order = next(o for o in admin_result.data if o["id"] == str(order_id))
        self.assertEqual(float(admin_order["total"]), 100.0)

        # Print amount: reads the persisted order/order_items, not the client payload.
        from app.services.kuaimai_service import build_order_template_render_data
        items = await self._get_order_items(order_id)
        render = build_order_template_render_data(order, items, shop_name="Restaurant A")
        self.assertEqual(render["pay_amount"], "100.00")
        self.assertEqual(render["total_amount"], "100.00")


if __name__ == "__main__":
    unittest.main()
