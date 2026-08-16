"""P0-16 Phase B2 -- durable WHO/WHEN/HOW audit facts for order termination.

Covers B2-T01 (customer cancel), B2-T02 (anonymous participant cancel),
B2-T03 (merchant cancel), B2-T04 (merchant reject), B2-T07 (repeated
terminal action preserves the original audit), and B2-T11 (client cannot
spoof actor fields).

Schema Gate (P0-16 B2 Schema Contract Gate Report) froze this contract:
  - terminated_at: DateTime, written once, same transaction as the status
    mutation that first makes the order terminal.
  - terminated_actor_type: one of account | customer | participant | system.
  - terminated_actor_id: BigInteger, NULL means "the tenant owner" (account)
    or "no client identity" (system) -- never a fabricated sentinel.
  - terminated_actor_role: only populated for actor_type=account.
  - termination_source: customer_cancel | participant_cancel |
    merchant_cancel | merchant_reject | stale_order_cleanup |
    synchronous_stale_cleanup.
"""

import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.models.base import Base
from app.models.dining import DiningParticipant, DiningSession
from app.models.order import Order
from app.models.tenant import Tenant
from app.api.v1.orders import OrderStatusUpdate, cancel_order, update_order_status
from app.services.dining_session_service import hash_participant_token
from app.services.order_lifecycle_service import OrderLifecycleService
from app.services.order_payment_service import OrderPaymentService

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TENANT_A = "tenant-a"


def make_request(customer_id=None, tenant_id=None, token_type=None, role=None, account_id=None):
    req = Request(
        {
            "type": "http", "method": "POST", "path": "/api/v1/orders/1/cancel",
            "headers": [], "query_string": b"", "server": ("testserver", 80),
            "scheme": "http", "client": ("testclient", 50000),
        }
    )
    if customer_id is not None:
        req.state.customer_id = customer_id
    if tenant_id is not None:
        req.state.tenant_id = tenant_id
    if token_type is not None:
        req.state.token_type = token_type
    if token_type == "merchant":
        req.state.role = role or "owner"
        req.state.account_id = account_id
    return req


class TerminationAuditBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.SessionLocal = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.db = self.SessionLocal()
        self.tenant = Tenant(
            tenant_id=TENANT_A, name="Restaurant A", password_hash="x",
            status=True, is_open=True, payment_mode="postpay",
        )
        self.db.add(self.tenant)
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _make_order(self, **overrides):
        defaults = dict(
            tenant_id=TENANT_A, table_no="A1", status="pending",
            payment_status="unpaid", payment_mode="postpay", total=28.0,
            created_at=datetime.utcnow(),
        )
        defaults.update(overrides)
        order = Order(**defaults)
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order


class CustomerCancelAuditTest(TerminationAuditBase):
    async def test_customer_cancel_writes_durable_who_when_how(self):
        order = await self._make_order(customer_id=555, status="pending_payment", payment_mode="prepay")

        with patch.object(OrderPaymentService, "_recover_wxpay_order_if_paid", new=AsyncMock(return_value=False)):
            result = await cancel_order(str(order.id), make_request(customer_id=555), db=self.db)

        self.assertEqual(result.code, 200, result.msg)
        await self.db.refresh(order)
        self.assertIsNotNone(order.terminated_at)
        self.assertEqual(order.terminated_actor_type, "customer")
        self.assertEqual(order.terminated_actor_id, 555)
        self.assertIsNone(order.terminated_actor_role)
        self.assertEqual(order.termination_source, "customer_cancel")


