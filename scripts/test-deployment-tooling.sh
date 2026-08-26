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
file_not_contains() { ! grep -qF -- "$2" "$1"; }

# Static workflow-contract predicates for admin-h5-release.yml (CASE S) --
# each is a real function taking the workflow file path, no bash -c.
workflow_top_level_read_only() {
  sed -n '1,/^jobs:/p' "$1" | grep -qE 'contents:[[:space:]]*read'
}
workflow_before_publish_has_no_write() {
  ! sed -n '1,/^  publish:/p' "$1" | grep -q 'contents: write'
}
workflow_publish_has_write() {
  sed -n '/^  publish:/,$p' "$1" | grep -q 'contents: write'
}
workflow_publish_guarded_not_pr() {
  sed -n '/^  publish:/,$p' "$1" | grep -qF "github.event_name != 'pull_request'"
}
# Real ordering proof (line-number comparison), not just "both strings
# exist somewhere" -- the incompleteness check must fire before the
# workflow ever attempts to download the existing release's assets.
workflow_incomplete_check_before_download() {
  local file="$1" incomplete_line download_line
  incomplete_line="$(grep -n 'BLOCKED_INCOMPLETE_EXISTING_ADMIN_RELEASE' "$file" | head -n1 | cut -d: -f1)"
  download_line="$(grep -n 'gh release download' "$file" | head -n1 | cut -d: -f1)"
  [ -n "$incomplete_line" ] && [ -n "$download_line" ] && [ "$incomplete_line" -lt "$download_line" ]
}
# Everything before the "publish:" job marker is the (all-events, including
# PR) "build" job -- these predicates prove COS credentials/uploads never
# appear there.
workflow_before_publish_has_no_cos_secrets() {
  ! sed -n '1,/^  publish:/p' "$1" | grep -q 'DEPLOY_COS_SECRET'
}
workflow_cos_upload_only_in_publish_job() {
  sed -n '/^  publish:/,$p' "$1" | grep -qF 'Publish to Tencent COS' \
    && ! sed -n '1,/^  publish:/p' "$1" | grep -qF 'Publish to Tencent COS'
}
workflow_cos_verification_before_summary() {
  local file="$1" verify_line summary_line
  verify_line="$(grep -n '^      - name: Verify public COS runtime URL' "$file" | head -n1 | cut -d: -f1)"
  summary_line="$(grep -n '^      - name: Publish summary' "$file" | head -n1 | cut -d: -f1)"
  [ -n "$verify_line" ] && [ -n "$summary_line" ] && [ "$verify_line" -lt "$summary_line" ]
}

