#!/usr/bin/env bash
#
# Single-authority production deploy: git main -> backend restart + admin-h5
# atomic release switch, SHA-tracked, fast-rollback-able.
#
# PRODUCTION_FRONTEND_BUILD=FORBIDDEN. This script never runs a frontend
# build (no npm/npx/vite anywhere in it, on principle, not just today's
# implementation -- the production host does not have the RAM for
# `vite build` and repeatedly locked up trying). admin-h5 is built exactly
# once, by GitHub Actions (.github/workflows/admin-h5-release.yml), and
# published as a checksummed GitHub Release asset keyed by the exact commit
# SHA. This script's only job for the frontend is: download that artifact,
# verify it, extract it safely, and atomically switch to it.
#
# Usage:
#   ./scripts/deploy-production.sh [--dry-run] [--force-admin] [--force-backend] [--bootstrap-admin]
#
#   --dry-run         Report what would happen; never writes to git, disk, or
#                     any running service.
#   --force-admin     Prepare/release admin-h5 even if admin-h5/** didn't
#                     change between BEFORE_SHA and TARGET_SHA. Required when
#                     resuming a migration release (see docs/production-
#                     deployment.md) -- there is no automatic resume path.
#   --force-backend   Restart the backend even if saas-base/** didn't change
#                     between BEFORE_SHA and TARGET_SHA. Same manual-resume
#                     use case as --force-admin.
#   --bootstrap-admin One-time first-cutover mode: implies --force-admin,
#                     downloads/verifies/releases/switches `current` (never
#                     builds), but does NOT treat a request to the live
#                     production URL as proof (nginx may still be serving
#                     the legacy dist/ at that point). See docs/production-
#                     deployment.md "First migration".
#
# Hard safety boundaries (see docs/production-deployment.md for the full
# contract this script implements):
#   - Refuses to run against a dirty production working tree.
#   - Only ever deploys origin/main, only via `git pull --ff-only` (never
#     reset --hard / clean -fd / force-pull).
#   - Change detection (admin/backend/migration/requirements) is computed
#     BEFORE any checkout/pull, comparing BEFORE_SHA (current HEAD) against
#     TARGET_SHA (fetched origin/main) -- never against a state the working
#     tree has already been advanced to.
#   - Never runs an Alembic migration automatically -- if a migration file
#     changed, the script stops BEFORE checking anything out. HEAD is
#     provably unchanged when this happens; resuming afterwards is always a
#     deliberate, documented manual procedure, never an automatic re-run.
#   - The admin-h5 artifact is downloaded and fully verified (checksum +
#     archive-entry safety + release.json identity) before backend deploy
#     even starts. If the artifact isn't published yet, the script stops
#     (ADMIN_ARTIFACT_NOT_READY) before touching the backend or `current`.
#   - Backend deploy (if any) happens and must succeed BEFORE the admin-h5
#     release is ever switched live -- a prepared-but-unswitched admin
#     release and a failed backend never coexist as "new frontend + broken
#     backend"; a backend failure leaves `current` exactly where it was.
#   - Admin-h5 releases are immutable (downloaded/extracted into a mktemp -d
#     staging dir, validated, then atomically renamed into place -- never
#     rm -rf'ing an existing/unknown path) and switched via `current` with
#     an ln -sfn + mv -Tf pair -- nginx never sees a missing `current`.
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
: "${ADMIN_RELEASE_ROOT:=/www/wwwroot/admin-h5/releases}"
: "${ADMIN_CURRENT:=/www/wwwroot/admin-h5/current}"
: "${BACKEND_SERVICE:=saas-base.service}"
: "${BACKEND_HEALTH_URL:=http://127.0.0.1:9898/health}"
: "${PRODUCTION_URL:=https://saas.zhangbaiyang.com/}"
: "${RELEASE_KEEP_MIN:=4}" # current + at least 3 historical releases
: "${DEPLOY_CONFIG_FILE:=/etc/xiao-deploy.env}"
# ARTIFACT_BASE_URL has NO default -- production evidence showed direct
# GitHub Release downloads from mainland China run at ~4-10KB/s and time
# out (PRODUCTION_GITHUB_RELEASE_DIRECT_DOWNLOAD=FORBIDDEN); the real
# transport is Tencent COS, and there is no safe generic default bucket URL
# to fall back to. Resolved below, after change detection, from the
# process environment first and $DEPLOY_CONFIG_FILE second -- never a
# hardcoded github.com/.../releases/download path.

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

