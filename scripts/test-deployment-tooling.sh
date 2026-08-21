#!/usr/bin/env bash
#
# Linux integration contract for the deployment tooling (scripts/deploy-
# production.sh, scripts/rollback-admin-h5.sh). TEST_LEVEL=LINUX_INTEGRATION_CONTRACT.
#
# Never touches real /www/wwwroot, systemctl, a production URL, a real
# GitHub Release, or this repo's own worktree/remote: every case builds a
# disposable git origin + checkout under mktemp -d, and npm/systemctl/curl/
# journalctl are replaced with shims on PATH so no real network, service, or
# Node toolchain is required. git/tar/sha256sum/python are real (that's
# exactly what needs proving for git logic and archive handling), just
# operating on throwaway repos and fixture archives.
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

# Named predicate functions instead of `bash -c '...'` one-liners -- avoids
# ShellCheck SC2016 (single-quoted string won't expand $1 at write-time; the
# expansion is intentional, deferred to bash -c's own invocation, but a
# named function makes that unambiguous without a disable comment).
file_absent() { [ ! -f "$1" ]; }
path_absent() { [ ! -e "$1" ]; }

# ---------------------------------------------------------------------------
# Mock bin/: only npm, systemctl, curl, journalctl. Everything else (git,
# tar, sha256sum, python, grep, sed, cp, mv, ln, mkdir, rm, readlink,
# mktemp, chown, date, bash...) is the real system binary further down PATH.
# ---------------------------------------------------------------------------
MOCKBIN="$WORK/bin"
mkdir -p "$MOCKBIN"

cat > "$MOCKBIN/npm" <<'MOCK'
#!/usr/bin/env bash
# deploy-production.sh must never invoke this (PRODUCTION_FRONTEND_BUILD=
# FORBIDDEN) -- this mock exists only so tests can prove that by asserting
# its call log never gets written to.
: "${MOCK_STATE_DIR:?MOCK_STATE_DIR not set}"
echo "$*" >> "$MOCK_STATE_DIR/npm_calls.log"
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
out=""
prev=""
for a in "$@"; do
  if [ "$prev" = "-o" ]; then out="$a"; fi
  prev="$a"
done
url="${*: -1}"
echo "$*" >> "$MOCK_STATE_DIR/curl_calls.log"

case "$url" in
  *9898/health*|*/health)
    if [ -f "$MOCK_STATE_DIR/backend_healthy" ]; then
      echo '{"code":200,"msg":"ok","data":{"status":"healthy"}}'
      exit 0
    fi
    exit 7
    ;;
  *.tar.gz.sha256)
    if [ -f "$MOCK_STATE_DIR/artifact_ready" ] && [ -n "$out" ]; then
      cp "$MOCK_STATE_DIR/artifact.tar.gz.sha256" "$out"
      exit 0
    fi
    exit 22
    ;;
  *.tar.gz)
    if [ -f "$MOCK_STATE_DIR/artifact_ready" ] && [ -n "$out" ]; then
      cp "$MOCK_STATE_DIR/artifact.tar.gz" "$out"
      exit 0
    fi
    exit 22
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
# Fixture archive builder -- crafts tar.gz artifacts (including deliberately
# unsafe ones: path traversal, symlink entries) purely with Python's
# tarfile module, so it works identically regardless of whether the host OS
# can create real symlinks (Windows/Git-Bash notoriously can't without
# elevated privileges -- this sidesteps that entirely for archive-safety
# testing specifically).
# ---------------------------------------------------------------------------
PYTHON_BIN="$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)"
if [ -z "$PYTHON_BIN" ]; then
  echo "No python3/python interpreter found -- cannot build test fixture archives." >&2
  exit 1
fi

cat > "$WORK/make_archive.py" <<'PYEOF'
import io
import json
import sys
import tarfile

mode, out_path, sha = sys.argv[1], sys.argv[2], sys.argv[3]


def add(tf, name, data=b"", ttype=tarfile.REGTYPE, linkname=None):
    info = tarfile.TarInfo(name=name)
    info.type = ttype
    if linkname is not None:
        info.linkname = linkname
    if ttype == tarfile.REGTYPE:
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    else:
        tf.addfile(info)


INDEX_HTML = b'<html><body><script src="/assets/app.js"></script></body></html>'
APP_JS = b"console.log(1)"
RELEASE_JSON = json.dumps(
    {"sha": sha, "built_at": "2026-01-01T00:00:00Z", "builder": "github-actions"}
).encode()

