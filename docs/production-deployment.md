# Production Deployment

**Single command, single Git authority -- target contract.** `/www/wwwroot/xiao`
is meant to become the *only* source-of-truth checkout for both `saas-base`
and `admin-h5` in production, retiring the historical second hand-maintained
source tree under `/www/wwwroot/admin-h5/{src,scripts,node_modules,...}`.

**PRODUCTION_FRONTEND_BUILD=FORBIDDEN.** The production host has ~1.6 GiB RAM
and `vite build` reliably locked it up on the first real bootstrap attempt --
this is a deployment-architecture problem, not something swap/`NODE_OPTIONS`/
lower concurrency fixes. `admin-h5` is built exactly once, by GitHub Actions,
and never on the production host at all. `scripts/deploy-production.sh`
contains no executable `npm`/`npx`/`vite` invocation anywhere (enforced by a
dedicated regression case in `scripts/test-deployment-tooling.sh`), and the
production host does not need Node.js or `admin-h5/node_modules` installed
for deployment to work.

**PRODUCTION_GITHUB_RELEASE_DIRECT_DOWNLOAD=FORBIDDEN.** GitHub Releases
remain the audit/backup/immutable-build-evidence copy of every admin-h5
artifact (see [Artifact build & publish](#artifact-build--publish-github-actions)),
but production evidence showed a direct `github.com/.../releases/download`
fetch from mainland China running at ~4-10KB/s and timing out even though
`github.com` and `raw.githubusercontent.com` were both otherwise reachable.
**Tencent COS is the production runtime transport** -- see
[Artifact transport](#artifact-transport-tencent-cos). The production host
never needs a COS secret to download from it: the public COS base URL is a
plain HTTPS GET, no credentials required.

**FIRST_MIGRATION_STATUS=NOT_YET_EXECUTED.** The tooling below (`scripts/
deploy-production.sh`, `scripts/rollback-admin-h5.sh`) exists and is
Linux-certified (see [GitHub Actions](#github-actions)), but the one-time
production cutover described in [First migration](#first-migration-one-time-no-downtime-cutover)
has not been run yet. Until it has, production nginx still serves
`/www/wwwroot/admin-h5/dist` and the legacy source tree is still live there --
this document describes the target end state and the exact steps to reach
it, not something already true of production today.

## The one command

```bash
cd /www/wwwroot/xiao
./scripts/deploy-production.sh
```

That's it. It:

1. Refuses to run if the production checkout has uncommitted changes
   (`BLOCKED_DIRTY_PRODUCTION_TREE`) -- never auto-resets/cleans/stashes.
2. Fetches `origin` and diffs **BEFORE_SHA (current HEAD) against TARGET_SHA
   (fetched `origin/main`) -- before checking anything out** -- to figure out
   what changed (`admin-h5/**`, `saas-base/**`, `saas-base/alembic/versions/**`).
   This ordering matters: it's what makes the migration stop below provably
   safe (see [Migration releases](#migration-releases)).
3. **Stops here, HEAD still untouched,** if an Alembic migration file
   changed -- migrations are reviewed and applied by hand, never
   automatically, and the working tree is never advanced past a migration it
   hasn't run. See [Migration releases](#migration-releases) below.
4. If `admin-h5/**` changed: resolves `ARTIFACT_BASE_URL` (process
   environment first, then a single key parsed out of `$DEPLOY_CONFIG_FILE`
   -- see [Artifact transport](#artifact-transport-tencent-cos)) and stops
   here, HEAD still untouched, if it's still unresolved
   (`BLOCKED_ARTIFACT_TRANSPORT_NOT_CONFIGURED`) -- before the pull, before
   any download, before the backend restart, before touching `current`.
5. Only now: fast-forwards `main` (`git pull --ff-only`) -- never
   force-pulls, never rebases, never resets.
6. If `admin-h5/**` changed: downloads the checksummed artifact for this
   exact commit from the resolved `ARTIFACT_BASE_URL` (production: Tencent
   COS -- never GitHub, see [Artifact transport](#artifact-transport-tencent-cos)),
   verifies its checksum and archive-entry safety, extracts it into an
   immutable, SHA-named release directory -- but does **not** switch
   `current` yet. If the artifact isn't there yet, stops here
   (`ADMIN_ARTIFACT_NOT_READY`) before touching the backend or `current`.
7. If `saas-base/**` changed: restarts `saas-base.service` and verifies
   `/health` returns healthy. **A failure here stops the whole deploy before
   the admin-h5 release prepared in step 6 is ever switched live** -- you
   never end up with a new frontend talking to a broken backend, or a broken
   frontend at all; `current` simply stays exactly where it was.
8. Only once the backend (if it was part of this deploy) is confirmed
   healthy: atomically switches the `current` symlink -- verified with a
   real HTTP request before committing to the switch (routine mode; see
   [Bootstrap mode](#bootstrap-mode-first-cutover-only) for the one-time
   exception), with an automatic rollback to the previous release if
   verification fails.

## What this replaces

**Do not, ever again:**

- `cp -r dist ...` by hand into `/www/wwwroot/admin-h5`
- Edit source files directly under `/www/wwwroot/admin-h5/src`
- Run `npm ci` / `npm run build` / `vite build` / `npx vite` **anywhere on
  the production host** -- not inside `deploy-production.sh`, not by hand,
  not to "just this once" work around a stuck deploy. This is the incident
  that started this phase: the production host doesn't have the RAM for it.
- Upload `dist/` via FTP/SFTP
- Maintain a second `git` checkout (or, worse, no `git` at all) under
  `/www/wwwroot/admin-h5`

All of that was the historical pattern this unification replaces. The only
sanctioned way to ship an admin-h5 or saas-base change to production is the
one command above, run against `/www/wwwroot/xiao`.

## Layout

**Git authority (the only source tree):**

```
/www/wwwroot/xiao/            # git checkout of origin/main
├── admin-h5/                 # frontend source -- built ONLY by GitHub Actions,
│                              # never on the production host, never edited here
├── saas-base/                # backend source, served directly by saas-base.service
└── scripts/
    ├── deploy-production.sh
    ├── rollback-admin-h5.sh
    ├── test-deployment-tooling.sh          # Linux integration contract, CI-only
    └── publish-admin-artifact-cos.py       # GitHub Actions publish job only,
                                             # never runs on the production host
```

**Frontend release artifacts (build output, not source):**

```
/www/wwwroot/admin-h5/
├── releases/
│   ├── <full-git-sha>/       # immutable -- index.html, assets/, release.json
│   │   ...
│   └── <full-git-sha>/
├── current -> releases/<full-git-sha>   # atomic symlink, what nginx serves
└── legacy-source.<timestamp>/           # temporary, see "First migration" below
```

A release directory *is* the built `dist/` content directly (`index.html` +
`assets/` at its root) -- there is no nested `dist/` inside a release.

Every release carries `release.json`:

```json
{
  "sha": "<full git sha>",
  "built_at": "<UTC ISO8601 timestamp>",
  "builder": "github-actions"
}
```

To find out which commit is currently live:

```bash
cat /www/wwwroot/admin-h5/current/release.json
```

## Artifact build & publish (GitHub Actions)

`admin-h5` is built exactly once per commit, by `.github/workflows/admin-h5-release.yml`
on `ubuntu-latest` -- never on the production host. On push to `main` (or an
explicit `workflow_dispatch` with a full commit SHA), it:

1. Checks out the exact target commit (identity-proofed the same way as the
   other workflows in this repo).
2. `npm ci && npm run build` in `admin-h5/`.
3. Stages `index.html` + `assets/` + a `release.json` (`{"sha", "built_at",
   "builder": "github-actions"}`, no secrets) at the archive root -- no
   nested `dist/` layer.
4. Packages `admin-h5-dist-<FULL_SHA>.tar.gz` + `admin-h5-dist-<FULL_SHA>.tar.gz.sha256`
   (`sha256sum <archive> > <archive>.sha256`, directly `sha256sum -c`-able).
5. Publishes both as assets on a GitHub Release tagged `admin-h5-<FULL_SHA>`
   (title `admin-h5 <FULL_SHA>`, prerelease). If a release for that tag
   already exists: both assets must actually be present (an incomplete
   existing release fails closed rather than being silently rebuilt over),
   the remote pair's own checksum is re-verified, its archive entries are
   inspected the same way as [Artifact safety gates](#artifact-safety-gates)
   below, and the extracted payload must be byte-identical to this build's
   own output (`release.json`'s `sha` matches, `index.html` matches via
   `cmp`, `assets/` matches via `diff -qr` -- `built_at` is excluded from
   the comparison, since it legitimately differs between a rebuild and
   what's already published). Any mismatch stops the workflow --
   **never silently overwritten, never `--clobber`'d** -- a same-SHA content
   difference needs a human, not an automatic fix.

This is split across two jobs, not one: `build` (all events, `permissions:
contents: read`) does the actual `npm ci && npm run build` and packaging;
`publish` (`needs: build`, `if: github.event_name != 'pull_request'`,
`permissions: contents: write`) never builds anything itself -- it only
downloads the exact artifact `build` already produced (via a workflow
artifact, which is job-to-job transport only, never the production runtime
transport) and publishes/reuses it. Untrusted PR candidate code runs
`npm ci`/`npm run build` only inside the read-only `build` job; nothing
that ever executes PR code holds `contents: write`. On a **pull request**,
`build` still runs (so packaging itself is exercised before merge) but
`publish` never does -- an unmerged PR never gets `contents: write`
release-publish behavior at all. Only `push` to `main` or an explicit
`workflow_dispatch` (with a real target SHA) reaches the `publish` job.

**GitHub Release = audit/backup/immutable-build-evidence, not the production
transport.** Production evidence showed a direct `github.com/.../releases/
download` fetch from mainland China running at ~4-10KB/s and timing out --
`PRODUCTION_GITHUB_RELEASE_DIRECT_DOWNLOAD=FORBIDDEN`. The Release still
gets published on every push/dispatch (a durable, human-browsable record of
exactly what was built for a given SHA), but `scripts/deploy-production.sh`
never fetches from it. See [Artifact transport](#artifact-transport-tencent-cos)
for what production actually downloads from.

After the GitHub Release step, the same `publish` job (still never PR,
still `permissions: contents: write` for the Release call only) also:

6. Installs `cos-python-sdk-v5==1.9.30` -- pinned to the exact same version
   `saas-base/requirements.txt` already freezes, so there is only one
   version of this SDK in play anywhere in this repo. (This does **not**
   import or reuse `saas-base/app/core/cos.py` -- that module is a
   different thing, for a different purpose, with its own env var names
   and its own bucket-wide access, and is untouched by this tooling.)
7. Runs `scripts/publish-admin-artifact-cos.py` (standalone, no business
   imports, no production `.env` dependency -- see
   [Artifact transport](#artifact-transport-tencent-cos)) to upload the
   archive + checksum to Tencent COS, or verify-and-reuse an existing
   identical object.
8. Downloads both files back from the **public** COS base URL with `curl`
   and re-runs `sha256sum -c` against them -- proving the public runtime
   path actually serves what was just uploaded (uploading successfully via
   the COS API is not the same claim as "production's HTTP GET will work").

## Artifact transport (Tencent COS)

**Production never needs a COS secret.** Downloading a public HTTPS object
requires no credential; only *publishing* to COS (the GitHub Actions
`publish` job) needs `DEPLOY_COS_SECRET_ID`/`DEPLOY_COS_SECRET_KEY`, and
those live only as GitHub Actions Secrets, never on the production host,
never in this repo, never logged.

**Object layout** -- frozen prefix, one immutable directory per SHA:

```
deploy-artifacts/admin-h5/
  admin-h5-<FULL_SHA>/
    admin-h5-dist-<FULL_SHA>.tar.gz
    admin-h5-dist-<FULL_SHA>.tar.gz.sha256
```

Same URL shape `deploy-production.sh` always expected
(`<base>/admin-h5-<SHA>/admin-h5-dist-<SHA>.tar.gz`) -- only the base
changed, from a hardcoded GitHub Release URL to a configured COS base.

**`scripts/publish-admin-artifact-cos.py`** (GitHub Actions side, single
responsibility, no business-module imports): before uploading, it
`head_object`s both the archive and checksum keys for this SHA. If neither
exists, it uploads both (`Content-Type: application/gzip` /
`text/plain; charset=utf-8`, `Cache-Control: public,max-age=31536000,immutable`
-- the path is SHA-addressed and therefore genuinely immutable). If both
already exist, it downloads them back and requires the archive's sha256
*and* the checksum file's exact bytes to match this build's own output
before treating it as a safe no-op reuse. Any other combination (only one
of the pair present, or present-but-different) is
`BLOCKED_EXISTING_COS_ARTIFACT_MISMATCH` / half-published incompleteness --
never a silent overwrite, never `delete` + rewrite.

**Production-side config** -- `scripts/deploy-production.sh` resolves
`ARTIFACT_BASE_URL` from the process environment first, then a *single key*
parsed out of `$DEPLOY_CONFIG_FILE` (default `/etc/xiao-deploy.env`) --
never `source`d as a script, just that one `ARTIFACT_BASE_URL=` line. If
admin-h5 changed this deploy and neither source provides a value, the
deploy stops (`BLOCKED_ARTIFACT_TRANSPORT_NOT_CONFIGURED`) before the git
pull, before any download, before the backend restart, before touching
`current`. There is **no automatic fallback to GitHub** if COS is
misconfigured or unreachable -- production already proved that link
unreliable; silently falling back to it would just reintroduce the exact
transport this phase exists to remove. One-time setup on the server:

```
# /etc/xiao-deploy.env
ARTIFACT_BASE_URL=<public COS base>/deploy-artifacts/admin-h5
```

That's the only line this file needs. Do not put the real bucket name,
region, or any `COS_SECRET_*` value in this doc, in the repo, or in this
file -- the production host only ever performs a plain, unauthenticated
`curl` GET.

## Nginx contract

`saas.zhangbaiyang.com.conf`'s `root` must point at the stable `current`
symlink, not at any specific release and not at the old `dist/`:

```nginx
root /www/wwwroot/admin-h5/current;
```

This line changes exactly once (see "First migration"); after that, nginx
config is never touched by routine deploys -- only the `current` symlink
target changes, which nginx follows on every request without a reload.

## Rollback

**Frontend only, no rebuild, no git checkout, seconds not minutes:**

```bash
cd /www/wwwroot/xiao
ls -1t /www/wwwroot/admin-h5/releases   # see what's available
./scripts/rollback-admin-h5.sh <release-sha>
```

This only re-points the `current` symlink to an already-built, already-
verified release directory. It refuses to switch to a release whose
`index.html` is missing (`BLOCKED_UNKNOWN_RELEASE`), and if the post-switch
HTTP verification fails it automatically restores whatever `current` pointed
to before the rollback attempt.

**Backend rollback** is not automated by this tooling (deliberately -- it's
a `git checkout <known-good-sha>` + `systemctl restart` on the server,
following the existing recipe in `CLAUDE.md`). Decide code-only vs. code+DB
rollback based on whether the range being rolled back includes a migration.

## Release retention

`deploy-production.sh` keeps `current`'s release plus at least 3 more of the
most recently created releases; older ones are pruned automatically after a
successful deploy. It never deletes the release `current` points to.

## Migration releases

**Never automatic, and there is no auto-resume.** If `deploy-production.sh`
detects a change under `saas-base/alembic/versions/**` between `BEFORE_SHA`
(current HEAD) and `TARGET_SHA` (fetched `origin/main`), it stops
**before checking anything out** -- HEAD is provably still `BEFORE_SHA` when
this happens -- and prints `MIGRATION_REQUIRED_MANUAL_REVIEW`.

A migration release is the one case that isn't "one command." Do this by hand:

```bash
cd /www/wwwroot/xiao

PRE_MIGRATION_SHA=$(git rev-parse HEAD)
git fetch origin
TARGET_SHA=$(git rev-parse origin/main)

# 1. Working tree must be clean (same check the script itself makes).
git status --porcelain

# 2. Review the actual migration(s) before touching anything.
git diff "$PRE_MIGRATION_SHA" "$TARGET_SHA" -- saas-base/alembic/versions/

# 3. Only after reviewing: pull, then apply.
git checkout main
git pull --ff-only origin main

cd saas-base
source venv/bin/activate
alembic upgrade head
cd ..

# 4. Resume the deploy. BEFORE_SHA now already equals TARGET_SHA, so the
#    script's own diff would see "nothing changed" -- --force-backend (and
#    --force-admin, if this same release also touches admin-h5) is what
#    actually gets the already-pulled code deployed:
./scripts/deploy-production.sh --force-backend
# or, if admin-h5 also changed in this release:
./scripts/deploy-production.sh --force-backend --force-admin
```

**Do not expect a bare re-run of `deploy-production.sh` (no flags) to pick
this up on its own.** Once you've pulled by hand, `BEFORE_SHA == TARGET_SHA`
as far as the script can tell, so its own admin/backend change detection is
a no-op -- the `--force-*` flags are what make the already-checked-out code
actually get built/restarted.

## Dry run

To see what a deploy *would* do without touching git, disk, or any running
service:

```bash
./scripts/deploy-production.sh --dry-run
```

This only runs `git fetch` + read-only diffs; it never checks out,
downloads, releases, switches, or restarts anything.

## Artifact safety gates

Every admin-h5 deploy that has to download a fresh artifact (i.e. no
already-valid `releases/<sha>` exists yet) passes through, in order:

1. **`ADMIN_ARTIFACT_NOT_READY`** -- the archive or checksum file 404s (the
   `admin-h5-release` workflow for this SHA hasn't finished publishing yet).
   Stops before touching the backend or `current`; just re-run once it's up.
2. **`BLOCKED_ADMIN_ARTIFACT_CHECKSUM`** -- `sha256sum -c` against the
   downloaded `.sha256` file fails.
3. **`BLOCKED_UNSAFE_ADMIN_ARTIFACT`** -- the archive contains an absolute
   path, a genuine `..` path component (checked per path component, so a
   legitimate filename like `app..js` is fine), or any entry that isn't a
   plain regular file or directory -- symlink, hardlink, device, fifo,
   socket. Never extracted. Checked via Python's `tarfile` module (not
   `tar -tvzf` text parsing, which can't reliably tell a hardlink from a
   regular file) -- production already requires Python for `saas-base`, so
   this adds no new host dependency.
4. **`BLOCKED_INVALID_ADMIN_ARTIFACT`** -- extracted fine, but missing
   `index.html`/`assets/`/`release.json`, or `release.json`'s `sha` doesn't
   match the commit being deployed.

Any of these leaves `current` untouched and the backend untouched (they all
happen before Phase C/D/E backend deploy even starts).

## Bootstrap mode (first cutover only)

`--bootstrap-admin` (implies `--force-admin`) downloads, verifies, releases,
and points `current` at the new release exactly like routine mode -- never
builds -- but does **not** treat a request to the live production URL as
proof of anything, because at first-cutover time nginx is still serving the
legacy `dist/`, so that request would just prove the *old* site still
works. Instead it reports:

```
ADMIN_BOOTSTRAP_READY=YES
ADMIN_HTTP_VERIFICATION=PENDING_NGINX_CUTOVER
```

The real HTTP gate (the one that can trigger an automatic rollback) is the
routine, non-bootstrap path used on every deploy *after* the nginx cutover
below has happened once. `deploy-production.sh` never edits nginx config
itself, in bootstrap mode or otherwise.

## First migration (one-time, no-downtime cutover)

The first time this tooling runs against a server still serving from the
legacy `/www/wwwroot/admin-h5/dist` layout:

1. The old `dist/` keeps serving traffic throughout -- nothing is torn down
   up front.
2. First, ensure `/etc/xiao-deploy.env` exists with `ARTIFACT_BASE_URL=<public
   COS base>/deploy-artifacts/admin-h5` (see [Artifact transport](#artifact-transport-tencent-cos))
   -- without it this step stops immediately with
   `BLOCKED_ARTIFACT_TRANSPORT_NOT_CONFIGURED`. Then run
   `deploy-production.sh --bootstrap-admin` (and `--force-backend` if the
   backend also needs a first sync) to download the COS-published artifact
   for the current main SHA and produce the first `releases/<sha>` +
   `current` symlink, side by side with the still-live `dist/`. This
   reports `ADMIN_HTTP_VERIFICATION=PENDING_NGINX_CUTOVER`, not a
   verified-live claim -- that's expected. If it instead reports
   `ADMIN_ARTIFACT_NOT_READY`, the `admin-h5-release` workflow for that SHA
   hasn't finished publishing to COS yet -- wait for it, don't build locally.
3. Update `saas.zhangbaiyang.com.conf`'s `root` from
   `/www/wwwroot/admin-h5/dist` to `/www/wwwroot/admin-h5/current`.
4. `nginx -t` -- only proceed if it passes.
5. `systemctl reload nginx` (reload, never restart -- no connection drop).
6. Verify `https://saas.zhangbaiyang.com/` over HTTP and confirm the served
   HTML references `/assets/`. This is the first point at which the site is
   actually proven to be serving the new release.
7. Only after all of the above succeed: move the old
   `/www/wwwroot/admin-h5/src`, `scripts/`, `node_modules/`, `package.json`,
   `package-lock.json` aside to `/www/wwwroot/admin-h5/legacy-source.<timestamp>`
   (never delete outright -- keep it around for a while as a safety net).

After this one-time cutover, `/www/wwwroot/admin-h5` contains only
`current`, `releases/`, and the temporary `legacy-source.<timestamp>/`, and
every subsequent deploy runs in routine (non-bootstrap) mode with the real
HTTP verification gate active.

## Backend dependency changes

`deploy-production.sh` only runs `pip install -r requirements.txt` when
`saas-base/requirements.txt` actually changed between the before/after
commit -- not on every deploy.

## GitHub Actions

Three separate things, easy to conflate:

1. **Building & publishing the admin-h5 artifact** -- `.github/workflows/
   admin-h5-release.yml`. See [Artifact build & publish](#artifact-build--publish-github-actions)
   above. The only place `npm run build` ever runs, period. Its `publish`
   job (never PR, never holding anything but its own scoped `contents:
   write`) needs these as **GitHub Actions Secrets** (repo or environment
   settings, never committed, never printed in a workflow log):
   `DEPLOY_COS_SECRET_ID`, `DEPLOY_COS_SECRET_KEY`, `DEPLOY_COS_REGION`,
   `DEPLOY_COS_BUCKET`, `DEPLOY_COS_BASE_URL`. A dedicated Tencent CAM
   sub-account scoped to only `deploy-artifacts/admin-h5/*` put/get/head on
   the target bucket is the recommended credential shape -- creating or
   printing real values is out of scope for any of this tooling itself. The
   `build` job (all events, including PR) never sees these -- see
   [Artifact transport](#artifact-transport-tencent-cos).
2. **Certifying the deployment tooling itself** -- `.github/workflows/
   deployment-tooling-ci.yml` runs on every push/PR that touches
   `scripts/deploy-production.sh`, `scripts/rollback-admin-h5.sh`,
   `scripts/test-deployment-tooling.sh`, `scripts/publish-admin-artifact-cos.py`,
   this doc, `Makefile`, or `admin-h5-release.yml` itself. It's the
   authority for the atomic symlink-swap, migration-fail-closed,
   artifact-checksum, archive-safety, PR-secret-isolation, and
   backend-before-admin-switch contracts -- **a Windows/MSYS dev machine
   cannot certify this tooling**: `ln -s`/`mv -T` symlink-swap semantics
   there differ from real GNU coreutils/Linux (confirmed empirically --
   running `scripts/test-deployment-tooling.sh` on Windows/Git-Bash fails
   exactly the symlink-dependent cases and passes everything else, archive/
   checksum/COS-mock logic included). Only a green run on this workflow's
   `ubuntu-latest` runner counts.
3. **GitHub -> production SSH auto-deploy** -- still NOT in scope. There is
   no established trust relationship yet between GitHub Actions and the
   production host (no SSH key, no GitHub Environment approval gate), so
   automatic `push to main -> production` is a deliberately separate, later
   piece of work. For now, running `scripts/deploy-production.sh` against
   real production is always a manual, server-side invocation by someone
   with access.
