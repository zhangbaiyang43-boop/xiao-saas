#!/usr/bin/env bash
#
# Linux integration contract for the deployment tooling (scripts/deploy-
# production.sh, scripts/rollback-admin-h5.sh). TEST_LEVEL=LINUX_INTEGRATION_CONTRACT.
#
# Never touches real /www/wwwroot, systemctl, a production URL, or this
# repo's own worktree/remote: every case builds a disposable git origin +
# checkout under mktemp -d, and npm/systemctl/curl/journalctl are replaced
# with shims on PATH so no real network, service, or Node toolchain is
# required. git itself is real (that's exactly what needs proving), just
# operating on throwaway repos.
#
# Windows/MSYS note: this script CAN run locally on a dev machine for quick
# iteration, but its result there is NOT authoritative for the symlink/mv
# atomic-swap behavior this suite exists to prove -- MSYS's coreutils differ
# from real GNU coreutils/Linux in exactly that area. Only a green run on
# GitHub's ubuntu-latest runner (.github/workflows/deployment-tooling-ci.yml)
# certifies this tooling.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_SCRIPT="$SCRIPT_DIR/deploy-production.sh"
ROLLBACK_SCRIPT="$SCRIPT_DIR/rollback-admin-h5.sh"
SELF="$SCRIPT_DIR/test-deployment-tooling.sh"

WORK="$(mktemp -d)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

PASS_COUNT=0
FAIL_COUNT=0
ok()  { PASS_COUNT=$((PASS_COUNT + 1)); echo "  ok:   $*"; }
bad() { FAIL_COUNT=$((FAIL_COUNT + 1)); echo "  FAIL: $*" >&2; }

assert_eq() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (expected [$2] got [$3])"; fi; }
assert_exit() { if [ "$2" -eq "$3" ]; then ok "$1"; else bad "$1 (expected exit $2 got $3)"; fi; }
assert_contains() { if grep -qF -- "$2" <<<"$3"; then ok "$1"; else bad "$1 (did not find [$2] in output)"; fi; }
assert_true() { local d="$1"; shift; if "$@"; then ok "$d"; else bad "$d"; fi; }

# ---------------------------------------------------------------------------
# Mock bin/: only npm, systemctl, curl, journalctl. Everything else (git,
# grep, sed, cp, mv, ln, mkdir, rm, readlink, mktemp, chown, date, bash...)
# is the real system binary further down PATH.
# ---------------------------------------------------------------------------
MOCKBIN="$WORK/bin"
mkdir -p "$MOCKBIN"

cat > "$MOCKBIN/npm" <<'MOCK'
#!/usr/bin/env bash
: "${MOCK_STATE_DIR:?MOCK_STATE_DIR not set}"
echo "$*" >> "$MOCK_STATE_DIR/npm_calls.log"
if [ "$1" = "run" ] && [ "$2" = "build" ]; then
  mkdir -p dist/assets
  echo '<html><body><script src="/assets/app.js"></script></body></html>' > dist/index.html
  echo 'console.log(1)' > dist/assets/app.js
fi
exit 0
MOCK

cat > "$MOCKBIN/systemctl" <<'MOCK'
#!/usr/bin/env bash
: "${MOCK_STATE_DIR:?MOCK_STATE_DIR not set}"
echo "$*" >> "$MOCK_STATE_DIR/systemctl_calls.log"
case "$1" in
  restart) exit 0 ;;
  is-active)
    if [ -f "$MOCK_STATE_DIR/backend_healthy" ]; then exit 0; else exit 3; fi
    ;;
  *) exit 0 ;;
esac
MOCK

cat > "$MOCKBIN/curl" <<'MOCK'
#!/usr/bin/env bash
: "${MOCK_STATE_DIR:?MOCK_STATE_DIR not set}"
url="${*: -1}"
case "$url" in
  *9898/health*|*/health)
    if [ -f "$MOCK_STATE_DIR/backend_healthy" ]; then
      echo '{"code":200,"msg":"ok","data":{"status":"healthy"}}'
      exit 0
    fi
    exit 7
    ;;
  *)
    if [ -f "$MOCK_STATE_DIR/frontend_verifiable" ]; then
      echo '<html><body><script src="/assets/app.js"></script></body></html>'
      exit 0
    fi
    exit 7
    ;;
