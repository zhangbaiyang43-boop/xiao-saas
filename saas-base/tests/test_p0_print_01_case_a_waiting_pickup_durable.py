"""P0-PRINT-01 Case A: WAITING_PICKUP_NO must be durable NOT_ELIGIBLE, not PENDING.

PENDING means provider-eligible. Prepay paid + pickup defer + pickup_no=null
must write NOT_ELIGIBLE; first staff assignment unlocks exactly one claim and
exactly one provider submission. Recovery must not churn waiting orders.
"""
from __future__ import annotations

import ast
import asyncio
import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy import event, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.config import settings
from app.models.base import Base
from app.models.dining import DiningSession
from app.models.entrance_code import EntranceCode
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.models.tenant_config import TenantConfig
from app.services.order_lifecycle_service import OrderLifecycleService
from app.services.order_payment_service import OrderPaymentService
from app.services.order_print_service import (
    PRINT_RECONCILE_BATCH_LIMIT,
    PRINT_RECONCILE_GRACE_SECONDS,
    _get_print_meta,
    ensure_initial_print_intent,
    recover_pending_print_orders_once,
)
from app.services.subscription_service import STATUS_TRIAL
from app.utils.id_generator import generate_snowflake_id

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
PAYMENT_SERVICE = ROOT / "app" / "services" / "order_payment_service.py"
PRINT_SERVICE = ROOT / "app" / "services" / "order_print_service.py"

TENANT_A = "tenant-case-a"
TENANT_B = "tenant-case-b"


@event.listens_for(OrderItem, "before_insert")
def _assign_order_item_id_for_sqlite(mapper, connection, target):
    if target.id is None:
        target.id = generate_snowflake_id()


def _function_source(path: Path, function_name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"missing function: {function_name}")


def make_merchant_request(tenant_id: str) -> Request:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/orders",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    request.state.tenant_id = tenant_id
    request.state.token_type = "merchant"
    request.state.role = "owner"
    request.state.account_id = None
    return request


def _pickup_business_info(*, enabled: bool, required_before_print: bool) -> dict:
    return {
        "printer_provider": "kuaimai",
        "kuaimai_printer": {
            "app_id": "app_1",
            "app_secret": "secret_1",
            "sn": "KM001",
            "order_template_id": "1634998374",
        },
        "pickup_no_enabled": enabled,
        "pickup_no_count": 37,
        "pickup_no_required_before_print": required_before_print,
    }


def _initial(order: Order) -> dict:
    meta = _get_print_meta(order)
    initial = meta.get("initial_print")
    return initial if isinstance(initial, dict) else {}


class CaseAWaitingPickupDurableTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._original_redis_enabled = settings.REDIS_ENABLED
        settings.REDIS_ENABLED = False

        self._db_file = f"{tempfile.gettempdir()}/p0_print_01_case_a_{uuid.uuid4().hex}.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_file}")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self._session_patch = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._session_patch.start()

        self.provider = AsyncMock(return_value="task-case-a")
        self._provider_patch = patch(
            "app.services.order_print_service._execute_provider_with_frozen_route",
            self.provider,
        )
        self._provider_patch.start()

        now = datetime.utcnow()
        self.db.add_all([
            Plan(code="FREE", name="免费版", is_active=True, price_month_cents=0, price_year_cents=0, sort_order=0),
            Plan(code="STANDARD", name="普通版", is_active=True, price_month_cents=5900, price_year_cents=60900, sort_order=1),
            Plan(code="PRO", name="专业版", is_active=True, price_month_cents=9900, price_year_cents=102200, sort_order=2),
        ])
        await self.db.flush()
        pro = (await self.db.execute(select(Plan).where(Plan.code == "PRO"))).scalar_one()

        for tid, mode, enabled, required in (
            (TENANT_A, "prepay", True, True),
            (TENANT_B, "prepay", True, True),
        ):
            self.db.add(
                Tenant(
                    tenant_id=tid,
                    name=f"Shop {tid}",
                    password_hash="x",
                    status=True,
                    is_open=True,
                    payment_mode=mode,
                    feieyun_sn="SN001",
                    feieyun_key="KEY001",
                )
            )
            self.db.add(
                TenantConfig(
                    tenant_id=tid,
                    member_rules={},
                    coupon_rules={},
                    business_info=_pickup_business_info(enabled=enabled, required_before_print=required),
                    plugin_settings={},
                )
            )
            self.db.add(
                Subscription(
                    tenant_id=tid,
                    plan_id=pro.id,
                    status=STATUS_TRIAL,
                    trial_started_at=now,
                    trial_ends_at=now + timedelta(days=30),
                )
            )
        self.dish_a = MenuItem(tenant_id=TENANT_A, name="SoupA", price="25.00", available=True)
        self.dish_b = MenuItem(tenant_id=TENANT_B, name="SoupB", price="25.00", available=True)
        self.db.add_all([self.dish_a, self.dish_b])
        for tid, tables in ((TENANT_A, ("A01", "A02", "P1", "G1", "H1")), (TENANT_B, ("B01",))):
            for table_no in tables:
                self.db.add(
                    EntranceCode(
                        id=generate_snowflake_id(),
                        tenant_id=tid,
                        name=table_no,
                        scene=f"E{tid[-1]}{table_no}",
                        table_no=table_no,
                        entry_type="table",
                        status=1,
                    )
                )
        await self.db.commit()

    async def asyncTearDown(self):
        self._provider_patch.stop()
        self._session_patch.stop()
        settings.REDIS_ENABLED = self._original_redis_enabled
        await self.db.close()
        await self.engine.dispose()
        try:
            os.remove(self._db_file)
        except OSError:
            pass

    async def _set_pickup(self, tenant_id: str, *, enabled: bool, required_before_print: bool) -> None:
        config = (
            await self.db.execute(select(TenantConfig).where(TenantConfig.tenant_id == tenant_id))
        ).scalar_one()
        info = dict(config.business_info or {})
        info.update(_pickup_business_info(enabled=enabled, required_before_print=required_before_print))
        config.business_info = info
        await self.db.commit()

    async def _insert_prepay_unpaid(self, tenant_id: str, table: str, *, pickup_no: str | None = None) -> Order:
        now = datetime.utcnow()
        session = DiningSession(
            tenant_id=tenant_id,
            table_no=table,
            status="OPEN",
            active_key=f"{tenant_id}:{table}:{uuid.uuid4().hex}",
            started_at=now,
            last_activity_at=now,
            pickup_no=pickup_no,
        )
        self.db.add(session)
        await self.db.flush()
        order = Order(
            tenant_id=tenant_id,
            dining_session_id=session.id,
            table_no=table,
            total=25,
            status="pending_payment",
            payment_status="unpaid",
            payment_mode="prepay",
            source="miniprogram",
            pickup_no=pickup_no,
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def _pay(self, order: Order) -> Order:
        svc = OrderPaymentService(self.db)
        await svc._on_payment_success(order, payment_method="mock")
        await self.db.commit()
        await svc._run_post_commit_payment_effects(order)
        await self.db.refresh(order)
        return order

    async def _assign(self, order: Order, pickup_no: str):
        svc = OrderLifecycleService(self.db)
        svc.set_tenant_id(str(order.tenant_id))
        result = await svc.update_order_pickup_no(int(order.id), pickup_no)
        await self.db.refresh(order)
        return result

    async def _backdate(self, order: Order, seconds: int = 60) -> None:
        old = datetime.utcnow() - timedelta(seconds=seconds)
        await self.db.execute(update(Order).where(Order.id == order.id).values(updated_at=old))
        await self.db.commit()
        await self.db.refresh(order)

    def _assert_waiting(self, order: Order) -> None:
        initial = _initial(order)
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.print_status, "NOT_ELIGIBLE")
        self.assertEqual(initial.get("status"), "NOT_ELIGIBLE")
        self.assertEqual(int(initial.get("attempts") or 0), 0)
        self.assertIsNone(initial.get("last_attempt_at"))
        self.assertEqual(self.provider.await_count, 0)

    # ------------------------------------------------------------------ A
    async def test_a_immediate_print_when_pickup_disabled(self):
        await self._set_pickup(TENANT_A, enabled=False, required_before_print=True)
        order = await self._insert_prepay_unpaid(TENANT_A, "A01")
        self.assertEqual(order.print_status, "PENDING")
        await self._pay(order)

        initial = _initial(order)
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.print_status, "SUCCESS")
        self.assertEqual(initial.get("status"), "SUCCESS")
        self.assertEqual(int(initial.get("attempts") or 0), 1)
        self.assertEqual(self.provider.await_count, 1)

    async def test_a_immediate_print_when_required_before_print_false(self):
        await self._set_pickup(TENANT_A, enabled=True, required_before_print=False)
        order = await self._insert_prepay_unpaid(TENANT_A, "A01")
        await self._pay(order)

        initial = _initial(order)
        self.assertEqual(order.print_status, "SUCCESS")
        self.assertEqual(initial.get("status"), "SUCCESS")
        self.assertEqual(int(initial.get("attempts") or 0), 1)
        self.assertEqual(self.provider.await_count, 1)

    # ------------------------------------------------------------------ B
    async def test_b_waiting_pickup_writes_not_eligible(self):
        order = await self._insert_prepay_unpaid(TENANT_A, "A01")
        self.assertIsNone(order.pickup_no)
        await self._pay(order)
        self._assert_waiting(order)

    async def test_b_ensure_intent_eligible_false_overrides_pending_default(self):
        order = await self._insert_prepay_unpaid(TENANT_A, "A01")
        self.assertEqual(order.print_status, "PENDING")
        await ensure_initial_print_intent(
            order, self.db, eligible=False, reason="payment_success",
        )
        await self.db.commit()
        await self.db.refresh(order)
        initial = _initial(order)
        self.assertEqual(order.print_status, "NOT_ELIGIBLE")
        self.assertEqual(initial.get("status"), "NOT_ELIGIBLE")
        self.assertIsNone(initial.get("last_attempt_at"))
        self.assertEqual(int(initial.get("attempts") or 0), 0)
        self.assertEqual(self.provider.await_count, 0)

    # ------------------------------------------------------------------ C
    async def test_c_recovery_does_not_churn_waiting_order(self):
        order = await self._insert_prepay_unpaid(TENANT_A, "A01")
        await self._pay(order)
        self._assert_waiting(order)
        await self._backdate(order, seconds=PRINT_RECONCILE_GRACE_SECONDS + 45)

        recovery_logs: list[str] = []

        def _capture_info(msg, *args, **kwargs):
            rendered = msg % args if args else str(msg)
            recovery_logs.append(rendered)

        with patch("app.services.order_print_service.logger.info", side_effect=_capture_info):
            handled_1 = await recover_pending_print_orders_once(self.db)
            handled_2 = await recover_pending_print_orders_once(self.db)

        await self.db.refresh(order)
        self.assertEqual(handled_1, 0)
        self.assertEqual(handled_2, 0)
        self._assert_waiting(order)
        self.assertFalse(
            any(
                "PRINT_RECOVERY_ATTEMPT" in line and str(order.id) in line
                for line in recovery_logs
            )
        )

    async def test_c_not_eligible_does_not_occupy_recovery_batch_limit(self):
        waiting_ids = []
        for idx in range(PRINT_RECONCILE_BATCH_LIMIT):
            order = await self._insert_prepay_unpaid(TENANT_A, "A01")
            order.payment_status = "paid"
            order.status = "pending"
            order.payment_time = datetime.utcnow().isoformat()
            await ensure_initial_print_intent(
                order, self.db, eligible=False, reason="payment_success",
            )
            await self.db.commit()
            waiting_ids.append(order.id)
            await self._backdate(order, seconds=PRINT_RECONCILE_GRACE_SECONDS + 90 + idx)

        await self._set_pickup(TENANT_B, enabled=False, required_before_print=False)
        eligible = await self._insert_prepay_unpaid(TENANT_B, "B01")
        eligible.payment_status = "paid"
        eligible.status = "pending"
        eligible.payment_time = datetime.utcnow().isoformat()
        await ensure_initial_print_intent(
            eligible, self.db, eligible=True, reason="payment_success",
        )
        await self.db.commit()
        self.assertEqual(eligible.print_status, "PENDING")
        await self._backdate(eligible, seconds=PRINT_RECONCILE_GRACE_SECONDS + 5)

        self.provider.reset_mock()
        handled = await recover_pending_print_orders_once(self.db)
        await self.db.refresh(eligible)
        self.assertGreaterEqual(handled, 1)
        self.assertEqual(self.provider.await_count, 1)
        self.assertEqual(eligible.print_status, "SUCCESS")

        for oid in waiting_ids:
            waiting = await self.db.get(Order, oid)
            self.assertEqual(waiting.print_status, "NOT_ELIGIBLE")
            self.assertEqual(int(_initial(waiting).get("attempts") or 0), 0)

    # ------------------------------------------------------------------ D
    async def test_d_pickup_assignment_unlocks_exactly_once(self):
        order = await self._insert_prepay_unpaid(TENANT_A, "A01")
        await self._pay(order)
        self._assert_waiting(order)

        result = await self._assign(order, "12")
        self.assertEqual(result.code, 200, result.msg)
        initial = _initial(order)
        self.assertEqual(order.pickup_no, "12")
        self.assertEqual(order.print_status, "SUCCESS")
        self.assertEqual(initial.get("status"), "SUCCESS")
        self.assertEqual(int(initial.get("attempts") or 0), 1)
        self.assertEqual(self.provider.await_count, 1)

    # ------------------------------------------------------------------ E
    async def test_e_repeated_payment_assign_and_recovery_stay_idempotent(self):
        order = await self._insert_prepay_unpaid(TENANT_A, "A01")
        await self._pay(order)
        self._assert_waiting(order)

        # Repeated payment callback / recovery on an already-paid waiting order.
        await self._pay(order)
        await self._backdate(order, seconds=PRINT_RECONCILE_GRACE_SECONDS + 45)
        await recover_pending_print_orders_once(self.db)
        await self.db.refresh(order)
        self._assert_waiting(order)

        result = await self._assign(order, "12")
        self.assertEqual(result.code, 200, result.msg)
        self.assertEqual(self.provider.await_count, 1)

        await self._pay(order)
        again = await self._assign(order, "12")
        self.assertEqual(again.code, 200, again.msg)
        await self._backdate(order, seconds=PRINT_RECONCILE_GRACE_SECONDS + 45)
        await recover_pending_print_orders_once(self.db)
        await recover_pending_print_orders_once(self.db)
        await self.db.refresh(order)

        initial = _initial(order)
        self.assertEqual(order.print_status, "SUCCESS")
        self.assertEqual(int(initial.get("attempts") or 0), 1)
        self.assertEqual(self.provider.await_count, 1)

    # ------------------------------------------------------------------ F
    async def test_f_success_recovery_does_not_resend(self):
        await self._set_pickup(TENANT_A, enabled=False, required_before_print=True)
        order = await self._insert_prepay_unpaid(TENANT_A, "A01")
        await self._pay(order)
        self.assertEqual(order.print_status, "SUCCESS")
        self.assertEqual(self.provider.await_count, 1)

        await self._backdate(order, seconds=PRINT_RECONCILE_GRACE_SECONDS + 45)
        await recover_pending_print_orders_once(self.db)
        await recover_pending_print_orders_once(self.db)
        await self.db.refresh(order)

        initial = _initial(order)
        self.assertEqual(order.print_status, "SUCCESS")
        self.assertEqual(int(initial.get("attempts") or 0), 1)
        self.assertEqual(self.provider.await_count, 1)

    # ------------------------------------------------------------------ G / H
    async def _create_pay_later(self, tenant_id: str, table: str, payment_mode: str) -> Order:
        from app.api.v1.orders import OrderCreate, OrderItemIn, create_order

        tenant = (await self.db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))).scalar_one()
        tenant.payment_mode = payment_mode
        await self.db.commit()
        dish = self.dish_a if tenant_id == TENANT_A else self.dish_b
        body = OrderCreate(
            shop=tenant_id,
            table=table,
            items=[OrderItemIn(dish_id=dish.id, name=dish.name, price=float(dish.price), qty=1)],
            total=float(dish.price),
        )
        result = await create_order(body, make_merchant_request(tenant_id), self.db)
        self.assertEqual(result.code, 200, result.msg)
        order = await self.db.get(Order, int(result.data["id"]))
        await self.db.refresh(order)
        return order

    async def test_g_postpay_waiting_then_assignment_prints_once(self):
        order = await self._create_pay_later(TENANT_A, "G1", "postpay")
        self.assertEqual(order.payment_mode, "postpay")
        self.assertIsNone(order.pickup_no)
        initial = _initial(order)
        self.assertEqual(order.print_status, "NOT_ELIGIBLE")
        self.assertEqual(initial.get("status"), "NOT_ELIGIBLE")
        self.assertEqual(self.provider.await_count, 0)

        await self._backdate(order, seconds=PRINT_RECONCILE_GRACE_SECONDS + 45)
        handled = await recover_pending_print_orders_once(self.db)
        await self.db.refresh(order)
        self.assertEqual(handled, 0)
        self.assertEqual(order.print_status, "NOT_ELIGIBLE")
        self.assertEqual(self.provider.await_count, 0)

        result = await self._assign(order, "15")
        self.assertEqual(result.code, 200, result.msg)
        initial = _initial(order)
        self.assertEqual(order.print_status, "SUCCESS")
        self.assertEqual(int(initial.get("attempts") or 0), 1)
        self.assertEqual(self.provider.await_count, 1)

    async def test_h_table_account_waiting_then_assignment_prints_once(self):
        order = await self._create_pay_later(TENANT_A, "H1", "table_account")
        self.assertEqual(order.payment_mode, "table_account")
        self.assertIsNone(order.pickup_no)
        initial = _initial(order)
        self.assertEqual(order.print_status, "NOT_ELIGIBLE")
        self.assertEqual(initial.get("status"), "NOT_ELIGIBLE")
        self.assertEqual(self.provider.await_count, 0)

        result = await self._assign(order, "16")
        self.assertEqual(result.code, 200, result.msg)
        initial = _initial(order)
        self.assertEqual(order.print_status, "SUCCESS")
        self.assertEqual(int(initial.get("attempts") or 0), 1)
        self.assertEqual(self.provider.await_count, 1)

    # ------------------------------------------------------------------ I
    async def test_i_tenant_a_actions_do_not_mutate_tenant_b(self):
        order_b = await self._insert_prepay_unpaid(TENANT_B, "B01")
        await self._pay(order_b)
        self.assertEqual(order_b.print_status, "NOT_ELIGIBLE")
        note_b = order_b.merchant_note
        status_b = order_b.status
        payment_b = order_b.payment_status
        pickup_b = order_b.pickup_no
        attempts_b = int(_initial(order_b).get("attempts") or 0)

        order_a = await self._insert_prepay_unpaid(TENANT_A, "A01")
        await self._pay(order_a)
        await self._assign(order_a, "12")
        await self._backdate(order_a, seconds=PRINT_RECONCILE_GRACE_SECONDS + 45)
        await recover_pending_print_orders_once(self.db)

        await self.db.refresh(order_b)
        self.assertEqual(order_b.print_status, "NOT_ELIGIBLE")
        self.assertEqual(order_b.merchant_note, note_b)
        self.assertEqual(order_b.status, status_b)
        self.assertEqual(order_b.payment_status, payment_b)
        self.assertEqual(order_b.pickup_no, pickup_b)
        self.assertEqual(int(_initial(order_b).get("attempts") or 0), attempts_b)


def test_source_payment_success_uses_existing_pickup_defer_helpers():
    source = _function_source(PAYMENT_SERVICE, "_on_payment_success")
    assert "load_pickup_settings" in source
    assert "should_defer_kitchen_print" in source
    assert "eligible=not defer" in source
    assert "eligible=True" not in source


def test_source_recovery_sql_excludes_not_eligible_without_extra_filter():
    source = _function_source(PRINT_SERVICE, "recover_pending_print_orders_once")
    assert 'Order.print_status.in_(["PENDING", "FAILED", "SENDING"])' in source
    assert "NOT_ELIGIBLE" not in source
    assert source.count("print_status") >= 1


def test_source_claim_still_commits_before_provider_io():
    source = _function_source(PRINT_SERVICE, "_claim_initial_print_attempt")
    send_at = source.find('"SENDING"')
    attempts_at = source.find("attempts")
    last_at = source.find("last_attempt_at")
    commit_at = source.find("await db.commit()")
    assert send_at >= 0
    assert attempts_at >= 0
    assert last_at >= 0
    assert commit_at > send_at
    assert commit_at > attempts_at
    assert commit_at > last_at
    assert "_execute_provider_with_frozen_route" not in source