# --- Canonical-artifact predicates (checkout ordering + canonicalization) ---
workflow_publish_checkout_before_artifact_download() {
  local file="$1" section checkout_line download_line
  section="$(sed -n '/^  publish:/,$p' "$file")"
  checkout_line="$(grep -n 'uses: actions/checkout@v4' <<<"$section" | head -n1 | cut -d: -f1)"
  download_line="$(grep -n 'uses: actions/download-artifact@v4' <<<"$section" | head -n1 | cut -d: -f1)"
  [ -n "$checkout_line" ] && [ -n "$download_line" ] && [ "$checkout_line" -lt "$download_line" ]
}
workflow_publish_no_checkout_after_download() {
  local file="$1" section download_line
  section="$(sed -n '/^  publish:/,$p' "$file")"
  download_line="$(grep -n 'uses: actions/download-artifact@v4' <<<"$section" | head -n1 | cut -d: -f1)"
  [ -z "$download_line" ] && return 1
  ! sed -n "$((download_line + 1)),\$p" <<<"$section" | grep -q 'uses: actions/checkout@v4'
}
workflow_canonical_from_remote_when_existing() {
  local file="$1" start end block
  start="$(grep -n 'name: Verify existing release is complete and payload-identical' "$file" | head -n1 | cut -d: -f1)"
  end="$(grep -n '^      - name: Publish GitHub Release$' "$file" | head -n1 | cut -d: -f1)"
  [ -z "$start" ] && return 1
  [ -z "$end" ] && return 1
  block="$(sed -n "${start},${end}p" "$file")"
  grep -qF "cp \"\$REMOTE_DIR/\$ARCHIVE\" \"canonical-build/\$ARCHIVE\"" <<<"$block"
}
workflow_canonical_from_local_when_new() {
  local file="$1" start end block
  start="$(grep -n '^      - name: Publish GitHub Release$' "$file" | head -n1 | cut -d: -f1)"
  end="$(grep -n 'name: Verify canonical artifact checksum' "$file" | head -n1 | cut -d: -f1)"
  [ -z "$start" ] && return 1
  [ -z "$end" ] && return 1
  block="$(sed -n "${start},${end}p" "$file")"
  grep -qF "cp \"local-build/\$ARCHIVE\" \"canonical-build/\$ARCHIVE\"" <<<"$block"
}
workflow_cos_publish_uses_canonical_build() {
  local file="$1" start end block
  start="$(grep -n 'name: Publish to Tencent COS' "$file" | head -n1 | cut -d: -f1)"
  end="$(grep -n 'name: Verify public COS runtime URL' "$file" | head -n1 | cut -d: -f1)"
  [ -z "$start" ] && return 1
  [ -z "$end" ] && return 1
  block="$(sed -n "${start},${end}p" "$file")"
  grep -qF "canonical-build/\$ARCHIVE" <<<"$block" \
    && grep -qF "canonical-build/\$CHECKSUM" <<<"$block" \
    && ! grep -qF "local-build/\$ARCHIVE" <<<"$block" \
    && ! grep -qF "local-build/\$CHECKSUM" <<<"$block"
}
workflow_canonical_checksum_before_cos_publish() {
  local file="$1" verify_line cos_line
  verify_line="$(grep -n 'name: Verify canonical artifact checksum' "$file" | head -n1 | cut -d: -f1)"
  cos_line="$(grep -n 'name: Publish to Tencent COS' "$file" | head -n1 | cut -d: -f1)"
  [ -n "$verify_line" ] && [ -n "$cos_line" ] && [ "$verify_line" -lt "$cos_line" ]
}
# scripts/publish-admin-artifact-cos.py is the core GitHub Release -> Tencent
# COS publisher -- both the push and pull_request path filters must trigger
# this workflow when it changes on its own, independent of admin-h5/**.
workflow_push_paths_contains_cos_publisher() {
  local file="$1"
  sed -n '/^  push:/,/^  pull_request:/p' "$file" | grep -qF "'scripts/publish-admin-artifact-cos.py'"
}
workflow_pull_request_paths_contains_cos_publisher() {
  local file="$1"
  sed -n '/^  pull_request:/,/^  workflow_dispatch:/p' "$file" | grep -qF "'scripts/publish-admin-artifact-cos.py'"
}

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
    elif mode == "hardlink":
        add(tf, "index.html", INDEX_HTML)
        add(tf, "assets/app.js", APP_JS)
        # A hardlink entry pointing at another member of the same archive --
        # tarfile shows this as LNKTYPE, distinct from a regular file even
        # though naive `tar -tvzf` permission-string parsing can't always
        # tell the two apart.
        add(tf, "assets/app-hardlink.js", ttype=tarfile.LNKTYPE, linkname="assets/app.js")
        add(tf, "release.json", RELEASE_JSON)
    elif mode == "doubledot":
        # A legitimate filename containing two literal dots -- must NOT be
        # rejected as if it were a ".." path-traversal component.
        add(tf, "index.html", INDEX_HTML)
        add(tf, "assets/app.js", APP_JS)
        add(tf, "assets/app..js", APP_JS)
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
# Fake qcloud_cos package (CASE AE/AF) -- exercises the real scripts/publish-
# admin-artifact-cos.py end to end (real hashing, real argument parsing,
# real control flow) against a disk-backed fake COS store, so no network
# call and no real credential are ever needed. A separate FAKE_COS_STORE
# directory per invocation keeps cases isolated from each other.
# ---------------------------------------------------------------------------
FAKE_COS_PKG="$WORK/fake_cos_pkg"
mkdir -p "$FAKE_COS_PKG/qcloud_cos"
cat > "$FAKE_COS_PKG/qcloud_cos/__init__.py" <<'PYEOF'
import os

STORE_DIR = os.environ.get("FAKE_COS_STORE", "/tmp/fake_cos_store")


class CosConfig:
    def __init__(self, Region=None, SecretId=None, SecretKey=None, Timeout=None):
        self.region = Region


class _FakeStream:
    def __init__(self, data):
        self._data = data

    def get_raw_stream(self):
        import io
        return io.BytesIO(self._data)


def _path_for(key):
    return os.path.join(STORE_DIR, key.replace("/", "__"))


class CosS3Client:
    def __init__(self, config):
        self.config = config
        os.makedirs(STORE_DIR, exist_ok=True)

    def head_object(self, Bucket, Key):
        from qcloud_cos.cos_exception import CosServiceError
        if not os.path.isfile(_path_for(Key)):
            raise CosServiceError("head_object", "not found", 404)
        return {}

    def get_object(self, Bucket, Key):
        with open(_path_for(Key), "rb") as f:
            return {"Body": _FakeStream(f.read())}

    def put_object(self, Bucket, Body, Key, ContentType=None, CacheControl=None):
        with open(_path_for(Key), "wb") as f:
            f.write(Body)
        return {}
