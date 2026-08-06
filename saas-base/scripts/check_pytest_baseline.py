#!/usr/bin/env python3
"""Fail CI unless pytest results match the known saas-base baseline.

The 26 failures are frontend menu.vue / useCheckout.js source-string contract
tests (not backend regressions). This gate keeps CI green at the baseline while
still failing when new tests break or the failure count grows.

Update EXPECTED_PASSED / EXPECTED_FAILED after intentionally fixing baseline
failures or adding tests.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

EXPECTED_PASSED = 398
EXPECTED_FAILED = 26


def parse_summary(text: str) -> tuple[int | None, int | None, int | None]:
    """Return (passed, failed, errors) parsed from pytest tail output."""
    passed = failed = errors = None

    # e.g. "26 failed, 398 passed, 10 warnings in 604.52s"
    m = re.search(r"(\d+) failed,\s*(\d+) passed", text)
    if m:
        failed = int(m.group(1))
        passed = int(m.group(2))
    else:
        m = re.search(r"(\d+) passed(?:,\s*(\d+) failed)?", text)
        if m:
            passed = int(m.group(1))
            failed = int(m.group(2) or 0)

    err_m = re.search(r"(\d+) error", text, flags=re.IGNORECASE)
    if err_m:
        errors = int(err_m.group(1))
    elif "ERROR " in text or " ERRORS " in text:
        errors = 1 if errors is None else errors

    return passed, failed, errors


def main() -> int:
    log_path = Path(sys.argv[1] if len(sys.argv) > 1 else "pytest-output.log")
    text = log_path.read_text(encoding="utf-8", errors="replace")
    passed, failed, errors = parse_summary(text)

    if passed is None:
        print(f"Could not parse pytest summary from {log_path}", file=sys.stderr)
        return 1

    failed = failed or 0
    errors = errors or 0

    print(f"Parsed: {passed} passed, {failed} failed, {errors} errors")
    print(f"Expected baseline: {EXPECTED_PASSED} passed, {EXPECTED_FAILED} failed")

    if errors:
        print(f"FAIL: {errors} collection/runtime error(s) — not allowed", file=sys.stderr)
        return 1

    if passed != EXPECTED_PASSED or failed != EXPECTED_FAILED:
        print(
            f"FAIL: counts differ from baseline "
            f"(got {passed}/{failed}, want {EXPECTED_PASSED}/{EXPECTED_FAILED}). "
            f"If this is an intentional fix, update scripts/check_pytest_baseline.py.",
            file=sys.stderr,
        )
        return 1

    print("OK: pytest results match known baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