with tarfile.open(out_path, "w:gz") as tf:
    if mode == "traversal":
        add(tf, "../evil.txt", b"pwn")
        add(tf, "index.html", INDEX_HTML)
        add(tf, "assets/app.js", APP_JS)
        add(tf, "release.json", RELEASE_JSON)
    elif mode == "symlink":
        add(tf, "index.html", INDEX_HTML)
        add(tf, "assets/app.js", APP_JS)
        add(tf, "assets/evil-link", ttype=tarfile.SYMTYPE, linkname="/etc/passwd")
        add(tf, "release.json", RELEASE_JSON)
    else:
        add(tf, "index.html", INDEX_HTML)
        add(tf, "assets/app.js", APP_JS)
        add(tf, "release.json", RELEASE_JSON)
PYEOF

make_archive() {
  # usage: make_archive <mode: normal|traversal|symlink> <out.tar.gz> <release.json-sha-field>
  "$PYTHON_BIN" "$WORK/make_archive.py" "$1" "$2" "$3"
}

make_checksum() {
  # usage: make_checksum <archive-path> <record-name> <checksum-out-path>
  local archive="$1" record_name="$2" out="$3" hash
  hash="$(sha256sum "$archive" | awk '{print $1}')"
  printf '%s  %s\n' "$hash" "$record_name" > "$out"
}

# usage: prepare_artifact_fixture <case-dir> <mode> <release-json-sha-field> <expected-local-filename-sha> [--corrupt-checksum]
# Populates $MOCK_STATE_DIR/artifact.tar.gz(.sha256) and touches
# artifact_ready, so the mock curl above will "serve" it for any
# admin-h5-dist-*.tar.gz(.sha256) request.
prepare_artifact_fixture() {
  local case_dir="$1" mode="$2" release_sha_field="$3" local_name_sha="$4" corrupt="${5:-}"
  local raw="$case_dir/raw-artifact.tar.gz"
  make_archive "$mode" "$raw" "$release_sha_field"
  make_checksum "$raw" "admin-h5-dist-${local_name_sha}.tar.gz" "$case_dir/raw-artifact.tar.gz.sha256"
  cp "$raw" "$MOCK_STATE_DIR/artifact.tar.gz"
  if [ "$corrupt" = "--corrupt-checksum" ]; then
    local record_name
    record_name="$(awk '{print $2}' "$case_dir/raw-artifact.tar.gz.sha256")"
    printf '%064d  %s\n' 0 "$record_name" > "$MOCK_STATE_DIR/artifact.tar.gz.sha256"
  else
    cp "$case_dir/raw-artifact.tar.gz.sha256" "$MOCK_STATE_DIR/artifact.tar.gz.sha256"
  fi
  touch "$MOCK_STATE_DIR/artifact_ready"
}

