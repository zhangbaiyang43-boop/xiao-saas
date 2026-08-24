# admin-h5 Local Performance Staging Readiness Design

## 1. Status and decisions

```text
PHASE=P0-ADMIN-PERFORMANCE-OBSERVABILITY-PHASE-04F-READY
BASELINE=823708c1cbac8ba7c730715afafbecd27d641f09
DESIGN_STATUS=APPROVED
ENVIRONMENT_SCOPE=LOCAL_DOCKER_ONLY
ACCESS_SCOPE=127.0.0.1_ONLY
SELECTED_APPROACH=A_FULL_STACK_DOCKER_COMPOSE
```

This design connects the Phase-04E dataset lifecycle to a reproducible local performance-staging environment. It creates a real MySQL-backed Source B environment on the current computer without changing production, business APIs, admin-h5 business code, the performance-event model, database schema, or the production deployment process.

The resulting environment is staging for controlled engineering evidence, not a remote shared staging service and not production-equivalent network evidence. `READY` means the local Source B prerequisites are executable and verified. It does not mean production performance has been measured.

## 2. Existing facts

The repository currently has a single production release path:

```text
Git main
  → GitHub Actions admin-h5 build
  → Release Artifact
  → Tencent COS
  → deploy-production.sh
  → immutable release + atomic current switch
```

The required production authorities were checked before this design:

- `.github/workflows/admin-h5-release.yml`
- `scripts/deploy-production.sh`
- `docs/production-deployment.md`

They define no staging host, domain, database, workflow, or release switch. This phase must not modify or imitate that production flow. In particular, it must not deploy to `saas.zhangbaiyang.com`, call the production API, build on the production host, upload `dist`, or overwrite a production release directory.

The local computer has Docker Desktop 29.7.2 and Docker Compose v5.4.0. The Docker Linux engine is reachable. The user selected loopback-only access; no LAN or public exposure is authorized.

## 3. Considered approaches

### 3.1 Selected: full-stack Docker Compose

Run MySQL 8, Redis 7, FastAPI and an Nginx-served admin-h5 artifact in one fixed Compose project. Build the frontend from the exact source SHA with staging environment metadata, proxy `/api` to the backend over the private Compose network, and execute migrations and dataset lifecycle commands as one-shot services.

Advantages:

- Real MySQL semantics and a production-like static frontend.
- Reproducible service versions, network names and volumes.
- Same-origin `/api` behavior without CORS drift.
- No dependency on host Python, Node or MySQL runtime state during normal operation.
- Strong physical separation from production configuration.

### 3.2 Rejected: Docker data services plus host processes

Running only MySQL/Redis in Docker while using host Uvicorn and Vite is faster to assemble, but it depends on the host virtual environment, Node modules and shell state. It is less repeatable and makes cleanup and evidence collection ambiguous.

### 3.3 Rejected: Vite development staging

A Vite development server can label events as staging, but its module graph, source transforms, resource delivery and runtime timing differ materially from a built artifact. Its page timings are unsuitable for the required Source B evidence.

## 4. Architecture

The fixed Compose project name is:

```text
xiao-performance-staging
```

Services:

| Service | Responsibility | Host exposure |
| --- | --- | --- |
| `mysql` | MySQL 8 data store, database `xiao_performance_staging` | none |
| `redis` | Login-code/cache dependency | none |
| `migrate` | One-shot `alembic upgrade head` | none |
| `dataset` | One-shot Phase-04E create/verify/cleanup commands | none |
| `backend` | FastAPI application at container port 8000 | `127.0.0.1:19898` |
| `admin` | Built admin-h5 plus same-origin Nginx proxy | `127.0.0.1:18989` |

Only `admin` and the backend health/debug port are published, both on IPv4 loopback. MySQL and Redis stay on the private Compose network and have no host port.

Named volumes use project-scoped names. They cannot collide with the existing `saas-base` Compose project or its `mysql_data` and `redis_data` volumes.

## 5. Frontend artifact identity

Performance events derive environment at build time from:

```text
VITE_ADMIN_ENVIRONMENT || Vite MODE
```

The current production workflow runs a production-mode build without `VITE_ADMIN_ENVIRONMENT=staging`, so its artifact correctly records `environment=production`. Reusing that byte-identical artifact in staging would mislabel Source B events and is forbidden.

The local staging artifact is therefore built from an `admin-h5/**` tree that
must be byte-identical to the tree at exact source SHA:

```text
823708c1cbac8ba7c730715afafbecd27d641f09
```

with:

```text
ADMIN_RELEASE_SHA=823708c1cbac8ba7c730715afafbecd27d641f09
VITE_ADMIN_ENVIRONMENT=staging
VITE_API_BASE_URL=/api
```

