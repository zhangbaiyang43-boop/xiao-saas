"""Phase 4C: workbench incremental sync + Final Gate cursor correctness."""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services import workbench_sync_service as wss

ROOT_ORDERS = __import__("pathlib").Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "orders.py"
ROOT_AUTH = __import__("pathlib").Path(__file__).resolve().parents[1] / "app" / "core" / "merchant_auth.py"
ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]

TS = datetime(2026, 8, 8, 20, 0, 5)


def _order(oid: int, updated_at: datetime, status: str = "pending", **extra):
    return SimpleNamespace(
        id=oid,
        updated_at=updated_at,
        created_at=updated_at,
        status=status,
        **extra,
    )


def _simulate_delta(orders, cursor: str, limit: int = 100):
    """Apply the same predicate + pagination as get_workbench_changes."""
    w, u, i = wss.decode_workbench_cursor(cursor)
    matched = [
        o
        for o in orders
        if wss.order_matches_delta_cursor(o, watermark=w, page_u=u, page_i=i)
    ]
    matched.sort(key=lambda o: (o.updated_at, o.id))
    has_more = len(matched) > limit
    page = matched[:limit]
    next_cursor = wss.advance_cursor_after_page(page, cursor, has_more=has_more)
    return page, next_cursor, has_more


class WorkbenchCursorContractTest(unittest.TestCase):
    def test_cursor_roundtrip_v2(self):
        cur = wss.encode_workbench_cursor(TS, TS - timedelta(seconds=1), 0)
        w, u, i = wss.decode_workbench_cursor(cur)
        self.assertEqual(w, TS)
        self.assertEqual(u, TS - timedelta(seconds=1))
        self.assertEqual(i, 0)

    def test_invalid_cursor_raises(self):
        with self.assertRaises(ValueError):
            wss.decode_workbench_cursor("%%%not-base64%%%")
        with self.assertRaises(ValueError):
            wss.decode_workbench_cursor("")

    def test_visibility_waiter_kitchen(self):
        pending = SimpleNamespace(status="pending")
        preparing = SimpleNamespace(status="preparing")
        done = SimpleNamespace(status="done")
        cancelled = SimpleNamespace(status="cancelled")
        self.assertTrue(wss.is_order_visible_in_workbench(pending, "waiter"))
        self.assertTrue(wss.is_order_visible_in_workbench(preparing, "waiter"))
        self.assertFalse(wss.is_order_visible_in_workbench(done, "waiter"))
        self.assertTrue(wss.is_order_visible_in_workbench(done, "kitchen"))
        self.assertFalse(wss.is_order_visible_in_workbench(cancelled, "kitchen"))

    def test_fg01_same_timestamp_initial_pagination(self):
        """FG-01: multiple rows same second paginate without skip/dup across pages."""
        orders = [_order(i, TS, status="pending") for i in range(1, 6)]
        cursor = wss.committed_cursor_from_watermark(TS - timedelta(seconds=10))
        page1, c1, more1 = _simulate_delta(orders, cursor, limit=2)
        self.assertTrue(more1)
        self.assertEqual([o.id for o in page1], [1, 2])
        page2, c2, more2 = _simulate_delta(orders, c1, limit=2)
        self.assertTrue(more2)
        self.assertEqual([o.id for o in page2], [3, 4])
        page3, c3, more3 = _simulate_delta(orders, c2, limit=2)
        self.assertFalse(more3)
        self.assertEqual([o.id for o in page3], [5])
        # Drain complete → committed cursor rescans watermark second.
        w, u, i = wss.decode_workbench_cursor(c3)
        self.assertEqual(w, TS)
        self.assertEqual(i, 0)

    def test_route_exists_once_and_staff_rule(self):
        source = ROOT_ORDERS.read_text(encoding="utf-8")
        self.assertEqual(source.count('@router.get("/orders/workbench")'), 1)
        self.assertEqual(source.count('@router.get("/orders/workbench/changes")'), 1)
        auth = ROOT_AUTH.read_text(encoding="utf-8")
        self.assertIn("orders/workbench/changes", auth)

    def test_fg12_changes_endpoint_has_no_print_reconcile(self):
        source = ROOT_ORDERS.read_text(encoding="utf-8")
        idx = source.index("async def list_workbench_order_changes")
        chunk = source[idx : idx + 2200]
        self.assertNotIn("reconcile_print_orders", chunk)
        self.assertNotIn("_print_paid_order_ticket", chunk)
        full_idx = source.index("async def list_workbench_orders")
        full_chunk = source[full_idx : full_idx + 1800]
        self.assertIn("reconcile_print_orders", full_chunk)


