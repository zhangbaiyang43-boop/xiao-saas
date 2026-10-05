"""P0-PRINT-03: server-side print exception escalation.

Normal path is silent; only a paid order the kitchen may never have received alerts.
Covers detection, per-tenant aggregation, dedupe/reminder cap, recovery, the SMS channel
contract (count only, own budget), shops that do not use printing, and the guarantee that
alerting can neither block fulfilment nor resend anything.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.base import Base
from app.models.order import Order
from app.models.subscription import Plan, Subscription
from app.models.tenant import Tenant
from app.services import print_exception_alert_service as alerts
from app.services.order_print_service import (
    MAX_PRINT_RETRY_ATTEMPTS,
    _set_print_meta,
    _sync_legacy_initial_fields,
)
from app.services.print_exception_alert_service import (
    GROUP_CONFIG,
    GROUP_DELIVERY,
    PRINT_ALERT_DEDUPE_SECONDS,
    PRINT_ALERT_GRACE_SECONDS,
    PRINT_ALERT_MAX_REMINDERS,
    SmsAlertChannel,
    _AlertStore,
    run_print_alert_cycle,
)
from app.services.subscription_service import STATUS_TRIAL
from app.services.tencent_sms_service import SmsSendStatus

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
TENANT_A = "tenant-print03-a"
TENANT_B = "tenant-print03-b"
TENANT_NO_PRINTER = "tenant-print03-noprinter"
TENANT_PARTIAL = "tenant-print03-partial"
PHONES = {
    TENANT_A: "13800000001",
    TENANT_B: "13800000002",
    TENANT_NO_PRINTER: "13800000003",
    TENANT_PARTIAL: "13800000004",
}
ROUTE = {"provider": "feieyun", "printer_identifier": "SN001", "template_or_route_mode": "text", "copies": 1}
PROVIDER_PATH = "app.services.order_print_service._execute_provider_with_frozen_route"
CAPABILITY_PATH = "app.services.optional_entitlement.optional_capability_enabled"


class Clock:
    def __init__(self) -> None:
        self.current = datetime.utcnow()

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


class FakeChannel:
    def __init__(self, *, raise_for=(), deliver=True) -> None:
        self.alerts: list[tuple[str, str, int, str | None]] = []
        self.recovered: list[tuple[str, str, str | None]] = []
        self.raise_for = set(raise_for)
        self.deliver = deliver

    async def send_alert(self, tenant_id, phone, group, count):
        if tenant_id in self.raise_for:
            raise RuntimeError("channel exploded")
        self.alerts.append((tenant_id, group, count, phone))
        return self.deliver

    async def send_recovered(self, tenant_id, phone, group):
        self.recovered.append((tenant_id, group, phone))
        return True


class PrintExceptionEscalationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._original_redis_enabled = settings.REDIS_ENABLED
        settings.REDIS_ENABLED = False

        self._db_file = f"{tempfile.gettempdir()}/p0_print_03_{uuid.uuid4().hex}.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_file}")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self._session_patch = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._session_patch.start()
        # Alerting must never reach a print provider.
        self.provider = AsyncMock(return_value="never")
        self._provider_patch = patch(PROVIDER_PATH, self.provider)
        self._provider_patch.start()

        now = datetime.utcnow()
        self.db.add_all([
            Plan(code="FREE", name="免费版", is_active=True, price_month_cents=0, price_year_cents=0, sort_order=0),
            Plan(code="STANDARD", name="普通版", is_active=True, price_month_cents=5900, price_year_cents=60900, sort_order=1),
            Plan(code="PRO", name="专业版", is_active=True, price_month_cents=9900, price_year_cents=102200, sort_order=2),
        ])
        await self.db.flush()
        pro = (await self.db.execute(select(Plan).where(Plan.code == "PRO"))).scalar_one()
        printers = {
            TENANT_A: ("SN001", "KEY001"),
            TENANT_B: ("SN002", "KEY002"),
            TENANT_NO_PRINTER: (None, None),
            TENANT_PARTIAL: ("SN004", None),
        }
        for tid, (sn, key) in printers.items():
            self.db.add(Tenant(
                tenant_id=tid, name=f"Shop {tid}", password_hash="x", status=True, is_open=True,
                payment_mode="prepay", phone=PHONES[tid], feieyun_sn=sn, feieyun_key=key,
            ))
            self.db.add(Subscription(
                tenant_id=tid, plan_id=pro.id, status=STATUS_TRIAL,
                trial_started_at=now, trial_ends_at=now + timedelta(days=30),
            ))
        await self.db.commit()

        self.clock = Clock()
        self.store = _AlertStore(now_fn=self.clock)
        self.channel = FakeChannel()

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

    # ------------------------------------------------------------------ helpers
    async def _make_order(
        self,
        tenant_id: str,
        *,
        print_status: str,
        attempts: int = 0,
        intent: bool = True,
        updated_age_s: int = 600,
        paid_age_s: int = 600,
        created_age_s: int = 0,
        last_error_code: str | None = None,
        manual_status: str | None = None,
        status: str = "pending",
    ) -> Order:
        now = datetime.utcnow()
        order = Order(
            tenant_id=tenant_id, table_no="A1", total="20.00", status=status,
            payment_mode="prepay", payment_status="paid",
            payment_time=(now - timedelta(seconds=paid_age_s)).isoformat(),
            source="miniprogram", print_status=print_status,
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        if intent:
            meta = {
                "version": 2,
                "initial_print": {
                    "status": print_status, "attempts": attempts, "last_error_code": last_error_code,
                    "last_attempt_at": (now - timedelta(seconds=updated_age_s)).isoformat() if attempts else None,
                    "eligible_at": now.isoformat(), "route": dict(ROUTE),
                },
                "manual_reprint_count": 0,
                "manual_reprints": [{"status": manual_status}] if manual_status else [],
            }
            _sync_legacy_initial_fields(meta)
            _set_print_meta(order, meta)
            await self.db.commit()
        await self.db.execute(
            update(Order).where(Order.id == order.id).values(
                updated_at=now - timedelta(seconds=updated_age_s),
                created_at=now - timedelta(seconds=created_age_s),
            )
        )
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def _exhausted(self, tenant_id: str, **kw) -> Order:
        return await self._make_order(
            tenant_id, print_status="FAILED", attempts=MAX_PRINT_RETRY_ATTEMPTS,
            last_error_code="FEIEYUN_PRINT_FAILED", **kw,
        )

    async def _cycle(self, channel=None):
        return await run_print_alert_cycle(
            self.SessionLocal, store=self.store, channel=channel or self.channel, now=self.clock(),
        )

    # ------------------------------------------------------------------ T1 normal path is silent
    async def test_t1_normal_orders_never_alert(self):
        await self._make_order(TENANT_A, print_status="SUCCESS", attempts=1)
        await self._make_order(TENANT_A, print_status="PENDING", updated_age_s=5, paid_age_s=5)
        await self._make_order(TENANT_A, print_status="SENDING", attempts=1, updated_age_s=5)
        await self._make_order(TENANT_A, print_status="FAILED", attempts=1, updated_age_s=40)
        await self._make_order(TENANT_A, print_status="UNKNOWN", attempts=1, updated_age_s=30)

        report = await self._cycle()

        self.assertEqual(self.channel.alerts, [])
        self.assertEqual(self.channel.recovered, [])
        self.assertEqual(report.open_groups, [])
        self.assertEqual(report.failures, 0)

    # ------------------------------------------------------------------ T2 first exhaustion alerts once
    async def test_t2_first_exhausted_alerts_exactly_once(self):
        await self._exhausted(TENANT_A)

        report = await self._cycle()

        self.assertEqual(self.channel.alerts, [(TENANT_A, GROUP_DELIVERY, 1, PHONES[TENANT_A])])
        self.assertEqual(report.alerts_sent, 1)
        self.provider.assert_not_awaited()

    # ------------------------------------------------------------------ T3 dedupe window + reminder cap
    async def test_t3_same_tenant_same_group_is_deduped_then_reminders_are_capped(self):
        await self._exhausted(TENANT_A)
        await self._cycle()
        self.clock.advance(60)
        report = await self._cycle()
        self.assertEqual(len(self.channel.alerts), 1)
        self.assertEqual(report.suppressed, 1)

        for _ in range(PRINT_ALERT_MAX_REMINDERS + 3):
            self.clock.advance(PRINT_ALERT_DEDUPE_SECONDS + 1)
            await self._cycle()
        # one alert + at most PRINT_ALERT_MAX_REMINDERS reminders, then silence
        self.assertEqual(len(self.channel.alerts), 1 + PRINT_ALERT_MAX_REMINDERS)

    # ------------------------------------------------------------------ T4 tenants are independent
    async def test_t4_different_tenants_alert_separately(self):
        await self._exhausted(TENANT_A)
        await self._exhausted(TENANT_B)

        await self._cycle()

        self.assertEqual({a[0] for a in self.channel.alerts}, {TENANT_A, TENANT_B})
        self.assertEqual(len(self.channel.alerts), 2)

    # ------------------------------------------------------------------ T5 one message per tenant
    async def test_t5_many_orders_aggregate_into_one_alert(self):
        for _ in range(4):
            await self._exhausted(TENANT_A)
        await self._make_order(TENANT_A, print_status="UNKNOWN", attempts=1)

        await self._cycle()

        self.assertEqual(len(self.channel.alerts), 1)
        self.assertEqual(self.channel.alerts[0][:3], (TENANT_A, GROUP_DELIVERY, 5))

    # ------------------------------------------------------------------ T6 UNKNOWN: alert only
    async def test_t6_stale_unknown_alerts_without_resending(self):
        await self._make_order(TENANT_A, print_status="UNKNOWN", attempts=1, updated_age_s=PRINT_ALERT_GRACE_SECONDS + 60)
        await self._cycle()
        self.assertEqual(len(self.channel.alerts), 1)

        for _ in range(3):
            self.clock.advance(PRINT_ALERT_DEDUPE_SECONDS + 1)
            await self._cycle()
        self.provider.assert_not_awaited()
        order = (await self.db.execute(select(Order).where(Order.tenant_id == TENANT_A))).scalar_one()
        await self.db.refresh(order)
        self.assertEqual(order.print_status, "UNKNOWN")

    # ------------------------------------------------------------------ T7 invariant violation
    async def test_t7_paid_without_print_intent_alerts_when_printing_is_expected(self):
        await self._make_order(TENANT_A, print_status="PENDING", intent=False, paid_age_s=PRINT_ALERT_GRACE_SECONDS + 60)
        await self._make_order(TENANT_B, print_status="PENDING", intent=False, paid_age_s=10, updated_age_s=10)

        await self._cycle()

        self.assertEqual(self.channel.alerts, [(TENANT_A, GROUP_DELIVERY, 1, PHONES[TENANT_A])])

    # ------------------------------------------------------------------ T8 shops that do not print
    async def test_t8_shops_that_do_not_use_printing_never_alert(self):
        await self._exhausted(TENANT_NO_PRINTER)  # capability yes, printer never configured
        await self._exhausted(TENANT_B)
        with patch(CAPABILITY_PATH, AsyncMock(side_effect=lambda tid, cap: tid != TENANT_B)):
            report = await self._cycle()

        self.assertEqual(self.channel.alerts, [])
        self.assertEqual(report.failures, 0)

    async def test_t8b_half_configured_printer_is_a_config_alert_not_a_delivery_alert(self):
        await self._make_order(TENANT_PARTIAL, print_status="FAILED", attempts=1, updated_age_s=PRINT_ALERT_GRACE_SECONDS + 60)

        await self._cycle()

        self.assertEqual(self.channel.alerts, [(TENANT_PARTIAL, GROUP_CONFIG, 1, PHONES[TENANT_PARTIAL])])

    async def test_t8c_a_person_reprinting_successfully_clears_the_exception(self):
        await self._exhausted(TENANT_A, manual_status="SUCCESS")

        await self._cycle()

        self.assertEqual(self.channel.alerts, [])

    # ------------------------------------------------------------------ T9 recovery
    async def test_t9_recovery_is_sent_once_and_only_with_proof_of_a_successful_print(self):
        order = await self._exhausted(TENANT_A)
        await self._cycle()
        self.assertEqual(len(self.channel.alerts), 1)

        self.clock.advance(120)
        await self.db.execute(
            update(Order).where(Order.id == order.id).values(
                print_status="SUCCESS", printed_at=self.clock() + timedelta(seconds=1),
            )
        )
        await self.db.commit()
        report = await self._cycle()
        self.assertEqual(self.channel.recovered, [(TENANT_A, GROUP_DELIVERY, PHONES[TENANT_A])])
        self.assertEqual(report.recoveries_sent, 1)

        self.clock.advance(PRINT_ALERT_DEDUPE_SECONDS + 1)
        await self._cycle()
        self.assertEqual(len(self.channel.recovered), 1)

    async def test_t9b_exception_that_just_disappears_closes_quietly(self):
        order = await self._exhausted(TENANT_A)
        await self._cycle()
        self.clock.advance(120)
        await self.db.execute(update(Order).where(Order.id == order.id).values(status="settled"))
        await self.db.commit()

        await self._cycle()

        self.assertEqual(self.channel.recovered, [])
        self.assertIsNone(await self.store.get(alerts._episode_key(TENANT_A, GROUP_DELIVERY)))

    async def test_t9c_a_new_episode_after_recovery_alerts_again(self):
        order = await self._exhausted(TENANT_A)
        await self._cycle()
        self.clock.advance(120)
        await self.db.execute(
            update(Order).where(Order.id == order.id).values(print_status="SUCCESS", printed_at=self.clock() + timedelta(seconds=1))
        )
        await self.db.commit()
        await self._cycle()

        self.clock.advance(PRINT_ALERT_DEDUPE_SECONDS + 1)
        await self._exhausted(TENANT_A)
        await self._cycle()

        self.assertEqual(len(self.channel.alerts), 2)

    # ------------------------------------------------------------------ T10 alerting never blocks anything
    async def test_t10_a_failing_channel_never_stops_the_cycle_or_other_tenants(self):
        await self._exhausted(TENANT_A)
        await self._exhausted(TENANT_B)
        channel = FakeChannel(raise_for={TENANT_A})

        report = await self._cycle(channel)

        self.assertEqual(report.failures, 1)
        self.assertEqual([a[0] for a in channel.alerts], [TENANT_B])
        self.provider.assert_not_awaited()

    async def test_t10b_an_undeliverable_alert_is_retried_once_per_window_not_every_scan(self):
        await self._exhausted(TENANT_A)
        channel = FakeChannel(deliver=False)

        await self._cycle(channel)
        self.clock.advance(60)
        await self._cycle(channel)
        self.assertEqual(len(channel.alerts), 1)  # second scan: still inside the window

        self.clock.advance(PRINT_ALERT_DEDUPE_SECONDS)
        channel.deliver = True
        report = await self._cycle(channel)
        self.assertEqual(len(channel.alerts), 2)
        self.assertEqual(report.alerts_sent, 1)

    async def test_t10c_the_cycle_survives_a_broken_database_factory(self):
        def broken_factory():
            raise RuntimeError("db down")

        report = await run_print_alert_cycle(broken_factory, store=self.store, channel=self.channel, now=self.clock())

        self.assertEqual(report.failures, 1)

    # ------------------------------------------------------------------ SMS channel contract
    async def test_sms_message_carries_only_a_count_and_uses_its_own_budget(self):
        sms = type("Sms", (), {})()
        sms.is_template_configured = lambda template_id: bool(template_id)
        sms.send_template_notice = AsyncMock(return_value=SmsSendStatus(ok=True, provider_code="Ok", provider_message="ok"))
        channel = SmsAlertChannel(self.store, sms=sms)

        with patch.object(settings, "TENCENT_SMS_PRINT_ALERT_TEMPLATE_ID", "900001"), \
                patch.object(settings, "TENCENT_SMS_PRINT_RECOVERED_TEMPLATE_ID", "900002"):
            self.assertTrue(await channel.send_alert(TENANT_A, PHONES[TENANT_A], GROUP_DELIVERY, 3))
            self.assertTrue(await channel.send_recovered(TENANT_A, PHONES[TENANT_A], GROUP_DELIVERY))

        first, second = sms.send_template_notice.await_args_list
        self.assertEqual(first.args, (PHONES[TENANT_A], "900001", ["3"]))
        self.assertEqual(second.args, (PHONES[TENANT_A], "900002", []))

    async def test_sms_channel_declines_without_a_valid_phone_or_template(self):
        sms = type("Sms", (), {})()
        sms.is_template_configured = lambda template_id: bool(template_id)
        sms.send_template_notice = AsyncMock(return_value=SmsSendStatus(ok=True, provider_code="Ok", provider_message="ok"))
        channel = SmsAlertChannel(self.store, sms=sms)

        with patch.object(settings, "TENCENT_SMS_PRINT_ALERT_TEMPLATE_ID", "900001"):
            self.assertFalse(await channel.send_alert(TENANT_A, None, GROUP_DELIVERY, 1))
            self.assertFalse(await channel.send_alert(TENANT_A, "12345", GROUP_DELIVERY, 1))
        with patch.object(settings, "TENCENT_SMS_PRINT_ALERT_TEMPLATE_ID", ""):
            self.assertFalse(await channel.send_alert(TENANT_A, PHONES[TENANT_A], GROUP_DELIVERY, 1))
        sms.send_template_notice.assert_not_awaited()

    async def test_sms_daily_budget_is_enforced(self):
        sms = type("Sms", (), {})()
        sms.is_template_configured = lambda template_id: True
        sms.send_template_notice = AsyncMock(return_value=SmsSendStatus(ok=True, provider_code="Ok", provider_message="ok"))
        channel = SmsAlertChannel(self.store, sms=sms)

        with patch.object(settings, "TENCENT_SMS_PRINT_ALERT_TEMPLATE_ID", "900001"), \
                patch.object(settings, "PRINT_ALERT_SMS_DAILY_LIMIT", 2):
            results = [await channel.send_alert(TENANT_A, PHONES[TENANT_A], GROUP_DELIVERY, 1) for _ in range(3)]

        self.assertEqual(results, [True, True, False])
        self.assertEqual(sms.send_template_notice.await_count, 2)

    # ------------------------------------------------------------------ static contracts
    def test_alerting_cannot_resend_or_touch_orders(self):
        source = (ROOT / "app" / "services" / "print_exception_alert_service.py").read_text(encoding="utf-8")
        for forbidden in ("_print_paid_order_ticket", "_execute_provider", "print_order(", ".commit()", "order.status =", "UPDATE"):
            self.assertNotIn(forbidden, source, forbidden)

    def test_alert_loop_is_its_own_task_wired_in_main(self):
        main_source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("print_alert_loop", main_source)
        self.assertIn("PRINT_ALERT_ENABLED", main_source)
        self.assertIn("asyncio.create_task(print_alert_loop())", main_source)
        loop_source = inspect.getsource(alerts.print_alert_loop)
        self.assertIn("CancelledError", loop_source)

    def test_alert_log_lines_never_carry_secrets_or_full_phone_numbers(self):
        source = (ROOT / "app" / "services" / "print_exception_alert_service.py").read_text(encoding="utf-8")
        for forbidden in ("feieyun_key", "app_secret", "credentials[", "openid", "order.total", "customer_id", "wx_transaction_id"):
            self.assertNotIn(forbidden, source, forbidden)


if __name__ == "__main__":
    unittest.main()
