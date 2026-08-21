#!/usr/bin/env bash
#
# Instant admin-h5 frontend rollback: atomically re-point `current` at an
# already-built, already-verified release. No rebuild, no git checkout --
# this should complete in seconds.
#
# Usage:
#   ./scripts/rollback-admin-h5.sh <release-sha>
#
# <release-sha> must name an existing directory under
# $ADMIN_RELEASE_ROOT/<release-sha>/ that still has an index.html (i.e. one
# of the releases deploy-production.sh's retention step kept).

set -Eeuo pipefail

: "${ADMIN_RELEASE_ROOT:=/www/wwwroot/admin-h5/releases}"
: "${ADMIN_CURRENT:=/www/wwwroot/admin-h5/current}"
: "${PRODUCTION_URL:=https://saas.zhangbaiyang.com/}"

log() { echo "[rollback] $*"; }

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <release-sha>" >&2
  echo "Available releases:" >&2
  ls -1t "$ADMIN_RELEASE_ROOT" 2>/dev/null >&2 || true
  exit 2
fi

TARGET_SHA="$1"
RELEASE_DIR="$ADMIN_RELEASE_ROOT/$TARGET_SHA"

if [ ! -s "$RELEASE_DIR/index.html" ]; then
  echo "STATUS=BLOCKED_UNKNOWN_RELEASE" >&2
  echo "$RELEASE_DIR/index.html does not exist -- refusing to switch to it." >&2
  echo "Available releases:" >&2
  ls -1t "$ADMIN_RELEASE_ROOT" 2>/dev/null >&2 || true
  exit 1
fi

PREVIOUS_ADMIN_TARGET=""
if [ -e "$ADMIN_CURRENT" ]; then
  PREVIOUS_ADMIN_TARGET="$(readlink -f "$ADMIN_CURRENT" || true)"
fi
log "PREVIOUS_ADMIN_TARGET=${PREVIOUS_ADMIN_TARGET:-<none>}"
log "Switching current -> $RELEASE_DIR"

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
  echo "STATUS=ROLLBACK_OK"
  echo "CURRENT_SHA=$TARGET_SHA"
else
  echo "STATUS=ROLLBACK_VERIFICATION_FAILED" >&2
  if [ -n "$PREVIOUS_ADMIN_TARGET" ]; then
    log "Restoring previous current: $PREVIOUS_ADMIN_TARGET"
    ln -sfn "$PREVIOUS_ADMIN_TARGET" "$ADMIN_CURRENT.new"
    mv -Tf "$ADMIN_CURRENT.new" "$ADMIN_CURRENT"
    echo "ADMIN_ROLLBACK=YES"
  fi
  exit 1
fi