esac
MOCK

cat > "$MOCKBIN/journalctl" <<'MOCK'
#!/usr/bin/env bash
echo "(mock journalctl: no real service to inspect)"
exit 0
MOCK

chmod +x "$MOCKBIN"/npm "$MOCKBIN"/systemctl "$MOCKBIN"/curl "$MOCKBIN"/journalctl
export PATH="$MOCKBIN:$PATH"

# ---------------------------------------------------------------------------
# Fixture helpers -- every case gets its own disposable origin + checkout.
# ---------------------------------------------------------------------------
setup_case() {
  local name="$1"
  CASE_DIR="$WORK/$name"
  mkdir -p "$CASE_DIR"
  ORIGIN="$CASE_DIR/origin.git"
  REPO="$CASE_DIR/repo"
  git init --quiet --bare -b main "$ORIGIN"
  git clone --quiet "$ORIGIN" "$REPO"
  (
    cd "$REPO"
    git config user.email test@test.local
    git config user.name Test
    mkdir -p admin-h5 saas-base/alembic/versions
    echo '{"name":"fixture"}' > admin-h5/package.json
    echo '{}' > admin-h5/package-lock.json
    echo 'fastapi' > saas-base/requirements.txt
    : > saas-base/alembic/versions/.gitkeep
    echo 'fixture repo for deployment-tooling tests' > README.md
    git add -A
    git commit -q -m init
    git push -q -u origin main
  )
  ADMIN_SOURCE="$REPO/admin-h5"
  ADMIN_RELEASE_ROOT="$CASE_DIR/admin-h5-releases"
  ADMIN_CURRENT="$CASE_DIR/admin-h5-current"
  BACKEND_SERVICE="fake-backend.service"
  BACKEND_HEALTH_URL="http://127.0.0.1:9898/health"
  PRODUCTION_URL="https://example.invalid/"
  MOCK_STATE_DIR="$CASE_DIR/mock-state"
  mkdir -p "$MOCK_STATE_DIR"
  export REPO ADMIN_SOURCE ADMIN_RELEASE_ROOT ADMIN_CURRENT BACKEND_SERVICE BACKEND_HEALTH_URL PRODUCTION_URL MOCK_STATE_DIR
}

# publish <path> <content> [<path2> <content2> ...] -- commits+pushes via a
# throwaway clone of the case's origin (never touches $REPO's own worktree),
# prints the new commit sha.
publish() {
  local pub="$CASE_DIR/publisher"
  rm -rf "$pub"
  git clone --quiet "$ORIGIN" "$pub" >/dev/null
  (
    cd "$pub"
    git config user.email test@test.local
    git config user.name Test
    while [ "$#" -gt 0 ]; do
      local path="$1" content="$2"
      shift 2
      mkdir -p "$(dirname "$path")"
      printf '%s\n' "$content" > "$path"
      git add "$path"
    done
    git commit -q -m "test change"
    git push -q origin main
  ) >/dev/null
  git -C "$pub" rev-parse HEAD
}

run_deploy() {
  set +e
  LAST_OUTPUT="$(bash "$DEPLOY_SCRIPT" "$@" 2>&1)"
  LAST_EXIT=$?
  set -e
}

run_rollback() {
  set +e
  LAST_OUTPUT="$(bash "$ROLLBACK_SCRIPT" "$@" 2>&1)"
  LAST_EXIT=$?
  set -e
}

make_valid_release() {
  local dir="$1" sha="$2"
  mkdir -p "$dir/assets"
  echo '<html><body><script src="/assets/app.js"></script></body></html>' > "$dir/index.html"
  echo 'console.log(1)' > "$dir/assets/app.js"
  printf '{\n  "sha": "%s",\n  "built_at": "2026-01-01T00:00:00Z"\n}\n' "$sha" > "$dir/release.json"
}

# ---------------------------------------------------------------------------
# CASE A -- bash -n on all three scripts
# ---------------------------------------------------------------------------
echo "== CASE A: bash -n =="
assert_true "deploy-production.sh syntax" bash -n "$DEPLOY_SCRIPT"
assert_true "rollback-admin-h5.sh syntax" bash -n "$ROLLBACK_SCRIPT"
assert_true "test-deployment-tooling.sh syntax" bash -n "$SELF"

