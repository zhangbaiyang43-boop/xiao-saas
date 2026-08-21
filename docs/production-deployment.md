# Production Deployment

**Single command, single Git authority -- target contract.** `/www/wwwroot/xiao`
is meant to become the *only* source-of-truth checkout for both `saas-base`
and `admin-h5` in production, retiring the historical second hand-maintained
source tree under `/www/wwwroot/admin-h5/{src,scripts,node_modules,...}`.

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
4. Only now: fast-forwards `main` (`git pull --ff-only`) -- never
   force-pulls, never rebases, never resets.
5. If `admin-h5/**` changed: builds it and copies the build into an
   immutable, SHA-named release directory -- but does **not** switch
   `current` yet.
6. If `saas-base/**` changed: restarts `saas-base.service` and verifies
   `/health` returns healthy. **A failure here stops the whole deploy before
   the admin-h5 release prepared in step 5 is ever switched live** -- you
   never end up with a new frontend talking to a broken backend, or a broken
   frontend at all; `current` simply stays exactly where it was.
7. Only once the backend (if it was part of this deploy) is confirmed
   healthy: atomically switches the `current` symlink -- verified with a
   real HTTP request before committing to the switch (routine mode; see
   [Bootstrap mode](#bootstrap-mode-first-cutover-only) for the one-time
   exception), with an automatic rollback to the previous release if
   verification fails.

## What this replaces

**Do not, ever again:**

- `cp -r dist ...` by hand into `/www/wwwroot/admin-h5`
- Edit source files directly under `/www/wwwroot/admin-h5/src`
- Run `npm run build` inside the old deploy directory
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
├── admin-h5/                 # frontend source -- built here, never edited elsewhere
├── saas-base/                # backend source, served directly by saas-base.service
└── scripts/
    ├── deploy-production.sh
    ├── rollback-admin-h5.sh
    └── test-deployment-tooling.sh   # Linux integration contract, CI-only
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
  "built_at": "<UTC ISO8601 timestamp>"
}
```

To find out which commit is currently live:

```bash
cat /www/wwwroot/admin-h5/current/release.json
```

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

This only runs `git fetch` + read-only diffs; it never checks out, builds,
releases, switches, or restarts anything.

## Bootstrap mode (first cutover only)

`--bootstrap-admin` (implies `--force-admin`) builds, releases, and points
`current` at the new release exactly like routine mode -- but does **not**
treat a request to the live production URL as proof of anything, because at
first-cutover time nginx is still serving the legacy `dist/`, so that request
would just prove the *old* site still works. Instead it reports:

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
2. Run `deploy-production.sh --bootstrap-admin` (and `--force-backend` if the
   backend also needs a first sync) to build from `/www/wwwroot/xiao/admin-h5`
   and produce the first `releases/<sha>` + `current` symlink, side by side
   with the still-live `dist/`. This reports `ADMIN_HTTP_VERIFICATION=
   PENDING_NGINX_CUTOVER`, not a verified-live claim -- that's expected.
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

Two separate things, easy to conflate:

1. **Certifying the deployment tooling itself** -- `.github/workflows/
   deployment-tooling-ci.yml` runs on every push/PR that touches
   `scripts/deploy-production.sh`, `scripts/rollback-admin-h5.sh`,
   `scripts/test-deployment-tooling.sh`, this doc, or `Makefile`. It's the
   authority for the atomic symlink-swap, migration-fail-closed, and
   backend-before-admin-switch contracts -- **a Windows/MSYS dev machine
   cannot certify this tooling**: `ln -s`/`mv -T` symlink-swap semantics
   there differ from real GNU coreutils/Linux (confirmed empirically --
   running `scripts/test-deployment-tooling.sh` on Windows/Git-Bash fails
   exactly the symlink-dependent cases and passes everything else). Only a
   green run on this workflow's `ubuntu-latest` runner counts.
2. **GitHub -> production SSH auto-deploy** -- still NOT in scope. There is
   no established trust relationship yet between GitHub Actions and the
   production host (no SSH key, no GitHub Environment approval gate), so
   automatic `push to main -> production` is a deliberately separate, later
   piece of work. For now, running `scripts/deploy-production.sh` against
   real production is always a manual, server-side invocation by someone
   with access.
