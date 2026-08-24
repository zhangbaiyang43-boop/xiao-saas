# admin-h5 Performance Test Tenant and Dataset Design

## 1. Status and scope

```text
PHASE=P0-ADMIN-PERFORMANCE-OBSERVABILITY-PHASE-04E
BASELINE=d018328b971ff482133e5ef213fa601628927249
DESIGN_STATUS=APPROVED
SELECTED_APPROACH=A_DETERMINISTIC_ORM_CLI
TARGET_ENVIRONMENT=LOCAL_TEST_FIRST
```

This design establishes a repeatable performance-test tenant and dataset for admin-h5 without changing business code, performance collection code, event fields, API contracts, database schema, pages, components, or Bundle configuration.

The approved environment decision is local/test first. The implementation can prove dataset generation, verification, cleanup, and isolation in a dedicated test database. It cannot claim a completed staging environment or production-representative performance sample. Until the same artifact and dataset are deployed to an actual staging environment and page/API events are observed there, Phase-04E remains `RESULT B`.

## 2. Problem

Phase-04D found two independent blockers:

1. Source A has only one visit for each core page and ten API-end events in total.
2. Source B has no staging runtime, no dedicated test tenant, and no dataset large enough to exercise 500 dishes, 10000 members, and 10000 orders.

The existing `test_data_seed.py` is unsuitable because it clears tenant data, uses random values, and creates only 12 dishes, 20 members, and approximately 35–155 orders. Expanding that business-facing seed endpoint would change business code and broaden a destructive SuperAdmin operation, which this phase forbids.

## 3. Considered approaches

### 3.1 Selected: deterministic ORM CLI

Create a dedicated script with `create`, `verify`, and `cleanup` subcommands. It imports existing SQLAlchemy models and writes only to a dedicated test database and fixed performance tenant. Dataset content is derived from record indexes and a fixed time anchor; it never calls `random`.

Advantages:

- No API or schema changes.
- Narrow and auditable cleanup scope.
- Repeatable semantic content and distribution.
- Testable environment guards and cross-tenant isolation.
- Suitable for local/test now and staging later.

### 3.2 Rejected: expand the existing seed API

This would expose large destructive writes through existing business/SuperAdmin code, retain or rewrite a random seed path, and enlarge API behavior. It conflicts with Phase-04E strict rules.

### 3.3 Rejected: SQL dump fixture

A static dump is coupled to database version, current primary-key space, and import tooling. It is harder to verify, harder to clean safely, and easier to apply to the wrong database.

## 4. File boundaries

Implementation is limited to one test-infrastructure module, its tests, and the required phase report:

- Create `saas-base/scripts/admin_performance_dataset.py`: CLI, deterministic record builders, environment guards, create/verify/cleanup orchestration, and JSON summaries.
- Create `saas-base/tests/test_admin_performance_dataset.py`: RED/GREEN contracts for guards, reproducibility, counts, marker protection, cleanup, and tenant isolation.
- Create `docs/frontend/ADMIN_PERFORMANCE_OBSERVABILITY_PHASE04E_TEST_TENANT.md`: implementation facts, commands, verification results, limitations, and final gate.

No existing runtime module is modified. No dependency or lockfile is changed.

## 5. Tenant contract

The tenant identity is fixed and is not accepted as a free-form CLI argument:

```text
tenant_id=perf_test_only_v1
tenant_name=[PERFORMANCE TEST ONLY] PERF_DATASET_V1
dataset_version=PERF_DATASET_V1
source=test
```

The existing `TenantConfig.business_info` JSON stores a non-business marker under `performanceTest`:

```json
{
  "performanceTest": {
    "datasetVersion": "PERF_DATASET_V1",
    "source": "test",
    "environment": "test"
  }
}
```

This uses an existing JSON column and does not change schema or API response contracts. The marker is internal infrastructure metadata; the CLI does not expose it through a new endpoint.

The tenant has no WeChat Pay, SMS, printer, or external-service credentials. It receives an existing PRO plan test subscription with a fixed validity window sufficient for entitlement-protected admin pages. The script requires that the global PRO plan already exists; it does not create or delete global plan catalog rows.

## 6. Login contract

The dedicated login-capable staff account is:

```text
username=perf_operator
role=frontdesk
status=active
```

Its password is read only from `PERF_TEST_PASSWORD` at create time and hashed with the project’s existing password helper. The script refuses to create the dataset if this value is missing or empty. Plaintext password, password hash, tokens, connection strings, and tenant credentials are absent from console JSON and the manifest.