# ---------------------------------------------------------------------------
# Fixture repo helpers -- every case gets its own disposable origin + checkout.
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
  ADMIN_RELEASE_ROOT="$CASE_DIR/admin-h5-releases"
  ADMIN_CURRENT="$CASE_DIR/admin-h5-current"
  BACKEND_SERVICE="fake-backend.service"
  BACKEND_HEALTH_URL="http://127.0.0.1:9898/health"
  PRODUCTION_URL="https://example.invalid/"
  MOCK_STATE_DIR="$CASE_DIR/mock-state"
  mkdir -p "$MOCK_STATE_DIR"
  export REPO ADMIN_RELEASE_ROOT ADMIN_CURRENT BACKEND_SERVICE BACKEND_HEALTH_URL PRODUCTION_URL MOCK_STATE_DIR
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
# CASE C -- dry-run never checks out/downloads/restarts/switches
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
assert_true "dry-run never invokes npm" file_absent "$MOCK_STATE_DIR/npm_calls.log"
assert_true "dry-run never downloads anything" file_absent "$MOCK_STATE_DIR/curl_calls.log"
assert_true "dry-run never creates ADMIN_CURRENT" path_absent "$ADMIN_CURRENT"

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
# CASE E -- real atomic symlink swap (admin-only change, via downloaded artifact)
# ---------------------------------------------------------------------------
echo "== CASE E: atomic symlink swap (downloaded artifact) =="
setup_case case-e
OLD_SHA="0000000000000000000000000000000000old1"
make_valid_release "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$OLD_SHA"
ln -sfn "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$ADMIN_CURRENT"
touch "$MOCK_STATE_DIR/frontend_verifiable"
NEW_SHA="$(publish admin-h5/feature.txt hello)"
prepare_artifact_fixture "$CASE_DIR" normal "$NEW_SHA" "$NEW_SHA"
run_deploy
assert_exit "admin-only deploy succeeds" 0 "$LAST_EXIT"
assert_contains "reports DEPLOY_OK" "STATUS=DEPLOY_OK" "$LAST_OUTPUT"
CURRENT_TARGET="$(readlink -f "$ADMIN_CURRENT")"
assert_eq "current points at the new release" "$ADMIN_RELEASE_ROOT/$NEW_SHA" "$CURRENT_TARGET"
assert_true "npm was never invoked" file_absent "$MOCK_STATE_DIR/npm_calls.log"

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
prepare_artifact_fixture "$CASE_DIR" normal "$NEW_SHA" "$NEW_SHA"
# deliberately no backend_healthy marker -> systemctl is-active fails
run_deploy
assert_exit "combined deploy fails when backend unhealthy" 1 "$LAST_EXIT"
assert_contains "reports BACKEND_DEPLOY_FAILED" "BACKEND_DEPLOY_FAILED" "$LAST_OUTPUT"
assert_true "admin release was still downloaded/prepared" test -s "$ADMIN_RELEASE_ROOT/$NEW_SHA/index.html"
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
prepare_artifact_fixture "$CASE_DIR" normal "$NEW_SHA" "$NEW_SHA"
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
# CASE J -- production deploy script contains no executable npm/npx/vite path
# ---------------------------------------------------------------------------
echo "== CASE J: no npm/npx/vite executable path in the production script =="
CODE_ONLY="$(grep -v '^[[:space:]]*#' "$DEPLOY_SCRIPT")"
if grep -Eq '(^|[^a-zA-Z0-9_])(npm|npx|vite)([^a-zA-Z0-9_]|$)' <<<"$CODE_ONLY"; then
  bad "deploy-production.sh must not invoke npm/npx/vite outside comments"
else
  ok "deploy-production.sh has no executable npm/npx/vite build path"
fi

# ---------------------------------------------------------------------------
# CASE K -- artifact not yet published: fail closed before backend/switch
# ---------------------------------------------------------------------------
echo "== CASE K: artifact not yet published =="
setup_case case-k
OLD_SHA="1111111111111111111111111111111111111k"
make_valid_release "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$OLD_SHA"
ln -sfn "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$ADMIN_CURRENT"
publish admin-h5/feature.txt hi >/dev/null
# deliberately never touch artifact_ready
run_deploy
assert_exit "missing artifact exits 1" 1 "$LAST_EXIT"
assert_contains "reports ADMIN_ARTIFACT_NOT_READY" "ADMIN_ARTIFACT_NOT_READY" "$LAST_OUTPUT"
assert_true "backend was never restarted" file_absent "$MOCK_STATE_DIR/systemctl_calls.log"
CURRENT_TARGET="$(readlink -f "$ADMIN_CURRENT")"
assert_eq "current unchanged when artifact is missing" "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$CURRENT_TARGET"

# ---------------------------------------------------------------------------
# CASE L -- valid artifact: checksum verified, release prepared and switched
# ---------------------------------------------------------------------------
echo "== CASE L: valid artifact -- checksum verified, release prepared =="
setup_case case-l
NEW_SHA="$(publish admin-h5/feature.txt hi)"
prepare_artifact_fixture "$CASE_DIR" normal "$NEW_SHA" "$NEW_SHA"
touch "$MOCK_STATE_DIR/frontend_verifiable"
run_deploy
assert_exit "valid artifact deploy succeeds" 0 "$LAST_EXIT"
assert_true "release directory was created" test -s "$ADMIN_RELEASE_ROOT/$NEW_SHA/index.html"
assert_true "release.json records the correct sha" grep -qF "\"sha\": \"$NEW_SHA\"" "$ADMIN_RELEASE_ROOT/$NEW_SHA/release.json"
assert_true "release.json records github-actions as builder" grep -qF '"builder": "github-actions"' "$ADMIN_RELEASE_ROOT/$NEW_SHA/release.json"

