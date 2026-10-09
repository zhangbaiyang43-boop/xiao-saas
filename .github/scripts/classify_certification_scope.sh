#!/usr/bin/env bash
# Classifies a pull request for backend certification from the REAL file diff
# between the PR base and the checked-out merge commit (never "the last commit").
#
# Run from the root of the checked-out candidate, after the identity gate.
# Env: CERT_EVENT, PR_BASE_SHA (pull_request only).
#
# Outputs (stdout, and $GITHUB_OUTPUT as scope= / authority_changed=):
#   CERT_SCOPE=AUTHORITY       a CI authority file changed: the PR certifies itself,
#                              the summary fails closed (manual bootstrap review).
#   CERT_SCOPE=BACKEND         anything that is not provably unrelated: full certification.
#   CERT_SCOPE=NOT_APPLICABLE  every changed path is on the unrelated allowlist.
# Fail-safe rule: an unknown path is BACKEND, a diff/parse error is FAIL, and
# NOT_APPLICABLE is only reachable when every path was positively recognised.
#
# CI authority paths (each one decides what is tested, how, or whether it passes):
#   .github/*                                   workflows, scripts, CODEOWNERS, composite
#                                               actions: control triggers, permissions,
#                                               identity, activation and the summary.
#   saas-base/ci/*                              Gate B manifest: selects Gate B tests.
#   saas-base/scripts/ci_backend_gate_runner.py executes Gate A / Gate B.
#   saas-base/tests/test_backend_candidate_certification_workflow_contract.py
#                                               polices the files above.
#   saas-base/{pytest.ini,pyproject.toml,setup.cfg,tox.ini,conftest.py},
#   saas-base/tests/conftest.py                 pytest configuration/plugins decide test
#                                               selection and outcome in Gate A/B/Full.
# NUL-delimited git output is used so spaces, newlines, quotes and non-ASCII names
# are single, exact paths.
set -u

output() {
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    echo "scope=$1" >> "$GITHUB_OUTPUT"
    echo "authority_changed=$2" >> "$GITHUB_OUTPUT"
  fi
}

fail() {
  echo "CERT_SCOPE=FAIL"
  echo "CERT_SCOPE_REASON=$1"
  output FAIL UNKNOWN
  exit 1
}

is_authority() {
  case "$1" in
    .github/*|saas-base/ci/*) return 0 ;;
    saas-base/scripts/ci_backend_gate_runner.py) return 0 ;;
    saas-base/tests/test_backend_candidate_certification_workflow_contract.py) return 0 ;;
    saas-base/pytest.ini|saas-base/pyproject.toml|saas-base/setup.cfg|saas-base/tox.ini) return 0 ;;
    saas-base/conftest.py|saas-base/tests/conftest.py) return 0 ;;
  esac
  return 1
}

is_unrelated() {
  case "$1" in
    docs/*|admin-h5/*|member-mini-client/*|*.md) return 0 ;;
  esac
  return 1
}

case "${CERT_EVENT:-}" in
  workflow_dispatch)
    # An explicit dispatch always runs the full set against the exact SHA.
    echo "CERT_SCOPE=BACKEND"
    echo "CI_AUTHORITY_CHANGE=NOT_EVALUATED"
    output BACKEND NOT_EVALUATED
    exit 0
    ;;
  pull_request) ;;
  *) fail "UNSUPPORTED_CERT_EVENT" ;;
esac

printf '%s' "${PR_BASE_SHA:-}" | grep -Eq '^[0-9a-f]{40}$' || fail "PR_BASE_SHA_INVALID"
git cat-file -e "${PR_BASE_SHA}^{commit}" 2>/dev/null || fail "PR_BASE_COMMIT_UNAVAILABLE"

authority=NO
backend=NO
count=0
paths_file="$(mktemp)" || fail "TEMP_FILE_FAILED"
trap 'rm -f "$paths_file"' EXIT
git -c core.quotepath=false diff --name-only -z --no-renames "$PR_BASE_SHA" HEAD > "$paths_file" || fail "DIFF_FAILED"
while IFS= read -r -d '' path; do
  count=$((count + 1))
  if is_authority "$path"; then
    authority=YES
  elif ! is_unrelated "$path"; then
    backend=YES
  fi
done < "$paths_file"
echo "CHANGED_PATH_COUNT=${count}"

if [ "$authority" = YES ]; then
  echo "CERT_SCOPE=AUTHORITY"
  echo "CI_AUTHORITY_CHANGE=YES"
  echo "PR_GATE_AUTHORITY=NOT_INDEPENDENT"
  output AUTHORITY YES
elif [ "$backend" = YES ] || [ "$count" -eq 0 ]; then
  echo "CERT_SCOPE=BACKEND"
  echo "CI_AUTHORITY_CHANGE=NO"
  output BACKEND NO
else
  echo "CERT_SCOPE=NOT_APPLICABLE"
  echo "CI_AUTHORITY_CHANGE=NO"
  output NOT_APPLICABLE NO
fi
