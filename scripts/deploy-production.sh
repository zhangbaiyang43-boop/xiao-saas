#!/usr/bin/env bash
#
# Single-authority production deploy: git main -> backend restart + admin-h5
# atomic release switch, SHA-tracked, fast-rollback-able.
#
# Usage:
#   ./scripts/deploy-production.sh [--dry-run] [--force-admin] [--force-backend] [--bootstrap-admin]
#
#   --dry-run         Report what would happen; never writes to git, disk, or
#                     any running service.
#   --force-admin     Build/release admin-h5 even if admin-h5/** didn't
#                     change between BEFORE_SHA and TARGET_SHA. Required when
#                     resuming a migration release (see docs/production-
#                     deployment.md) -- there is no automatic resume path.
#   --force-backend   Restart the backend even if saas-base/** didn't change
#                     between BEFORE_SHA and TARGET_SHA. Same manual-resume
#                     use case as --force-admin.
#   --bootstrap-admin One-time first-cutover mode: implies --force-admin,
#                     builds/releases/switches `current`, but does NOT treat
#                     a request to the live production URL as proof (nginx
#                     may still be serving the legacy dist/ at that point).
#                     See docs/production-deployment.md "First migration".
#
# Hard safety boundaries (see docs/production-deployment.md for the full
# contract this script implements):
#   - Refuses to run against a dirty production working tree.
#   - Only ever deploys origin/main, only via `git pull --ff-only` (never
#     reset --hard / clean -fd / force-pull).
#   - Change detection (admin/backend/migration/requirements/lockfile) is
#     computed BEFORE any checkout/pull, comparing BEFORE_SHA (current HEAD)
#     against TARGET_SHA (fetched origin/main) -- never against a state the
#     working tree has already been advanced to.
#   - Never runs an Alembic migration automatically -- if a migration file
#     changed, the script stops BEFORE checking anything out. HEAD is
#     provably unchanged when this happens; resuming afterwards is always a
#     deliberate, documented manual procedure, never an automatic re-run.
#   - Backend deploy (if any) happens and must succeed BEFORE the admin-h5
#     release is ever switched live -- a prepared-but-unswitched admin
#     release and a failed backend never coexist as "old frontend + broken
#     backend" or "new frontend + broken backend"; a backend failure leaves
#     `current` exactly where it was.
#   - Admin-h5 releases are immutable (built into a mktemp -d temp dir,
#     validated, then atomically renamed into place -- never rm -rf'ing an
#     existing/unknown path) and switched via `current` with an
#     ln -sfn + mv -Tf pair -- nginx never sees a missing `current`.
#   - A failed frontend HTTP verification (routine mode only, not bootstrap)
#     atomically restores the previous `current` target.
#   - An existing releases/<sha> directory is only ever reused if it passes
#     full validation (index.html + assets/ + release.json whose sha field
#     matches <sha>); otherwise the deploy stops rather than overwrite an
#     unknown directory.

set -Eeuo pipefail

# ---------------------------------------------------------------------------
# Identity (overridable via environment for testing; production defaults
# match docs/production-deployment.md).
# ---------------------------------------------------------------------------
: "${REPO:=/www/wwwroot/xiao}"
: "${ADMIN_SOURCE:=$REPO/admin-h5}"
: "${ADMIN_RELEASE_ROOT:=/www/wwwroot/admin-h5/releases}"
: "${ADMIN_CURRENT:=/www/wwwroot/admin-h5/current}"
: "${BACKEND_SERVICE:=saas-base.service}"
: "${BACKEND_HEALTH_URL:=http://127.0.0.1:9898/health}"
: "${PRODUCTION_URL:=https://saas.zhangbaiyang.com/}"
: "${RELEASE_KEEP_MIN:=4}" # current + at least 3 historical releases

DRY_RUN=0
FORCE_ADMIN=0
FORCE_BACKEND=0
BOOTSTRAP_ADMIN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --force-admin) FORCE_ADMIN=1 ;;
    --force-backend) FORCE_BACKEND=1 ;;
    --bootstrap-admin) BOOTSTRAP_ADMIN=1; FORCE_ADMIN=1 ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