PYEOF
cat > "$FAKE_COS_PKG/qcloud_cos/cos_exception.py" <<'PYEOF'
class CosServiceError(Exception):
    def __init__(self, method, msg, status_code):
        super().__init__(msg)
        self._status_code = status_code

    def get_status_code(self):
        return self._status_code


class CosClientError(Exception):
    pass
PYEOF

# usage: run_cos_publish <sha> <archive> <checksum> <fake-cos-store-dir>
run_cos_publish() {
  local sha="$1" archive="$2" checksum="$3" store="$4"
  mkdir -p "$store"
  set +e
  LAST_OUTPUT="$(PYTHONPATH="$FAKE_COS_PKG" FAKE_COS_STORE="$store" \
    DEPLOY_COS_SECRET_ID=test-id DEPLOY_COS_SECRET_KEY=test-key \
    DEPLOY_COS_REGION=ap-guangzhou DEPLOY_COS_BUCKET=test-bucket \
    DEPLOY_COS_BASE_URL=https://cos.example.invalid \
    "$PYTHON_BIN" "$SCRIPT_DIR/publish-admin-artifact-cos.py" \
    --sha "$sha" --archive "$archive" --checksum "$checksum" 2>&1)"
  LAST_EXIT=$?
  set -e
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
  # Default artifact transport: set via env, exactly like production's
  # "process environment wins" rule -- the mock curl matches on URL suffix
  # (.tar.gz/.tar.gz.sha256) regardless of host, so any value works here.
  # CASE X explicitly unsets this to test the missing-config path; CASE Y/Z
  # exercise the env-vs-config-file precedence directly. Points at a
  # per-case config file that does NOT exist by default (only CASE Z
  # creates one), so no case accidentally depends on a real /etc file.
  ARTIFACT_BASE_URL="https://cos.example.invalid/deploy-artifacts/admin-h5"
  DEPLOY_CONFIG_FILE="$CASE_DIR/xiao-deploy.env"
  export REPO ADMIN_RELEASE_ROOT ADMIN_CURRENT BACKEND_SERVICE BACKEND_HEALTH_URL PRODUCTION_URL MOCK_STATE_DIR ARTIFACT_BASE_URL DEPLOY_CONFIG_FILE
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
# CASE S -- admin-h5-release.yml: PR/build job never holds contents:write
# ---------------------------------------------------------------------------
echo "== CASE S: PR build job has no contents:write =="
RELEASE_WORKFLOW="$SCRIPT_DIR/../.github/workflows/admin-h5-release.yml"
assert_true "release workflow file exists" test -f "$RELEASE_WORKFLOW"
assert_true "workflow default permissions is contents: read" workflow_top_level_read_only "$RELEASE_WORKFLOW"
assert_true "nothing before the publish job holds contents: write" workflow_before_publish_has_no_write "$RELEASE_WORKFLOW"
assert_true "the publish job holds contents: write" workflow_publish_has_write "$RELEASE_WORKFLOW"
assert_true "the publish job is guarded to never run on pull_request" workflow_publish_guarded_not_pr "$RELEASE_WORKFLOW"

# ---------------------------------------------------------------------------
# CASE T -- existing release: self-consistent + correct sha, but payload
# (assets/) actually differs -> must fail closed, never silently reused.
# This contract lives entirely in admin-h5-release.yml's publish job (the
# production-side deploy script never re-derives or compares payloads for
# an *existing* release, it only checks release.json's sha -- see CASE I);
# exercising the real `gh` CLI against a real GitHub Release is out of
# reach for this mktemp-only, no-network suite (see section 9/12 policy),
# so this is verified statically: the exact fail-closed status, and that
# both the index.html and assets/ comparisons are real, not skipped.
# ---------------------------------------------------------------------------
echo "== CASE T: existing release with differing asset payload (workflow-side contract) =="
assert_true "publish job checks for BLOCKED_EXISTING_ADMIN_ARTIFACT_MISMATCH" \
  grep -qF "BLOCKED_EXISTING_ADMIN_ARTIFACT_MISMATCH" "$RELEASE_WORKFLOW"
assert_true "publish job compares index.html byte-for-byte (cmp)" \
  grep -qF "cmp -s" "$RELEASE_WORKFLOW"
assert_true "publish job compares assets/ recursively (diff -qr)" \
  grep -qF "diff -qr" "$RELEASE_WORKFLOW"
assert_true "publish job does not fail on a differing built_at timestamp" \
  grep -qF "built_at legitimately" "$RELEASE_WORKFLOW"

# ---------------------------------------------------------------------------
# CASE U -- existing tag with a missing checksum/archive asset must fail
# closed as incomplete, never be treated as "not published yet, rebuild it".
# ---------------------------------------------------------------------------
echo "== CASE U: existing release missing an asset (workflow-side contract) =="
assert_true "publish job checks for BLOCKED_INCOMPLETE_EXISTING_ADMIN_RELEASE" \
  grep -qF "BLOCKED_INCOMPLETE_EXISTING_ADMIN_RELEASE" "$RELEASE_WORKFLOW"
assert_true "incompleteness is checked before any download of the existing release" \
  workflow_incomplete_check_before_download "$RELEASE_WORKFLOW"

# ---------------------------------------------------------------------------
# CASE V -- a hardlink archive entry fails closed, just like a symlink
# ---------------------------------------------------------------------------
echo "== CASE V: hardlink archive entry =="
setup_case case-v
OLD_SHA="8888888888888888888888888888888888888v"
make_valid_release "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$OLD_SHA"
ln -sfn "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$ADMIN_CURRENT"
NEW_SHA="$(publish admin-h5/feature.txt hi)"
prepare_artifact_fixture "$CASE_DIR" hardlink "$NEW_SHA" "$NEW_SHA"
run_deploy
assert_exit "hardlink archive exits 1" 1 "$LAST_EXIT"
assert_contains "reports BLOCKED_UNSAFE_ADMIN_ARTIFACT (hardlink)" "BLOCKED_UNSAFE_ADMIN_ARTIFACT" "$LAST_OUTPUT"
assert_true "hardlink: release dir was never created" path_absent "$ADMIN_RELEASE_ROOT/$NEW_SHA"
CURRENT_TARGET="$(readlink -f "$ADMIN_CURRENT")"
assert_eq "current unchanged after hardlink rejection" "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$CURRENT_TARGET"

# ---------------------------------------------------------------------------
# CASE W -- a legal filename containing two literal dots must NOT be
# misjudged as a ".." path-traversal component.
# ---------------------------------------------------------------------------
echo "== CASE W: double-dot filename is not unsafe =="
setup_case case-w
NEW_SHA="$(publish admin-h5/feature.txt hi)"
prepare_artifact_fixture "$CASE_DIR" doubledot "$NEW_SHA" "$NEW_SHA"
touch "$MOCK_STATE_DIR/frontend_verifiable"
run_deploy
assert_exit "double-dot filename archive deploys successfully" 0 "$LAST_EXIT"
assert_true "app..js was extracted, not rejected as unsafe" test -f "$ADMIN_RELEASE_ROOT/$NEW_SHA/assets/app..js"

# ---------------------------------------------------------------------------
# CASE X -- production artifact transport not configured fails closed,
# before git pull, before download, before backend restart, before switch.
# ---------------------------------------------------------------------------
echo "== CASE X: artifact transport not configured =="
setup_case case-x
unset ARTIFACT_BASE_URL
# DEPLOY_CONFIG_FILE (from setup_case) deliberately does not exist yet.
OLD_SHA="9999999999999999999999999999999999999x"
make_valid_release "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$OLD_SHA"
ln -sfn "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$ADMIN_CURRENT"
BEFORE_SHA="$(git -C "$REPO" rev-parse HEAD)"
publish admin-h5/feature.txt hi >/dev/null
run_deploy
assert_exit "missing transport config exits 1" 1 "$LAST_EXIT"
assert_contains "reports BLOCKED_ARTIFACT_TRANSPORT_NOT_CONFIGURED" "BLOCKED_ARTIFACT_TRANSPORT_NOT_CONFIGURED" "$LAST_OUTPUT"
AFTER_SHA_CHECK="$(git -C "$REPO" rev-parse HEAD)"
assert_eq "HEAD unchanged (never reached git pull)" "$BEFORE_SHA" "$AFTER_SHA_CHECK"
assert_true "backend was never restarted" file_absent "$MOCK_STATE_DIR/systemctl_calls.log"
assert_true "no download was attempted" file_absent "$MOCK_STATE_DIR/curl_calls.log"
CURRENT_TARGET="$(readlink -f "$ADMIN_CURRENT")"
assert_eq "current unchanged" "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$CURRENT_TARGET"
export ARTIFACT_BASE_URL="https://cos.example.invalid/deploy-artifacts/admin-h5" # restore for subsequent cases

# ---------------------------------------------------------------------------
# CASE Y -- explicit environment ARTIFACT_BASE_URL wins over the config file
# ---------------------------------------------------------------------------
echo "== CASE Y: environment wins over config file =="
setup_case case-y
mkdir -p "$(dirname "$DEPLOY_CONFIG_FILE")"
echo 'ARTIFACT_BASE_URL=https://this-config-file-value-must-be-ignored.invalid' > "$DEPLOY_CONFIG_FILE"
export ARTIFACT_BASE_URL="https://cos.example.invalid/deploy-artifacts/admin-h5" # already set by setup_case; reaffirm intent
touch "$MOCK_STATE_DIR/frontend_verifiable"
NEW_SHA="$(publish admin-h5/feature.txt hi)"
prepare_artifact_fixture "$CASE_DIR" normal "$NEW_SHA" "$NEW_SHA"
run_deploy
assert_exit "deploy succeeds using the env value" 0 "$LAST_EXIT"
assert_true "downloaded from the env URL, not the config-file URL" \
  grep -qF "cos.example.invalid" "$MOCK_STATE_DIR/curl_calls.log"
assert_true "config-file URL was never used" \
  file_not_contains "$MOCK_STATE_DIR/curl_calls.log" "this-config-file-value-must-be-ignored"

# ---------------------------------------------------------------------------
# CASE Z -- ARTIFACT_BASE_URL resolved from the config file when the
# environment doesn't already provide it (single-key parse, not `source`).
# ---------------------------------------------------------------------------
echo "== CASE Z: config file provides ARTIFACT_BASE_URL =="
setup_case case-z
unset ARTIFACT_BASE_URL
mkdir -p "$(dirname "$DEPLOY_CONFIG_FILE")"
cat > "$DEPLOY_CONFIG_FILE" <<'EOF'
# comment line, and an unrelated key, to prove only ARTIFACT_BASE_URL= is parsed
SOME_OTHER_KEY=should-be-ignored
ARTIFACT_BASE_URL=https://cos.example.invalid/deploy-artifacts/admin-h5
EOF
touch "$MOCK_STATE_DIR/frontend_verifiable"
NEW_SHA="$(publish admin-h5/feature.txt hi)"
prepare_artifact_fixture "$CASE_DIR" normal "$NEW_SHA" "$NEW_SHA"
run_deploy
assert_exit "deploy succeeds using the config-file value" 0 "$LAST_EXIT"
assert_contains "reports DEPLOY_OK" "STATUS=DEPLOY_OK" "$LAST_OUTPUT"
export ARTIFACT_BASE_URL="https://cos.example.invalid/deploy-artifacts/admin-h5" # restore for subsequent cases

# ---------------------------------------------------------------------------
# CASE AA -- production deploy script has no executable/default
# github.com/releases/download runtime path (code, not comments)
# ---------------------------------------------------------------------------
echo "== CASE AA: no GitHub Release runtime download path in production script =="
DEPLOY_CODE_ONLY="$(grep -v '^[[:space:]]*#' "$DEPLOY_SCRIPT")"
if grep -qF 'github.com' <<<"$DEPLOY_CODE_ONLY"; then
  bad "deploy-production.sh must not have any executable github.com reference"
else
  ok "deploy-production.sh has no executable github.com reference"
fi

# ---------------------------------------------------------------------------
# CASE AB -- COS URL shape is exactly <base>/admin-h5-<SHA>/admin-h5-dist-<SHA>.tar.gz
# ---------------------------------------------------------------------------
echo "== CASE AB: artifact URL shape =="
setup_case case-ab
touch "$MOCK_STATE_DIR/frontend_verifiable"
NEW_SHA="$(publish admin-h5/feature.txt hi)"
prepare_artifact_fixture "$CASE_DIR" normal "$NEW_SHA" "$NEW_SHA"
run_deploy
assert_exit "deploy succeeds" 0 "$LAST_EXIT"
assert_true "URL shape is exactly <base>/admin-h5-<SHA>/admin-h5-dist-<SHA>.tar.gz" \
  grep -qF "cos.example.invalid/deploy-artifacts/admin-h5/admin-h5-${NEW_SHA}/admin-h5-dist-${NEW_SHA}.tar.gz" \
  "$MOCK_STATE_DIR/curl_calls.log"

# ---------------------------------------------------------------------------
# CASE AC / AD -- COS upload + its secrets exist only in the non-PR publish
# job of admin-h5-release.yml, never in the all-events build job.
# ---------------------------------------------------------------------------
echo "== CASE AC/AD: COS upload and its secrets are publish-job-only =="
assert_true "COS upload step exists only in the publish job" \
  workflow_cos_upload_only_in_publish_job "$RELEASE_WORKFLOW"
assert_true "no DEPLOY_COS_SECRET_* reference before the publish job (build/PR section)" \
  workflow_before_publish_has_no_cos_secrets "$RELEASE_WORKFLOW"

# ---------------------------------------------------------------------------
# CASE AE -- existing COS object, same sha256 content -> reuse (real script,
# fake disk-backed COS store, no network).
# ---------------------------------------------------------------------------
echo "== CASE AE: existing COS artifact with identical content is reused =="
COS_STORE_AE="$WORK/cos-store-ae"
echo "archive payload for AE" > "$WORK/ae-archive.tar.gz"
sha256sum "$WORK/ae-archive.tar.gz" | awk '{print $1"  admin-h5-dist-shaAE.tar.gz"}' > "$WORK/ae-archive.tar.gz.sha256"
run_cos_publish shaAE "$WORK/ae-archive.tar.gz" "$WORK/ae-archive.tar.gz.sha256" "$COS_STORE_AE"
assert_exit "first publish succeeds" 0 "$LAST_EXIT"
run_cos_publish shaAE "$WORK/ae-archive.tar.gz" "$WORK/ae-archive.tar.gz.sha256" "$COS_STORE_AE"
assert_exit "second publish with identical content is reused, not blocked" 0 "$LAST_EXIT"
assert_contains "reports COS_ARTIFACT_READY" "STATUS=COS_ARTIFACT_READY" "$LAST_OUTPUT"

# ---------------------------------------------------------------------------
# CASE AF -- existing COS object, same sha, differing payload -> fail closed
# ---------------------------------------------------------------------------
echo "== CASE AF: existing COS artifact with differing payload fails closed =="
COS_STORE_AF="$WORK/cos-store-af"
echo "original payload for AF" > "$WORK/af-archive.tar.gz"
sha256sum "$WORK/af-archive.tar.gz" | awk '{print $1"  admin-h5-dist-shaAF.tar.gz"}' > "$WORK/af-archive.tar.gz.sha256"
run_cos_publish shaAF "$WORK/af-archive.tar.gz" "$WORK/af-archive.tar.gz.sha256" "$COS_STORE_AF"
assert_exit "first publish succeeds" 0 "$LAST_EXIT"
echo "DIFFERENT payload for AF" > "$WORK/af-archive.tar.gz"
sha256sum "$WORK/af-archive.tar.gz" | awk '{print $1"  admin-h5-dist-shaAF.tar.gz"}' > "$WORK/af-archive.tar.gz.sha256"
run_cos_publish shaAF "$WORK/af-archive.tar.gz" "$WORK/af-archive.tar.gz.sha256" "$COS_STORE_AF"
assert_exit "second publish with different content is blocked" 1 "$LAST_EXIT"
assert_contains "reports BLOCKED_EXISTING_COS_ARTIFACT_MISMATCH" "BLOCKED_EXISTING_COS_ARTIFACT_MISMATCH" "$LAST_OUTPUT"

# ---------------------------------------------------------------------------
# CASE AG -- public COS round-trip verification step precedes the workflow's
# final success summary (static ordering proof; real network round-trip
# against a live COS bucket is out of reach for this suite).
# ---------------------------------------------------------------------------
echo "== CASE AG: public COS round-trip verification precedes summary =="
assert_true "verification step exists" \
  grep -qF -- '- name: Verify public COS runtime URL' "$RELEASE_WORKFLOW"
assert_true "verification does a real sha256sum -c against the public URL download" \
  grep -qF "sha256sum -c \"\$CHECKSUM\"" "$RELEASE_WORKFLOW"
assert_true "verification step precedes the summary step" \
  workflow_cos_verification_before_summary "$RELEASE_WORKFLOW"

# ---------------------------------------------------------------------------
# CASE AH -- publish job's checkout happens before actions/download-artifact,
# and there is no second checkout after the artifact download (checkout can
# clean/reset the workspace; downloading first then checking out risks the
# checkout wiping local-build/ out from under the rest of the job).
# ---------------------------------------------------------------------------
echo "== CASE AH: publish job checks out before downloading the build artifact =="
assert_true "checkout precedes actions/download-artifact" \
  workflow_publish_checkout_before_artifact_download "$RELEASE_WORKFLOW"
assert_true "no checkout occurs after the artifact download" \
  workflow_publish_no_checkout_after_download "$RELEASE_WORKFLOW"

# ---------------------------------------------------------------------------
# CASE AI -- rerun of the same SHA: the existing GitHub Release is accepted
# (semantic payload match), and canonical-build is populated from THAT
# release's own bytes, never this run's fresh local rebuild (which can
# legitimately differ byte-for-byte -- built_at, tar/gzip metadata -- even
# for an identical source SHA). Static: real GitHub Release network round-
# trip is out of reach for this suite (see CASE T/U).
# ---------------------------------------------------------------------------
echo "== CASE AI: existing-release rerun canonicalizes to remote bytes =="
assert_true "canonical-build is populated from \$REMOTE_DIR when reusing an existing release" \
  workflow_canonical_from_remote_when_existing "$RELEASE_WORKFLOW"
assert_true "canonical-build is populated from local-build only for a newly-created release" \
  workflow_canonical_from_local_when_new "$RELEASE_WORKFLOW"

# ---------------------------------------------------------------------------
# CASE AJ -- the COS publisher step is only ever given canonical-build
# paths, never local-build paths directly.
# ---------------------------------------------------------------------------
echo "== CASE AJ: COS publish step receives canonical-build, not local-build =="
assert_true "COS publish step uses canonical-build/\$ARCHIVE and canonical-build/\$CHECKSUM only" \
  workflow_cos_publish_uses_canonical_build "$RELEASE_WORKFLOW"

# ---------------------------------------------------------------------------
# CASE AK -- the canonical artifact's checksum is verified before it is ever
# handed to the COS publisher.
# ---------------------------------------------------------------------------
echo "== CASE AK: canonical checksum verified immediately before COS publish =="
assert_true "canonical checksum verification step exists" \
  grep -qF 'name: Verify canonical artifact checksum' "$RELEASE_WORKFLOW"
assert_true "canonical checksum step runs a real sha256sum -c" \
  grep -qF 'cd canonical-build && sha256sum -c' "$RELEASE_WORKFLOW"
assert_true "canonical checksum verification precedes the COS publish step" \
  workflow_canonical_checksum_before_cos_publish "$RELEASE_WORKFLOW"

# ---------------------------------------------------------------------------
# CASE AL -- rerunning the same SHA must not produce a false
# BLOCKED_EXISTING_COS_ARTIFACT_MISMATCH: because canonicalization (CASE AI)
# always feeds COS the SAME already-published bytes on every rerun of a
# given SHA -- never a fresh, potentially-different local rebuild -- the
# real publish-admin-artifact-cos.py script sees identical content both
# times and reuses cleanly. Real script, fake disk-backed COS store, no
# network -- exercises the actual mechanism CASE AI's static check proves
# the workflow wires up correctly.
# ---------------------------------------------------------------------------
echo "== CASE AL: same-SHA rerun via canonical bytes does not false-mismatch =="
COS_STORE_AL="$WORK/cos-store-al"
echo "canonical payload for AL (this is what canonical-build/ would always contain, regardless of what a fresh local rebuild produced)" > "$WORK/al-canonical.tar.gz"
sha256sum "$WORK/al-canonical.tar.gz" | awk '{print $1"  admin-h5-dist-shaAL.tar.gz"}' > "$WORK/al-canonical.tar.gz.sha256"
run_cos_publish shaAL "$WORK/al-canonical.tar.gz" "$WORK/al-canonical.tar.gz.sha256" "$COS_STORE_AL"
assert_exit "first run (new GitHub Release) publishes canonical bytes" 0 "$LAST_EXIT"
# "Rerun" hands the exact same canonical bytes again (as the real workflow
# would, having re-derived them from the existing GitHub Release rather
# than from a fresh, possibly-different rebuild).
run_cos_publish shaAL "$WORK/al-canonical.tar.gz" "$WORK/al-canonical.tar.gz.sha256" "$COS_STORE_AL"
assert_exit "rerun with the same canonical bytes is reused, not blocked" 0 "$LAST_EXIT"
assert_contains "rerun reports COS_ARTIFACT_READY, not a mismatch" "STATUS=COS_ARTIFACT_READY" "$LAST_OUTPUT"

# ---------------------------------------------------------------------------
# CASE AM -- admin-h5-release.yml's push.paths must trigger on a standalone
# change to scripts/publish-admin-artifact-cos.py (it's the core GitHub
# Release -> Tencent COS production artifact transport publisher now).
# ---------------------------------------------------------------------------
echo "== CASE AM: push.paths contains scripts/publish-admin-artifact-cos.py =="
assert_true "push.paths triggers on publish-admin-artifact-cos.py" \
  workflow_push_paths_contains_cos_publisher "$RELEASE_WORKFLOW"

# ---------------------------------------------------------------------------
# CASE AN -- same closure for pull_request.paths, so a PR touching only the
# publisher gets build-only verification.
# ---------------------------------------------------------------------------
echo "== CASE AN: pull_request.paths contains scripts/publish-admin-artifact-cos.py =="
assert_true "pull_request.paths triggers on publish-admin-artifact-cos.py" \
  workflow_pull_request_paths_contains_cos_publisher "$RELEASE_WORKFLOW"

# ---------------------------------------------------------------------------
# CASE AO -- DEPLOY_CONFIG_FILE exists with unrelated keys/comments but no
# ARTIFACT_BASE_URL= line: resolve_artifact_base_url's grep must not exit
# the whole script under `set -Eeuo pipefail` when it finds no match. Must
# still fail closed into BLOCKED_ARTIFACT_TRANSPORT_NOT_CONFIGURED, exactly
# like a missing config file (CASE X), not crash some other way.
# ---------------------------------------------------------------------------
echo "== CASE AO: config file exists but has no ARTIFACT_BASE_URL key =="
setup_case case-ao
unset ARTIFACT_BASE_URL
mkdir -p "$(dirname "$DEPLOY_CONFIG_FILE")"
cat > "$DEPLOY_CONFIG_FILE" <<'EOF'
# comment line, and an unrelated key -- deliberately no ARTIFACT_BASE_URL=
SOME_OTHER_KEY=should-be-ignored
EOF
OLD_SHA="aaaa1111111111111111111111111111111ao"
make_valid_release "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$OLD_SHA"
ln -sfn "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$ADMIN_CURRENT"
BEFORE_SHA="$(git -C "$REPO" rev-parse HEAD)"
publish admin-h5/feature.txt hi >/dev/null
run_deploy
assert_exit "missing key exits 1" 1 "$LAST_EXIT"
assert_contains "reports BLOCKED_ARTIFACT_TRANSPORT_NOT_CONFIGURED" "BLOCKED_ARTIFACT_TRANSPORT_NOT_CONFIGURED" "$LAST_OUTPUT"
AFTER_SHA_CHECK="$(git -C "$REPO" rev-parse HEAD)"
assert_eq "HEAD unchanged (never reached git pull)" "$BEFORE_SHA" "$AFTER_SHA_CHECK"
assert_true "backend was never restarted" file_absent "$MOCK_STATE_DIR/systemctl_calls.log"
CURRENT_TARGET="$(readlink -f "$ADMIN_CURRENT")"
assert_eq "current unchanged" "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$CURRENT_TARGET"
export ARTIFACT_BASE_URL="https://cos.example.invalid/deploy-artifacts/admin-h5" # restore for subsequent cases

# ---------------------------------------------------------------------------
# CASE AP -- DEPLOY_CONFIG_FILE contains ARTIFACT_BASE_URL= with an empty
# value: must fail closed the same way as a missing key, not resolve to an
# empty-string transport base.
# ---------------------------------------------------------------------------
echo "== CASE AP: config file has ARTIFACT_BASE_URL with an empty value =="
setup_case case-ap
unset ARTIFACT_BASE_URL
mkdir -p "$(dirname "$DEPLOY_CONFIG_FILE")"
printf 'ARTIFACT_BASE_URL=\n' > "$DEPLOY_CONFIG_FILE"
OLD_SHA="aaaa2222222222222222222222222222222ap"
make_valid_release "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$OLD_SHA"
ln -sfn "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$ADMIN_CURRENT"
BEFORE_SHA="$(git -C "$REPO" rev-parse HEAD)"
publish admin-h5/feature.txt hi >/dev/null
run_deploy
assert_exit "empty value exits 1" 1 "$LAST_EXIT"
assert_contains "reports BLOCKED_ARTIFACT_TRANSPORT_NOT_CONFIGURED" "BLOCKED_ARTIFACT_TRANSPORT_NOT_CONFIGURED" "$LAST_OUTPUT"
AFTER_SHA_CHECK="$(git -C "$REPO" rev-parse HEAD)"
assert_eq "HEAD unchanged (never reached git pull)" "$BEFORE_SHA" "$AFTER_SHA_CHECK"
assert_true "backend was never restarted" file_absent "$MOCK_STATE_DIR/systemctl_calls.log"
CURRENT_TARGET="$(readlink -f "$ADMIN_CURRENT")"
assert_eq "current unchanged" "$ADMIN_RELEASE_ROOT/$OLD_SHA" "$CURRENT_TARGET"
export ARTIFACT_BASE_URL="https://cos.example.invalid/deploy-artifacts/admin-h5" # restore for subsequent cases

# ---------------------------------------------------------------------------
echo
echo "PASS=$PASS_COUNT FAIL=$FAIL_COUNT"
if [ "$FAIL_COUNT" -gt 0 ]; then
  echo "STATUS=LINUX_INTEGRATION_CONTRACT_FAILED"
  exit 1
fi
echo "STATUS=LINUX_INTEGRATION_CONTRACT_OK"