# ---------------------------------------------------------------------------
# CASE B -- dirty production tree fails closed
# ---------------------------------------------------------------------------
echo "== CASE B: dirty production tree =="
setup_case case-b
echo dirty > "$REPO/untracked.txt"
run_deploy
assert_exit "dirty tree exits 1" 1 "$LAST_EXIT"
assert_contains "reports BLOCKED_DIRTY_PRODUCTION_TREE" "BLOCKED_DIRTY_PRODUCTION_TREE" "$LAST_OUTPUT"

# ---------------------------------------------------------------------------
# CASE C -- dry-run never checks out/builds/restarts/switches
# ---------------------------------------------------------------------------
echo "== CASE C: dry-run is a true no-op =="
setup_case case-c
BEFORE_SHA="$(git -C "$REPO" rev-parse HEAD)"
publish admin-h5/feature.txt hello >/dev/null
run_deploy --dry-run
assert_exit "dry-run exits 0" 0 "$LAST_EXIT"
assert_contains "reports DRY_RUN_OK" "STATUS=DRY_RUN_OK" "$LAST_OUTPUT"
AFTER_SHA="$(git -C "$REPO" rev-parse HEAD)"
assert_eq "dry-run never advances HEAD" "$BEFORE_SHA" "$AFTER_SHA"
assert_true "dry-run never invokes npm" bash -c '[ ! -f "$1" ]' _ "$MOCK_STATE_DIR/npm_calls.log"
assert_true "dry-run never creates ADMIN_CURRENT" bash -c '[ ! -e "$1" ]' _ "$ADMIN_CURRENT"

# ---------------------------------------------------------------------------
# CASE D -- migration candidate fails closed BEFORE any checkout/pull
# ---------------------------------------------------------------------------
echo "== CASE D: migration fails closed before pull =="
setup_case case-d
BEFORE_SHA="$(git -C "$REPO" rev-parse HEAD)"
publish saas-base/alembic/versions/20260101_0001_test.py "# migration" >/dev/null
run_deploy
assert_exit "migration candidate exits 1" 1 "$LAST_EXIT"
assert_contains "reports MIGRATION_REQUIRED_MANUAL_REVIEW" "MIGRATION_REQUIRED_MANUAL_REVIEW" "$LAST_OUTPUT"
AFTER_SHA="$(git -C "$REPO" rev-parse HEAD)"
assert_eq "HEAD unchanged when migration blocks" "$BEFORE_SHA" "$AFTER_SHA"

# ---------------------------------------------------------------------------
# CASE E -- real atomic symlink swap (admin-only change)
# ---------------------------------------------------------------------------
echo "== CASE E: atomic symlink swap =="
setup_case case-e
OLD_SHA="0000000000000000000000000000000000old1"
make_valid_release "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$OLD_SHA"
ln -sfn "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$ADMIN_CURRENT"
touch "$MOCK_STATE_DIR/frontend_verifiable"
NEW_SHA="$(publish admin-h5/feature.txt hello)"
run_deploy
assert_exit "admin-only deploy succeeds" 0 "$LAST_EXIT"
assert_contains "reports DEPLOY_OK" "STATUS=DEPLOY_OK" "$LAST_OUTPUT"
CURRENT_TARGET="$(readlink -f "$ADMIN_CURRENT")"
assert_eq "current points at the new release" "$ADMIN_RELEASE_ROOT/$NEW_SHA" "$CURRENT_TARGET"

# ---------------------------------------------------------------------------
# CASE F -- rollback re-points current, no rebuild, no git checkout
# ---------------------------------------------------------------------------
echo "== CASE F: rollback =="
setup_case case-f
SHA_A="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
SHA_B="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
make_valid_release "$ADMIN_RELEASE_ROOT/$SHA_A" "$SHA_A"
make_valid_release "$ADMIN_RELEASE_ROOT/$SHA_B" "$SHA_B"
ln -sfn "$ADMIN_RELEASE_ROOT/$SHA_B" "$ADMIN_CURRENT"
touch "$MOCK_STATE_DIR/frontend_verifiable"
run_rollback "$SHA_A"
assert_exit "rollback succeeds" 0 "$LAST_EXIT"
CURRENT_TARGET="$(readlink -f "$ADMIN_CURRENT")"
assert_eq "current now points at release A" "$ADMIN_RELEASE_ROOT/$SHA_A" "$CURRENT_TARGET"