Owner SMS login is not used because it is externally dependent and not repeatable.

## 7. Dataset contract

### 7.1 Reproducibility definition

`PERF_DATASET_V1` guarantees identical semantic content, counts, grouping, distributions, and fixed business timestamps on every successful create. Database primary keys continue to use the existing snowflake generator and may differ between runs; primary-key byte identity is not part of the dataset contract.

Every record is derived from a zero-based sequence and fixed constants. The implementation must not import or call `random`. Business timestamps use a fixed UTC anchor so repeated runs do not drift with wall-clock time. The manifest’s generation timestamp records the actual run time and is expected to differ.

### 7.2 Dishes

Exact target: 500 `MenuItem` rows.

- 20 deterministic categories, 25 dishes each.
- Short, medium, and maximum-safe-length names distributed by sequence.
- Deterministic descriptions, prices, original prices, tags, sales counts, stock, sort order, emoji, and image URL fields.
- Availability covers available, sold-out, and unavailable states.
- A deterministic subset has `spec_groups` stored in the existing `business_info.menu_item_specs` map keyed by generated menu-item ID.
- Spec groups use the current list shape: group name/type/required plus option name and price delta.

The image field contains a fixed non-sensitive test URL pattern. The generator does not upload, download, or validate image bytes. Image-resource performance remains pending until staging serves controlled static assets.

### 7.3 Members

Exact target: 10000 `Customer` rows and 10000 corresponding `MemberAccount` rows.

- Deterministic non-routable test phone strings, names of varied lengths, open IDs, member numbers, tags, status, and join timestamps.
- Member accounts cover existing level codes/names, points balances, balances, total/yearly consumption, and last-consume timestamps.
- Every member account maps to exactly one customer in the fixed tenant.
- Searchable values remain syntactically valid for current admin filters without representing real people.

### 7.4 Orders and Dashboard facts

Exact target: 10000 `Order` rows plus deterministic `OrderItem` rows.

- Existing known statuses are distributed deterministically across pending-payment, pending, preparing, done, settled, rejected, and cancelled.
- Orders span a fixed historical time range and include multiple days and service periods.
- Each order contains between one and five items, selected deterministically from the 500 generated dishes.
- A deterministic subset links to generated customers; remaining orders represent guest activity.
- Payment fields remain internally coherent enough for read-only list and aggregate endpoints and use `payment_method=mock` where applicable.
- `print_status=SUCCESS` for every generated order so the print-recovery loop cannot claim or dispatch test rows.
- No refund tasks, payment provider identifiers, printer tasks, coupon sends, or external notifications are generated.

Dashboard uses these same orders as its statistics source. No extra statistics table or cached aggregate is created.

## 8. CLI contract

The CLI has exactly three actions:

```text
python scripts/admin_performance_dataset.py create --manifest-out ../outputs/performance/PERF_DATASET_V1.json
python scripts/admin_performance_dataset.py verify
python scripts/admin_performance_dataset.py verify --manifest-out ../outputs/performance/PERF_DATASET_V1.json
python scripts/admin_performance_dataset.py cleanup
```

All actions emit a machine-readable JSON summary and return zero only when their contract succeeds.

### 8.1 `create`

1. Validate environment, database name, acknowledgement, password, and target identity.
2. Require the global PRO plan.
3. If the fixed tenant exists, require the exact name and performance marker; otherwise fail closed.
4. In one outer transaction, remove the previous marked V1 dataset, recreate the tenant/config/account/subscription, and insert data in bounded batches.
5. Run the same verification checks used by `verify` before committing.
6. Commit once and write a manifest containing dataset version, generation time, environment, counts, distributions, and a deterministic semantic checksum.

If any stage fails, the outer transaction rolls back and no partially regenerated dataset is accepted.

### 8.2 `verify`

`verify` is read-only. Its optional `--manifest-out` form rewrites the manifest from the verified database without regenerating data. It checks:

- Exact tenant identity and performance marker.
- Exact counts for dishes, customers, member accounts, orders, and expected order items.
- Twenty dish categories and required dish state/spec coverage.
- One-to-one customer/member-account coverage.
- Required member levels/statuses and order status/time distributions.
- No non-success print status.
- The dedicated login account and active test subscription exist.
- The semantic checksum matches `PERF_DATASET_V1` expectations.

A mismatch returns non-zero and reports only aggregate facts, never credentials or business records.

### 8.3 `cleanup`

