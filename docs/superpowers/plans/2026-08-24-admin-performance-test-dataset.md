# Admin Performance Test Dataset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fail-closed, deterministic create/verify/cleanup CLI for the fixed `PERF_DATASET_V1` admin performance-test tenant.

**Architecture:** Add one test-infrastructure Python module that uses existing SQLAlchemy models and owns its transaction without modifying runtime services. Pure deterministic builders feed a guarded lifecycle layer; an isolated SQLite test database proves contracts locally, while real MySQL/staging and browser-event evidence remain explicit external gates.

**Tech Stack:** Python 3.10, SQLAlchemy async ORM/Core, pytest/unittest async tests, existing FastAPI project models and password hashing.

---

## File map

- Create `saas-base/scripts/admin_performance_dataset.py`: fixed dataset constants, guards, deterministic builders, lifecycle functions, CLI, manifest output.
- Create `saas-base/tests/test_admin_performance_dataset.py`: TDD contracts and isolated database lifecycle proof.
- Create `docs/frontend/ADMIN_PERFORMANCE_OBSERVABILITY_PHASE04E_IMPLEMENTATION.md`: phase evidence and final gate.

No existing runtime file, migration, API, frontend file, dependency manifest, or lockfile changes.

### Task 1: RED — missing dataset contract and guards

**Files:**
- Create: `saas-base/tests/test_admin_performance_dataset.py`

- [ ] **Step 1: Write failing import/guard tests**

Create tests that import the wished-for API and assert the fixed identity plus fail-closed environment behavior:

```python
from scripts.admin_performance_dataset import (
    DATASET_VERSION,
    PERF_TENANT_ID,
    DatasetSafetyError,
    validate_runtime_guard,
)

def test_dataset_identity_is_fixed():
    assert DATASET_VERSION == "PERF_DATASET_V1"
    assert PERF_TENANT_ID == "perf_test_only_v1"

def test_runtime_guard_rejects_production_and_wrong_database():
    with pytest.raises(DatasetSafetyError):
        validate_runtime_guard("production", "mysql+asyncmy://u:p@db/x_test", "PERF_DATASET_V1")
    with pytest.raises(DatasetSafetyError):
        validate_runtime_guard("test", "mysql+asyncmy://u:p@db/business", "PERF_DATASET_V1")
```

- [ ] **Step 2: Run RED**

Run:

```powershell
cd saas-base
py -3.10 -m pytest tests/test_admin_performance_dataset.py -v
```

Expected: collection fails because `scripts.admin_performance_dataset` does not exist. Record this exact failure in the phase report.

- [ ] **Step 3: Add deterministic builder expectations while still RED**

Add tests for a small `DatasetScale(dishes=6, members=12, orders=14, categories=3)`, asserting identical semantic checksum and row content from two builds, required state/status coverage, fixed timestamps, and no secret values in summaries.

- [ ] **Step 4: Re-run RED**

Expected: the same missing-module failure confirms every new capability is absent before implementation.

### Task 2: GREEN — constants, safety guards, and deterministic builders

**Files:**
- Create: `saas-base/scripts/admin_performance_dataset.py`
- Test: `saas-base/tests/test_admin_performance_dataset.py`

- [ ] **Step 1: Implement the minimal fixed contract**

Define:

```python
DATASET_VERSION = "PERF_DATASET_V1"
PERF_TENANT_ID = "perf_test_only_v1"
PERF_TENANT_NAME = "[PERFORMANCE TEST ONLY] PERF_DATASET_V1"
PERF_USERNAME = "perf_operator"
DEFAULT_SCALE = DatasetScale(dishes=500, members=10_000, orders=10_000, categories=20)
FIXED_ANCHOR = datetime(2026, 1, 1, 12, 0, 0)
```

`validate_runtime_guard()` parses the URL with SQLAlchemy `make_url`, accepts only `test|staging`, requires database suffix `_test|_staging`, and requires exact acknowledgement. It never logs the URL.

- [ ] **Step 2: Implement pure deterministic row builders**

Implement dish, customer/member, order/order-item and marker builders driven only by sequence and constants. Use fixed URL/name/category/status formulas and a SHA-256 checksum over canonical JSON that excludes database IDs, password hashes, and generation time.

- [ ] **Step 3: Run focused GREEN tests**

Run the same pytest command. Expected: identity, guard, deterministic-content and checksum tests pass.

- [ ] **Step 4: Refactor only after GREEN**

Extract canonical JSON/checksum and batch helpers only if duplication exists. Re-run focused tests and require zero failures.

### Task 3: RED/GREEN — lifecycle database contracts

**Files:**
- Modify: `saas-base/tests/test_admin_performance_dataset.py`
- Modify: `saas-base/scripts/admin_performance_dataset.py`

- [ ] **Step 1: Write lifecycle RED tests**

Use an isolated SQLite/aiosqlite database containing only the models touched by the script plus a control tenant. Tests call:

```python
await create_dataset(session_factory, password="test-only-password", scale=SMALL_SCALE)
report = await verify_dataset(session_factory, scale=SMALL_SCALE)
assert report["status"] == "PASS"
assert report["counts"] == {
    "dishes": 6,
    "customers": 12,
    "member_accounts": 12,
    "orders": 14,
    "order_items": expected_order_item_count(14),
}
```

Also require:

- a second create returns the same semantic checksum and counts;
- an unmarked tenant with the fixed ID causes create and cleanup to fail;
- verify detects a deliberately corrupted count or print status;
- cleanup removes the performance tenant and preserves the control tenant and its row counts;
- a forced exception during create rolls back to the previous committed dataset.

- [ ] **Step 2: Run lifecycle RED**

Expected: tests fail because lifecycle functions do not exist.

- [ ] **Step 3: Implement marker-safe cleanup**

Implement internal cleanup that first validates exact tenant name and TenantConfig marker. Delete OrderItem by target order IDs, then target tenant rows in the approved order. Do not commit internally.

- [ ] **Step 4: Implement create**

Create/recreate the fixed tenant, config marker and menu specs, `perf_operator`, active fixed-window PRO subscription, 500/10000/10000 default rows, and order items in bounded batches. Require an existing PRO Plan. Set all order `print_status` values to `SUCCESS` and all payment methods to `mock`. Own one outer transaction and run verification before commit.

- [ ] **Step 5: Implement verify and cleanup public functions**

`verify_dataset()` is read-only and reports exact counts, distributions, marker/account/subscription facts, and checksum. `cleanup_dataset()` owns one transaction and returns aggregate deleted counts without exposing records.

- [ ] **Step 6: Run lifecycle GREEN**

Run the focused test file. Expected: all guard, builder, lifecycle, idempotency, isolation, corruption and rollback tests pass.

### Task 4: RED/GREEN — CLI and manifest secrecy

**Files:**
- Modify: `saas-base/tests/test_admin_performance_dataset.py`
- Modify: `saas-base/scripts/admin_performance_dataset.py`

- [ ] **Step 1: Write CLI/manifest RED tests**

Test argument parsing for exactly `create`, `verify`, and `cleanup`; create requires `--manifest-out`; verify optionally accepts it. Assert manifest fields include dataset version, tenant ID, generation time, scale, counts, environment and semantic checksum, while serialized output excludes password, hash, token, cookie, and database URL.

- [ ] **Step 2: Run RED**

Expected: tests fail because CLI/manifest functions are absent.

- [ ] **Step 3: Implement CLI**

Read settings and secrets at runtime, run guards before mutations, create an async engine/session without importing the application-global session, execute the chosen lifecycle action, and emit JSON. Write manifests atomically through a temporary sibling file and rename. `verify --manifest-out` recreates a manifest without mutation.

- [ ] **Step 4: Run GREEN**

Run the focused tests. Expected: all pass with no sensitive output.

### Task 5: Full-scale local contract and regression verification

**Files:**
- Test: `saas-base/tests/test_admin_performance_dataset.py`

- [ ] **Step 1: Run full-scale isolated lifecycle test**

Execute one marked test that creates, verifies, recreates, verifies, cleans, and verifies absence for the default 500/10000/10000 scale in a temporary SQLite test database. Record duration and exact counts. This proves local semantic lifecycle only, not MySQL or staging performance.

- [ ] **Step 2: Run focused test file fresh**

```powershell
cd saas-base
py -3.10 -m pytest tests/test_admin_performance_dataset.py -v
```

Expected: zero failures.

- [ ] **Step 3: Run related regressions**

```powershell
py -3.10 -m pytest tests/test_performance_contracts.py tests/test_menu_performance_contracts.py tests/test_tenant_account_contracts.py tests/test_merchant_staff_security_gate.py -v
```

Expected: zero failures. Do not claim backend full-suite certification unless the full suite is actually run to completion.

- [ ] **Step 4: Verify repository boundaries**

Require the diff to contain only the two Python files and the Phase-04E report. Confirm no migration, runtime API, frontend, dependency or lockfile differences.

### Task 6: Implementation report and final gate

**Files:**
- Create: `docs/frontend/ADMIN_PERFORMANCE_OBSERVABILITY_PHASE04E_IMPLEMENTATION.md`

- [ ] **Step 1: Write evidence-backed report**

Document exact files, RED failure, GREEN/VERIFY commands and counts, lifecycle commands, scale/checksum contract, isolation proof, limitations and acceptance answers.

- [ ] **Step 2: Apply final decision honestly**

If local/test lifecycle passes but real MySQL staging and four-page performance events remain unavailable, output:

```text
RESULT B
Local/test dataset infrastructure complete.
Real staging tenant, MySQL runtime proof and admin-h5 event proof remain pending.
Continue Phase-04E; do not enter Phase-04F.
```

Only output `RESULT A` if an actual staging environment exists and all required page/API events are observed there.

- [ ] **Step 3: Run final fresh verification**

Re-run focused tests, related regression tests, `git diff --check`, exact file-scope inspection and sensitive-token scan. Cite the fresh outputs in the handoff.
