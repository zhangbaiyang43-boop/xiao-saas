# Admin Performance Staging Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify a loopback-only Docker Compose performance-staging environment that runs the frozen admin-h5 source against isolated MySQL data and produces trustworthy staging performance events.

**Architecture:** A fixed `xiao-performance-staging` Compose project runs MySQL, Redis, migration/dataset jobs, a lifespan-disabled FastAPI backend and an Nginx-served staging build. Existing business APIs and the Phase-03C event model remain unchanged; test-only CLIs prepare deterministic data and a one-time owner login code.

**Tech Stack:** Docker Desktop/Compose, MySQL 8, Redis 7, Python 3.10, FastAPI, SQLAlchemy/Alembic, Vue 3/Vite, Nginx, PowerShell, pytest.

---

## File map

- Modify `saas-base/scripts/admin_performance_dataset.py`: add the fixed valid performance owner phone and use it for the fixed tenant.
- Modify `saas-base/tests/test_admin_performance_dataset.py`: prove the phone contract and stored tenant phone.
- Create `saas-base/scripts/admin_performance_owner_code.py`: staging-only one-time owner login-code preparation.
- Create `saas-base/tests/test_admin_performance_owner_code.py`: owner-code guard, tenant marker and secrecy tests.
- Create `deploy/performance-staging/compose.yml`: isolated service topology and one-shot jobs.
- Create `deploy/performance-staging/admin.Dockerfile`: staging artifact build and Nginx image.
- Create `deploy/performance-staging/nginx.conf`: static SPA serving and same-origin `/api` proxy.
- Create `deploy/performance-staging/.env.example`: variable names and non-secret fixed identifiers.
- Create `scripts/performance-staging.ps1`: prepare/start/verify/cleanup/stop/destroy orchestration.
- Create `saas-base/tests/test_performance_staging_environment_contracts.py`: static safety and orchestration contracts.
- Create `docs/frontend/ADMIN_PERFORMANCE_OBSERVABILITY_PHASE04F_READY.md`: evidence-backed readiness result.

No file under `admin-h5/src`, `saas-base/app/api`, `saas-base/app/models`, `saas-base/alembic/versions`, `.github/workflows`, dependency manifests, lockfiles, or production deployment tooling may change.

### Task 1: RED/GREEN — valid fixed performance owner phone

**Files:**
- Modify: `saas-base/tests/test_admin_performance_dataset.py`
- Modify: `saas-base/scripts/admin_performance_dataset.py`

- [ ] **Step 1: Write the failing identity and persistence tests**

Add `PERF_OWNER_PHONE` to the import list and extend the fixed-identity test:

```python
def test_dataset_identity_is_fixed() -> None:
    assert DATASET_VERSION == "PERF_DATASET_V1"
    assert PERF_TENANT_ID == "perf_test_only_v1"
    assert PERF_OWNER_PHONE == "19900000000"
    assert len(PERF_OWNER_PHONE) == 11
    assert PERF_OWNER_PHONE.startswith(tuple(str(value) for value in range(13, 20)))
```

In the small lifecycle scenario, query the created tenant and assert:

```python
tenant = await session.scalar(
    select(Tenant).where(Tenant.tenant_id == PERF_TENANT_ID)
)
assert tenant.phone == PERF_OWNER_PHONE
```

- [ ] **Step 2: Run RED**

Run:

```powershell
$env:JWT_SECRET_KEY='phase04f-test-only-secret-32-bytes-minimum'
py -3.10 -m pytest tests/test_admin_performance_dataset.py::test_dataset_identity_is_fixed -v
```

Expected: collection fails because `PERF_OWNER_PHONE` is not defined.

- [ ] **Step 3: Implement the minimal fixed phone contract**

Add next to the other fixed identities:

```python
PERF_OWNER_PHONE = "19900000000"
```

Replace the fixed tenant's current phone literal with:

```python
phone=PERF_OWNER_PHONE,
```

Do not change customer phone generation, staff role, API schemas or validation logic.

- [ ] **Step 4: Run GREEN and the full Phase-04E focused file**

