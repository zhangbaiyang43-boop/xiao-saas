"""OPS-01 P0-01: guest GET /orders/my must derive tenant from ownership, not JWT."""
from __future__ import annotations

import asyncio
import inspect
import os
import tempfile
import unittest
import uuid
from datetime import datetime
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.tenant_context import TenantContext
from app.models.base import Base
from app.models.dining import DiningParticipant, DiningSession
from app.models.order import Order
from app.models.tenant import Tenant
from app.services.dining_session_service import hash_participant_token
from app.services.order_lifecycle_service import OrderLifecycleService
from app.services.wxpay_recovery_gate import GateDecision, RecoveryOutcome

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"
GUEST_TOKEN_A = "guest-token-owner-a"
GUEST_TOKEN_B = "guest-token-owner-b"
WRONG_TOKEN = "guest-token-wrong"


class GuestOrderStatusTenantAuthorityTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        TenantContext.clear()
        self._db_file = os.path.join(
            tempfile.gettempdir(), f"ops_p0_guest_order_{uuid.uuid4().hex}.db"
        )
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self._db_file}")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.db.add_all([
            Tenant(tenant_id=TENANT_A, name="A", password_hash="x", status=True, is_open=True),
            Tenant(tenant_id=TENANT_B, name="B", password_hash="x", status=True, is_open=True),
        ])
        now = datetime.utcnow()
        self.session_a = DiningSession(
            tenant_id=TENANT_A, table_no="A1", status="OPEN",
            active_key=f"{TENANT_A}:A1", started_at=now, last_activity_at=now,
        )
        self.session_b = DiningSession(
            tenant_id=TENANT_B, table_no="B1", status="OPEN",
            active_key=f"{TENANT_B}:B1", started_at=now, last_activity_at=now,
        )
        self.db.add_all([self.session_a, self.session_b])
        await self.db.flush()
        self.participant_a = DiningParticipant(
            tenant_id=TENANT_A, session_id=self.session_a.id,
            guest_token_hash=hash_participant_token(GUEST_TOKEN_A),
            joined_at=now, last_active_at=now,
        )
        self.participant_b = DiningParticipant(
            tenant_id=TENANT_B, session_id=self.session_b.id,
            guest_token_hash=hash_participant_token(GUEST_TOKEN_B),
            joined_at=now, last_active_at=now,
        )
        self.db.add_all([self.participant_a, self.participant_b])
        await self.db.flush()
        await self.db.commit()
        self._session_patch = patch("app.core.database.AsyncSessionLocal", self.SessionLocal)
        self._session_patch.start()

    async def asyncTearDown(self):
        self._session_patch.stop()
        TenantContext.clear()
        await self.db.close()
        await self.engine.dispose()
        try:
            os.remove(self._db_file)
        except OSError:
            pass

    async def _guest_order(self, *, tenant_id=TENANT_A, participant=None, **kwargs):
        participant = participant or self.participant_a
        session = self.session_a if tenant_id == TENANT_A else self.session_b
        table = "A1" if tenant_id == TENANT_A else "B1"
        fields = {
            "tenant_id": tenant_id,
            "customer_id": None,
            "participant_id": participant.id,
            "dining_session_id": session.id,
            "table_no": table,
            "total": "28.00",
            "status": "pending_payment",
            "payment_status": "unpaid",
            "payment_mode": "prepay",
            "source": "miniprogram",
        }
        fields.update(kwargs)
        order = Order(**fields)
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def _member_order(self, *, tenant_id=TENANT_A, customer_id=501, **kwargs):
        fields = {
            "tenant_id": tenant_id,
            "customer_id": customer_id,
            "participant_id": None,
            "table_no": "M1",
            "total": "18.00",
            "status": "pending",
            "payment_status": "paid",
            "payment_mode": "prepay",
            "source": "miniprogram",
        }
        fields.update(kwargs)
        order = Order(**fields)
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    def _svc(self):
        TenantContext.clear()
        return OrderLifecycleService(self.db)

    async def test_a_guest_without_authorization_reads_own_order(self):
        order = await self._guest_order()
        result = await self._svc().get_my_order(
            int(order.id), customer_id=None, participant_token=GUEST_TOKEN_A,
        )
        self.assertEqual(result.code, 200, result.msg)
        self.assertEqual(result.data["status"], "pending_payment")
        self.assertEqual(result.data["payment_status"], "unpaid")

    def test_b_guest_path_does_not_require_tenant_context_before_ownership(self):
        source = inspect.getsource(OrderLifecycleService.get_my_order)
        self.assertNotIn("self.require_tenant_id()", source)
        self.assertIn("get_current_tenant_id()", source)
        self.assertIn("participant_token", source)

    async def test_c_wrong_participant_token_cannot_read_order(self):
        order = await self._guest_order()
        result = await self._svc().get_my_order(
            int(order.id), customer_id=None, participant_token=WRONG_TOKEN,
        )
        self.assertEqual(result.code, 403)
        self.assertIsNone(result.data)

    async def test_d_other_tenant_participant_token_cannot_read_order(self):
        order = await self._guest_order(tenant_id=TENANT_A, participant=self.participant_a)
        result = await self._svc().get_my_order(
            int(order.id), customer_id=None, participant_token=GUEST_TOKEN_B,
        )
        self.assertEqual(result.code, 403)
        self.assertIsNone(result.data)

    async def test_e_logged_in_member_path_remains_valid(self):
        order = await self._member_order(customer_id=501)
        TenantContext.set_tenant_id(TENANT_A)
        result = await OrderLifecycleService(self.db).get_my_order(
            int(order.id), customer_id=501, participant_token=None,
        )
        self.assertEqual(result.code, 200, result.msg)
        self.assertEqual(result.data["id"], str(order.id))

    async def test_f_member_from_another_tenant_cannot_read_order(self):
        order = await self._member_order(tenant_id=TENANT_B, customer_id=701)
        TenantContext.set_tenant_id(TENANT_A)
        result = await OrderLifecycleService(self.db).get_my_order(
            int(order.id), customer_id=701, participant_token=None,
        )
        self.assertEqual(result.code, 404)
        self.assertIsNone(result.data)

    async def test_g_guest_pending_to_paid_recovery(self):
        order = await self._guest_order()
        called = {"n": 0}

        async def fake_recovery(recon_order, db, **_kwargs):
            called["n"] += 1
            recon_order.payment_status = "paid"
            recon_order.status = "pending"
            await db.commit()
            return RecoveryOutcome(
                decision=GateDecision.RECOVERED, recovered=True, attempt_count=1,
            )

        from app.services import wxpay_recovery_gate as gate_mod

        with patch.object(gate_mod.recovery_gate, "attempt_recovery", new=fake_recovery):
            result = await self._svc().get_my_order(
                int(order.id), customer_id=None, participant_token=GUEST_TOKEN_A,
            )
        self.assertGreater(called["n"], 0, "recovery_gate.attempt_recovery was not invoked")
        self.assertEqual(result.code, 200, result.msg)
        self.assertEqual(result.data["payment_status"], "paid")
        self.assertEqual(result.data["status"], "pending")

    async def test_h_guest_paid_member_value_is_not_applicable(self):
        order = await self._guest_order(status="pending", payment_status="paid")
        result = await self._svc().get_my_order(
            int(order.id), customer_id=None, participant_token=GUEST_TOKEN_A,
        )
        self.assertEqual(result.code, 200, result.msg)
        self.assertEqual(result.data["member_value"]["status"], "not_applicable")

    async def test_i_missing_identity_is_forbidden_not_500(self):
        order = await self._guest_order()
        try:
            result = await self._svc().get_my_order(
                int(order.id), customer_id=None, participant_token=None,
            )
        except ValueError as exc:
            self.fail(f"missing identity must not raise: {exc}")
        self.assertEqual(result.code, 403)
        self.assertIsNone(result.data)

    async def test_j_cancel_order_ownership_semantics_unchanged(self):
        from app.api.v1.orders import cancel_order
        from starlette.requests import Request

        order = await self._guest_order(
            status="pending", payment_status="unpaid", payment_mode="postpay",
        )
        req = Request({
            "type": "http",
            "method": "POST",
            "path": f"/api/v1/orders/{order.id}/cancel",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        })
        denied = await cancel_order(str(order.id), req, participant_token=WRONG_TOKEN, db=self.db)
        self.assertEqual(denied.code, 403)
        allowed = await cancel_order(str(order.id), req, participant_token=GUEST_TOKEN_A, db=self.db)
        self.assertEqual(allowed.code, 200, allowed.msg)
        await self.db.refresh(order)
        self.assertEqual(order.status, "cancelled")

    async def test_k_tenant_a_token_cannot_read_tenant_b_orphan_order(self):
        order = await self._member_order(
            tenant_id=TENANT_B, customer_id=None, participant_id=None,
        )
        result = await self._svc().get_my_order(
            int(order.id), customer_id=None, participant_token=GUEST_TOKEN_A,
        )
        self.assertEqual(result.code, 403)
        self.assertIsNone(result.data)

    async def test_l_customer_id_without_tenant_cannot_globally_read_member_order(self):
        order = await self._member_order(tenant_id=TENANT_A, customer_id=501)
        result = await self._svc().get_my_order(
            int(order.id), customer_id=501, participant_token=None,
        )
        self.assertEqual(result.code, 403)
        self.assertIsNone(result.data)


if __name__ == "__main__":
    unittest.main()