# Cleanup for exactly one in-flight temp staging dir at a time -- never a
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

release_is_valid() {
  # usage: release_is_valid <dir> <expected-sha>
  [ -s "$1/index.html" ] && [ -d "$1/assets" ] && [ -s "$1/release.json" ] \
    && [ "$(release_json_sha "$1/release.json")" = "$2" ]
}

archive_is_safe() {
  # usage: archive_is_safe <archive.tar.gz>
  # Only regular files and directories are allowed; everything else
  # (symlink, hardlink, device, fifo, socket) is rejected, along with any
  # absolute path or genuine ".." path component. This is a build artifact
  # from our own CI, not an untrusted user upload, but it's still an
  # unpacked-from-the-internet archive and gets treated as one.
  #
  # Delegated to Python's tarfile module rather than parsing `tar -tvzf`
  # text: GNU tar's verbose listing does not reliably distinguish a
  # hardlink entry from a regular file in its permission-string column,
  # and pure-shell path matching (`*..*`) would wrongly reject a legitimate
  # filename like "app..js". tarfile's TarInfo.isreg()/isdir() and a real
  # per-path-component check are both exact. saas-base already requires
  # Python on this host, so this adds no new production dependency.
  local archive="$1" python_bin
  python_bin="$(command -v python3 2>/dev/null || command -v python3.12 2>/dev/null || command -v python 2>/dev/null || true)"
  if [ -z "$python_bin" ]; then
    log "No python interpreter available to inspect archive entries -- refusing to extract an unverifiable artifact"
    return 1
  fi
  "$python_bin" - "$archive" <<'PYEOF'
import sys
import tarfile

path = sys.argv[1]
try:
    with tarfile.open(path, "r:gz") as tf:
        for info in tf.getmembers():
            name = info.name
            if name.startswith("/"):
                sys.exit(1)
            if ".." in name.split("/"):
                sys.exit(1)
            if not (info.isreg() or info.isdir()):
                sys.exit(1)
except tarfile.TarError:
    sys.exit(1)
sys.exit(0)
PYEOF
}