Run:

```powershell
py -3.10 -m pytest tests/test_admin_performance_dataset.py -q
```

Expected: 18 tests pass, including the default 500/10000/10000 lifecycle.

- [ ] **Step 5: Commit Task 1**

```powershell
git add -- saas-base/scripts/admin_performance_dataset.py saas-base/tests/test_admin_performance_dataset.py
git commit -m "test(admin): make performance owner login-capable"
```

### Task 2: RED/GREEN — staging-only owner login-code helper

**Files:**
- Create: `saas-base/tests/test_admin_performance_owner_code.py`
- Create: `saas-base/scripts/admin_performance_owner_code.py`

- [ ] **Step 1: Write failing pure validation tests**

Create tests that import:

```python
from scripts.admin_performance_owner_code import (
    OwnerCodeSafetyError,
    mask_owner_phone,
    validate_owner_code,
)


def test_owner_code_must_be_exactly_six_digits() -> None:
    assert validate_owner_code("123456") == "123456"
    for value in ("", "12345", "1234567", "abcdef", "12 456"):
        with pytest.raises(OwnerCodeSafetyError):
            validate_owner_code(value)


def test_owner_phone_is_masked() -> None:
    assert mask_owner_phone("19900000000") == "199****0000"
```

- [ ] **Step 2: Write failing database marker and service-call tests**

Use an isolated SQLite database with `Tenant` and `TenantConfig`. Create the exact marked tenant and patch the existing SMS service method:

```python
async def test_seed_uses_existing_login_code_service_without_exposing_code() -> None:
    engine, factory = await make_database(marked=True)
    try:
        with patch(
            "scripts.admin_performance_owner_code.TencentSmsService.store_login_code",
            new=AsyncMock(),
        ) as store:
            report = await seed_owner_login_code(factory, "123456")
        store.assert_awaited_once_with(
            PERF_OWNER_PHONE,
            "123456",
            SmsPurpose.LOGIN,
        )
        assert report == {
            "status": "PASS",
            "dataset_version": DATASET_VERSION,
            "tenant_id": PERF_TENANT_ID,
            "phone": "199****0000",
            "purpose": "login",
        }
        assert "123456" not in json.dumps(report)
    finally:
        await engine.dispose()
```

Add negative cases for missing tenant, unmarked tenant, wrong fixed name and wrong phone. Each must raise `OwnerCodeSafetyError` before `store_login_code` is called.

- [ ] **Step 3: Run RED**

Run:

```powershell
py -3.10 -m pytest tests/test_admin_performance_owner_code.py -v
```

Expected: collection fails because the helper module does not exist.

- [ ] **Step 4: Implement validation and marked-tenant verification**

Create the helper with these public contracts:

```python
class OwnerCodeSafetyError(RuntimeError):
    pass


def validate_owner_code(value: str) -> str:
    code = str(value or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        raise OwnerCodeSafetyError("PERF_OWNER_LOGIN_CODE must be exactly six digits")
    return code


def mask_owner_phone(phone: str) -> str:
    return f"{phone[:3]}****{phone[-4:]}"


async def seed_owner_login_code(
    session_factory: async_sessionmaker[AsyncSession],
    code: str,
) -> dict[str, str]:
    normalized_code = validate_owner_code(code)
    async with session_factory() as session:
        tenant = await session.scalar(
            select(Tenant).where(Tenant.tenant_id == PERF_TENANT_ID)
        )
        config = await session.scalar(
            select(TenantConfig).where(TenantConfig.tenant_id == PERF_TENANT_ID)
        )
        marker = (config.business_info or {}).get("performanceTest") if config else None
        if (
            tenant is None
            or tenant.name != PERF_TENANT_NAME
            or tenant.phone != PERF_OWNER_PHONE
            or not isinstance(marker, dict)
            or marker.get("datasetVersion") != DATASET_VERSION
            or marker.get("source") != "test"
        ):
            raise OwnerCodeSafetyError("exact marked performance tenant is required")
    await TencentSmsService().store_login_code(
        PERF_OWNER_PHONE,
        normalized_code,
        SmsPurpose.LOGIN,
    )
    return {
        "status": "PASS",
        "dataset_version": DATASET_VERSION,
        "tenant_id": PERF_TENANT_ID,
        "phone": mask_owner_phone(PERF_OWNER_PHONE),
        "purpose": SmsPurpose.LOGIN,
    }
```