class ParticipantCancelAuditTest(TerminationAuditBase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        now = datetime.utcnow()
        self.session = DiningSession(
            tenant_id=TENANT_A, table_no="A1", status="OPEN",
            active_key=f"{TENANT_A}:A1", started_at=now, last_activity_at=now,
        )
        self.db.add(self.session)
        await self.db.flush()
        self.raw_token = "guest-token-xyz"
        self.participant = DiningParticipant(
            tenant_id=TENANT_A, session_id=self.session.id,
            guest_token_hash=hash_participant_token(self.raw_token),
            joined_at=now, last_active_at=now,
        )
        self.db.add(self.participant)
        await self.db.commit()
        await self.db.refresh(self.participant)

    async def test_anonymous_participant_cancel_writes_durable_who_when_how(self):
        order = await self._make_order(
            customer_id=None, participant_id=self.participant.id,
            dining_session_id=self.session.id, status="pending",
        )

        result = await cancel_order(
            str(order.id), make_request(), participant_token=self.raw_token, db=self.db,
        )

        self.assertEqual(result.code, 200, result.msg)
        await self.db.refresh(order)
        self.assertIsNotNone(order.terminated_at)
        self.assertEqual(order.terminated_actor_type, "participant")
        self.assertEqual(order.terminated_actor_id, self.participant.id)
        self.assertIsNone(order.terminated_actor_role)
        self.assertEqual(order.termination_source, "participant_cancel")
        # never persist the raw guest token anywhere in the audit facts
        self.assertNotEqual(order.terminated_actor_id, self.raw_token)


class MerchantCancelAuditTest(TerminationAuditBase):
    async def test_owner_cancel_writes_null_actor_id_with_owner_role(self):
        order = await self._make_order(status="pending")

        result = await update_order_status(
            str(order.id), OrderStatusUpdate(status="cancelled"),
            make_request(tenant_id=TENANT_A, token_type="merchant", role="owner", account_id=None),
            db=self.db,
        )

        self.assertEqual(result.code, 200, result.msg)
        await self.db.refresh(order)
        self.assertIsNotNone(order.terminated_at)
        self.assertEqual(order.terminated_actor_type, "account")
        self.assertIsNone(order.terminated_actor_id)
        self.assertEqual(order.terminated_actor_role, "owner")
        self.assertEqual(order.termination_source, "merchant_cancel")

    async def test_staff_cancel_writes_real_account_id_and_role(self):
        # No current staff role holds PERM_FINANCE_REFUND (owner-only, see
        # app/core/permissions.py ORDER_STATUS_PERMISSIONS["cancelled"]), so
        # this calls the service layer directly -- the same layer the route
        # calls into after its own unrelated, unchanged permission gate --
        # to prove the audit-write logic itself is actor-generic, not
        # hardcoded to the owner shape.
        order = await self._make_order(status="pending")
        service = OrderLifecycleService(self.db)
        service.set_tenant_id(TENANT_A)

        result = await service.update_order_status(
            order.id, OrderStatusUpdate(status="cancelled"),
            account_id=777, role="frontdesk",
        )

        self.assertEqual(result.code, 200, result.msg)
        await self.db.refresh(order)
        self.assertEqual(order.terminated_actor_type, "account")
        self.assertEqual(order.terminated_actor_id, 777)
        self.assertEqual(order.terminated_actor_role, "frontdesk")
        self.assertEqual(order.termination_source, "merchant_cancel")


class MerchantRejectAuditTest(TerminationAuditBase):
    async def test_merchant_reject_writes_durable_who_when_how(self):
        order = await self._make_order(status="pending")

        result = await update_order_status(
            str(order.id), OrderStatusUpdate(status="rejected"),
            make_request(tenant_id=TENANT_A, token_type="merchant", role="owner", account_id=None),
            db=self.db,
        )

        self.assertEqual(result.code, 200, result.msg)
        await self.db.refresh(order)
        self.assertIsNotNone(order.terminated_at)
        self.assertEqual(order.terminated_actor_type, "account")
        self.assertIsNone(order.terminated_actor_id)
        self.assertEqual(order.terminated_actor_role, "owner")
        self.assertEqual(order.termination_source, "merchant_reject")


class RepeatedTerminalActionPreservesAuditTest(TerminationAuditBase):
    async def test_second_cancel_attempt_after_already_cancelled_does_not_overwrite_audit(self):
        order = await self._make_order(status="pending")

        first = await update_order_status(
            str(order.id), OrderStatusUpdate(status="cancelled"),
            make_request(tenant_id=TENANT_A, token_type="merchant", role="owner", account_id=None),
            db=self.db,
        )
        self.assertEqual(first.code, 200, first.msg)
        await self.db.refresh(order)
        original_terminated_at = order.terminated_at
        original_source = order.termination_source
        self.assertEqual(original_source, "merchant_cancel")

        # A second, different actor attempts to touch the now-terminal order.
        # role=owner (not frontdesk) so the request clears the pre-existing,
        # unrelated PERM_ORDER_REJECT gate and genuinely reaches the illegal-
        # transition guard this test is about.
        second = await update_order_status(
            str(order.id), OrderStatusUpdate(status="rejected"),
            make_request(tenant_id=TENANT_A, token_type="merchant", role="owner", account_id=None),
            db=self.db,
        )
        self.assertEqual(second.code, 409)  # illegal transition, blocked before any write
        await self.db.refresh(order)
        self.assertEqual(order.terminated_at, original_terminated_at)
        self.assertEqual(order.termination_source, original_source)
        self.assertEqual(order.terminated_actor_role, "owner")


class ClientCannotSpoofActorTest(unittest.TestCase):
    """B2-T11: the request body/query surface for every termination-writing
    endpoint has no channel for a client to supply an actor identity -- the
    audit fields are populated exclusively from server-resolved principal/
    customer_id/participant_id, never from client input. Source-text proof,
    matching the P0-16 B1 regression-scan convention."""

    def setUp(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[1]
        self.orders_source = (root / "app/api/v1/orders.py").read_text(encoding="utf-8-sig")
        self.lifecycle_source = (root / "app/services/order_lifecycle_service.py").read_text(encoding="utf-8-sig")
        self.main_source = (root / "app/main.py").read_text(encoding="utf-8-sig")
        self.model_source = (root / "app/models/order.py").read_text(encoding="utf-8-sig")

    def test_order_status_update_body_has_no_actor_field(self):
        import re
        m = re.search(r"class OrderStatusUpdate\(PydanticBase\):(.*?)\n\n", self.orders_source, re.DOTALL)
        self.assertIsNotNone(m, "OrderStatusUpdate class not found")
        body = m.group(1)
        for forbidden in ("terminated_actor", "settled_by", "actor_id", "actor_role", "actor_type"):
            self.assertNotIn(forbidden, body)

    def test_model_helper_writes_terminated_actor_id_only_from_its_own_parameter(self):
        import re
        # The actual order.terminated_actor_id = ... assignment lives inside
        # set_termination_audit_if_unset (app/models/order.py) -- a narrow,
        # server-only helper whose only inputs are its own call parameters.
        self.assertIn("def set_termination_audit_if_unset(", self.model_source)
        assignment = re.search(r"order\.terminated_actor_id\s*=\s*([^\n]+)", self.model_source)
        self.assertIsNotNone(assignment, "no order.terminated_actor_id assignment found")
        self.assertEqual(assignment.group(1).strip(), "actor_id")

    def test_every_termination_call_site_passes_actor_id_from_a_server_side_symbol(self):
        import re
        # Every call site (order_lifecycle_service.py, orders.py, main.py)
        # must pass actor_id= from a server-resolved symbol -- order.customer_id,
        # order.participant_id, a threaded account_id parameter, or a literal
        # None -- never body.* or request.*.
        call_sites = 0
        for source in (self.lifecycle_source, self.orders_source, self.main_source):
            for m in re.finditer(r"set_termination_audit_if_unset\(([^)]*(?:\([^)]*\)[^)]*)*)\)", source, re.DOTALL):
                call_sites += 1
                args = m.group(1)
                actor_id_match = re.search(r"actor_id\s*=\s*([^\s,]+)", args)
                self.assertIsNotNone(actor_id_match, f"call site missing actor_id=: {args}")
                rhs = actor_id_match.group(1)
                self.assertNotIn("body.", rhs)
                self.assertNotIn("request.", rhs)
        # 5 textual call sites: cancel_order's customer/participant branches
        # (2, only one executes per invocation), update_order_status (1),
        # orders.py's synchronous sweep (1), main.py's background loop (1).
        self.assertEqual(call_sites, 5, f"expected exactly 5 termination call sites, found {call_sites}")


if __name__ == "__main__":
    unittest.main()