# ---------------------------------------------------------------------------
# CASE M -- checksum mismatch fails closed, current unchanged
# ---------------------------------------------------------------------------
echo "== CASE M: checksum mismatch =="
setup_case case-m
OLD_SHA="2222222222222222222222222222222222222m"
make_valid_release "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$OLD_SHA"
ln -sfn "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$ADMIN_CURRENT"
NEW_SHA="$(publish admin-h5/feature.txt hi)"
prepare_artifact_fixture "$CASE_DIR" normal "$NEW_SHA" "$NEW_SHA" --corrupt-checksum
run_deploy
assert_exit "checksum mismatch exits 1" 1 "$LAST_EXIT"
assert_contains "reports BLOCKED_ADMIN_ARTIFACT_CHECKSUM" "BLOCKED_ADMIN_ARTIFACT_CHECKSUM" "$LAST_OUTPUT"
CURRENT_TARGET="$(readlink -f "$ADMIN_CURRENT")"
assert_eq "current unchanged after checksum failure" "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$CURRENT_TARGET"

# ---------------------------------------------------------------------------
# CASE N -- release.json sha mismatch fails closed, current unchanged
# ---------------------------------------------------------------------------
echo "== CASE N: release.json sha mismatch =="
setup_case case-n
OLD_SHA="3333333333333333333333333333333333333n"
make_valid_release "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$OLD_SHA"
ln -sfn "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$ADMIN_CURRENT"
NEW_SHA="$(publish admin-h5/feature.txt hi)"
prepare_artifact_fixture "$CASE_DIR" normal "totally-wrong-sha-value" "$NEW_SHA"
run_deploy
assert_exit "release.json sha mismatch exits 1" 1 "$LAST_EXIT"
assert_contains "reports BLOCKED_INVALID_ADMIN_ARTIFACT" "BLOCKED_INVALID_ADMIN_ARTIFACT" "$LAST_OUTPUT"
CURRENT_TARGET="$(readlink -f "$ADMIN_CURRENT")"
assert_eq "current unchanged after artifact validation failure" "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$CURRENT_TARGET"

# ---------------------------------------------------------------------------
# CASE O -- unsafe archive entries (traversal, symlink) fail closed
# ---------------------------------------------------------------------------
echo "== CASE O: unsafe archive entries =="
setup_case case-o
OLD_SHA="4444444444444444444444444444444444444o"
make_valid_release "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$OLD_SHA"
ln -sfn "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$ADMIN_CURRENT"

NEW_SHA="$(publish admin-h5/feature.txt hi)"
prepare_artifact_fixture "$CASE_DIR" traversal "$NEW_SHA" "$NEW_SHA"
run_deploy
assert_exit "traversal archive exits 1" 1 "$LAST_EXIT"
assert_contains "reports BLOCKED_UNSAFE_ADMIN_ARTIFACT (traversal)" "BLOCKED_UNSAFE_ADMIN_ARTIFACT" "$LAST_OUTPUT"
assert_true "traversal: release dir was never created" path_absent "$ADMIN_RELEASE_ROOT/$NEW_SHA"

rm -f "$MOCK_STATE_DIR/artifact_ready" "$MOCK_STATE_DIR/artifact.tar.gz" "$MOCK_STATE_DIR/artifact.tar.gz.sha256"
NEW_SHA2="$(publish admin-h5/feature2.txt hi2)"
prepare_artifact_fixture "$CASE_DIR" symlink "$NEW_SHA2" "$NEW_SHA2"
run_deploy
assert_exit "symlink archive exits 1" 1 "$LAST_EXIT"
assert_contains "reports BLOCKED_UNSAFE_ADMIN_ARTIFACT (symlink)" "BLOCKED_UNSAFE_ADMIN_ARTIFACT" "$LAST_OUTPUT"
assert_true "symlink: release dir was never created" path_absent "$ADMIN_RELEASE_ROOT/$NEW_SHA2"

CURRENT_TARGET="$(readlink -f "$ADMIN_CURRENT")"
assert_eq "current still unchanged after both unsafe attempts" "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$CURRENT_TARGET"