- [ ] **Step 5: Implement the fail-closed CLI**

The CLI must:

1. import settings only at execution time;
2. call Phase-04E `validate_runtime_guard(settings.APP_ENV, settings.DATABASE_URL, PERF_DATASET_ACK)`;
3. require `APP_ENV=staging` after the shared guard (local `test` is insufficient for this helper);
4. read `PERF_OWNER_LOGIN_CODE` only from the process environment;
5. create/dispose its own async engine;
6. print only the safe JSON report;
7. return 2 for safety failures and 1 for an unexpected generic failure without printing the exception or any secret.

Use this exact entrypoint shape:

```python
def main() -> int:
    try:
        report = asyncio.run(_run_cli())
    except (DatasetSafetyError, OwnerCodeSafetyError) as exc:
        print(json.dumps({"status": "FAIL", "message": str(exc)}), file=sys.stderr)
        return 2
    except Exception:
        print(json.dumps({"status": "FAIL", "message": "owner code preparation failed"}), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0
```

- [ ] **Step 6: Run GREEN and secrecy scan**

Run:

```powershell
py -3.10 -m pytest tests/test_admin_performance_owner_code.py -q
rg -n "print\(.*code|token|cookie|request.body|response.body" scripts/admin_performance_owner_code.py
```

Expected: all tests pass; the scan finds no secret-emitting path.

- [ ] **Step 7: Commit Task 2**

```powershell
git add -- saas-base/scripts/admin_performance_owner_code.py saas-base/tests/test_admin_performance_owner_code.py
git commit -m "test(admin): add staging owner code helper"
```

### Task 3: RED — freeze the performance-staging environment contract

**Files:**
- Create: `saas-base/tests/test_performance_staging_environment_contracts.py`

- [ ] **Step 1: Write missing-file and topology tests**

Resolve the repository root from the test file and require all environment files. Read them as UTF-8 text and assert:

```python
FILES = {
    "compose": ROOT / "deploy/performance-staging/compose.yml",
    "dockerfile": ROOT / "deploy/performance-staging/admin.Dockerfile",
    "nginx": ROOT / "deploy/performance-staging/nginx.conf",
    "env": ROOT / "deploy/performance-staging/.env.example",
    "lifecycle": ROOT / "scripts/performance-staging.ps1",
}


def test_required_environment_files_exist() -> None:
    assert all(path.is_file() for path in FILES.values())


def test_compose_is_loopback_only_and_data_services_are_private() -> None:
    compose = FILES["compose"].read_text(encoding="utf-8")
    assert "name: xiao-performance-staging" in compose
    assert '"127.0.0.1:18989:80"' in compose
    assert '"127.0.0.1:19898:8000"' in compose
    assert '"3306:' not in compose
    assert '"6379:' not in compose
    assert "xiao_performance_staging" in compose
    assert "--lifespan" in compose and '"off"' in compose
```

Also assert exact services `mysql`, `redis`, `migrate`, `dataset`, `owner-code`, `backend`, `admin`, exact frozen SHA build arg, `VITE_ADMIN_ENVIRONMENT: staging`, and no production domain in Compose/Nginx/env/lifecycle text.

- [ ] **Step 2: Write destructive-action and source-identity tests**

Require the lifecycle script to contain:

```text
ValidateSet('Prepare','Start','Verify','Cleanup','Stop','Destroy')
ConfirmDestroy
xiao-performance-staging
git diff --quiet
-- admin-h5
docker compose
```

Assert it contains neither `docker system prune` nor a generic volume wildcard nor a production deploy command.

- [ ] **Step 3: Run RED**

Run:

```powershell
py -3.10 -m pytest tests/test_performance_staging_environment_contracts.py -v
```