log() { echo "[deploy] $*"; }

# Cleanup for exactly one in-flight temp release dir at a time -- never a
# blind rm -rf of anything this invocation didn't itself just mktemp -d.
CLEANUP_TMP=""
cleanup() {
  if [ -n "$CLEANUP_TMP" ] && [ -d "$CLEANUP_TMP" ]; then
    rm -rf "$CLEANUP_TMP"
  fi
}
trap cleanup EXIT

release_json_sha() {
  # Minimal, dependency-free extraction of the "sha" field from our own
  # release.json format -- no jq requirement on the production host.
  grep -o '"sha"[[:space:]]*:[[:space:]]*"[^"]*"' "$1" 2>/dev/null \
    | sed -E 's/.*:[[:space:]]*"([^"]*)"/\1/' \
    | head -n1
}

# ---------------------------------------------------------------------------
# 1. Identity + dirty-tree gate
# ---------------------------------------------------------------------------
cd "$REPO"

if [ -n "$(git status --porcelain)" ]; then
  echo "STATUS=BLOCKED_DIRTY_PRODUCTION_TREE"
  echo "The production checkout at $REPO has uncommitted changes. Refusing to" >&2
  echo "touch it automatically (no reset/clean/stash). Investigate and clean" >&2
  echo "up by hand, then re-run." >&2
  exit 1
fi

BEFORE_SHA="$(git rev-parse HEAD)"
log "BEFORE_SHA=$BEFORE_SHA"

git fetch origin
TARGET_SHA="$(git rev-parse origin/main)"
log "TARGET_SHA=$TARGET_SHA"

# ---------------------------------------------------------------------------
# 2. Change detection -- BEFORE any checkout/pull. Always against
#    BEFORE_SHA..TARGET_SHA, never against a state the working tree has
#    already been advanced to (that was the bug: computing this after the
#    pull meant a migration-blocked run had already moved HEAD forward).
# ---------------------------------------------------------------------------
ADMIN_CHANGED=0
BACKEND_CHANGED=0
MIGRATION_CHANGED=0
REQUIREMENTS_CHANGED=0
LOCKFILE_CHANGED=0

if [ "$BEFORE_SHA" != "$TARGET_SHA" ]; then
  if git diff --name-only "$BEFORE_SHA" "$TARGET_SHA" -- 'admin-h5/' | grep -q .; then ADMIN_CHANGED=1; fi
  if git diff --name-only "$BEFORE_SHA" "$TARGET_SHA" -- 'saas-base/' | grep -q .; then BACKEND_CHANGED=1; fi
  if git diff --name-only "$BEFORE_SHA" "$TARGET_SHA" -- 'saas-base/alembic/versions/' | grep -q .; then MIGRATION_CHANGED=1; fi
  if git diff --name-only "$BEFORE_SHA" "$TARGET_SHA" -- 'saas-base/requirements.txt' | grep -q .; then REQUIREMENTS_CHANGED=1; fi
  if git diff --name-only "$BEFORE_SHA" "$TARGET_SHA" -- 'admin-h5/package-lock.json' | grep -q .; then LOCKFILE_CHANGED=1; fi
fi

# Force flags never bypass the migration safety boundary -- only ever
# widen ADMIN_CHANGED/BACKEND_CHANGED (used to resume after a manual
# migration pull, where BEFORE_SHA==TARGET_SHA already and the diff above
# is a no-op).
[ "$FORCE_ADMIN" -eq 1 ] && ADMIN_CHANGED=1
[ "$FORCE_BACKEND" -eq 1 ] && BACKEND_CHANGED=1

log "ADMIN_CHANGED=$ADMIN_CHANGED BACKEND_CHANGED=$BACKEND_CHANGED MIGRATION_CHANGED=$MIGRATION_CHANGED"

if [ "$DRY_RUN" -eq 1 ]; then
  log "DRY_RUN=1 -- no git checkout/pull, no build, no release, no restart."
  log "Would deploy: $BEFORE_SHA -> $TARGET_SHA"
  if [ "$MIGRATION_CHANGED" -eq 1 ]; then
    log "Would STOP: MIGRATION_REQUIRED_MANUAL_REVIEW (alembic/versions changed) -- HEAD would remain $BEFORE_SHA"
  fi
  echo "STATUS=DRY_RUN_OK"
  exit 0