resolve_artifact_base_url() {
  # Process environment wins if already set. Otherwise parse exactly the
  # ARTIFACT_BASE_URL= key out of $DEPLOY_CONFIG_FILE -- never `source` the
  # whole file (it is a deployment-transport config file, not a script, and
  # must never be treated as one).
  if [ -n "${ARTIFACT_BASE_URL:-}" ]; then
    return 0
  fi
  if [ -f "$DEPLOY_CONFIG_FILE" ]; then
    local line value
    line="$(grep -E '^ARTIFACT_BASE_URL=' "$DEPLOY_CONFIG_FILE" 2>/dev/null | tail -n1 || true)"
    if [ -n "$line" ]; then
      value="${line#ARTIFACT_BASE_URL=}"
      value="${value%\"}"; value="${value#\"}"
      value="${value%\'}"; value="${value#\'}"
      ARTIFACT_BASE_URL="$value"
    fi
  fi
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

if [ "$BEFORE_SHA" != "$TARGET_SHA" ]; then
  if git diff --name-only "$BEFORE_SHA" "$TARGET_SHA" -- 'admin-h5/' | grep -q .; then ADMIN_CHANGED=1; fi
  if git diff --name-only "$BEFORE_SHA" "$TARGET_SHA" -- 'saas-base/' | grep -q .; then BACKEND_CHANGED=1; fi
  if git diff --name-only "$BEFORE_SHA" "$TARGET_SHA" -- 'saas-base/alembic/versions/' | grep -q .; then MIGRATION_CHANGED=1; fi
  if git diff --name-only "$BEFORE_SHA" "$TARGET_SHA" -- 'saas-base/requirements.txt' | grep -q .; then REQUIREMENTS_CHANGED=1; fi
fi

# Force flags never bypass the migration safety boundary -- only ever
# widen ADMIN_CHANGED/BACKEND_CHANGED (used to resume after a manual
# migration pull, where BEFORE_SHA==TARGET_SHA already and the diff above
# is a no-op).
[ "$FORCE_ADMIN" -eq 1 ] && ADMIN_CHANGED=1
[ "$FORCE_BACKEND" -eq 1 ] && BACKEND_CHANGED=1

log "ADMIN_CHANGED=$ADMIN_CHANGED BACKEND_CHANGED=$BACKEND_CHANGED MIGRATION_CHANGED=$MIGRATION_CHANGED"

if [ "$DRY_RUN" -eq 1 ]; then
  log "DRY_RUN=1 -- no git checkout/pull, no download, no release, no restart."
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
# 3b. Artifact transport configuration -- only required when this deploy
#     actually needs to fetch an admin-h5 artifact (ADMIN_CHANGED=1). Must
#     be resolved and checked before git pull, before any download, before
#     the backend restart, and before any current switch -- so a missing
#     config fails closed at the very start, not partway through.
# ---------------------------------------------------------------------------
resolve_artifact_base_url
if [ "$ADMIN_CHANGED" -eq 1 ] && [ -z "${ARTIFACT_BASE_URL:-}" ]; then
  echo "STATUS=BLOCKED_ARTIFACT_TRANSPORT_NOT_CONFIGURED" >&2
  echo "ARTIFACT_BASE_URL is not set (checked the process environment, then" >&2
  echo "$DEPLOY_CONFIG_FILE) and this deploy needs to download an admin-h5" >&2
  echo "artifact. Set ARTIFACT_BASE_URL in the environment, or add a line" >&2
  echo "ARTIFACT_BASE_URL=<public COS base>/deploy-artifacts/admin-h5 to" >&2
  echo "$DEPLOY_CONFIG_FILE, then re-run. Not pulling, downloading, restarting" >&2
  echo "the backend, or touching current." >&2
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
# 5. Phase A + B -- download + verify + extract the GitHub-built admin-h5
#    artifact and prepare an immutable release, but do NOT switch `current`
#    yet. A prepared-but-unswitched release is the whole point: if the
#    backend deploy below fails, this release simply never goes live, and
#    `current` is never touched. No frontend build ever happens here.
# ---------------------------------------------------------------------------
RELEASE_DIR="$ADMIN_RELEASE_ROOT/$AFTER_SHA"

if [ "$ADMIN_CHANGED" -eq 1 ]; then
  if [ -d "$RELEASE_DIR" ]; then
    log "Release $RELEASE_DIR already exists -- validating before reuse"
    if release_is_valid "$RELEASE_DIR" "$AFTER_SHA"; then
      log "Existing release validated -- reusing, no download needed"
    else
      echo "STATUS=BLOCKED_INVALID_EXISTING_RELEASE" >&2
      echo "$RELEASE_DIR exists but failed validation (missing index.html/assets/" >&2
      echo "release.json, or release.json's sha does not match $AFTER_SHA). Refusing" >&2
      echo "to overwrite an unknown existing release directory." >&2
      exit 1
    fi
  else
    ARTIFACT_TAG="admin-h5-$AFTER_SHA"
    ARTIFACT_NAME="admin-h5-dist-$AFTER_SHA.tar.gz"
    CHECKSUM_NAME="$ARTIFACT_NAME.sha256"
    ARTIFACT_URL="$ARTIFACT_BASE_URL/$ARTIFACT_TAG/$ARTIFACT_NAME"
    CHECKSUM_URL="$ARTIFACT_BASE_URL/$ARTIFACT_TAG/$CHECKSUM_NAME"

    mkdir -p "$ADMIN_RELEASE_ROOT"
    STAGE_DIR="$(mktemp -d "$ADMIN_RELEASE_ROOT/.stage-${AFTER_SHA}.XXXXXX")"
    CLEANUP_TMP="$STAGE_DIR"
    mkdir -p "$STAGE_DIR/download" "$STAGE_DIR/extract"

    # -fsSL: fail on HTTP errors, silent but still show errors, follow
    # redirects (COS/CDN URLs may redirect). Bounded connect/total time +
    # a few retries so a transient blip doesn't need a full manual re-run,
    # without masking a genuinely unreachable/misconfigured transport.
    DOWNLOAD_CURL_OPTS=(--connect-timeout 10 --max-time 120 --retry 3 --retry-delay 2 --retry-all-errors -fsSL)

    log "Downloading admin-h5 artifact: $ARTIFACT_URL"
    if ! curl "${DOWNLOAD_CURL_OPTS[@]}" -o "$STAGE_DIR/download/$ARTIFACT_NAME" "$ARTIFACT_URL"; then
      echo "STATUS=ADMIN_ARTIFACT_NOT_READY" >&2
      echo "Could not download $ARTIFACT_URL -- the admin-h5-release workflow" >&2
      echo "for $AFTER_SHA may not have finished publishing yet. Not restarting" >&2
      echo "the backend or switching current; re-run once the artifact exists." >&2
      exit 1
    fi
    if ! curl "${DOWNLOAD_CURL_OPTS[@]}" -o "$STAGE_DIR/download/$CHECKSUM_NAME" "$CHECKSUM_URL"; then
      echo "STATUS=ADMIN_ARTIFACT_NOT_READY" >&2
      echo "Could not download $CHECKSUM_URL." >&2
      exit 1
    fi

    log "Verifying checksum"
    if ! (cd "$STAGE_DIR/download" && sha256sum -c "$CHECKSUM_NAME" >/dev/null); then
      echo "STATUS=BLOCKED_ADMIN_ARTIFACT_CHECKSUM" >&2
      echo "$STAGE_DIR/download/$ARTIFACT_NAME failed sha256sum -c against $CHECKSUM_NAME." >&2
      exit 1
    fi

    log "Checking archive entries for path traversal / absolute paths / symlinks"
    if ! archive_is_safe "$STAGE_DIR/download/$ARTIFACT_NAME"; then
      echo "STATUS=BLOCKED_UNSAFE_ADMIN_ARTIFACT" >&2
      echo "$ARTIFACT_NAME contains an absolute path, a .. path component, or a" >&2
      echo "symlink entry -- refusing to extract it." >&2
      exit 1
    fi

    tar -xzf "$STAGE_DIR/download/$ARTIFACT_NAME" -C "$STAGE_DIR/extract"

    if ! release_is_valid "$STAGE_DIR/extract" "$AFTER_SHA"; then
      echo "STATUS=BLOCKED_INVALID_ADMIN_ARTIFACT" >&2
      echo "Extracted artifact failed validation (missing index.html/assets/" >&2
      echo "release.json, or release.json's sha does not match $AFTER_SHA)." >&2
      exit 1
    fi

    chown -R www:www "$STAGE_DIR/extract" 2>/dev/null || log "chown to www:www failed/skipped (non-root or user missing) -- verify ownership manually"
    mv -T "$STAGE_DIR/extract" "$RELEASE_DIR"
    rm -rf "$STAGE_DIR"
    CLEANUP_TMP="" # everything under it is either moved out or deleted
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
    # Invoke the venv's python directly (production systemd contract) rather
    # than `source venv/bin/activate` -- that depends on shell-sourcing a
    # file whose existence a static linter can't verify (ShellCheck SC1091),
    # and on PATH resolving `pip` to the right interpreter afterwards. Named
    # explicitly, there's exactly one authority for which Python/pip this is.
    BACKEND_VENV_PYTHON="$REPO/saas-base/venv/bin/python"
    if [ ! -x "$BACKEND_VENV_PYTHON" ]; then
      echo "STATUS=BLOCKED_BACKEND_VENV_MISSING" >&2
      echo "$BACKEND_VENV_PYTHON does not exist or is not executable." >&2
      exit 1
    fi
    "$BACKEND_VENV_PYTHON" -m pip install -r "$REPO/saas-base/requirements.txt"
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
    if [ "$ADMIN_CHANGED" -eq 1 ]; then
      echo "ADMIN_CURRENT_UNCHANGED=YES (release $RELEASE_DIR prepared but never switched live)" >&2
    else
      echo "ADMIN_CURRENT_UNCHANGED=YES (no admin-h5 release was part of this deploy)" >&2
    fi
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
