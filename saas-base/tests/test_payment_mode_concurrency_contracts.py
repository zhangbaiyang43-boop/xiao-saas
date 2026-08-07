import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ORDERS_SOURCE = (ROOT / "app" / "api" / "v1" / "orders.py").read_text(encoding="utf-8-sig")
PAYMENT_SERVICE_SOURCE = (
    ROOT / "app" / "services" / "order_payment_service.py"
).read_text(encoding="utf-8-sig")
LIFECYCLE_SERVICE_SOURCE = (
    ROOT / "app" / "services" / "order_lifecycle_service.py"
).read_text(encoding="utf-8-sig")
PRINT_SERVICE_SOURCE = (ROOT / "app" / "services" / "order_print_service.py").read_text(encoding="utf-8-sig")
DINING_SERVICE_SOURCE = (ROOT / "app" / "services" / "dining_session_service.py").read_text(encoding="utf-8-sig")
DINING_MIGRATION_SOURCE = (
    ROOT / "alembic" / "versions" / "20260715_0001_add_dining_session_tables.py"
).read_text(encoding="utf-8-sig")


def function_source(source: str, name: str) -> str:
    lines = source.splitlines()
    start = next(
        (
            idx
            for idx, line in enumerate(lines)
            if line.startswith(f"async def {name}(")
            or line.startswith(f"def {name}(")
            or line.startswith(f"    async def {name}(")
        ),
        None,
    )
    assert start is not None, f"{name} source not found"
    is_class_method = lines[start].startswith("    async def")
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if is_class_method:
            if line.startswith("    async def ") or line.startswith("    def "):
                end = idx
                break
        elif line.startswith("@router.") or line.startswith("class ") or line.startswith("async def ") or line.startswith("def "):
            end = idx
            break
    return "\n".join(lines[start:end])


def lifecycle_method_source(name: str) -> str:
    lines = LIFECYCLE_SERVICE_SOURCE.splitlines()
    start = next(
        (idx for idx, line in enumerate(lines) if line.startswith(f"    async def {name}(")),
        None,
    )
    assert start is not None, f"{name} source not found"
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if line.startswith("    async def ") or line.startswith("    def "):
            end = idx
            break
    return "\n".join(lines[start:end])


class PaymentModeConcurrencyContractsTest(unittest.TestCase):
    def test_payment_success_and_notify_are_locked_and_idempotent(self):
        success_source = function_source(PAYMENT_SERVICE_SOURCE, "_on_payment_success")
        notify_source = function_source(PAYMENT_SERVICE_SOURCE, "wxpay_notify")
        mock_source = function_source(PAYMENT_SERVICE_SOURCE, "mock_pay_order")
        self.assertIn('if getattr(order, "payment_status", None) == "paid"', success_source)
        self.assertIn('return None, 0.0', success_source)
        self.assertIn('order.payment_status = "paid"', success_source)
        self.assertIn('order.status = "pending"', success_source)
        self.assertIn('with_for_update()', notify_source)
        self.assertIn('self._on_payment_success(order, payment_method="wxpay")', notify_source)
        self.assertIn('with_for_update()', mock_source)
        self.assertIn('self._on_payment_success(order, payment_method="mock")', mock_source)

    def test_free_or_zero_amount_payment_path_locks_before_marking_paid(self):
        pay_source = function_source(PAYMENT_SERVICE_SOURCE, "create_wxpay_order")
        self.assertIn('if pay_amount <= 0:', pay_source)
        self.assertIn('select(Order).where(Order.id == int(order_id)).with_for_update()', pay_source)
        self.assertIn('self._on_payment_success(order, payment_method="free")', pay_source)
        self.assertIn('await self.db.commit()', pay_source)

    def test_active_dining_session_creation_uses_unique_active_key_and_retry(self):
        self.assertIn('active_key = f"{tenant_id}:{table_no}"', DINING_SERVICE_SOURCE)
        self.assertIn('DiningSession.active_key == active_key', DINING_SERVICE_SOURCE)
        self.assertIn('.with_for_update()', DINING_SERVICE_SOURCE)
        self.assertIn('except IntegrityError:', DINING_SERVICE_SOURCE)
        self.assertIn('ux_dining_session_active_key', DINING_MIGRATION_SOURCE)
        self.assertIn('unique=True', DINING_MIGRATION_SOURCE)

    def test_table_account_settlement_locks_session_and_settles_all_done_orders(self):
        settle_source = lifecycle_method_source("settle_table")
        # 会话查找按"这一桌还有没到终态的订单"来找，不再要求 DiningSession.status=="OPEN"——
        # 这样历史上出现过的"会话被标成 CLOSED/EXPIRED 但订单还卡在 done"这种不一致数据，
        # 下一次点结账也能被这里捞到并带回正轨，而不是永远 404（见 orders.py 里的注释）。
        self.assertIn('Order.status.notin_(("settled", "cancelled", "rejected"))', settle_source)
        self.assertIn('.with_for_update()', settle_source)
        self.assertIn('TABLE_CLOSE_BLOCKING_STATUSES', settle_source)
        self.assertIn('settlement_orders = [o for o in table_orders if o.status == "done"]', settle_source)
        self.assertIn('_mark_order_offline_paid(o)', settle_source)
        self.assertIn('active_session.active_key = None', settle_source)

    def test_reprint_path_does_not_mutate_payment_state(self):
        reprint_source = function_source(ORDERS_SOURCE, "reprint_order_ticket")
        print_source = function_source(PRINT_SERVICE_SOURCE, "_print_paid_order_ticket")
        self.assertIn('allowed, reason = can_reprint_order(order, print_type=print_type)', reprint_source)
        self.assertIn('_print_paid_order_ticket(order, db, manual=True, reason="manual_reprint", operator=tenant_id)', reprint_source)
        self.assertNotIn('payment_status = "paid"', reprint_source)
        self.assertNotIn('payment_method =', reprint_source)
        self.assertIn('select(Order).where(Order.id == order.id).with_for_update()', print_source)


if __name__ == "__main__":
    unittest.main()