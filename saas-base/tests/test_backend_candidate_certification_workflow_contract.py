from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "backend-candidate-certification.yml"
)


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_backend_candidate_certification_supports_safe_pull_requests() -> None:
    text = _workflow_text()

    assert "pull_request:" in text
    assert "branches: [main]" in text
    assert "types: [opened, synchronize, reopened]" in text
    assert "pull_request_target" not in text
    assert "permissions:\n  contents: read" in text
    assert "contents: write" not in text
    assert "actions: write" not in text
    assert "packages: write" not in text
    assert "pull-requests: write" not in text


def test_backend_candidate_certification_normalizes_event_identity_once() -> None:
    text = _workflow_text()

    assert "CERT_EVENT: ${{ github.event_name }}" in text
    assert (
        "TARGET_REF: ${{ github.event_name == 'pull_request' "
        "&& github.ref || inputs.target_ref }}"
    ) in text
    assert "PR_HEAD_SHA: ${{ github.event_name == 'pull_request'" in text
    assert "github.event.pull_request.head.sha" in text
    assert "PR_BASE_SHA: ${{ github.event_name == 'pull_request'" in text
    assert "github.event.pull_request.base.sha" in text
    assert text.count("ref: ${{ env.TARGET_REF }}") == 3
    assert "CHECKED_OUT_SHA=${GATE_A_CHECKED_OUT_SHA}" in text
    assert "CERTIFICATION_CHECKOUT_SHA_MISMATCH" in text


def test_backend_candidate_certification_keeps_all_authoritative_gates() -> None:
    text = _workflow_text()

    assert "Gate A (candidate's own new/changed backend tests)" in text
    assert "--paths-file gate-a-files.txt" in text
    assert "Gate B (cumulative P0 contracts + static core regression)" in text
    assert "--paths-file gate-b-combined.txt" in text
    assert "Backend Full (serial, authoritative -- same semantics as backend-full.yml)" in text
    assert "python -m pytest tests/ --collect-only -q" in text
    assert "python -m pytest tests/ -q -W error::RuntimeWarning" in text
    assert "needs: [gate-a, gate-b, full]" in text
    assert "CANDIDATE_CERTIFIED=YES" in text
