"""Static scan: sensitive-model select() calls must filter by tenant_id.

Fallback guardrail — not a proof of isolation, but catches obvious omissions early.
"""
from __future__ import annotations

import ast
import re
import unittest
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = (ROOT / "app" / "api", ROOT / "app" / "services")

SENSITIVE_MODELS = frozenset(
    {
        "Order",
        "Coupon",
        "MemberAccount",
        "Consumption",
        "PointLedger",
    }
)

# (file relative to saas-base, line number, function name) -> why this select() is safe without
# Model.tenant_id in the same function body.
ALLOWLIST: dict[tuple[str, int, str], str] = {
    (
        "app/api/v1/customers.py",
        170,
        "list_customers",
    ): "MemberAccount rows loaded by customer_ids from CustomerService.list_customers(tenant_id=...); customers are already tenant-scoped.",
    (
        "app/services/coupon_service.py",
        1358,
        "_set_order_coupon_status_if_locked",
    ): "Coupon locked by order.coupon_id where order is an already-loaded, tenant-bound Order instance passed into this helper.",
    (
        "app/services/order_lifecycle_service.py",
        98,
        "cancel_order",
    ): "Order loaded by primary key then customer/participant ownership is verified before any mutation.",
    (
        "app/services/order_lifecycle_service.py",
        224,
        "get_my_order",
    ): "Order loaded by primary key then customer/participant ownership is verified before returning data.",
    (
        "app/services/order_lifecycle_service.py",
        268,
        "get_my_order",
    ): "P1-WXPAY-RECOVERY-GATE: re-selects the same already-ownership-verified order by "
    "primary key inside the isolated recovery-gate session; ownership was already "
    "verified against the original `order` above before this point is ever reached.",
    (
        "app/services/order_lifecycle_service.py",
        284,
        "get_my_order",
    ): "P1-WXPAY-RECOVERY-GATE: re-selects the same already-ownership-verified order_id "
    "by primary key through the display session after a successful gate-mediated "
    "recovery commit; ownership was already verified above.",
    (
        "app/services/order_lifecycle_service.py",
        672,
        "create_review",
    ): "Order loaded by primary key then customer_id must match caller before review is created.",
    (
        "app/services/order_payment_service.py",
        72,
        "_recover_wxpay_order_if_paid",
    ): "Re-locks the same Order row already passed in; tenant scope inherited from the caller's order object.",
    (
        "app/services/order_payment_service.py",
        368,
        "_refund_order_payment",
    ): "Coupon locked by order.coupon_id on an order already loaded in the refund flow.",
    (
        "app/services/order_payment_service.py",
        463,
        "mock_pay_order",
    ): "Order loaded by id then customer/participant ownership is verified before mock payment.",
    (
        "app/services/order_payment_service.py",
        529,
        "create_wxpay_order",
    ): "Order loaded by id then customer/participant ownership is verified; tenant taken from order.tenant_id for WxPayService.",
    (
        "app/services/order_payment_service.py",
        565,
        "create_wxpay_order",
    ): "Re-locks the same order_id after the ownership gate at the top of create_wxpay_order.",
    (
        "app/services/order_payment_service.py",
        592,
        "create_wxpay_order",
    ): "Re-locks the same order_id after the ownership gate at the top of create_wxpay_order.",
    (
        "app/services/order_payment_service.py",
        700,
        "wxpay_notify",
    ): "WeChat notify resolves merchant cert first, then rejects order.tenant_id mismatch against matched_tenant.",
    (
        "app/services/order_print_service.py",
        269,
        "_print_paid_order_ticket",
    ): "Re-locks the same Order row already passed in by order.id for print-state consistency.",
    (
        "app/services/payment_handoff_service.py",
        173,
        "_load_order_by_id",
    ): "Private loader; every call site re-verifies ownership after loading (token-hash lookup in resolve(), "
    "tenant_id-filtered StaffAssistedPaymentHandoff row in resolve_latest_for_order(), explicit "
    "order.tenant_id != tenant_id check in _load_order_for_staff_handoff()).",
    (
        "app/services/order_print_service.py",
        974,
        "recover_pending_print_orders_once",
    ): "Intentionally cross-tenant: a startup/interval background recovery job (see _print_recovery_loop in "
    "main.py), same trust model as _pending_payment_reconcile_once and _marketing_recall_loop. Each recovered "
    "Order carries its own tenant_id, used correctly per-order by the printing code it calls into.",
}