`cleanup` repeats every environment and identity guard. It refuses to act if the tenant name or marker differs. It deletes only rows associated with the fixed tenant in foreign-key-safe order:

1. Order items selected through the fixed tenant’s order IDs.
2. Orders.
3. Member accounts.
4. Customers.
5. Menu items.
6. Merchant account.
7. Subscription.
8. Tenant config.
9. Tenant.

It does not delete global Plan rows or any other tenant’s data. Cleanup commits once; failure rolls back.

## 9. Environment and database guards

Every action, including `verify`, checks environment identity so reports cannot be accidentally labeled from production.

Mutating actions require all of the following:

```text
APP_ENV is exactly test or staging
database name ends with _test or _staging
PERF_DATASET_ACK is exactly PERF_DATASET_V1
```

`create` additionally requires `PERF_TEST_PASSWORD`.

The CLI rejects production, development, local, missing, or unknown APP_ENV values. A developer who wants a local process must run it with `APP_ENV=test` against a dedicated database whose name ends in `_test`; the project’s ordinary local database is not eligible.

The guard examines the parsed configured database URL without printing it. It never offers `--force`, arbitrary tenant ID, or a bypass flag.

## 10. Transaction and batching model

The script uses the existing async SQLAlchemy engine/session. Inserts are emitted in bounded batches to avoid holding every ORM object at once, while preserving one outer transaction for create. Generated IDs are retained only where needed to connect member accounts, orders, and order items.

The implementation must not call service methods that commit internally. It may reuse pure helpers such as password hashing, but transaction ownership remains in the CLI.

## 11. Performance-event validation boundary

Dataset construction does not add or change performance events. Phase-03C remains the only event source.

Local/test acceptance can verify that the tenant is login-capable and that current admin APIs can read the four datasets. It cannot certify Source B sampling until a real staging runtime uses:

```text
environment=staging
version=d018328b971ff482133e5ef213fa601628927249
source=test (external batch manifest)
```

Staging verification must then visit Dashboard, OrderManage, DishManage, and MemberManage and observe the existing page-enter, first-content-visible, page-ready, API start/end, request name, API group, status, and duration fields. Production and staging samples remain separate.

## 12. Failure handling

- Wrong environment/database: fail before opening a mutating transaction.
- Missing password or acknowledgement: fail before writes.
- Existing tenant without exact marker: fail closed; never repair, adopt, or delete it.
- Missing PRO plan: fail without creating global catalog data.
- Count/distribution/checksum mismatch: roll back create and return non-zero.
- Cleanup identity mismatch: return non-zero with zero deletions.
- Interrupted create: transaction rollback leaves the previous committed state intact.
- Manifest write failure after database commit: report failure and instruct the operator to run `verify --manifest-out ../outputs/performance/PERF_DATASET_V1.json`; do not regenerate automatically. The database verification result remains authoritative.

## 13. Test strategy

Implementation follows RED-GREEN-REFACTOR.

Focused tests cover:

1. Production, development, local, missing, and wrong-suffix database environments are rejected.
2. Missing acknowledgement and password are rejected.
3. Builders produce the same semantic rows/checksum twice and never depend on randomness or current business time.
4. Existing unmarked tenant causes create and cleanup to fail with no cross-tenant changes.
5. Create yields exact counts and required distributions.
6. Re-running create yields the same semantic checksum and counts.
7. Verify detects count, marker, print-status, and relationship corruption.
8. Cleanup removes only the fixed performance tenant and preserves a control tenant.
9. Summaries and manifests omit password, hash, token, cookie, and database URL.

The narrow test suite uses an isolated temporary test database configuration. A real MySQL test-database run remains a separate runtime gate; SQLite success must not be reported as MySQL certification.

## 14. Acceptance and phase decision

Code-level completion requires:

- A fixed test tenant contract and login account.
- Repeatable creation and verification of 500 dishes, 10000 customers/member accounts, and 10000 orders.
- Safe cleanup and cross-tenant preservation tests.
- A versioned manifest and semantic checksum.
- No runtime/API/schema/dependency changes.

Phase-04E final result remains:

```text
RESULT B
Local/test dataset infrastructure implemented and verified.
Real staging tenant, MySQL runtime proof, and admin-h5 performance-event proof remain pending.
Continue test-environment construction; do not enter Phase-04F yet.
```

Only after the same dataset is created and verified in an actual staging environment and the existing performance events are observed on all four pages may the report change to `RESULT A` and enter Phase-04F dual-source sampling.
