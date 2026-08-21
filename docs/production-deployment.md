# Production Deployment

**Single command, single Git authority.** As of this document, `/www/wwwroot/xiao`
is the *only* source-of-truth checkout for both `saas-base` and `admin-h5` in
production. There is no second hand-maintained source tree.

## The one command

```bash
cd /www/wwwroot/xiao
./scripts/deploy-production.sh
```

That's it. It:

1. Refuses to run if the production checkout has uncommitted changes
   (`BLOCKED_DIRTY_PRODUCTION_TREE`) -- never auto-resets/cleans/stashes.
2. Fetches `origin` and fast-forwards `main` only (`git pull --ff-only`) --
   never force-pulls, never rebases, never resets.
3. Diffs the before/after commit to figure out what actually changed
   (`admin-h5/**`, `saas-base/**`, `saas-base/alembic/versions/**`).
4. **Stops before touching anything** if an Alembic migration file changed --
   migrations are reviewed and applied by hand, never automatically. See
   [Migrations](#migrations) below.
5. If `admin-h5/**` changed: builds it, copies the build into an immutable,
   SHA-named release directory, and atomically switches the `current` symlink
   -- verified with a real HTTP request before committing to the switch, with
   an automatic rollback to the previous release if verification fails.
6. If `saas-base/**` changed: restarts `saas-base.service` and verifies
   `/health` returns healthy before declaring success.

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
    └── rollback-admin-h5.sh
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

## Migrations

**Never automatic.** If `deploy-production.sh` detects a change under
`saas-base/alembic/versions/**` between the before/after commit, it stops
immediately, before building anything or restarting the backend, and prints
`MIGRATION_REQUIRED_MANUAL_REVIEW`. Review the migration, run
`alembic upgrade head` deliberately (see `CLAUDE.md`'s standard recipe), and
only then re-run `deploy-production.sh` -- it will see there's nothing new
to pull and proceed straight to the (already-applied) code deploy.

## Dry run

To see what a deploy *would* do without touching git, disk, or any running
service:

```bash
./scripts/deploy-production.sh --dry-run
```

This only runs `git fetch` + read-only diffs; it never checks out, builds,
releases, switches, or restarts anything.

## First migration (one-time, no-downtime cutover)

The first time this tooling runs against a server still serving from the
legacy `/www/wwwroot/admin-h5/dist` layout:

1. The old `dist/` keeps serving traffic throughout -- nothing is torn down
   up front.
2. Run `deploy-production.sh --force-admin` (and `--force-backend` if the
   backend also needs a first sync) to build from `/www/wwwroot/xiao/admin-h5`
   and produce the first `releases/<sha>` + `current` symlink, side by side
   with the still-live `dist/`.
3. Update `saas.zhangbaiyang.com.conf`'s `root` from
   `/www/wwwroot/admin-h5/dist` to `/www/wwwroot/admin-h5/current`.
4. `nginx -t` -- only proceed if it passes.
5. `systemctl reload nginx` (reload, never restart -- no connection drop).
6. Verify `https://saas.zhangbaiyang.com/` over HTTP and confirm the served
   HTML references `/assets/`.
7. Only after all of the above succeed: move the old
   `/www/wwwroot/admin-h5/src`, `scripts/`, `node_modules/`, `package.json`,
   `package-lock.json` aside to `/www/wwwroot/admin-h5/legacy-source.<timestamp>`
   (never delete outright -- keep it around for a while as a safety net).

After this one-time cutover, `/www/wwwroot/admin-h5` contains only
`current`, `releases/`, and the temporary `legacy-source.<timestamp>/`.

## Backend dependency changes

`deploy-production.sh` only runs `pip install -r requirements.txt` when
`saas-base/requirements.txt` actually changed between the before/after
commit -- not on every deploy.

## GitHub Actions

Not in scope for this phase. There is no established trust relationship yet
between GitHub Actions and the production host (no SSH key, no GitHub
Environment approval gate), so automatic `push to main -> production` is a
deliberately separate, later piece of work. For now, deployment is always a
manual, server-side invocation of `scripts/deploy-production.sh`.