# ---------------------------------------------------------------------------
# CASE G -- backend failure leaves current untouched (prepared != live)
# ---------------------------------------------------------------------------
echo "== CASE G: backend failure ordering =="
setup_case case-g
OLD_SHA="cccccccccccccccccccccccccccccccccccccccc"
make_valid_release "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$OLD_SHA"
ln -sfn "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$ADMIN_CURRENT"
touch "$MOCK_STATE_DIR/frontend_verifiable" # would pass if ever reached -- must NOT be reached
NEW_SHA="$(publish admin-h5/feature.txt hi saas-base/app_marker.py "# backend change")"
# deliberately no backend_healthy marker -> systemctl is-active fails
run_deploy
assert_exit "combined deploy fails when backend unhealthy" 1 "$LAST_EXIT"
assert_contains "reports BACKEND_DEPLOY_FAILED" "BACKEND_DEPLOY_FAILED" "$LAST_OUTPUT"
assert_true "admin release was still built/prepared" test -s "$ADMIN_RELEASE_ROOT/$NEW_SHA/index.html"
CURRENT_TARGET="$(readlink -f "$ADMIN_CURRENT")"
assert_eq "current still points at the OLD release (never switched live)" "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$CURRENT_TARGET"

# ---------------------------------------------------------------------------
# CASE H -- successful combined deployment switches current
# ---------------------------------------------------------------------------
echo "== CASE H: successful combined deployment =="
setup_case case-h
OLD_SHA="dddddddddddddddddddddddddddddddddddddddd"
make_valid_release "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$OLD_SHA"
ln -sfn "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$ADMIN_CURRENT"
touch "$MOCK_STATE_DIR/frontend_verifiable"
touch "$MOCK_STATE_DIR/backend_healthy"
NEW_SHA="$(publish admin-h5/feature.txt hi saas-base/app_marker.py "# backend change")"
run_deploy
assert_exit "combined deploy succeeds" 0 "$LAST_EXIT"
assert_contains "reports DEPLOY_OK" "STATUS=DEPLOY_OK" "$LAST_OUTPUT"
CURRENT_TARGET="$(readlink -f "$ADMIN_CURRENT")"
assert_eq "current now points at the new release" "$ADMIN_RELEASE_ROOT/$NEW_SHA" "$CURRENT_TARGET"

# ---------------------------------------------------------------------------
# CASE I -- existing release with a mismatched sha fails closed, unmodified
# ---------------------------------------------------------------------------
echo "== CASE I: existing corrupt release =="
setup_case case-i
NEW_SHA="$(publish admin-h5/feature.txt hi)"
mkdir -p "$ADMIN_RELEASE_ROOT/$NEW_SHA/assets"
echo '<html></html>' > "$ADMIN_RELEASE_ROOT/$NEW_SHA/index.html"
echo x > "$ADMIN_RELEASE_ROOT/$NEW_SHA/assets/app.js"
printf '{\n  "sha": "totally-wrong-sha",\n  "built_at": "2020-01-01T00:00:00Z"\n}\n' > "$ADMIN_RELEASE_ROOT/$NEW_SHA/release.json"
run_deploy
assert_exit "corrupt existing release blocks with exit 1" 1 "$LAST_EXIT"
assert_contains "reports BLOCKED_INVALID_EXISTING_RELEASE" "BLOCKED_INVALID_EXISTING_RELEASE" "$LAST_OUTPUT"
assert_contains "corrupt release.json was not overwritten" "totally-wrong-sha" "$(cat "$ADMIN_RELEASE_ROOT/$NEW_SHA/release.json")"

# ---------------------------------------------------------------------------
echo
echo "PASS=$PASS_COUNT FAIL=$FAIL_COUNT"
if [ "$FAIL_COUNT" -gt 0 ]; then
  echo "STATUS=LINUX_INTEGRATION_CONTRACT_FAILED"
  exit 1
fi
echo "STATUS=LINUX_INTEGRATION_CONTRACT_OK"
