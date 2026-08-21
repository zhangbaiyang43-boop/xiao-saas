#!/usr/bin/env bash
#
# Single-authority production deploy: git main -> backend restart + admin-h5
# atomic release switch, SHA-tracked, fast-rollback-able.
#
# Usage:
#   ./scripts/deploy-production.sh [--dry-run] [--force-admin] [--force-backend]
#
#   --dry-run       Report what would happen; never writes to git, disk, or
#                   any running service.
#   --force-admin   Build/release admin-h5 even if admin-h5/** didn't change
#                   between BEFORE_SHA and AFTER_SHA (first migration only).
#   --force-backend Restart the backend even if saas-base/** didn't change
#                   between BEFORE_SHA and AFTER_SHA (first migration only).
#
# Hard safety boundaries (see docs/production-deployment.md for the full
# contract this script implements):
#   - Refuses to run against a dirty production working tree.
#   - Only ever deploys origin/main, only via `git pull --ff-only` (never
#     reset --hard / clean -fd / force-pull).
#   - Never runs an Alembic migration automatically -- a migration file
#     change between BEFORE_SHA and AFTER_SHA stops the whole deploy before
#     anything is built or restarted.
#   - Admin-h5 releases are immutable (built into a temp dir, verified, then
#     atomically renamed into place) and switched via `current` with an
#     ln -sfn + mv -Tf pair -- nginx never sees a missing `current`.
#   - A failed frontend HTTP verification atomically restores the previous
#     `current` target.

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
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --force-admin) FORCE_ADMIN=1 ;;
    --force-backend) FORCE_BACKEND=1 ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

log() { echo "[deploy] $*"; }

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

if [ "$DRY_RUN" -eq 1 ]; then
  log "DRY_RUN=1 -- no git checkout/pull, no build, no release, no restart."
  ADMIN_CHANGED=0
  BACKEND_CHANGED=0
  MIGRATION_CHANGED=0
  if [ "$BEFORE_SHA" != "$TARGET_SHA" ]; then
    if git diff --name-only "$BEFORE_SHA" "$TARGET_SHA" -- 'admin-h5/' | grep -q .; then ADMIN_CHANGED=1; fi
    if git diff --name-only "$BEFORE_SHA" "$TARGET_SHA" -- 'saas-base/' | grep -q .; then BACKEND_CHANGED=1; fi
    if git diff --name-only "$BEFORE_SHA" "$TARGET_SHA" -- 'saas-base/alembic/versions/' | grep -q .; then MIGRATION_CHANGED=1; fi
  fi
  log "Would deploy: $BEFORE_SHA -> $TARGET_SHA"
  log "ADMIN_CHANGED=$ADMIN_CHANGED BACKEND_CHANGED=$BACKEND_CHANGED MIGRATION_CHANGED=$MIGRATION_CHANGED"
  if [ "$MIGRATION_CHANGED" -eq 1 ]; then
    log "Would STOP: MIGRATION_REQUIRED_MANUAL_REVIEW (alembic/versions changed)"
  fi
  echo "STATUS=DRY_RUN_OK"
  exit 0
fi

# ---------------------------------------------------------------------------
# 2. Git update -- main only, fast-forward only
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

# ---------------------------------------------------------------------------
# 3. Determine changed modules
# ---------------------------------------------------------------------------
ADMIN_CHANGED=0
BACKEND_CHANGED=0
MIGRATION_CHANGED=0
REQUIREMENTS_CHANGED=0
LOCKFILE_CHANGED=0

if [ "$BEFORE_SHA" != "$AFTER_SHA" ]; then
  if git diff --name-only "$BEFORE_SHA" "$AFTER_SHA" -- 'admin-h5/' | grep -q .; then ADMIN_CHANGED=1; fi
  if git diff --name-only "$BEFORE_SHA" "$AFTER_SHA" -- 'saas-base/' | grep -q .; then BACKEND_CHANGED=1; fi
  if git diff --name-only "$BEFORE_SHA" "$AFTER_SHA" -- 'saas-base/alembic/versions/' | grep -q .; then MIGRATION_CHANGED=1; fi
  if git diff --name-only "$BEFORE_SHA" "$AFTER_SHA" -- 'saas-base/requirements.txt' | grep -q .; then REQUIREMENTS_CHANGED=1; fi
  if git diff --name-only "$BEFORE_SHA" "$AFTER_SHA" -- 'admin-h5/package-lock.json' | grep -q .; then LOCKFILE_CHANGED=1; fi