Expected: failures report the five missing environment files.

### Task 4: GREEN — Compose topology and staging artifact

**Files:**
- Create: `deploy/performance-staging/compose.yml`
- Create: `deploy/performance-staging/admin.Dockerfile`
- Create: `deploy/performance-staging/nginx.conf`
- Create: `deploy/performance-staging/.env.example`
- Test: `saas-base/tests/test_performance_staging_environment_contracts.py`

- [ ] **Step 1: Create the environment example without secrets**

The committed file defines keys only:

```dotenv
COMPOSE_PROJECT_NAME=xiao-performance-staging
APP_ENV=staging
PERFORMANCE_DB_NAME=xiao_performance_staging
PERFORMANCE_DB_USER=perf_app
MYSQL_ROOT_PASSWORD=
MYSQL_APP_PASSWORD=
JWT_SECRET_KEY=
PERF_TEST_PASSWORD=
PERF_OWNER_LOGIN_CODE=
PERF_DATASET_ACK=PERF_DATASET_V1
ADMIN_RELEASE_SHA=823708c1cbac8ba7c730715afafbecd27d641f09
```

No real or placeholder credential value is committed.

- [ ] **Step 2: Create the Nginx contract**

Use one server listening on 80. The important routes are:

```nginx
location /api/ {
    proxy_pass http://backend:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}

location / {
    try_files $uri $uri/ /index.html;
}
```

Do not reference a production upstream or TLS certificate.

- [ ] **Step 3: Create the multi-stage admin image**

The build stage uses `node:20-alpine`, runs `npm ci` and `npm run build`, and receives:

```dockerfile
ARG ADMIN_RELEASE_SHA
ARG VITE_ADMIN_ENVIRONMENT=staging
ARG VITE_API_BASE_URL=/api
ARG VITE_API_ORIGIN=http://127.0.0.1:18989
ENV ADMIN_RELEASE_SHA=$ADMIN_RELEASE_SHA
ENV VITE_ADMIN_ENVIRONMENT=$VITE_ADMIN_ENVIRONMENT
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_API_ORIGIN=$VITE_API_ORIGIN
```

The final `nginx:1.27-alpine` stage copies `dist/`, the Nginx config, and writes `/usr/share/nginx/html/release.json` containing only full SHA, `environment=staging`, and `builder=local-docker-performance-staging`. Validate the SHA against `^[0-9a-f]{40}$` during build.

- [ ] **Step 4: Create the fixed Compose services**

Use a private bridge network and project-scoped named volumes. Critical environment values:

```yaml
name: xiao-performance-staging

services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_DATABASE: ${PERFORMANCE_DB_NAME}
      MYSQL_USER: ${PERFORMANCE_DB_USER}
      MYSQL_PASSWORD: ${MYSQL_APP_PASSWORD}
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
    volumes:
      - mysql_staging_data:/var/lib/mysql

  redis:
    image: redis:7.0-alpine
    volumes:
      - redis_staging_data:/data
```

Define a shared backend environment block with database/Redis/JWT/staging values and external-provider switches disabled. `migrate`, `dataset`, `owner-code` and `backend` all build from the existing `saas-base/Dockerfile`; override commands rather than editing that Dockerfile.

The backend command is exactly:

```yaml
command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--lifespan", "off"]
```

`admin` builds with context at repository root, the new Dockerfile and frozen arguments, depends on healthy backend, and publishes only `127.0.0.1:18989:80`. Backend publishes only `127.0.0.1:19898:8000`.

- [ ] **Step 5: Run static GREEN and Compose resolution**

Run:

```powershell
py -3.10 -m pytest tests/test_performance_staging_environment_contracts.py -q
docker compose --env-file deploy/performance-staging/.env.example -f deploy/performance-staging/compose.yml config --quiet
```

The second command is expected to fail while secrets are empty if Compose interpolation requires them; if it does, use a process-only test environment with non-secret test literals and require `config --quiet` to pass. Never put those values into the committed example.

- [ ] **Step 6: Commit Task 4**