# ---------------------------------------------------------------------------
# CASE P -- combined admin/backend, artifact fully prepared, backend
# unhealthy: re-certifies the G invariant specifically through the download
# path (backend restart genuinely attempted and genuinely fails here, unlike
# K where the backend is never even reached).
# ---------------------------------------------------------------------------
echo "== CASE P: combined deploy, artifact prepared, backend unhealthy =="
setup_case case-p
OLD_SHA="5555555555555555555555555555555555555p"
make_valid_release "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$OLD_SHA"
ln -sfn "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$ADMIN_CURRENT"
touch "$MOCK_STATE_DIR/frontend_verifiable"
NEW_SHA="$(publish admin-h5/feature.txt hi saas-base/app_marker.py "# backend change")"
prepare_artifact_fixture "$CASE_DIR" normal "$NEW_SHA" "$NEW_SHA"
run_deploy
assert_exit "combined deploy fails when backend unhealthy" 1 "$LAST_EXIT"
assert_contains "reports BACKEND_DEPLOY_FAILED" "BACKEND_DEPLOY_FAILED" "$LAST_OUTPUT"
assert_true "release.json records the correct sha even though never switched live" grep -qF "\"sha\": \"$NEW_SHA\"" "$ADMIN_RELEASE_ROOT/$NEW_SHA/release.json"
assert_true "backend restart was actually attempted" grep -qF "restart" "$MOCK_STATE_DIR/systemctl_calls.log"
CURRENT_TARGET="$(readlink -f "$ADMIN_CURRENT")"
assert_eq "current still points at the OLD release" "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$CURRENT_TARGET"

# ---------------------------------------------------------------------------
# CASE Q -- successful combined deployment: artifact verified, backend
# healthy, atomic switch succeeds, and recent history is retained.
# ---------------------------------------------------------------------------
echo "== CASE Q: successful combined deployment =="
setup_case case-q
OLD_SHA="6666666666666666666666666666666666666q"
make_valid_release "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$OLD_SHA"
ln -sfn "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$ADMIN_CURRENT"
touch "$MOCK_STATE_DIR/frontend_verifiable"
touch "$MOCK_STATE_DIR/backend_healthy"
NEW_SHA="$(publish admin-h5/feature.txt hi saas-base/app_marker.py "# backend change")"
prepare_artifact_fixture "$CASE_DIR" normal "$NEW_SHA" "$NEW_SHA"
run_deploy
assert_exit "combined deploy succeeds" 0 "$LAST_EXIT"
assert_contains "reports DEPLOY_OK" "STATUS=DEPLOY_OK" "$LAST_OUTPUT"
CURRENT_TARGET="$(readlink -f "$ADMIN_CURRENT")"
assert_eq "current now points at the new release" "$ADMIN_RELEASE_ROOT/$NEW_SHA" "$CURRENT_TARGET"
assert_true "the previous release is retained (recent history kept)" test -d "$ADMIN_RELEASE_ROOT/$OLD_SHA"

# ---------------------------------------------------------------------------
# CASE R -- bootstrap mode uses the prebuilt artifact, never builds
# ---------------------------------------------------------------------------
echo "== CASE R: bootstrap uses the prebuilt artifact, never builds =="
setup_case case-r
NEW_SHA="$(publish admin-h5/feature.txt hi)"
prepare_artifact_fixture "$CASE_DIR" normal "$NEW_SHA" "$NEW_SHA"
# Deliberately do NOT set frontend_verifiable -- bootstrap must not depend
# on (or even attempt) the real production HTTP gate.
run_deploy --bootstrap-admin
assert_exit "bootstrap deploy succeeds" 0 "$LAST_EXIT"
assert_contains "reports ADMIN_BOOTSTRAP_READY" "ADMIN_BOOTSTRAP_READY=YES" "$LAST_OUTPUT"
assert_contains "reports PENDING_NGINX_CUTOVER" "ADMIN_HTTP_VERIFICATION=PENDING_NGINX_CUTOVER" "$LAST_OUTPUT"
CURRENT_TARGET="$(readlink -f "$ADMIN_CURRENT")"
assert_eq "current points at the new release" "$ADMIN_RELEASE_ROOT/$NEW_SHA" "$CURRENT_TARGET"
assert_true "bootstrap never invokes npm" file_absent "$MOCK_STATE_DIR/npm_calls.log"

# ---------------------------------------------------------------------------
echo
echo "PASS=$PASS_COUNT FAIL=$FAIL_COUNT"
if [ "$FAIL_COUNT" -gt 0 ]; then
  echo "STATUS=LINUX_INTEGRATION_CONTRACT_FAILED"
  exit 1
fi
echo "STATUS=LINUX_INTEGRATION_CONTRACT_OK"
