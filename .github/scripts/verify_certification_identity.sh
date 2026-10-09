#!/usr/bin/env bash
# Hard identity gate for Backend Candidate Certification.
#
# Run from inside the checked-out candidate repository. Inputs (env):
#   CERT_EVENT    pull_request | workflow_dispatch
#   PR_BASE_SHA   github.event.pull_request.base.sha   (pull_request only)
#   PR_HEAD_SHA   github.event.pull_request.head.sha   (pull_request only)
#   GITHUB_SHA    the event's proposed merge commit     (pull_request only)
#   TARGET_REF    dispatch target_ref                   (workflow_dispatch only)
#
# pull_request: the checked-out HEAD must be the proposed merge commit whose
# first parent is exactly PR_BASE_SHA and whose second parent is exactly
# PR_HEAD_SHA. Printing the SHAs is not enough; every one is compared.
# workflow_dispatch: remains an exact-SHA certification and is never reported
# as a PR merge-ref certification.
set -u

output() {
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    echo "result=$1" >> "$GITHUB_OUTPUT"
  fi
}

fail() {
  echo "PR_IDENTITY_GATE=FAIL"
  echo "PR_IDENTITY_REASON=$1"
  output FAIL
  exit 1
}

is_sha() {
  printf '%s' "$1" | grep -Eq '^[0-9a-f]{40}$'
}

CHECKED_OUT_SHA="$(git rev-parse HEAD 2>/dev/null)" || fail GIT_HEAD_UNREADABLE
is_sha "$CHECKED_OUT_SHA" || fail GIT_HEAD_NOT_A_SHA
echo "CERT_EVENT=${CERT_EVENT:-}"
echo "CHECKED_OUT_SHA=${CHECKED_OUT_SHA}"

case "${CERT_EVENT:-}" in
  pull_request)
    echo "PR_BASE_SHA=${PR_BASE_SHA:-}"
    echo "PR_HEAD_SHA=${PR_HEAD_SHA:-}"
    echo "EVENT_MERGE_SHA=${GITHUB_SHA:-}"
    [ -n "${PR_BASE_SHA:-}" ] || fail PR_BASE_SHA_EMPTY
    [ -n "${PR_HEAD_SHA:-}" ] || fail PR_HEAD_SHA_EMPTY
    is_sha "$PR_BASE_SHA" || fail PR_BASE_SHA_MALFORMED
    is_sha "$PR_HEAD_SHA" || fail PR_HEAD_SHA_MALFORMED
    [ -n "${GITHUB_SHA:-}" ] || fail EVENT_MERGE_SHA_EMPTY
    [ "$CHECKED_OUT_SHA" = "$GITHUB_SHA" ] || fail CHECKED_OUT_NOT_EVENT_MERGE_COMMIT
    # Read the raw commit object: shallow clones hide parents from rev-list.
    parents="$(git cat-file commit HEAD | awk '/^$/ {exit} /^parent / {print $2}')"
    parent_count="$(printf '%s\n' "$parents" | grep -c .)"
    echo "PARENT_COUNT=${parent_count}"
    [ "$parent_count" -eq 2 ] || fail "MERGE_PARENT_COUNT_${parent_count}_NOT_2"
    first_parent="$(printf '%s\n' "$parents" | sed -n 1p)"
    second_parent="$(printf '%s\n' "$parents" | sed -n 2p)"
    echo "FIRST_PARENT=${first_parent}"
    echo "SECOND_PARENT=${second_parent}"
    [ "$first_parent" = "$PR_BASE_SHA" ] || fail FIRST_PARENT_NOT_PR_BASE_SHA
    [ "$second_parent" = "$PR_HEAD_SHA" ] || fail SECOND_PARENT_NOT_PR_HEAD_SHA
    echo "PR_IDENTITY_GATE=PASS"
    echo "CERT_MODE=PR_MERGE_REF"
    output PASS
    ;;
  workflow_dispatch)
    if is_sha "${TARGET_REF:-}"; then
      [ "$CHECKED_OUT_SHA" = "$TARGET_REF" ] || fail DISPATCH_TARGET_SHA_MISMATCH
    fi
    echo "PR_IDENTITY_GATE=NOT_APPLICABLE"
    echo "CERT_MODE=DISPATCH_SHA_CERTIFICATION"
    echo "PR_MERGE_REF_CERTIFIED=NO"
    output NOT_APPLICABLE
    ;;
  *)
    fail "UNSUPPORTED_CERT_EVENT"
    ;;
esac