The environment implementation itself will create later commits outside
`admin-h5/**`. Before building, the lifecycle checks that `git diff
823708c1cbac8ba7c730715afafbecd27d641f09 -- admin-h5` is empty. This permits
environment-only commits while proving that the frontend source still matches
the frozen version. The result has the same frontend source version but is an
environment-specific staging artifact, not the production Artifact and not
byte-identical to it. Its `release.json` records the frozen full SHA,
`environment=staging`, and a local staging builder identity. The report must
preserve this distinction.

Nginx serves the static artifact and preserves `/api/...` when proxying to `backend:8000`, matching the repository's FastAPI route prefixes.

## 6. Backend execution boundary

The backend uses the repository's existing Dockerfile but Compose overrides its command with:

```text
uvicorn app.main:app --host 0.0.0.0 --port 8000 --lifespan off
```

`--lifespan off` is mandatory for this read-only performance environment. The current FastAPI startup hooks launch stale-order cleanup, payment recovery, marketing, coupon-reminder and print-recovery loops. Those jobs would mutate the fixed historical dataset or attempt optional external behavior. Disabling lifespan avoids those side effects without changing business code.

The environment also sets:

- `APP_ENV=staging`
- `AUTO_CREATE_TABLES=false`
- database URL pointing only to `mysql/xiao_performance_staging`
- Redis URL pointing only to the private `redis` service
- real-payment and mock-money switches disabled
- external SMS, WeChat Pay, printer and notification credentials empty

Alembic owns schema creation. The environment requires exactly one repository head and a successful `alembic upgrade head`; it does not call `Base.metadata.create_all` and adds no migration.

## 7. Secrets and local configuration

Committed configuration contains variable names and safe defaults only. Runtime secrets are stored in:

```text
deploy/performance-staging/.env.performance-staging.local
```

The root `.gitignore` already ignores `.env.*`. The lifecycle script generates or requires:

- MySQL root password
- application database password
- JWT secret
- performance tenant password
- one-time owner login code

Secret values never appear in manifests, reports, Git diffs or routine console summaries. The local environment file is never copied into a container image; Compose passes values at runtime.

## 8. Performance tenant and authentication correction

Phase-04E currently creates:

- tenant `perf_test_only_v1`
- tenant phone `00000000000`
- staff account `perf_operator` with role `frontdesk`

Two facts block the required page validation:

1. `00000000000` fails the existing merchant phone format contract.
2. Dashboard, OrderManage and DishManage are owner-only routes; a frontdesk session must not access them.

The test infrastructure will make the minimum correction without altering business authentication or authorization:

- add fixed `PERF_OWNER_PHONE=19900000000` to the Phase-04E test dataset tool;
- store this phone on the fixed performance tenant;
- retain `perf_operator` unchanged for staff-path verification, but do not misuse it as an owner;
- add a staging-only CLI that validates the same environment/database/tenant marker and calls the existing `TencentSmsService.store_login_code()` with a six-digit code from `PERF_OWNER_LOGIN_CODE`;
- use the existing `/api/v1/login` endpoint and existing admin owner-login UI to authenticate.

The helper does not send SMS, create an endpoint, create a permanent token, change roles, or bypass route permissions. The existing verification consumes the stored code. Console output contains only the masked phone, expiry and status.

## 9. Dataset lifecycle

The environment lifecycle is:

```text
prepare
  → start mysql + redis
  → wait for health
  → run migrate
  → run dataset create
  → run dataset verify
  → run dataset cleanup
  → run dataset create again
  → run dataset verify again
  → seed one-time owner login code
  → start backend + admin
  → verify HTTP/artifact/auth/events
```

The create-cleanup-recreate sequence proves cleanup before leaving a usable final dataset in place.

Expected exact final counts:

| Data | Count |
| --- | ---: |
| MenuItem | 500 |
| category | 20 |
| Customer | 10000 |
| MemberAccount | 10000 |
| Order | 10000 |
| OrderItem | 30000 |

The dataset manifest remains `source=test`, `environment=staging`, versioned as `PERF_DATASET_V1`, and contains aggregate facts only.

Lifecycle operations:

- `start`: non-destructive bring-up and verification; preserves volumes on failure for diagnosis.
- `verify`: read-only Compose/config/health/migration/dataset checks.
- `cleanup`: Phase-04E marker-safe tenant cleanup only; other rows and volumes remain.
- `stop`: stops containers and preserves the database volume.
- `destroy`: explicit destructive operation that requires a confirmation switch and removes only the validated `xiao-performance-staging` containers/network/volumes.

No operation runs `docker system prune`, deletes generic volumes, or targets unresolved names.

## 10. Admin access and event validation

Validation uses the existing admin UI at:

```text
http://127.0.0.1:18989
```

After existing owner login succeeds, visit in order:

1. Dashboard `/`
2. OrderManage `/orders`
3. DishManage `/menu`
4. MemberManage `/customers`

Read the existing read-only outlet:

```text
window.__ADMIN_PERF_EVENTS__
```

Each page must have:

- `admin_page_enter`
- `admin_first_content_visible`
- `admin_page_ready`

Core requests must have matched `admin_api_request_start` and `admin_api_request_end`, with non-negative duration, a status and the expected API group. Every accepted event must contain:

```text
environment=staging
version=823708c1cbac8ba7c730715afafbecd27d641f09
```

The in-memory queue remains bounded and local. Events are not uploaded, persisted, expanded or merged with production samples. A validation snapshot may be exported to a Git-ignored output file containing performance metadata only; it must exclude token, cookie, request/response body, user information and merchant business records.

## 11. Isolation proof

Production is not queried merely to manufacture a before/after count. The approved local-only model proves isolation through configuration and connectivity:

- no production `.env` is read or mounted;
- no production database hostname, URL or credential is accepted;
- database host is the Compose service name `mysql`;
- database name is exactly `xiao_performance_staging` and satisfies the `_staging` guard;
- public production domains are absent from resolved Compose configuration and built admin API origin;
- host bindings are loopback-only;
- MySQL/Redis have no host ports;
- the dataset tenant marker is `source=test`;
- production deployment files and production Release directories are unchanged.

The final report states `PRODUCTION_COUNTS=NOT_QUERIED`. This is stronger and safer than connecting to production for a count comparison, and it avoids falsely claiming access that this phase does not have.

## 12. File boundaries

Expected implementation files:

- Create `deploy/performance-staging/compose.yml`.
- Create `deploy/performance-staging/admin.Dockerfile`.
- Create `deploy/performance-staging/nginx.conf`.
- Create `deploy/performance-staging/.env.example`.
- Create `scripts/performance-staging.ps1`.
- Create `saas-base/scripts/admin_performance_owner_code.py`.
- Create focused environment and owner-code contract tests.
- Modify `saas-base/scripts/admin_performance_dataset.py` only for the fixed valid test phone.
- Modify `saas-base/tests/test_admin_performance_dataset.py` for that test-phone contract.
- Create `docs/frontend/ADMIN_PERFORMANCE_OBSERVABILITY_PHASE04F_READY.md`.

Explicitly out of scope:

- `admin-h5/src/**`
- `saas-base/app/api/**`
- `saas-base/app/models/**`
- `saas-base/alembic/versions/**`
- dependency and lock files
- `.github/workflows/**`
- `scripts/deploy-production.sh`
- production Nginx, COS, Release Artifact or Atomic Switch configuration

## 13. Failure handling

The lifecycle fails closed and reports `NOT_READY` if any of the following occurs:

- Docker engine unavailable.
- Required loopback port already in use.
- the requested full SHA is not a commit, or the current `admin-h5/**` tree differs from that commit.
- secret environment file is missing, tracked, malformed or contains unsafe defaults.
- resolved Compose configuration exposes MySQL/Redis or contains production hosts.
- Alembic has multiple heads or upgrade fails.
- dataset create, verify, cleanup or recreate fails.
- artifact `release.json`, embedded version or staging environment is wrong.
- backend/admin health check fails.
- owner login fails.
- any core page redirects to login/unauthorized state.
- required page/API events are absent or contain the wrong environment/version.

Failure preserves logs and non-destructive volumes for inspection. Automatic retries do not regenerate data behind an unexplained verification failure. `destroy` is never an automatic failure handler.

## 14. Test strategy

Implementation follows TDD for new scripts and contracts.

Static/focused tests cover:

1. Fixed test owner phone passes existing format and remains non-secret metadata.
2. Owner-code helper rejects non-staging environment, wrong database suffix, wrong marker, missing/malformed code and missing tenant.
3. Owner-code helper stores a login-purpose code through the existing service and emits no code/token/secret.
4. Compose project, service names, loopback bindings, private MySQL/Redis and `--lifespan off` are fixed.
5. Resolved configuration excludes production domains and production database identifiers.
6. Admin build arguments freeze staging environment and full SHA.
7. Destructive volume removal requires exact project identity plus an explicit confirmation switch.

Runtime gates cover:

1. `docker compose config` succeeds.
2. MySQL and Redis become healthy.
3. `alembic heads` returns one head and `upgrade head` succeeds.
4. Real MySQL create/verify/cleanup/recreate/verify returns exact counts.
5. Backend and admin health/artifact checks succeed.
6. Existing owner login works through the API/UI.
7. All four pages and required page/API events pass the exact environment/version checks.
8. Dataset verify still passes after the controlled page-read batch.

The existing Phase-04E focused tests and related performance/menu/account/security regressions are re-run. Passing SQLite tests remain unit-contract evidence only; MySQL Compose results are recorded separately.

## 15. READY decision

The phase can output `RESULT A: READY` only when all runtime gates in section 14 pass on the local Docker environment and the required events are observed.

If any runtime gate is unavailable or fails, the report outputs:

```text
RESULT B: NOT_READY
Continue local performance-staging construction.
Do not enter Phase-04F dual-source sampling.
```

Even after local `READY`, Source B and production samples remain separate. Local staging results can validate data-volume, MySQL/API and page-rendering behavior, but they cannot prove production network latency or production-user P95.