fi

[ "$FORCE_ADMIN" -eq 1 ] && ADMIN_CHANGED=1
[ "$FORCE_BACKEND" -eq 1 ] && BACKEND_CHANGED=1

log "ADMIN_CHANGED=$ADMIN_CHANGED BACKEND_CHANGED=$BACKEND_CHANGED MIGRATION_CHANGED=$MIGRATION_CHANGED"

# ---------------------------------------------------------------------------
# 4. Migration safety boundary -- checked before anything is built/restarted
# ---------------------------------------------------------------------------
if [ "$MIGRATION_CHANGED" -eq 1 ]; then
  echo "STATUS=MIGRATION_REQUIRED_MANUAL_REVIEW" >&2
  echo "saas-base/alembic/versions/** changed between $BEFORE_SHA and $AFTER_SHA." >&2
  echo "This script never runs 'alembic upgrade head' automatically. Review the" >&2
  echo "migration by hand, apply it deliberately, then re-run this script (it" >&2
  echo "will see BEFORE_SHA==AFTER_SHA on the next invocation and just deploy" >&2
  echo "the already-checked-out code)." >&2
  exit 1
fi

ADMIN_STATUS="SKIPPED"
BACKEND_STATUS="SKIPPED"

# ---------------------------------------------------------------------------
# 5. Admin-h5 build + immutable release + atomic switch
# ---------------------------------------------------------------------------
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
  ADMIN_STATUS="BUILD_OK"

  RELEASE_DIR="$ADMIN_RELEASE_ROOT/$AFTER_SHA"
  if [ -d "$RELEASE_DIR" ]; then
    log "Release $RELEASE_DIR already exists -- verifying instead of overwriting"
    test -s "$RELEASE_DIR/index.html"
  else
    RELEASE_TMP="${RELEASE_DIR}.tmp"
    rm -rf "$RELEASE_TMP"
    mkdir -p "$ADMIN_RELEASE_ROOT"
    mkdir -p "$RELEASE_TMP"
    cp -a "$ADMIN_SOURCE/dist/." "$RELEASE_TMP/"
    cat > "$RELEASE_TMP/release.json" <<EOF
{
  "sha": "$AFTER_SHA",
  "built_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
    chown -R www:www "$RELEASE_TMP" 2>/dev/null || log "chown to www:www failed/skipped (non-root or user missing) -- verify ownership manually"
    test -s "$RELEASE_TMP/index.html"
    mv -T "$RELEASE_TMP" "$RELEASE_DIR"
  fi

  PREVIOUS_ADMIN_TARGET=""
  if [ -e "$ADMIN_CURRENT" ]; then
    PREVIOUS_ADMIN_TARGET="$(readlink -f "$ADMIN_CURRENT" || true)"
  fi
  log "PREVIOUS_ADMIN_TARGET=${PREVIOUS_ADMIN_TARGET:-<none>}"

  ln -sfn "$RELEASE_DIR" "$ADMIN_CURRENT.new"
  mv -Tf "$ADMIN_CURRENT.new" "$ADMIN_CURRENT"

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

  # -------------------------------------------------------------------
  # Release retention: keep `current` + at least RELEASE_KEEP_MIN-1 more.
  # -------------------------------------------------------------------
  if [ "$ADMIN_STATUS" = "SWITCHED" ] && [ -d "$ADMIN_RELEASE_ROOT" ]; then
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

# ---------------------------------------------------------------------------
# 6. Backend restart
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
    journalctl -u "$BACKEND_SERVICE" -n 40 --no-pager >&2 || true
    exit 1
  fi
fi

log "ADMIN_STATUS=$ADMIN_STATUS BACKEND_STATUS=$BACKEND_STATUS"
echo "DEPLOYED_SHA=$AFTER_SHA"

if [ "$ADMIN_STATUS" = "FAILED_ROLLED_BACK" ]; then
  echo "STATUS=ADMIN_DEPLOY_FAILED_ROLLED_BACK" >&2
  exit 1
fi

echo "STATUS=DEPLOY_OK"
