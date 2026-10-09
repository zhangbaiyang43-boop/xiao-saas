#!/usr/bin/env bash
# Verifies the WeChat Pay keyring source policy under a real systemd manager.
#
# Usage: verify_keyring_systemd.sh <path-to-saas-base>
#
# Runs the production loader (app.core.wxpay_secret_crypto.get_keyring) as
# transient systemd services with different UIDs / LoadCredential setups, and
# asserts which keyring sources are trusted. Synthetic keys only.
set -u

# This script runs candidate code as root. It is only acceptable on an ephemeral
# GitHub-hosted runner that holds no production credential, so refuse anywhere else
# before doing anything privileged.
if [ "${GITHUB_ACTIONS:-}" != "true" ] || [ "${RUNNER_ENVIRONMENT:-}" != "github-hosted" ]; then
  echo "REFUSING: must run on a GitHub-hosted runner (GITHUB_ACTIONS=${GITHUB_ACTIONS:-} RUNNER_ENVIRONMENT=${RUNNER_ENVIRONMENT:-})" >&2
  echo "KEYRING_SYSTEMD_GATE=REFUSED"
  exit 1
fi

SAAS_BASE="$(cd "${1:?usage: $0 <saas-base>}" && pwd)"
PY="$(python -c 'import os,sys; print(os.path.realpath(sys.executable))')"
# /opt is world-writable on GitHub runners, which the policy correctly rejects.
WORK=/var/lib/wxpay-keyring-gate
FAILED=0
N=0

sudo rm -rf "$WORK"
sudo mkdir -p "$WORK/code" "$WORK/root-dir" "$WORK/service-dir" "$WORK/writable-dir"
sudo cp -r "$SAAS_BASE/app" "$WORK/code/app"
sudo chmod -R a+rX "$WORK/code"
sudo chmod 0755 "$WORK" "$WORK/root-dir" "$WORK/service-dir"
sudo chmod 0775 "$WORK/writable-dir"

KEYRING_JSON="$("$PY" - <<'PYEOF'
import json
from cryptography.fernet import Fernet
print(json.dumps({"formatVersion": 1, "activeKeyId": "gate-2026-01", "keys": [
    {"keyId": "gate-2026-01", "algorithm": "fernet", "usage": "encrypt-decrypt",
     "key": Fernet.generate_key().decode()}]}))
PYEOF
)"

put() { # put <path> <owner> <mode>
  printf '%s' "$KEYRING_JSON" | sudo tee "$1" > /dev/null
  sudo chown "$2" "$1"
  sudo chmod "$3" "$1"
}

put "$WORK/root-dir/keyring.json" root:root 0600
put "$WORK/root-dir/world-readable.json" root:root 0644
put "$WORK/service-dir/nobody-owned.json" nobody:nogroup 0600
put "$WORK/writable-dir/keyring.json" root:root 0600
sudo ln -s "$WORK/root-dir/keyring.json" "$WORK/root-dir/symlink.json"

PROBE='
from app.core import wxpay_secret_crypto as c
try:
    k = c.get_keyring()
    print("RESULT=CONFIGURED active=" + k.active_key_id)
except c.SecretEncryptionUnavailable as e:
    print("RESULT=" + e.reason_code)
'

scenario() { # scenario <label> <expected RESULT> <keyring path> [extra systemd-run args...]
  local label="$1" expected="$2" keyring_path="$3"
  shift 3
  N=$((N + 1))
  local unit="wxpay-keyring-gate-$N"
  local out
  out="$(sudo systemd-run --quiet --wait --pipe --collect --unit="$unit" \
    -p PrivateTmp=yes -p WorkingDirectory=/tmp \
    -E PYTHONPATH="$WORK/code" \
    -E JWT_SECRET_KEY=ci-only-dummy-signing-key-not-a-real-secret-0123456789abcdef \
    -E REDIS_ENABLED=false \
    -E WXPAY_SECRET_KEYRING_PATH="${keyring_path//@UNIT@/$unit}" \
    "${@//@UNIT@/$unit}" "$PY" -c "$PROBE" 2>&1)"
  if printf '%s\n' "$out" | grep -q "^RESULT=${expected}"; then
    echo "PASS  ${label}: ${expected}"
  else
    echo "FAIL  ${label}: expected ${expected}"
    printf '%s\n' "$out" | sed 's/^/      /'
    namei -lv "${keyring_path//@UNIT@/$unit}" 2>&1 | sed 's/^/      namei: /'
    FAILED=1
  fi
}

# Diagnostic only: how systemd really materializes a LoadCredential file for User=nobody.
sudo systemd-run --quiet --wait --pipe --collect --unit=wxpay-keyring-gate-diag \
  -p User=nobody -p LoadCredential="wxpay-keyring:$WORK/root-dir/keyring.json" \
  /bin/sh -c 'echo "CREDENTIALS_DIRECTORY=$CREDENTIALS_DIRECTORY euid=$(id -u)"; stat -c "DIAG %u:%g %a %h %n" "$CREDENTIALS_DIRECTORY" "$CREDENTIALS_DIRECTORY"/wxpay-keyring; ls -ldn /run /run/credentials; getfacl -p "$CREDENTIALS_DIRECTORY"/wxpay-keyring 2>&1 || true' 2>&1 | sed 's/^/      diag: /'

# Source A: root-only original file, service runs as root.
scenario "root service, root-only file" CONFIGURED "$WORK/root-dir/keyring.json"
# A non-root service cannot be elevated into reading the root-only file.
scenario "nobody service, root-only file" WXPAY_KEYRING_PERMISSION_DENIED "$WORK/root-dir/keyring.json" -p User=nobody
# Source B: systemd LoadCredential copy owned by the service user.
scenario "nobody service, LoadCredential copy" CONFIGURED \
  "/run/credentials/@UNIT@.service/wxpay-keyring" \
  -p User=nobody -p LoadCredential="wxpay-keyring:$WORK/root-dir/keyring.json"
# The same trust is not granted to a service-owned file outside the credentials directory.
scenario "nobody service, nobody-owned file elsewhere" WXPAY_KEYRING_PERMISSION_DENIED "$WORK/service-dir/nobody-owned.json" -p User=nobody
# Env-selected paths cannot widen trust: bad mode, symlink, writable ancestor.
scenario "root service, world-readable file" WXPAY_KEYRING_PERMISSION_DENIED "$WORK/root-dir/world-readable.json"
scenario "root service, symlinked file" WXPAY_KEYRING_PERMISSION_DENIED "$WORK/root-dir/symlink.json"
scenario "root service, group-writable parent directory" WXPAY_KEYRING_PERMISSION_DENIED "$WORK/writable-dir/keyring.json"
scenario "root service, missing file" WXPAY_KEYRING_MISSING "$WORK/root-dir/absent.json"

sudo rm -rf "$WORK"
if [ "$FAILED" -eq 0 ]; then
  echo "KEYRING_SYSTEMD_GATE=PASS"
else
  echo "KEYRING_SYSTEMD_GATE=FAIL"
  exit 1
fi
