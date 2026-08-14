import ast
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
PRINT_SERVICE = ROOT / "app" / "services" / "order_print_service.py"
PAYMENT_SERVICE = ROOT / "app" / "services" / "order_payment_service.py"
FEIEYUN_SERVICE = ROOT / "app" / "services" / "feieyun_service.py"
ORDERS_API = ROOT / "app" / "api" / "v1" / "orders.py"
PICKUP_SERVICE = ROOT / "app" / "services" / "pickup_no_service.py"
MAIN = ROOT / "app" / "main.py"


def _function_source(path: Path, function_name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"missing function: {function_name}")


def _load_pure_function(path: Path, function_name: str):
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
    )
    namespace = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[function_name]


def test_d01_prepay_transition_creates_print_intent_inside_payment_transaction():
    source = _function_source(PAYMENT_SERVICE, "_on_payment_success")
    intent_at = source.find("ensure_initial_print_intent")
    final_flush_at = source.rfind("await self.db.flush()")

    assert intent_at >= 0
    assert final_flush_at > intent_at


def test_d03_startup_recovery_quarantines_stale_sending_without_provider_resend():
    source = _function_source(PRINT_SERVICE, "recover_pending_print_orders_once")

    assert "SENDING" in source
    assert "UNKNOWN" in source
    assert "STALE_SENDING" in source
    assert "allow_provider_call=False" in source


def test_b01_startup_recovery_filters_in_sql_before_limit():
    source = _function_source(PRINT_SERVICE, "recover_pending_print_orders_once")

    assert "Order.print_status.in_" in source
    assert ".limit(PRINT_RECONCILE_BATCH_LIMIT)" in source
    assert "settled" in source
    assert "list(orders)[:PRINT_RECONCILE_BATCH_LIMIT]" not in source


def test_b01_sql_cutoffs_exclude_cooldown_and_nonstale_rows_before_limit():
    source = _function_source(PRINT_SERVICE, "recover_pending_print_orders_once")

    assert "PRINT_RETRY_COOLDOWN_SECONDS" in source
    assert "PRINT_SENDING_STALE_SECONDS" in source
    assert 'Order.print_status == "PENDING"' in source
    assert 'Order.print_status == "FAILED"' in source
    assert 'Order.print_status == "SENDING"' in source


def test_c01_automatic_claim_is_tenant_scoped_and_committed_before_provider():
    source = _function_source(PRINT_SERVICE, "_claim_initial_print_attempt")

    assert "Order.tenant_id == tenant_id" in source
    assert ".with_for_update()" in source
    assert '"SENDING"' in source
    assert "await db.commit()" in source


def test_mnl01_manual_path_does_not_mutate_initial_print_fields():
    source = _function_source(PRINT_SERVICE, "_record_manual_reprint_result")

    assert "manual_reprints" in source
    assert "manual_reprint_count" in source
    assert "order.print_status" not in source
    assert "order.printed_at" not in source
    assert "initial_print" not in source


def test_content01_feieyun_item_remark_is_rendered_exactly_once():
    build_order_ticket = _load_pure_function(FEIEYUN_SERVICE, "build_order_ticket")
    order = SimpleNamespace(
        id=10001,
        pickup_no=None,
        table_no="A01",
        source="miniapp",
        remark="整单备注",
        total=18,
    )
    item = SimpleNamespace(name="牛肉饭", qty=1, price=18, item_remark="不要香菜")

    ticket = build_order_ticket(order, [item])

    assert ticket.count("不要香菜") == 1


def test_route01_initial_execution_uses_frozen_route_snapshot():
    source = _function_source(PRINT_SERVICE, "_execute_provider_with_frozen_route")

    assert 'initial_print.get("route")' in source
    assert "printer_identifier" in source
    assert "template_or_route_mode" in source
    assert "app_secret" not in source


def test_postpay_intent_is_created_before_business_commit():
    source = _function_source(ORDERS_API, "_persist_create_order_and_build_response")
    intent_at = source.find("ensure_initial_print_intent")
    commit_at = source.find("await db.commit()", intent_at)

    assert intent_at >= 0
    assert commit_at > intent_at


def test_pickup_eligibility_transition_is_committed_with_assignment():
    source = _function_source(PICKUP_SERVICE, "assign_for_order")
    eligible_at = source.find("mark_initial_print_eligible")
    commit_at = source.find("await self.db.commit()", eligible_at)

    assert eligible_at >= 0
    assert commit_at > eligible_at


def test_startup_schedules_periodic_recovery_and_shutdown_cancels_it():
    startup = _function_source(MAIN, "startup")
    shutdown = _function_source(MAIN, "shutdown_print_recovery")

    assert "asyncio.create_task(print_recovery_loop())" in startup
    assert "_print_recovery_task.cancel()" in shutdown
    assert "await _print_recovery_task" in shutdown


def test_receipt_reprint_fails_closed_until_a_receipt_renderer_exists():
    source = _function_source(ORDERS_API, "reprint_order_ticket")

    assert 'if print_type != "kitchen"' in source
    assert 'receipt reprint is not supported' in source
