"""P0-02 snapshot closure: OrderItem.name must be a pure server-canonical
dish+spec+addon description; per-item user remarks must be captured in a
dedicated OrderItem.item_remark column, never folded into the commerce-fact
name, and never trusted from a client-forged `item_in.name` for anything
beyond best-effort legacy remark recovery.

See conversation report ("P0-02 ITEM REMARK CARRIER DESIGN GATE" +
"P0-02 FINAL SNAPSHOT + ITEM REMARK IMPLEMENTATION") for the full audit and
design rationale. This file covers S1-S12 as specified there.
"""

import asyncio
import unittest
from unittest.mock import patch

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified
from starlette.requests import Request

from app.models.base import Base
from app.models.dining import DiningSession
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.api.v1.orders import (
    create_order,
    OrderCreate,
    OrderItemIn,
    OrderItemSpecIn,
    list_orders,
    serialize_fulfillment_order,
    serialize_recent_served_order,
)
from app.services.dining_session_service import DiningSessionService
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-remark-a"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def make_request():
    return Request({
        "type": "http", "method": "POST", "path": "/api/v1/orders", "headers": [],
        "query_string": b"", "server": ("testserver", 80), "scheme": "http",
        "client": ("testclient", 50000),
    })


def make_owner_request():
    req = Request({
        "type": "http", "method": "GET", "path": "/api/v1/orders", "headers": [],
        "query_string": b"", "server": ("testserver", 80), "scheme": "http",
        "client": ("testclient", 50000),
    })
    req.state.tenant_id = TENANT_A
    req.state.token_type = "merchant"
    req.state.role = "owner"
    req.state.account_id = None
    return req


class ItemRemarkSnapshotTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()

        self.db.add(Tenant(tenant_id=TENANT_A, name="Remark Restaurant", password_hash="x",
                            status=True, is_open=True, payment_mode="postpay"))
        await self.db.flush()

        self.dish = MenuItem(tenant_id=TENANT_A, name="宫保鸡丁", price="28.00", available=True)
        self.db.add(self.dish)
        await self.db.flush()

        self.db.add(TenantConfig(
            tenant_id=TENANT_A,
            member_rules={}, coupon_rules={}, plugin_settings={},
            business_info={
                "menu_item_specs": {
                    str(self.dish.id): [
                        {"name": "份量", "type": "single", "options": [
                            {"name": "小份", "price_delta": 0},
                            {"name": "大份", "price_delta": 10},
                        ]},
                        {"name": "加料", "type": "multi", "options": [
                            {"name": "加鸡蛋", "price_delta": 2},
                            {"name": "微辣", "price_delta": 0},
                            # S7: an addon option whose own name contains the
                            # separator character used to join labels.
                            {"name": "加辣、加葱", "price_delta": 1},
                        ]},
                    ],
                },
            },
        ))
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _order_count(self):
        return len((await self.db.execute(select(Order))).scalars().all())

    async def _get_single_order_item(self):
        order = (await self.db.execute(select(Order))).scalars().one()
        item = (await self.db.execute(
            select(OrderItem).where(OrderItem.order_id == order.id)
        )).scalars().one()
        return order, item

    # ---- S1: forged item name cannot alter snapshot ----
    async def test_s1_forged_item_name_cannot_alter_snapshot(self):
        body = OrderCreate(
            shop=TENANT_A, table="",
            items=[OrderItemIn(
                dish_id=self.dish.id,
                name="宫保鸡丁(超级豪华大份、鲍鱼)",  # forged, doesn't match real selection at all
                price=28, qty=1,  # real: base 28 + 小份(+0) + 微辣(+0)
                specifications=[OrderItemSpecIn(group="份量", value="小份")],
                extras=["微辣"],
            )],
            total=28,
        )
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200, result.msg)
        _, item = await self._get_single_order_item()
        self.assertEqual(item.name, "宫保鸡丁(小份、微辣)")
        self.assertIsNone(item.item_remark)

    # ---- S2: new item_remark stored separately ----
    async def test_s2_new_item_remark_stored_separately(self):
        body = OrderCreate(
            shop=TENANT_A, table="",
            items=[OrderItemIn(
                dish_id=self.dish.id, name="宫保鸡丁(大份、加鸡蛋)", price=40, qty=1,
                specifications=[OrderItemSpecIn(group="份量", value="大份")],
                extras=["加鸡蛋"],
                item_remark="不要香菜",
            )],
            total=40,
        )
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200, result.msg)
        _, item = await self._get_single_order_item()
        self.assertEqual(item.name, "宫保鸡丁(大份、加鸡蛋)")
        self.assertEqual(item.item_remark, "不要香菜")

    # ---- S3: legacy Mini remark extraction ----
    async def test_s3_legacy_mini_remark_extraction(self):
        body = OrderCreate(
            shop=TENANT_A, table="",
            items=[OrderItemIn(
                dish_id=self.dish.id,
                name="宫保鸡丁(大份、加鸡蛋、不要香菜)",  # no item_remark field at all -- legacy client
                price=40, qty=1,
                specifications=[OrderItemSpecIn(group="份量", value="大份")],
                extras=["加鸡蛋"],
            )],
            total=40,
        )
        self.assertNotIn("item_remark", body.items[0].model_fields_set)
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200, result.msg)
        _, item = await self._get_single_order_item()
        self.assertEqual(item.name, "宫保鸡丁(大份、加鸡蛋)")
        self.assertEqual(item.item_remark, "不要香菜")

    # ---- S4: explicit empty remark must not fall back to legacy extraction ----
    async def test_s4_explicit_empty_remark_wins_over_legacy_residual(self):
        body = OrderCreate(
            shop=TENANT_A, table="",
            items=[OrderItemIn(
                dish_id=self.dish.id,
                name="宫保鸡丁(大份、加鸡蛋、不要香菜)",  # stale client also still sends old-style name
                price=40, qty=1,
                specifications=[OrderItemSpecIn(group="份量", value="大份")],
                extras=["加鸡蛋"],
                item_remark="",  # explicitly present, explicitly empty
            )],
            total=40,
        )
        self.assertIn("item_remark", body.items[0].model_fields_set)
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200, result.msg)
        _, item = await self._get_single_order_item()
        self.assertEqual(item.name, "宫保鸡丁(大份、加鸡蛋)")
        self.assertIsNone(item.item_remark)
        self.assertNotEqual(item.item_remark, "不要香菜")

    # ---- S5: remark containing the separator character itself ----
    async def test_s5_remark_with_embedded_separator_preserved_whole(self):
        body = OrderCreate(
            shop=TENANT_A, table="",
            items=[OrderItemIn(
                dish_id=self.dish.id,
                name="宫保鸡丁(大份、加鸡蛋、不要香菜、不要葱)",
                price=40, qty=1,
                specifications=[OrderItemSpecIn(group="份量", value="大份")],
                extras=["加鸡蛋"],
            )],
            total=40,
        )
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200, result.msg)
        _, item = await self._get_single_order_item()
        self.assertEqual(item.name, "宫保鸡丁(大份、加鸡蛋)")
        self.assertEqual(item.item_remark, "不要香菜、不要葱")

    # ---- S6: remark containing embedded parentheses ----
    async def test_s6_remark_with_embedded_parentheses_preserved_whole(self):
        body = OrderCreate(
            shop=TENANT_A, table="",
            items=[OrderItemIn(
                dish_id=self.dish.id,
                name="宫保鸡丁(大份、加鸡蛋、不要辣(孩子吃))",
                price=40, qty=1,
                specifications=[OrderItemSpecIn(group="份量", value="大份")],
                extras=["加鸡蛋"],
            )],
            total=40,
        )
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200, result.msg)
        _, item = await self._get_single_order_item()
        self.assertEqual(item.name, "宫保鸡丁(大份、加鸡蛋)")
        self.assertEqual(item.item_remark, "不要辣(孩子吃)")

    # ---- S7: canonical spec/addon option name itself contains the separator ----
    async def test_s7_option_name_with_separator_still_deterministic(self):
        # No remark case: client name matches canonical exactly.
        body_no_remark = OrderCreate(
            shop=TENANT_A, table="",
            items=[OrderItemIn(
                dish_id=self.dish.id,
                name="宫保鸡丁(小份、加辣、加葱)",
                price=29, qty=1,
                specifications=[OrderItemSpecIn(group="份量", value="小份")],
                extras=["加辣、加葱"],
            )],
            total=29,
        )
        result = await create_order(body_no_remark, make_request(), db=self.db)
        self.assertEqual(result.code, 200, result.msg)
        _, item = await self._get_single_order_item()
        self.assertEqual(item.name, "宫保鸡丁(小份、加辣、加葱)")
        self.assertIsNone(item.item_remark)

        # With remark appended after an option name that itself contains "、".
        body_with_remark = OrderCreate(
            shop=TENANT_A, table="",
            items=[OrderItemIn(
                dish_id=self.dish.id,
                name="宫保鸡丁(小份、加辣、加葱、不要香菜)",
                price=29, qty=1,
                specifications=[OrderItemSpecIn(group="份量", value="小份")],
                extras=["加辣、加葱"],
            )],
            total=29,
        )
        result2 = await create_order(body_with_remark, make_request(), db=self.db)
        self.assertEqual(result2.code, 200, result2.msg)
        order2 = (await self.db.execute(
            select(Order).where(Order.id == int(result2.data["id"]))
        )).scalar_one()
        item2 = (await self.db.execute(
            select(OrderItem).where(OrderItem.order_id == order2.id)
        )).scalars().one()
        self.assertEqual(item2.name, "宫保鸡丁(小份、加辣、加葱)")
        self.assertEqual(item2.item_remark, "不要香菜")

    # ---- S8: remark max length, fail-closed not truncated ----
    async def test_s8_remark_at_max_length_passes(self):
        remark_255 = "备" * 255
        body = OrderCreate(
            shop=TENANT_A, table="",
            items=[OrderItemIn(
                dish_id=self.dish.id, name="宫保鸡丁", price=28, qty=1,
                item_remark=remark_255,
            )],
            total=28,
        )
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200, result.msg)
        _, item = await self._get_single_order_item()
        self.assertEqual(item.item_remark, remark_255)
        self.assertEqual(len(item.item_remark), 255)

    async def test_s8_remark_over_max_length_rejected_not_truncated(self):
        remark_256 = "备" * 256
        body = OrderCreate(
            shop=TENANT_A, table="",
            items=[OrderItemIn(
                dish_id=self.dish.id, name="宫保鸡丁", price=28, qty=1,
                item_remark=remark_256,
            )],
            total=28,
        )
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 400)
        self.assertEqual(await self._order_count(), 0)

    # ---- S9: historical menu mutation does not alter persisted snapshot ----
    async def test_s9_historical_menu_mutation_does_not_alter_snapshot(self):
        body = OrderCreate(
            shop=TENANT_A, table="",
            items=[OrderItemIn(
                dish_id=self.dish.id, name="宫保鸡丁(大份、加鸡蛋)", price=40, qty=1,
                specifications=[OrderItemSpecIn(group="份量", value="大份")],
                extras=["加鸡蛋"],
                item_remark="不要香菜",
            )],
            total=40,
        )
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200, result.msg)
        order_id = int(result.data["id"])

        # Mutate current menu config after order creation.
        self.dish.name = "宫保辣子鸡"
        self.dish.price = "99.00"
        await self.db.commit()
        config = (await self.db.execute(
            select(TenantConfig).where(TenantConfig.tenant_id == TENANT_A)
        )).scalar_one()
        specs = dict(config.business_info.get("menu_item_specs") or {})
        specs[str(self.dish.id)] = [
            {"name": "份量", "type": "single", "options": [
                {"name": "小份", "price_delta": 0},
                {"name": "豪华大份", "price_delta": 999},
            ]},
            {"name": "加料", "type": "multi", "options": [
                {"name": "双蛋", "price_delta": 20},
            ]},
        ]
        config.business_info = {**config.business_info, "menu_item_specs": specs}
        flag_modified(config, "business_info")
        await self.db.commit()

        item = (await self.db.execute(
            select(OrderItem).where(OrderItem.order_id == order_id)
        )).scalars().one()
        self.assertEqual(item.name, "宫保鸡丁(大份、加鸡蛋)")
        self.assertEqual(item.item_remark, "不要香菜")
        self.assertEqual(str(item.price), "40.00")

    # ---- S10: print shows remark exactly once, split from name ----
    async def test_s10_print_shows_remark_exactly_once(self):
        from app.services.kuaimai_service import build_order_template_render_data

        body = OrderCreate(
            shop=TENANT_A, table="",
            items=[OrderItemIn(
                dish_id=self.dish.id, name="宫保鸡丁(大份、加鸡蛋)", price=40, qty=1,
                specifications=[OrderItemSpecIn(group="份量", value="大份")],
                extras=["加鸡蛋"],
                item_remark="不要香菜",
            )],
            total=40,
        )
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200, result.msg)
        order_id = int(result.data["id"])
        order = (await self.db.execute(select(Order).where(Order.id == order_id))).scalar_one()
        items = (await self.db.execute(
            select(OrderItem).where(OrderItem.order_id == order_id)
        )).scalars().all()

        render = build_order_template_render_data(order, items, shop_name="Remark Restaurant")
        row = render["items"][0]
        self.assertEqual(row["goods_name"], "宫保鸡丁(大份、加鸡蛋)")
        self.assertNotIn("不要香菜", row["goods_name"])
        self.assertEqual(row["display_name"].count("不要香菜"), 1)
        self.assertIn("备注：不要香菜", row["display_name"])

    # ---- S11: backward-compatible serialization across all consumers ----
    async def test_s11_backward_compatible_serialization(self):
        body = OrderCreate(
            shop=TENANT_A, table="",
            items=[OrderItemIn(
                dish_id=self.dish.id, name="宫保鸡丁(大份、加鸡蛋)", price=40, qty=1,
                specifications=[OrderItemSpecIn(group="份量", value="大份")],
                extras=["加鸡蛋"],
                item_remark="不要香菜",
            )],
            total=40,
        )
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200, result.msg)
        order_id = int(result.data["id"])

        # create_order's own response (serialize_order under the hood).
        create_item = result.data["items"][0]
        self.assertEqual(create_item["name"], "宫保鸡丁(大份、加鸡蛋、不要香菜)")
        self.assertEqual(create_item["item_remark"], "不要香菜")

        order = (await self.db.execute(select(Order).where(Order.id == order_id))).scalar_one()
        items = (await self.db.execute(
            select(OrderItem).where(OrderItem.order_id == order_id)
        )).scalars().all()

        # Admin list (shared serialize_order).
        admin_result = await list_orders(make_owner_request(), date_str="today", db=self.db)
        admin_order = next(o for o in admin_result.data if o["id"] == str(order_id))
        self.assertEqual(admin_order["items"][0]["name"], "宫保鸡丁(大份、加鸡蛋、不要香菜)")
        self.assertEqual(admin_order["items"][0]["item_remark"], "不要香菜")

        # DiningSessionService's own serializer.
        ds_dict = DiningSessionService(self.db)._serialize_order(order, items)
        self.assertEqual(ds_dict["items"][0]["name"], "宫保鸡丁(大份、加鸡蛋、不要香菜)")
        self.assertEqual(ds_dict["items"][0]["item_remark"], "不要香菜")

        # Staff fulfillment workbench.
        fulfillment = serialize_fulfillment_order(order, items)
        self.assertEqual(fulfillment["items"][0]["name"], "宫保鸡丁(大份、加鸡蛋、不要香菜)")
        self.assertEqual(fulfillment["items"][0]["item_remark"], "不要香菜")

        # Waiter recent-served DTO.
        served = serialize_recent_served_order(order, items)
        self.assertEqual(served["items"][0]["name"], "宫保鸡丁(大份、加鸡蛋、不要香菜)")
        self.assertEqual(served["items"][0]["item_remark"], "不要香菜")

    async def test_s11b_no_remark_composed_name_unchanged(self):
        body = OrderCreate(
            shop=TENANT_A, table="",
            items=[OrderItemIn(dish_id=self.dish.id, name="宫保鸡丁", price=28, qty=1)],
            total=28,
        )
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200, result.msg)
        self.assertEqual(result.data["items"][0]["name"], "宫保鸡丁")
        self.assertIsNone(result.data["items"][0]["item_remark"])

    # ---- S12: financial P0-02 contracts remain green alongside remark logic ----
    async def test_s12a_item_price_tamper_still_rejected(self):
        body = OrderCreate(
            shop=TENANT_A, table="",
            items=[OrderItemIn(dish_id=self.dish.id, name="宫保鸡丁", price=0.01, qty=1)],
            total=0.01,
        )
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 400)
        self.assertEqual(await self._order_count(), 0)

    async def test_s12b_total_tamper_ignored_server_recomputes(self):
        body = OrderCreate(
            shop=TENANT_A, table="",
            items=[OrderItemIn(
                dish_id=self.dish.id, name="宫保鸡丁(大份、加鸡蛋)", price=40, qty=2,
                specifications=[OrderItemSpecIn(group="份量", value="大份")],
                extras=["加鸡蛋"],
                item_remark="不要香菜",
            )],
            total=1.0,
        )
        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200, result.msg)
        self.assertEqual(result.data["total"], 80.0)
        order = (await self.db.execute(select(Order).where(Order.id == int(result.data["id"])))).scalar_one()
        expected_fen = max(1, round(float(order.total) * 100))
        self.assertEqual(expected_fen, 8000)


if __name__ == "__main__":
    unittest.main()