fi

# ---------------------------------------------------------------------------
# 3. Migration safety boundary -- checked BEFORE any checkout/pull. HEAD is
#    provably still BEFORE_SHA when this fires; there is no automatic
#    resume. See docs/production-deployment.md's manual migration release
#    procedure (git pull + alembic upgrade head by hand, then re-run this
#    script with --force-backend, and --force-admin if that release also
#    touches admin-h5).
# ---------------------------------------------------------------------------
if [ "$MIGRATION_CHANGED" -eq 1 ]; then
  CURRENT_HEAD_ON_BLOCK="$(git rev-parse HEAD)"
  echo "STATUS=MIGRATION_REQUIRED_MANUAL_REVIEW" >&2
  echo "saas-base/alembic/versions/** changed between $BEFORE_SHA and $TARGET_SHA." >&2
  echo "This script never runs 'alembic upgrade head' automatically, and never" >&2
  echo "checks out code ahead of a migration it hasn't applied yet." >&2
  echo "HEAD_UNCHANGED=$([ "$CURRENT_HEAD_ON_BLOCK" = "$BEFORE_SHA" ] && echo YES || echo NO) (HEAD=$CURRENT_HEAD_ON_BLOCK)" >&2
  echo "Follow the manual migration release procedure in docs/production-deployment.md" >&2
  echo "-- a bare re-run of this script will NOT automatically continue; it requires" >&2
  echo "--force-backend (and --force-admin if applicable) after the manual pull + migration." >&2
  if [ "$CURRENT_HEAD_ON_BLOCK" != "$BEFORE_SHA" ]; then
    # Defensive only -- should be unreachable given the ordering above.
    echo "INTERNAL ERROR: HEAD moved before the migration gate could stop it." >&2
    exit 3
  fi
  exit 1
fi

# ---------------------------------------------------------------------------
# 4. Git update -- main only, fast-forward only. Only reached once we know
#    there is no unreviewed migration in this range.
# ---------------------------------------------------------------------------
git checkout main
git pull --ff-only origin main

AFTER_SHA="$(git rev-parse HEAD)"
log "AFTER_SHA=$AFTER_SHA"

if [ "$AFTER_SHA" != "$TARGET_SHA" ]; then
  echo "STATUS=BLOCKED_WRONG_PRODUCTION_SHA" >&2
  echo "Post-pull HEAD ($AFTER_SHA) does not match fetched origin/main ($TARGET_SHA)." >&2
  exit 1
fi

ADMIN_STATUS="SKIPPED"
BACKEND_STATUS="SKIPPED"

# ---------------------------------------------------------------------------
# 5. Phase A + B -- build admin-h5 and prepare an immutable release, but do
#    NOT switch `current` yet. A prepared-but-unswitched release is the
#    whole point: if the backend deploy below fails, this release simply
#    never goes live, and `current` is never touched.
# ---------------------------------------------------------------------------
RELEASE_DIR="$ADMIN_RELEASE_ROOT/$AFTER_SHA"