```powershell
git add -- deploy/performance-staging saas-base/tests/test_performance_staging_environment_contracts.py
git commit -m "test(admin): define local performance staging"
```

### Task 5: RED/GREEN — safe PowerShell lifecycle

**Files:**
- Create: `scripts/performance-staging.ps1`
- Modify: `saas-base/tests/test_performance_staging_environment_contracts.py`

- [ ] **Step 1: Extend RED contracts for all lifecycle gates**

Assert the script contains named functions for:

```text
Assert-DockerReady
Assert-AdminSourceIdentity
Assert-LoopbackPortsAvailable
Initialize-LocalEnvironment
Assert-ResolvedComposeIsolation
Invoke-MigrationGate
Invoke-DatasetLifecycle
Invoke-OwnerCodePreparation
Wait-HttpHealthy
Invoke-StagingVerify
Invoke-StagingDestroy
```

Require `Destroy` to throw unless both `-ConfirmDestroy` and the exact project name are present. Require secrets to be generated with `.NET RandomNumberGenerator`, not `Get-Random`.

- [ ] **Step 2: Run RED**

Run the focused test and expect missing function-name failures.

- [ ] **Step 3: Implement command surface and safe process invocation**

Start the script with:

```powershell
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Prepare','Start','Verify','Cleanup','Stop','Destroy')]
    [string]$Action,
    [switch]$ConfirmDestroy
)

$ErrorActionPreference = 'Stop'
$ProjectName = 'xiao-performance-staging'
$FrozenAdminSha = '823708c1cbac8ba7c730715afafbecd27d641f09'
```

Resolve absolute repository/config/env paths from `$PSScriptRoot`. Invoke Docker with argument arrays:

```powershell
& docker compose --project-name $ProjectName --env-file $LocalEnv -f $ComposeFile @Arguments
if ($LASTEXITCODE -ne 0) { throw "docker compose failed" }
```

Never build one shell command string and never print the environment-file contents.

- [ ] **Step 4: Implement prepare and preflight**

`Prepare` must:

1. require Docker server availability;
2. confirm the frozen SHA exists;
3. run `git diff --quiet $FrozenAdminSha -- admin-h5` and fail if the tree differs;
4. confirm the local env path is ignored by Git;
5. create missing secrets as hex and a six-digit code through cryptographic RNG;
6. preserve an existing valid local env rather than rotating it silently;
7. resolve `docker compose config` to memory and reject production domains, non-loopback published ports or MySQL/Redis host ports;
8. reject occupied ports 18989/19898 before first start.

- [ ] **Step 5: Implement Start lifecycle**

Use this exact order and stop immediately on failure:

```text
up -d mysql redis
wait for both health checks
run --rm migrate
run --rm dataset create --dataset-version PERF_DATASET_V1 --manifest-out /tmp/PERF_DATASET_V1.json
run --rm dataset verify --dataset-version PERF_DATASET_V1
run --rm dataset cleanup --dataset-version PERF_DATASET_V1
run --rm dataset create --dataset-version PERF_DATASET_V1 --manifest-out /tmp/PERF_DATASET_V1.json
run --rm dataset verify --dataset-version PERF_DATASET_V1
run --rm owner-code
up -d backend admin
wait for http://127.0.0.1:19898/health
wait for http://127.0.0.1:18989/release.json
Verify
```

Capture safe JSON command output under a task-specific directory in `$env:TEMP`; do not create a tracked runtime file.

- [ ] **Step 6: Implement Verify, Cleanup, Stop and Destroy**

`Verify` checks Compose isolation, container health, one Alembic head, dataset verify, backend health, admin release SHA/environment and current service configuration.

`Cleanup` runs only the marker-safe dataset cleanup. `Stop` uses `docker compose stop` and preserves volumes. `Destroy` must implement:

```powershell
if (-not $ConfirmDestroy) {
    throw 'Destroy requires -ConfirmDestroy'
}
if ($ProjectName -ne 'xiao-performance-staging') {
    throw 'Refusing to destroy an unexpected project'
}
Invoke-Compose @('down', '--volumes', '--remove-orphans')
```

