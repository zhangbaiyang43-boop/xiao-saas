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
#
# Paths are read NUL-delimited with quoting disabled, so spaces, newlines and
# non-ASCII names (e.g. a Chinese migration file name) are exact single paths and
# can neither hide a trigger nor be split into a fake one.
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

is_trigger() {
  case "$capability:$1" in
    mysql:saas-base/alembic/versions/*) return 0 ;;
    mysql:saas-base/tests/*_schema_mysql.py)
      # a file directly in tests/, not a nested path
      [ "${1#saas-base/tests/}" = "${1##*/}" ] && return 0
      return 1
      ;;
    systemd:saas-base/app/core/wxpay_secret_crypto.py) return 0 ;;
  esac
  return 1
}

case "$capability" in
  mysql) present_spec='saas-base/tests/test_*_schema_mysql.py' ;;
  systemd) present_spec='saas-base/app/core/wxpay_secret_crypto.py' ;;
  *) fail "UNKNOWN_CAPABILITY" ;;
esac

printf '%s' "${ACTIVATION_BASE_SHA:-}" | grep -Eq '^[0-9a-f]{40}$' || fail "ACTIVATION_BASE_SHA_INVALID"
git cat-file -e "${ACTIVATION_BASE_SHA}^{commit}" 2>/dev/null || fail "ACTIVATION_BASE_COMMIT_UNAVAILABLE"

paths_file="$(mktemp)" || fail "TEMP_FILE_FAILED"
trap 'rm -f "$paths_file"' EXIT
git -c core.quotepath=false diff --name-only -z --no-renames "$ACTIVATION_BASE_SHA" HEAD > "$paths_file" || fail "ACTIVATION_DIFF_FAILED"

required=NO
while IFS= read -r -d '' path; do
  if is_trigger "$path"; then
    required=YES
  fi
done < "$paths_file"

present_count=0
while IFS= read -r -d '' _; do
  present_count=$((present_count + 1))
done < <(git -c core.quotepath=false ls-files -z -- "$present_spec")

echo "ACTIVATION_BASE_SHA=${ACTIVATION_BASE_SHA}"
echo "ACTIVATION_${capability}_REQUIRED=${required}"
echo "ACTIVATION_${capability}_TESTS_PRESENT=${present_count}"

if [ "$present_count" -gt 0 ]; then
  echo "ACTIVATION_${capability}=ACTIVE"
  output ACTIVE
elif [ "$required" = YES ]; then
  fail "REQUIRED_TEST_MISSING"
else
  echo "ACTIVATION_${capability}=BASELINE_NOT_ACTIVE"
  output BASELINE_NOT_ACTIVE
fi