class WorkbenchSameSecondFinalGateTest(unittest.TestCase):
    """Final Gate: second-precision late older-id updates must not be skipped."""

    def test_fg02_same_second_late_older_id_not_skipped(self):
        """TEST-SAME-SECOND-LATE-UPDATE / FG-02/04."""
        a = _order(100, TS, status="pending")
        b = _order(200, TS, status="pending")
        # Cursor established after B is the high-water (as Full would).
        cursor = wss.cursor_from_orders([a, b])
        w, u, i = wss.decode_workbench_cursor(cursor)
        self.assertEqual(w, TS)
        self.assertEqual(i, 0)

        # After cursor exists: older-id A mutates in the SAME second.
        a.status = "preparing"
        a.updated_at = TS  # frozen same DB second

        page, _next, _more = _simulate_delta([a, b], cursor)
        ids = {o.id for o in page}
        self.assertIn(100, ids, "same-second late older-id A must be returned")
        self.assertEqual(page[[o.id for o in page].index(100)].status, "preparing")

    def test_fg03_same_second_new_higher_id_order(self):
        a = _order(100, TS)
        b = _order(200, TS)
        cursor = wss.cursor_from_orders([a, b])
        c = _order(300, TS, status="pending")
        page, _, _ = _simulate_delta([a, b, c], cursor)
        self.assertIn(300, {o.id for o in page})

    def test_fg05_same_second_older_id_preparing_to_done(self):
        a = _order(100, TS, status="preparing")
        b = _order(200, TS, status="pending")
        cursor = wss.cursor_from_orders([a, b])
        a.status = "done"
        a.updated_at = TS
        page, _, _ = _simulate_delta([a, b], cursor)
        hit = next(o for o in page if o.id == 100)
        self.assertEqual(hit.status, "done")

    def test_fg06_same_second_print_status_update(self):
        a = _order(100, TS, status="pending", print_status="FAILED")
        b = _order(200, TS, status="pending", print_status="SUCCESS")
        cursor = wss.cursor_from_orders([a, b])
        a.print_status = "SUCCESS"
        a.updated_at = TS
        page, _, _ = _simulate_delta([a, b], cursor)
        hit = next(o for o in page if o.id == 100)
        self.assertEqual(hit.print_status, "SUCCESS")

    def test_fg07_same_second_pickup_update(self):
        a = _order(100, TS, status="pending", pickup_no="")
        b = _order(200, TS, status="pending", pickup_no="01")
        cursor = wss.cursor_from_orders([a, b])
        a.pickup_no = "07"
        a.updated_at = TS
        page, _, _ = _simulate_delta([a, b], cursor)
        hit = next(o for o in page if o.id == 100)
        self.assertEqual(hit.pickup_no, "07")

    def test_legacy_v1_cursor_normalizes_to_overlap_rescan(self):
        """Old v1 (u,i=B) must not keep the late older-id gap."""
        import base64
        import json

        payload = {"v": 1, "u": TS.isoformat(sep="T", timespec="seconds"), "i": 200}
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        v1 = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        a = _order(100, TS, status="preparing")
        b = _order(200, TS, status="pending")
        page, _, _ = _simulate_delta([a, b], v1)
        self.assertIn(100, {o.id for o in page})

    def test_fg10_pagination_does_not_loop(self):
        orders = [_order(i, TS) for i in (10, 20, 30, 40, 50)]
        cursor = wss.committed_cursor_from_watermark(TS - timedelta(seconds=5))
        seen = []
        for _ in range(10):
            page, cursor, more = _simulate_delta(orders, cursor, limit=2)
            seen.extend(o.id for o in page)
            if not more:
                break
        else:
            self.fail("pagination looped")
        self.assertEqual(seen, [10, 20, 30, 40, 50])


class WorkbenchChangesQueryContractTest(unittest.TestCase):
    def test_bootstrap_returns_empty_items(self):
        class FakeResult:
            def first(self):
                return (datetime(2026, 8, 8, 10, 0, 0), 99)

        class FakeDB:
            async def execute(self, *_a, **_k):
                return FakeResult()

        packed = asyncio.run(
            wss.get_workbench_changes(
                FakeDB(),
                tenant_id="t1",
                role="kitchen",
                cursor=None,
            )
        )
        self.assertTrue(packed["bootstrap"])
        self.assertEqual(packed["items"], [])
        self.assertEqual(packed["removed_ids"], [])
        self.assertIn("next_cursor", packed)
        self.assertFalse(packed["has_more"])
        w, u, i = wss.decode_workbench_cursor(packed["next_cursor"])
        self.assertEqual(w, datetime(2026, 8, 8, 10, 0, 0))
        self.assertEqual(i, 0)


class WorkbenchUpdatedAtMutationSourceTest(unittest.TestCase):
    def test_status_and_payment_and_pickup_and_print_assign(self):
        lifecycle = (ROOT / "app" / "services" / "order_lifecycle_service.py").read_text(
            encoding="utf-8"
        )
        payment = (ROOT / "app" / "services" / "order_payment_service.py").read_text(encoding="utf-8")
        pickup = (ROOT / "app" / "services" / "pickup_no_service.py").read_text(encoding="utf-8")
        printing = (ROOT / "app" / "services" / "order_print_service.py").read_text(encoding="utf-8")
        self.assertIn("order.status = body.status", lifecycle)
        self.assertIn('order.payment_status = "paid"', payment)
        self.assertIn("order.pickup_no = pickup_no", pickup)
        self.assertIn("order.print_status = status", printing)


class WorkbenchDeltaPaginationLogicTest(unittest.TestCase):
    def test_advance_cursor_committed_resets_page_id(self):
        page = [
            _order(1, TS),
            _order(2, TS),
        ]
        prev = wss.committed_cursor_from_watermark(TS - timedelta(seconds=2))
        nxt = wss.advance_cursor_after_page(page, prev, has_more=False)
        w, u, i = wss.decode_workbench_cursor(nxt)
        self.assertEqual(w, TS)
        self.assertEqual(i, 0)

    def test_advance_cursor_has_more_keeps_page_id(self):
        page = [_order(1, TS), _order(2, TS)]
        prev = wss.committed_cursor_from_watermark(TS - timedelta(seconds=2))
        nxt = wss.advance_cursor_after_page(page, prev, has_more=True)
        w, u, i = wss.decode_workbench_cursor(nxt)
        self.assertEqual(u, TS)
        self.assertEqual(i, 2)


if __name__ == "__main__":
    unittest.main()