@dataclass(frozen=True)
class SelectHit:
    rel_path: str
    line: int
    func_name: str
    model: str


def _iter_python_files(base: Path):
    for path in sorted(base.rglob("*.py")):
        if path.name.startswith("__"):
            continue
        yield path


def _function_source(lines: list[str], node: ast.AST) -> str:
    start = node.lineno - 1
    end = getattr(node, "end_lineno", node.lineno)
    return "".join(lines[start:end])


def _has_tenant_filter(source: str, model: str) -> bool:
    if re.search(rf"\b{model}\.tenant_id\b", source):
        return True
    if re.search(rf"filter_by_tenant\s*\([^)]*\b{model}\b", source, re.DOTALL):
        return True
    return False


class _SelectScanner(ast.NodeVisitor):
    def __init__(self, rel_path: str, lines: list[str]):
        self.rel_path = rel_path
        self.lines = lines
        self.hits: list[SelectHit] = []
        self._func_stack: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._func_stack.append(node.name)
        self.generic_visit(node)
        self._func_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._func_stack.append(node.name)
        self.generic_visit(node)
        self._func_stack.pop()

    def visit_Call(self, node: ast.Call):
        model = _select_model_name(node)
        if model:
            func_name = self._func_stack[-1] if self._func_stack else "<module>"
            self.hits.append(
                SelectHit(
                    rel_path=self.rel_path,
                    line=node.lineno,
                    func_name=func_name,
                    model=model,
                )
            )
        self.generic_visit(node)


def _select_model_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name) and func.id == "select":
        if node.args and isinstance(node.args[0], ast.Name):
            return node.args[0].id if node.args[0].id in SENSITIVE_MODELS else None
    return None


def _scan_file(path: Path) -> list[tuple[SelectHit, str]]:
    rel_path = path.relative_to(ROOT).as_posix()
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text, filename=rel_path)

    scanner = _SelectScanner(rel_path, lines)
    scanner.visit(tree)

    violations: list[tuple[SelectHit, str]] = []
    func_nodes: dict[str, ast.AST] = {}

    class _FuncCollector(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            func_nodes[node.name] = node
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node):
            func_nodes[node.name] = node
            self.generic_visit(node)

    _FuncCollector().visit(tree)

    for hit in scanner.hits:
        key = (hit.rel_path, hit.line, hit.func_name)
        if key in ALLOWLIST:
            continue

        if hit.func_name == "<module>":
            func_source = text
        else:
            node = func_nodes.get(hit.func_name)
            if node is None:
                func_source = text
            else:
                func_source = _function_source(lines, node)

        if not _has_tenant_filter(func_source, hit.model):
            violations.append((hit, func_source))

    return violations


def scan_tenant_isolation_violations() -> list[tuple[SelectHit, str]]:
    all_violations: list[tuple[SelectHit, str]] = []
    for base in SCAN_DIRS:
        if not base.is_dir():
            continue
        for path in _iter_python_files(base):
            all_violations.extend(_scan_file(path))
    return all_violations


class TenantIsolationScanTest(unittest.TestCase):
    def test_sensitive_selects_filter_by_tenant_id(self):
        violations = scan_tenant_isolation_violations()
        if not violations:
            return

        lines = [
            "Sensitive select() calls missing tenant_id filter in enclosing function:",
            "(add to ALLOWLIST in test_tenant_isolation_scan.py if intentionally exempt)",
            "",
        ]
        for hit, _ in violations:
            lines.append(f"  {hit.rel_path}:{hit.line}:{hit.func_name}  select({hit.model})")
        self.fail("\n".join(lines))


if __name__ == "__main__":
    unittest.main()