if [ "$ADMIN_CHANGED" -eq 1 ]; then
  (
    cd "$ADMIN_SOURCE"

    if [ ! -d node_modules ] || [ "$LOCKFILE_CHANGED" -eq 1 ]; then
      log "Installing admin-h5 dependencies (node_modules missing or lockfile changed)"
      npm ci --no-audit --no-fund
    else
      log "Skipping npm ci (node_modules present, lockfile unchanged)"
    fi

    # GitHub's admin-h5 CI is the certification authority for this code --
    # do not re-run its checks here, just build what was already certified.
    log "Building admin-h5"
    npm run build

    test -s dist/index.html
    test -d dist/assets
  )

  if [ -d "$RELEASE_DIR" ]; then
    log "Release $RELEASE_DIR already exists -- validating before reuse"
    if [ -s "$RELEASE_DIR/index.html" ] && [ -d "$RELEASE_DIR/assets" ] \
       && [ -s "$RELEASE_DIR/release.json" ] \
       && [ "$(release_json_sha "$RELEASE_DIR/release.json")" = "$AFTER_SHA" ]; then
      log "Existing release validated (index.html + assets/ + release.json.sha == $AFTER_SHA)"
    else
      echo "STATUS=BLOCKED_INVALID_EXISTING_RELEASE" >&2
      echo "$RELEASE_DIR exists but failed validation (missing index.html/assets/" >&2
      echo "release.json, or release.json's sha does not match $AFTER_SHA). Refusing" >&2
      echo "to overwrite an unknown existing release directory." >&2
      exit 1
    fi
  else
    mkdir -p "$ADMIN_RELEASE_ROOT"
    RELEASE_TMP="$(mktemp -d "$ADMIN_RELEASE_ROOT/.tmp-${AFTER_SHA}.XXXXXX")"
    CLEANUP_TMP="$RELEASE_TMP"
    cp -a "$ADMIN_SOURCE/dist/." "$RELEASE_TMP/"
    cat > "$RELEASE_TMP/release.json" <<EOF
{
  "sha": "$AFTER_SHA",
  "built_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
    chown -R www:www "$RELEASE_TMP" 2>/dev/null || log "chown to www:www failed/skipped (non-root or user missing) -- verify ownership manually"
    test -s "$RELEASE_TMP/index.html"
    test -d "$RELEASE_TMP/assets"
    mv -T "$RELEASE_TMP" "$RELEASE_DIR"
    CLEANUP_TMP="" # ownership of that path transferred to RELEASE_DIR; nothing left to clean up
  fi
  ADMIN_STATUS="PREPARED"
  log "ADMIN_STATUS=PREPARED (release=$RELEASE_DIR, current not switched yet)"
fi

# ---------------------------------------------------------------------------
# 6. Phase C + D + E -- backend dependency prep, restart, health gate.
#    Must succeed before admin-h5 is ever switched live. Exiting here (on
#    failure) leaves `current` exactly where it was before this run.
# ---------------------------------------------------------------------------
if [ "$BACKEND_CHANGED" -eq 1 ]; then
  if [ "$REQUIREMENTS_CHANGED" -eq 1 ]; then
    log "requirements.txt changed -- installing dependencies"
    (cd "$REPO/saas-base" && source venv/bin/activate && pip install -r requirements.txt)
  else
    log "requirements.txt unchanged -- skipping pip install"
  fi

  log "Restarting $BACKEND_SERVICE"
  systemctl restart "$BACKEND_SERVICE"

  if systemctl is-active --quiet "$BACKEND_SERVICE"; then
    HEALTH_BODY="$(curl -fsS "$BACKEND_HEALTH_URL" || true)"
    if grep -q 'healthy' <<<"$HEALTH_BODY"; then
      BACKEND_STATUS="OK"
    else
      BACKEND_STATUS="HEALTH_CHECK_FAILED"
    fi
  else
    BACKEND_STATUS="RESTART_FAILED"
  fi

  if [ "$BACKEND_STATUS" != "OK" ]; then
    echo "STATUS=BACKEND_DEPLOY_FAILED" >&2
    echo "ADMIN_CURRENT_UNCHANGED=YES (release${ADMIN_CHANGED:+ $RELEASE_DIR} prepared but never switched live)" >&2
    journalctl -u "$BACKEND_SERVICE" -n 40 --no-pager >&2 || true
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# 7. Phase F + G -- atomic admin-h5 switch + verification. Only reached once
#    the backend (if it was part of this deploy) is confirmed healthy.
# ---------------------------------------------------------------------------
if [ "$ADMIN_CHANGED" -eq 1 ]; then
  PREVIOUS_ADMIN_TARGET=""
  if [ -e "$ADMIN_CURRENT" ]; then
    PREVIOUS_ADMIN_TARGET="$(readlink -f "$ADMIN_CURRENT" || true)"
  fi
  log "PREVIOUS_ADMIN_TARGET=${PREVIOUS_ADMIN_TARGET:-<none>}"

  ln -sfn "$RELEASE_DIR" "$ADMIN_CURRENT.new"
  mv -Tf "$ADMIN_CURRENT.new" "$ADMIN_CURRENT"

  if [ "$BOOTSTRAP_ADMIN" -eq 1 ]; then
    # First-cutover mode: nginx may still be serving the legacy dist/, so a
    # request to PRODUCTION_URL proves nothing about this release. Verify
    # only that `current` itself is a real, servable release; the real HTTP
    # gate is the routine (non-bootstrap) path used on every deploy after
    # the one-time nginx cutover documented in docs/production-deployment.md.
    if test -s "$ADMIN_CURRENT/index.html"; then
      ADMIN_STATUS="SWITCHED_BOOTSTRAP"
      echo "ADMIN_BOOTSTRAP_READY=YES"
      echo "ADMIN_HTTP_VERIFICATION=PENDING_NGINX_CUTOVER"
      log "current -> $RELEASE_DIR. Now do the one-time nginx cutover by hand (see docs)."
    else
      echo "STATUS=BOOTSTRAP_FAILED" >&2
      exit 1
    fi
  else
    FRONTEND_OK=1
    test -s "$ADMIN_CURRENT/index.html" || FRONTEND_OK=0
    if [ "$FRONTEND_OK" -eq 1 ]; then
      HTTP_BODY="$(curl -fsS "$PRODUCTION_URL" || true)"
      if [ -z "$HTTP_BODY" ] || ! grep -q '/assets/' <<<"$HTTP_BODY"; then
        FRONTEND_OK=0
      fi
    fi

    if [ "$FRONTEND_OK" -eq 1 ]; then
      ADMIN_STATUS="SWITCHED"
      log "Frontend verification passed: $PRODUCTION_URL -> $RELEASE_DIR"
    else
      log "Frontend verification FAILED -- rolling back current atomically"
      if [ -n "$PREVIOUS_ADMIN_TARGET" ]; then
        ln -sfn "$PREVIOUS_ADMIN_TARGET" "$ADMIN_CURRENT.new"
        mv -Tf "$ADMIN_CURRENT.new" "$ADMIN_CURRENT"
        echo "ADMIN_ROLLBACK=YES"
      else
        echo "ADMIN_ROLLBACK=YES (no previous target existed -- current left pointing at the new, unverified release; investigate manually)" >&2
      fi
      ADMIN_STATUS="FAILED_ROLLED_BACK"
    fi
  fi

  # -------------------------------------------------------------------
  # Release retention: keep `current` + at least RELEASE_KEEP_MIN-1 more.
  # -------------------------------------------------------------------
  if { [ "$ADMIN_STATUS" = "SWITCHED" ] || [ "$ADMIN_STATUS" = "SWITCHED_BOOTSTRAP" ]; } && [ -d "$ADMIN_RELEASE_ROOT" ]; then
    CURRENT_TARGET_NAME="$(basename "$(readlink -f "$ADMIN_CURRENT")")"
    # shellcheck disable=SC2012
    mapfile -t ALL_RELEASES < <(ls -1t "$ADMIN_RELEASE_ROOT" 2>/dev/null || true)
    KEEP_COUNT=0
    for name in "${ALL_RELEASES[@]}"; do
      KEEP_COUNT=$((KEEP_COUNT + 1))
      if [ "$KEEP_COUNT" -le "$RELEASE_KEEP_MIN" ] || [ "$name" = "$CURRENT_TARGET_NAME" ]; then
        continue
      fi
      log "Pruning old release: $name"
      rm -rf "${ADMIN_RELEASE_ROOT:?}/$name"
    done
  fi
fi

log "ADMIN_STATUS=$ADMIN_STATUS BACKEND_STATUS=$BACKEND_STATUS"
echo "DEPLOYED_SHA=$AFTER_SHA"

if [ "$ADMIN_STATUS" = "FAILED_ROLLED_BACK" ]; then
  echo "STATUS=ADMIN_DEPLOY_FAILED_ROLLED_BACK" >&2
  exit 1
fi

echo "STATUS=DEPLOY_OK"
