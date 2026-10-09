#!/usr/bin/env bash
# Decides whether a capability-specific certification gate is ACTIVE, not yet
# active on this baseline, or required-but-missing.
#
# Usage: resolve_certification_activation.sh <mysql|systemd>
# Run from the root of the checked-out candidate. Env:
#   ACTIVATION_BASE_SHA  commit to diff against (PR base SHA, or main's tip for
#                        workflow_dispatch). Must be a 40-hex commit.
#
# A gate is REQUIRED when the candidate touches that capability's trigger paths
# relative to the base. Required + test missing  -> FAIL (never a silent skip).
# Not required + test missing                    -> BASELINE_NOT_ACTIVE (an
# explicit, reported state; the summary never counts it as "B1 verified").
# Test present                                   -> ACTIVE (always executed).
# The trigger is "what the candidate changed", so a candidate cannot opt out by
# deleting or omitting its own test.
set -u

capability="${1:-}"

output() {
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    echo "result=$1" >> "$GITHUB_OUTPUT"
  fi
}

fail() {
  echo "ACTIVATION_${capability}=FAIL"
  echo "ACTIVATION_REASON=$1"
  output FAIL
  exit 1
}

case "$capability" in
  mysql)
    trigger='^saas-base/alembic/versions/|^saas-base/tests/[^/]*_schema_mysql\.py$'
    present="$(git ls-files 'saas-base/tests/test_*_schema_mysql.py')"
    ;;
  systemd)
    trigger='^saas-base/app/core/wxpay_secret_crypto\.py$|^\.github/scripts/verify_keyring_systemd\.sh$'
    present="$(git ls-files 'saas-base/app/core/wxpay_secret_crypto.py')"
    ;;
  *)
    fail "UNKNOWN_CAPABILITY"
    ;;
esac

printf '%s' "${ACTIVATION_BASE_SHA:-}" | grep -Eq '^[0-9a-f]{40}$' || fail "ACTIVATION_BASE_SHA_INVALID"
git cat-file -e "${ACTIVATION_BASE_SHA}^{commit}" 2>/dev/null || fail "ACTIVATION_BASE_COMMIT_UNAVAILABLE"
changed="$(git diff --name-only "$ACTIVATION_BASE_SHA" HEAD)" || fail "ACTIVATION_DIFF_FAILED"

required=NO
if printf '%s\n' "$changed" | grep -Eq "$trigger"; then
  required=YES
fi
echo "ACTIVATION_BASE_SHA=${ACTIVATION_BASE_SHA}"
echo "ACTIVATION_${capability}_REQUIRED=${required}"
echo "ACTIVATION_${capability}_TESTS_PRESENT=$(printf '%s' "$present" | grep -c . )"

if [ -n "$present" ]; then
  echo "ACTIVATION_${capability}=ACTIVE"
  output ACTIVE
elif [ "$required" = YES ]; then
  fail "REQUIRED_TEST_MISSING"
else
  echo "ACTIVATION_${capability}=BASELINE_NOT_ACTIVE"
  output BASELINE_NOT_ACTIVE
fi
