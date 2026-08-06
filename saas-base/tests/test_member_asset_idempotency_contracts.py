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
MEMBERSHIP_SOURCE = (ROOT / "app" / "services" / "membership_service.py").read_text(encoding="utf-8-sig")


def function_source(source: str, name: str) -> str:
    lines = source.splitlines()
    start = next(
        (idx for idx, line in enumerate(lines) if line.startswith(f"async def {name}(") or line.startswith(f"    async def {name}(")),
        None,
    )
    assert start is not None, f"{name} source not found"
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if line.startswith("@router.") or line.startswith("async def ") or line.startswith("class ") or line.startswith("    async def "):
            end = idx
            break
    return "\n".join(lines[start:end])


class MemberAssetIdempotencyContractsTest(unittest.TestCase):
    def test_payment_success_is_the_only_asset_mutation_entry(self):
        success_source = function_source(PAYMENT_SERVICE_SOURCE, "_on_payment_success")
        mock_source = function_source(PAYMENT_SERVICE_SOURCE, "mock_pay_order")
        notify_source = function_source(PAYMENT_SERVICE_SOURCE, "wxpay_notify")
        pay_source = function_source(PAYMENT_SERVICE_SOURCE, "create_wxpay_order")

        self.assertIn("locked_coupon.status = \"USED\"", success_source)
        self.assertIn("apply_consumption", success_source)
        self.assertIn("with_for_update()", mock_source)
        self.assertIn("with_for_update()", notify_source)
        self.assertIn("locked_order_result", pay_source)
        self.assertLess(mock_source.index("with_for_update()"), mock_source.index("_on_payment_success"))
        self.assertLess(notify_source.index("with_for_update()"), notify_source.index("_on_payment_success"))

    def test_failed_or_cancelled_payment_does_not_mutate_assets(self):
        confirm_pay_source = function_source(PAYMENT_SERVICE_SOURCE, "create_wxpay_order")
        cancel_source = function_source(LIFECYCLE_SERVICE_SOURCE, "cancel_order")
        notify_source = function_source(PAYMENT_SERVICE_SOURCE, "wxpay_notify")

        self.assertIn('if order.status != "pending_payment"', confirm_pay_source)
        self.assertIn('if trade_state != "SUCCESS"', notify_source)
        self.assertNotIn("_on_payment_success", cancel_source)
        self.assertIn('coupon.status == "LOCKED"', cancel_source)
        self.assertIn('coupon.status = "UNUSED"', cancel_source)
        self.assertNotIn("points_balance", cancel_source)
        self.assertNotIn("acc.balance", cancel_source)

    def test_duplicate_callbacks_are_blocked_before_asset_mutation(self):
        notify_source = function_source(PAYMENT_SERVICE_SOURCE, "wxpay_notify")
        # _on_payment_success (the only place that mutates coupon/points/consumption assets)
        # must be gated behind an explicit order.status == "pending_payment" check, so a
        # retried/duplicate WeChat callback for an order that's already been processed (paid,
        # or reconciled via the cancelled/rejected auto-refund path below) never mutates
        # assets a second time.
        self.assertIn('if order.status == "pending_payment":', notify_source)
        self.assertLess(
            notify_source.index('if order.status == "pending_payment":'),
            notify_source.index("_on_payment_success"),
        )

    def test_coupon_asset_queries_are_tenant_scoped(self):
        success_source = function_source(PAYMENT_SERVICE_SOURCE, "_on_payment_success")

        self.assertIn("Coupon.tenant_id == str(order.tenant_id)", success_source)
        self.assertIn("Coupon.customer_id == int(customer_id)", success_source)

    def test_balance_is_not_mutated_by_order_payment(self):
        # 余额业务线已下线：下单、支付、mock-pay 都不应该再触碰 MemberAccount。
        success_source = function_source(PAYMENT_SERVICE_SOURCE, "_on_payment_success")
        create_order_source = function_source(ORDERS_SOURCE, "create_order")
        pay_source = function_source(PAYMENT_SERVICE_SOURCE, "create_wxpay_order")
        mock_source = function_source(PAYMENT_SERVICE_SOURCE, "mock_pay_order")

        self.assertNotIn("MemberAccount", success_source)
        self.assertNotIn("MemberAccount", create_order_source)
        self.assertNotIn("MemberAccount", pay_source)
        self.assertNotIn("MemberAccount", mock_source)

    def test_points_use_order_id_as_idempotency_reference(self):
        success_source = function_source(PAYMENT_SERVICE_SOURCE, "_on_payment_success")
        apply_source = function_source(MEMBERSHIP_SOURCE, "apply_consumption")
        add_points_source = function_source(MEMBERSHIP_SOURCE, "add_points")

        self.assertIn("consumption_id=order.id", success_source)
        self.assertIn("ref_id=str(consumption_id or \"\")", apply_source)
        self.assertIn("PointLedger", add_points_source)
        self.assertIn("MemberAccount.tenant_id == tenant_id", apply_source)


if __name__ == "__main__":
    unittest.main()