- [ ] **Step 7: Run GREEN and PowerShell parse validation**

Run:

```powershell
py -3.10 -m pytest tests/test_performance_staging_environment_contracts.py -q
$null = [scriptblock]::Create((Get-Content ..\scripts\performance-staging.ps1 -Raw))
```

Expected: tests pass and parsing throws no exception.

- [ ] **Step 8: Commit Task 5**

```powershell
git add -- scripts/performance-staging.ps1 saas-base/tests/test_performance_staging_environment_contracts.py
git commit -m "test(admin): orchestrate performance staging lifecycle"
```

### Task 6: VERIFY — real Docker/MySQL lifecycle

**Files:**
- Runtime only: Git-ignored local env, Docker containers/networks/volumes, `$env:TEMP` evidence

- [ ] **Step 1: Run focused tests before Docker mutation**

```powershell
cd saas-base
$env:JWT_SECRET_KEY='phase04f-test-only-secret-32-bytes-minimum'
py -3.10 -m pytest tests/test_admin_performance_dataset.py tests/test_admin_performance_owner_code.py tests/test_performance_staging_environment_contracts.py -q
```

Expected: zero failures.

- [ ] **Step 2: Prepare without starting containers**

```powershell
cd ..
.\scripts\performance-staging.ps1 -Action Prepare
```

Verify:

- local env exists and `git check-ignore` succeeds;
- no secret is printed;
- resolved configuration has only the approved project/network/ports;
- `git status --short` contains no runtime file.

- [ ] **Step 3: Build and start the environment**

```powershell
.\scripts\performance-staging.ps1 -Action Start
```

This may download base images and package dependencies. Record image names, build completion, migration head, dataset command results and elapsed time. Do not describe download/build time as page performance.

- [ ] **Step 4: Prove real MySQL dataset lifecycle**

Record the two successful create/verify passes and the cleanup pass. Require final exact counts:

```json
{
  "dishes": 500,
  "customers": 10000,
  "member_accounts": 10000,
  "orders": 10000,
  "order_items": 30000
}
```

Require `database=xiao_performance_staging`, `environment=staging`, `tenant_id=perf_test_only_v1`, and dataset `PERF_DATASET_V1`. Do not output the database URL or credentials.

- [ ] **Step 5: Verify services and artifact identity**

```powershell
Invoke-RestMethod http://127.0.0.1:19898/health
Invoke-RestMethod http://127.0.0.1:18989/release.json
.\scripts\performance-staging.ps1 -Action Verify
```

Expected release facts:

```json
{
  "sha": "823708c1cbac8ba7c730715afafbecd27d641f09",
  "environment": "staging",
  "builder": "local-docker-performance-staging"
}
```

- [ ] **Step 6: Run post-start dataset verification**

Require the final dataset verify to pass before browser interaction. If it fails, stop and retain containers/volume; do not regenerate until the mismatch is understood.

### Task 7: VERIFY — existing owner login and performance events

**Files:**
- Runtime only: browser session and bounded in-memory events

- [ ] **Step 1: Open the loopback admin and authenticate through the existing UI**

Open `http://127.0.0.1:18989/login`. Select owner login, enter the fixed performance phone and the local one-time code from the ignored environment without printing either secret value in logs. Do not click “send code”; the helper already stored it in staging Redis. Submit the existing login form.

Expected: existing `/api/v1/login` succeeds, role is owner, and the browser reaches Dashboard. If login fails, record `ADMIN_ACCESS=FAIL` and stop; do not inject a JWT or weaken route guards as fallback.

- [ ] **Step 2: Clear only the bounded performance queue**

Use the existing exported helper or reload immediately after authentication so the batch begins from a known queue boundary. Do not alter the event model or replace `window.__ADMIN_PERF_EVENTS__`.

- [ ] **Step 3: Visit the four pages sequentially**

Wait for visible content and the existing ready event on each route:

```text
Dashboard      /
OrderManage    /orders
DishManage     /menu
MemberManage   /customers
```

Do not edit, receive, print, issue coupons or change order/menu/member state. This is a read-only navigation batch.

