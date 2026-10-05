# Phase 03R — Super Admin candidate runtime (non-production, disposable)

One purpose: let a browser open `/super` on the **exact** Phase 03 candidate commit, with synthetic
data and a test-only super login, so Phase 03V (visual runtime certification) can run. Then destroy it.

This is **not** a staging system. It is localhost-only, has no external integrations, and is removed
with one command.

```text
candidate SHA ─▶ git archive (outside the working tree) ─▶ isolated Docker build
              ─▶ localhost-only runtime ─▶ synthetic data ─▶ test super login ─▶ Phase 03V ─▶ destroy
```

## Pinned versions

| Item | Value | Why |
|---|---|---|
| Admin SHA | `41ca65d86b6697781e7b5dd0f646c873292e44c2` | the frozen Phase 03 candidate |
| Backend SHA | the same `41ca65d…` | the candidate also changes the backend (`GET /api/super/merchants/{tenant_id}`, subscription/channel read summaries, `subscription_service.py`). The UI depends on those. The base commit `becd36a4` does **not** have them, so using it would break Merchant 360 |
| Alembic head | `20260830_0001` | candidate adds no migration; DB is built from empty to this head |

Nothing floats on a branch name: `Prepare` resolves the remote branch, requires it to equal the frozen SHA,
and extracts that commit with `git archive`.

## Local build exception (Phase 03R only)

The project rule is NO_LOCAL_BUILD. This phase needs one narrow exception:

```text
LOCAL_BUILD_EXCEPTION = ONLY_FOR_PHASE_03R_ISOLATED_DOCKER_RUNTIME
```

Allowed: building the candidate admin and backend images inside Docker, installing the project's existing
dependencies there, running the isolated MySQL / Redis / FastAPI. Still forbidden: `npm run build` or tests in the
main working tree, building `member-mini-client` / `channel-h5`, building or publishing a production image,
touching the production server.

`Up` refuses to run unless you pass `-ConfirmLocalBuildException`. That flag is the explicit authorisation.

## Commands (Windows, Docker Desktop running)

Run from any worktree of this repository that contains these files. From Git Bash:

```bash
cd /c/Users/15936/Desktop/xiao/.worktrees/super-admin-cert-runtime   # a worktree with this tooling
PS="powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/super-admin-cert.ps1"

$PS -Action Prepare                                  # verify + extract candidate, write .env.local
$PS -Action Up -ConfirmLocalBuildException           # Docker build + start (a few minutes the first time)
$PS -Action Verify                                   # runtime smoke, prints the Phase 03R report keys
$PS -Action Credentials                              # copies the test super password to the clipboard
# open the printed SUPER_RUNTIME_URL in a browser, paste the password
$PS -Action Down                                     # destroy everything
```

`Verify` is a smoke only (health, pages open, build SHA proof, one login, fixture presence). It is not Phase 03V.

## Isolation

- Compose project `xiao-super-admin-cert` (fixed in the file); every resource is project-prefixed: network `cert_private`, volume `cert_mysql_data`, no `container_name`.
- Admin and backend ports bind to `127.0.0.1` only (defaults 28989 / 29898, the next free port is chosen). `Verify` fails if Docker publishes on `0.0.0.0`.
- Own MySQL 8 and Redis. No production database, dump, Redis, volume, network or `.env` is referenced. The build context is a `git archive`, so the untracked production `.env` and `static/` can not be copied in.
- Every WeChat / SMS / printer / COS setting is blank, mock-money endpoints are off, `SAAS_REAL_PAYMENT_ENABLED` and `SAAS_MANUAL_PAYMENT_ENABLED` are false.
- The seed script refuses to run unless `APP_ENV=staging`, the acknowledgement variable is set and `DATABASE_URL` is the disposable database.

## Secrets

`Prepare` generates random test-only secrets into `deploy/super-admin-cert/.env.local` (git-ignored by `.env.*`). They are never printed and never committed.
The super login is password-only (`SUPER_ADMIN_TOTP_SECRET` is empty on purpose; TOTP is not enforced when unset).
`Credentials` copies the password to the clipboard. `Down` deletes `.env.local`.

## Synthetic fixtures

| Merchant | Account | Payment (display state) | Plan | Channel | Orders |
|---|---|---|---|---|---|
| `cert-merchant-a` 认证商户A（正常） | enabled | verified | PRO, active | 1 partner, active binding | 3 today |
| `cert-merchant-b` 认证商户B（已停用·免费版） | disabled | unconfigured | free (expired trial) | none | 0 |
| `cert-merchant-c` 认证商户C（待验证·试用） | enabled | pending | PRO trial | none | 0 |

Billing: one paid invoice for A (history) and one `WAITING_CONFIRMATION` manual payment for C (pending badge, queue, queue → merchant link).
The merchant numbers (`1900000001`, `1900000003`) are placeholders that only drive the displayed payment state. No real key or certificate exists.
Nothing here can confirm a real payment; **do not click "confirm" in Phase 03V** unless a certification step explicitly says so.

## Known limits

- "Payment verified" is a database state, not a proof that WeChat works. Merchant payment *writes* (config, verify, pause) must not be exercised against these placeholders.
- `SAAS_MANUAL_PAYMENT_ENABLED=false`: the manual-payment screens read and list, but any confirm path depends on that flag. Phase 03V is read-oriented.
- Windows + Docker Desktop only (the tooling is PowerShell, like `scripts/performance-staging.ps1`).
- The first build downloads Node and Python dependencies inside Docker.

## Teardown

```bash
$PS -Action Down
```

Runs `docker compose --project-name xiao-super-admin-cert down -v --remove-orphans`, removes the extracted source under the temp directory and `.env.local`.
It does not touch the repository, the candidate branch, any commit, or any other Docker project.
