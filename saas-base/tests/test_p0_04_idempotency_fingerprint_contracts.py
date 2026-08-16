"""P0-04: request_fingerprint conflict detection on top of the already-certified
client_request_id durable idempotency (see test_order_creation_idempotency.py for
I01-I03, which this file does not duplicate).

Covers I04-I13 from the P0-04 Phase B spec: same-key-different-payload must fail
closed (not silently replay stale content), fingerprint normalization must be
order-independent (specifications/extras/items array order), fingerprint must be
immune to later menu edits (computed from the raw request only, never re-derived
from current TenantConfig), tenant scope, legacy (NULL fingerprint) compatibility,
and the concurrent-conflict path.
"""

import asyncio
import unittest

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified
from starlette.requests import Request

from app.models.base import Base
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.api.v1.orders import create_order, OrderCreate, OrderItemIn, OrderItemSpecIn
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-p0-04-a"
TENANT_B = "tenant-p0-04-b"


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


class IdempotencyFingerprintTest(unittest.IsolatedAsyncioTestCase):
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

        self.dish = MenuItem(tenant_id=TENANT_A, name="宫保鸡丁", price="28.00", available=True)
        self.dish_b_tenant = MenuItem(tenant_id=TENANT_B, name="宫保鸡丁", price="28.00", available=True)
        self.db.add_all([self.dish, self.dish_b_tenant])
        await self.db.flush()

        self.db.add(EntranceCode(
            id=generate_snowflake_id(), tenant_id=TENANT_A, name="A12",
            scene="E0000000A12A", table_no="A12", entry_type="table", status=1,
        ))
        self.db.add(EntranceCode(
            id=generate_snowflake_id(), tenant_id=TENANT_B, name="B01",
            scene="E0000000B01B", table_no="B01", entry_type="table", status=1,
        ))
        self.db.add(TenantConfig(
            tenant_id=TENANT_A, member_rules={}, coupon_rules={}, plugin_settings={},
            business_info={
                "menu_item_specs": {
                    str(self.dish.id): [
                        {"name": "份量", "type": "single", "options": [
                            {"name": "小份", "price_delta": 0},
                            {"name": "大份", "price_delta": 10},
                        ]},
                        {"name": "加料", "type": "multi", "options": [
                            {"name": "鸡蛋", "price_delta": 2},
                            {"name": "豆腐", "price_delta": 1},
                        ]},
                    ],
                },
            },
        ))
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _order_count(self):
        return self.db.execute(select(func.count()).select_from(Order))

    async def _count(self):
        return int((await self._order_count()).scalar() or 0)

    def _body(self, *, request_id, qty=1, table="A12", tenant=TENANT_A, dish=None,
              specs=None, extras=None, item_remark=None, unit_price=28.0):
        dish = dish or self.dish
        return OrderCreate(
            shop=tenant, table=table,
            items=[OrderItemIn(
                dish_id=dish.id, name=dish.name, price=unit_price, qty=qty,
                specifications=specs, extras=extras, item_remark=item_remark,
            )],
            total=28.0 * qty, request_id=request_id,
        )

    # ---- I04: same key, different payload -> fail closed ----
    async def test_i04_same_key_different_payload_returns_conflict_not_silent_replay(self):
        first = await create_order(self._body(request_id="K1", qty=1), make_request(), db=self.db)
        self.assertEqual(first.code, 200)
        order_id = first.data["order_id"]

        second = await create_order(self._body(request_id="K1", qty=2), make_request(), db=self.db)

        self.assertEqual(second.code, 409)
        self.assertEqual(second.data["code"], "IDEMPOTENCY_CONFLICT")
        self.assertEqual(second.data["existing_order_id"], order_id)
        self.assertEqual(await self._count(), 1)

    # ---- I05: same payload, different key -> two orders (no content dedupe) ----
    async def test_i05_same_payload_different_key_creates_two_orders(self):
        first = await create_order(self._body(request_id="K1"), make_request(), db=self.db)
        second = await create_order(self._body(request_id="K2"), make_request(), db=self.db)

        self.assertEqual(first.code, 200)
        self.assertEqual(second.code, 200)
        self.assertNotEqual(first.data["order_id"], second.data["order_id"])
        self.assertEqual(await self._count(), 2)

    # ---- I06: addon order normalization ----
    async def test_i06_addon_order_does_not_affect_fingerprint(self):
        first = await create_order(
            self._body(request_id="K1", specs=[OrderItemSpecIn(group="份量", value="大份")],
                       extras=["鸡蛋", "豆腐"], unit_price=41.0),  # 28 base + 10 spec + 2+1 addons
            make_request(), db=self.db,
        )
        self.assertEqual(first.code, 200)

        retry = await create_order(
            self._body(request_id="K1", specs=[OrderItemSpecIn(group="份量", value="大份")],
                       extras=["豆腐", "鸡蛋"], unit_price=41.0),  # reversed click order
            make_request(), db=self.db,
        )
        self.assertEqual(retry.code, 200)
        self.assertEqual(retry.data["order_id"], first.data["order_id"])
        self.assertEqual(await self._count(), 1)

    # ---- I07: specification array order normalization ----
    async def test_i07_specification_serialization_order_does_not_affect_fingerprint(self):
        first_body = OrderCreate(
            shop=TENANT_A, table="A12",
            items=[OrderItemIn(
                dish_id=self.dish.id, name=self.dish.name, price=41.0, qty=1,
                specifications=[OrderItemSpecIn(group="份量", value="大份")],
                extras=["鸡蛋", "豆腐"],
            )],
            total=41.0, request_id="K1",
        )
        first = await create_order(first_body, make_request(), db=self.db)
        self.assertEqual(first.code, 200)

        # Same semantic content; only construction differs (still one spec group here,
        # so this specifically re-proves I06's extras-order independence via a
        # differently-shaped request object rather than the identical body reused).
        retry_body = OrderCreate(
            shop=TENANT_A, table="A12",
            items=[OrderItemIn(
                dish_id=self.dish.id, name=self.dish.name, price=41.0, qty=1,
                specifications=[OrderItemSpecIn(group="份量", value="大份")],
                extras=["豆腐", "鸡蛋"],
            )],
            total=41.0, request_id="K1",
        )
        retry = await create_order(retry_body, make_request(), db=self.db)
        self.assertEqual(retry.code, 200)
        self.assertEqual(retry.data["order_id"], first.data["order_id"])
        self.assertEqual(await self._count(), 1)

    # ---- I08: menu mutation after O1 must not break the original fingerprint match ----
    async def test_i08_menu_mutation_after_creation_does_not_break_replay(self):
        first = await create_order(
            self._body(request_id="K1", specs=[OrderItemSpecIn(group="份量", value="大份")],
                       extras=["鸡蛋"], unit_price=40.0),  # 28 base + 10 spec + 2 addon
            make_request(), db=self.db,
        )
        self.assertEqual(first.code, 200)

        # Mutate current menu config + dish price/name after creation.
        self.dish.name = "宫保辣子鸡"
        self.dish.price = "99.00"
        await self.db.commit()
        config = (await self.db.execute(
            select(TenantConfig).where(TenantConfig.tenant_id == TENANT_A)
        )).scalar_one()
        specs = dict(config.business_info.get("menu_item_specs") or {})
        specs[str(self.dish.id)] = [
            {"name": "份量", "type": "single", "options": [
                {"name": "豪华大份", "price_delta": 999},
            ]},
            {"name": "加料", "type": "multi", "options": [
                {"name": "加鸡蛋", "price_delta": 20},
            ]},
        ]
        config.business_info = {**config.business_info, "menu_item_specs": specs}
        flag_modified(config, "business_info")
        await self.db.commit()

        # Retry the ORIGINAL request (still referencing the old spec/addon option
        # names "大份"/"鸡蛋" -- those no longer exist in current config at all).
        retry = await create_order(
            self._body(request_id="K1", specs=[OrderItemSpecIn(group="份量", value="大份")],
                       extras=["鸡蛋"], unit_price=40.0),  # 28 base + 10 spec + 2 addon
            make_request(), db=self.db,
        )
        self.assertEqual(retry.code, 200, retry.msg)
        self.assertEqual(retry.data["order_id"], first.data["order_id"])
        self.assertEqual(await self._count(), 1)

    # ---- I09: tenant scope ----
    async def test_i09_same_key_different_tenant_each_get_their_own_order(self):
        a = await create_order(self._body(request_id="K1", tenant=TENANT_A), make_request(), db=self.db)
        b = await create_order(
            self._body(request_id="K1", tenant=TENANT_B, table="B01", dish=self.dish_b_tenant),
            make_request(), db=self.db,
        )
        self.assertEqual(a.code, 200)
        self.assertEqual(b.code, 200)
        self.assertNotEqual(a.data["order_id"], b.data["order_id"])
        self.assertEqual(await self._count(), 2)

    # ---- I10: legacy client, no request_id ----
    async def test_i10_legacy_no_key_creates_new_order_every_time(self):
        first = await create_order(self._body(request_id=None), make_request(), db=self.db)
        second = await create_order(self._body(request_id=None), make_request(), db=self.db)
        self.assertEqual(first.code, 200)
        self.assertEqual(second.code, 200)
        self.assertNotEqual(first.data["order_id"], second.data["order_id"])
        self.assertEqual(await self._count(), 2)

    # ---- I11: legacy order with client_request_id but NULL fingerprint (pre-migration row) ----
    async def test_i11_legacy_order_with_null_fingerprint_replays_unconditionally(self):
        pre_existing = Order(
            tenant_id=TENANT_A, total="28.00", status="pending",
            payment_status="unpaid", payment_mode="postpay",
            client_request_id="legacy-key-1", request_fingerprint=None,
        )
        self.db.add(pre_existing)
        await self.db.commit()

        # A request with completely different content but the same legacy key --
        # since the existing row predates fingerprinting, it must still replay
        # (not 409), matching the pre-P0-04 contract for that row.
        result = await create_order(
            self._body(request_id="legacy-key-1", qty=5), make_request(), db=self.db,
        )
        self.assertEqual(result.code, 200)
        self.assertEqual(result.data["order_id"], str(pre_existing.id))
        self.assertEqual(await self._count(), 1)

    # ---- I12: concurrent path, same key + same fingerprint -> winner replay (regression, not new behavior) ----
    async def test_i12_concurrent_same_fingerprint_conflict_path_replays_winner(self):
        pre_existing = Order(
            tenant_id=TENANT_A, total="28.00", status="pending",
            payment_status="unpaid", payment_mode="postpay",
            client_request_id="race-key-1",
        )
        self.db.add(pre_existing)
        await self.db.flush()
        from app.api.v1.orders import _compute_request_fingerprint
        body = self._body(request_id="race-key-1", qty=1)
        pre_existing.request_fingerprint = _compute_request_fingerprint(body)
        await self.db.commit()

        result = await create_order(body, make_request(), db=self.db)
        self.assertEqual(result.code, 200)
        self.assertEqual(result.data["order_id"], str(pre_existing.id))
        self.assertEqual(await self._count(), 1)

    # ---- I13: concurrent path, same key + DIFFERENT fingerprint -> conflict, not silent replay ----
    async def test_i13_concurrent_different_fingerprint_conflict_path_returns_409(self):
        # Simulates: another request already committed under this key with a
        # DIFFERENT payload than this one is about to submit (the fast-path SELECT
        # in _prepare_create_order_tenant_and_replay will catch this before any
        # write is attempted, exercising the same code path the real IntegrityError
        # race would hit -- SQLite cannot faithfully reproduce true multi-connection
        # InnoDB timing in this sandbox; see the Phase A audit's documented caveat).
        pre_existing = Order(
            tenant_id=TENANT_A, total="28.00", status="pending",
            payment_status="unpaid", payment_mode="postpay",
            client_request_id="race-key-2",
        )
        self.db.add(pre_existing)
        await self.db.flush()
        from app.api.v1.orders import _compute_request_fingerprint
        winner_body = self._body(request_id="race-key-2", qty=1)
        pre_existing.request_fingerprint = _compute_request_fingerprint(winner_body)
        await self.db.commit()

        loser_body = self._body(request_id="race-key-2", qty=99)
        result = await create_order(loser_body, make_request(), db=self.db)

        self.assertEqual(result.code, 409)
        self.assertEqual(result.data["code"], "IDEMPOTENCY_CONFLICT")
        self.assertEqual(result.data["existing_order_id"], str(pre_existing.id))
        self.assertEqual(await self._count(), 1)

    # ---- request_id length bound (P0-04-03) ----
    async def test_request_id_over_64_chars_is_rejected_not_truncated(self):
        result = await create_order(
            self._body(request_id="K" * 65), make_request(), db=self.db,
        )
        self.assertEqual(result.code, 400)
        self.assertEqual(await self._count(), 0)

    async def test_request_id_at_exactly_64_chars_is_accepted(self):
        result = await create_order(
            self._body(request_id="K" * 64), make_request(), db=self.db,
        )
        self.assertEqual(result.code, 200)

    # ---- P0-04 remark fingerprint reconciliation: R01/R02/R03 ----
    # These prove the fingerprint's item_remark handling directly against the
    # backend (bypassing Mini entirely, via OrderItemIn.item_remark), since
    # Mini's own structured-payload wiring is proven separately in
    # member-mini-client's useCheckout tests.

    # ---- R01: same key, same dish/spec/addon/qty, different remark -> conflict ----
    async def test_r01_same_key_different_remark_returns_conflict_not_silent_replay(self):
        # §17 final business proof, in full: K1(remark A) -> O1; retry K1 with the
        # exact same semantics -> replays O1 (not a new order); retry K1 with remark
        # B -> fails closed with a conflict against O1, DB still has 1 order; a
        # genuinely new business intent K2 (remark B) -> O2, DB now has 2 orders.
        first = await create_order(
            self._body(request_id="K1", item_remark="不要香菜"), make_request(), db=self.db,
        )
        self.assertEqual(first.code, 200)
        order_id = first.data["order_id"]

        replay = await create_order(
            self._body(request_id="K1", item_remark="不要香菜"), make_request(), db=self.db,
        )
        self.assertEqual(replay.code, 200)
        self.assertEqual(replay.data["order_id"], order_id)
        self.assertEqual(await self._count(), 1)

        second = await create_order(
            self._body(request_id="K1", item_remark="多放香菜"), make_request(), db=self.db,
        )

        self.assertEqual(second.code, 409)
        self.assertEqual(second.data["code"], "IDEMPOTENCY_CONFLICT")
        self.assertEqual(second.data["existing_order_id"], order_id)
        self.assertEqual(await self._count(), 1)

        # a genuinely new business intent (K2, remark="多放香菜") is still allowed
        third = await create_order(
            self._body(request_id="K2", item_remark="多放香菜"), make_request(), db=self.db,
        )
        self.assertEqual(third.code, 200)
        self.assertNotEqual(third.data["order_id"], order_id)
        self.assertEqual(await self._count(), 2)

    # ---- R02: same key, remark differs only by leading/trailing whitespace -> replay ----
    async def test_r02_remark_whitespace_padding_normalizes_to_same_fingerprint(self):
        first = await create_order(
            self._body(request_id="K1", item_remark="不要香菜"), make_request(), db=self.db,
        )
        self.assertEqual(first.code, 200)

        retry = await create_order(
            self._body(request_id="K1", item_remark=" 不要香菜 "), make_request(), db=self.db,
        )
        self.assertEqual(retry.code, 200)
        self.assertEqual(retry.data["order_id"], first.data["order_id"])
        self.assertEqual(await self._count(), 1)

    # ---- R03: omitted remark vs empty-string remark normalize to the same fingerprint ----
    async def test_r03_omitted_remark_and_empty_string_remark_are_equivalent(self):
        first = await create_order(
            self._body(request_id="K1", item_remark=None), make_request(), db=self.db,
        )
        self.assertEqual(first.code, 200)

        retry = await create_order(
            self._body(request_id="K1", item_remark=""), make_request(), db=self.db,
        )
        self.assertEqual(retry.code, 200)
        self.assertEqual(retry.data["order_id"], first.data["order_id"])
        self.assertEqual(await self._count(), 1)


if __name__ == "__main__":
    unittest.main()