- [ ] **Step 4: Validate page events in-browser**

Read `window.__ADMIN_PERF_EVENTS__`, filter only the four target page names, and calculate a safe summary. For every page require all three event names and exact metadata:

```text
environment=staging
version=823708c1cbac8ba7c730715afafbecd27d641f09
timestamp valid
duration non-negative when present
```

Do not export route query strings, tokens, cookies, request/response bodies or row data.

- [ ] **Step 5: Validate API events**

Require matched start/end evidence for core groups reached by the batch:

```text
orders
menu
members
```

Dashboard may use multiple existing groups. Every accepted end event needs status and non-negative duration. Record counts and request names only; this phase does not judge slow/fast.

- [ ] **Step 6: Verify the dataset after browser reads**

```powershell
.\scripts\performance-staging.ps1 -Action Verify
```

Expected: exact counts and checksum still pass. A mismatch means the supposedly read-only access batch mutated the dataset and the environment is `NOT_READY`.

### Task 8: Regression, boundary audit and readiness report

**Files:**
- Create: `docs/frontend/ADMIN_PERFORMANCE_OBSERVABILITY_PHASE04F_READY.md`

- [ ] **Step 1: Run final focused and related regressions**

```powershell
cd saas-base
$env:JWT_SECRET_KEY='phase04f-test-only-secret-32-bytes-minimum'
py -3.10 -m pytest tests/test_admin_performance_dataset.py tests/test_admin_performance_owner_code.py tests/test_performance_staging_environment_contracts.py tests/test_performance_contracts.py tests/test_menu_performance_contracts.py tests/test_tenant_account_contracts.py tests/test_merchant_staff_security_gate.py -q
```

Expected: zero failures. Do not claim the full backend suite unless it is separately run to completion.

- [ ] **Step 2: Audit the exact file boundary**

Require changes only in the file map at the top of this plan plus the approved spec/plan/report. Run:

```powershell
git diff --name-only 823708c1cbac8ba7c730715afafbecd27d641f09...HEAD
git diff --check
git status --short
```

Fail if any admin runtime, business API/model, migration, workflow, dependency, lockfile or production deployment file changed.

- [ ] **Step 3: Scan for secrets and production endpoints**

Scan committed candidate files for actual credentials, JWTs, cookies, database URLs and production domains. Environment variable names are allowed; values are not. Verify the ignored local env is absent from `git ls-files`.

- [ ] **Step 4: Write the required readiness report**

The report must contain:

1. environment address `http://127.0.0.1:18989`, backend health address, environment `staging`, frozen version and local-only scope;
2. tenant `perf_test_only_v1`, purpose and marker isolation;
3. target/actual/status tables for 500 dishes, 10000 members and 10000 orders;
4. four-page page-event and API-event results;
5. isolation proof with `PRODUCTION_COUNTS=NOT_QUERIED` and no production connection;
6. commands and exact test/runtime results;
7. limitations: local network/device only, no production latency/P95 claim, no performance optimization;
8. `READY` or `NOT_READY` based only on executed evidence.

- [ ] **Step 5: Apply the final gate**

Output `RESULT A: READY` only if Docker/MySQL lifecycle, login, all four page events, API events, post-navigation verify and regressions pass. Otherwise output `RESULT B: NOT_READY` and list the exact failed or unexecuted gate. Never lower the gate to finish the phase.

- [ ] **Step 6: Commit the report and final implementation**

Stage only the approved file set and commit:

```powershell
git add -- deploy/performance-staging scripts/performance-staging.ps1 saas-base/scripts/admin_performance_dataset.py saas-base/scripts/admin_performance_owner_code.py saas-base/tests/test_admin_performance_dataset.py saas-base/tests/test_admin_performance_owner_code.py saas-base/tests/test_performance_staging_environment_contracts.py docs/frontend/ADMIN_PERFORMANCE_OBSERVABILITY_PHASE04F_READY.md
git commit -m "test(admin): establish local performance staging"
```

Do not push, merge, deploy, destroy the ready environment or modify production without a separate user choice.
