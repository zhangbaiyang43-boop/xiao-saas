import os
import shutil
import subprocess
from pathlib import Path

import pytest


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
    assert text.count("ref: ${{ env.TARGET_REF }}") == 5
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
    assert "MySQL 5.7 schema convergence" in text
    assert "Verify Alembic convergence on MySQL 5.7" in text
    assert "needs: [gate-a, gate-b, full, mysql-schema, keyring-systemd]" in text
    assert "CANDIDATE_CERTIFIED=YES" in text
    assert "CERTIFICATION_SUMMARY=PASS" in text
    assert "CERTIFICATION_SUMMARY=FAIL" in text


REPO_ROOT = Path(__file__).resolve().parents[2]
IDENTITY_SCRIPT = REPO_ROOT / ".github" / "scripts" / "verify_certification_identity.sh"
BASH = shutil.which("bash")
GIT = shutil.which("git")


def test_every_authoritative_job_runs_the_identity_gate_and_summary_requires_it() -> None:
    text = _workflow_text()

    assert text.count("name: PR merge-ref identity gate") == 5
    assert text.count("verify_certification_identity.sh") == 5
    assert text.count("pr_identity_gate: ${{ steps.pr_identity.outputs.result }}") == 5
    for job in ("gate-a", "gate-b", "full", "mysql-schema", "keyring-systemd"):
        assert f"needs.{job}.outputs.pr_identity_gate" in text
    assert "EXPECTED_IDENTITY=PASS" in text
    assert "EXPECTED_IDENTITY=NOT_APPLICABLE" in text
    assert 'echo "PR_IDENTITY_GATE=FAIL"' in text
    assert "PR_MERGE_REF_CERTIFIED=NO" in text
    assert "KEYRING_SYSTEMD_RESULT" in text
    assert "MYSQL_SCHEMA_RESULT" in text


def test_keyring_systemd_job_runs_the_real_systemd_probe() -> None:
    text = _workflow_text()

    assert "Keyring source policy under real systemd" in text
    assert "verify_keyring_systemd.sh saas-base" in text


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        [GIT, *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env=dict(
            os.environ,
            GIT_AUTHOR_NAME="t",
            GIT_AUTHOR_EMAIL="t@example.invalid",
            GIT_COMMITTER_NAME="t",
            GIT_COMMITTER_EMAIL="t@example.invalid",
            GIT_CONFIG_GLOBAL=os.devnull,
        ),
    )
    return result.stdout.strip()


def _build_merge_repo(tmp_path: Path) -> dict:
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a.txt").write_text("base\n")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-q", "-m", "base")
    old_base = _git(tmp_path, "rev-parse", "HEAD")
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    (tmp_path / "b.txt").write_text("feature\n")
    _git(tmp_path, "add", "b.txt")
    _git(tmp_path, "commit", "-q", "-m", "feature")
    head = _git(tmp_path, "rev-parse", "HEAD")
    _git(tmp_path, "checkout", "-q", "main")
    (tmp_path / "c.txt").write_text("main moved\n")
    _git(tmp_path, "add", "c.txt")
    _git(tmp_path, "commit", "-q", "-m", "main moved")
    base = _git(tmp_path, "rev-parse", "HEAD")
    _git(tmp_path, "merge", "-q", "--no-ff", "-m", "merge", "feature")
    merge = _git(tmp_path, "rev-parse", "HEAD")
    return {"old_base": old_base, "base": base, "head": head, "merge": merge}


def _run_gate(cwd: Path, **environment: str) -> subprocess.CompletedProcess:
    env = {key: value for key, value in os.environ.items() if key not in {"GITHUB_OUTPUT", "GITHUB_SHA"}}
    env.update(environment)
    return subprocess.run([BASH, str(IDENTITY_SCRIPT)], cwd=cwd, env=env, capture_output=True, text=True)


def _pr_env(shas: dict, **overrides: str) -> dict:
    env = {
        "CERT_EVENT": "pull_request",
        "PR_BASE_SHA": shas["base"],
        "PR_HEAD_SHA": shas["head"],
        "GITHUB_SHA": shas["merge"],
    }
    env.update(overrides)
    return env


@pytest.mark.skipif(not BASH or not GIT or os.name == "nt", reason="needs POSIX bash and git")
class TestPullRequestIdentityGateBehavior:
    def test_true_merge_ref_passes(self, tmp_path):
        shas = _build_merge_repo(tmp_path)
        result = _run_gate(tmp_path, **_pr_env(shas))
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PR_IDENTITY_GATE=PASS" in result.stdout

    def test_stale_base_sha_fails(self, tmp_path):
        shas = _build_merge_repo(tmp_path)
        result = _run_gate(tmp_path, **_pr_env(shas, PR_BASE_SHA=shas["old_base"]))
        assert result.returncode == 1
        assert "PR_IDENTITY_GATE=FAIL" in result.stdout
        assert "FIRST_PARENT_NOT_PR_BASE_SHA" in result.stdout

    def test_wrong_head_sha_fails(self, tmp_path):
        shas = _build_merge_repo(tmp_path)
        result = _run_gate(tmp_path, **_pr_env(shas, PR_HEAD_SHA=shas["base"]))
        assert result.returncode == 1
        assert "SECOND_PARENT_NOT_PR_HEAD_SHA" in result.stdout

    def test_swapped_parents_fail(self, tmp_path):
        shas = _build_merge_repo(tmp_path)
        result = _run_gate(tmp_path, **_pr_env(shas, PR_BASE_SHA=shas["head"], PR_HEAD_SHA=shas["base"]))
        assert result.returncode == 1

    def test_empty_shas_fail(self, tmp_path):
        shas = _build_merge_repo(tmp_path)
        for name in ("PR_BASE_SHA", "PR_HEAD_SHA", "GITHUB_SHA"):
            result = _run_gate(tmp_path, **_pr_env(shas, **{name: ""}))
            assert result.returncode == 1, name
            assert "PR_IDENTITY_GATE=FAIL" in result.stdout

    def test_non_merge_head_fails_even_when_event_shas_look_right(self, tmp_path):
        shas = _build_merge_repo(tmp_path)
        _git(tmp_path, "checkout", "-q", "--detach", shas["head"])
        result = _run_gate(tmp_path, **_pr_env(shas, GITHUB_SHA=shas["head"]))
        assert result.returncode == 1
        assert "MERGE_PARENT_COUNT_1_NOT_2" in result.stdout

    def test_checked_out_commit_must_be_the_event_merge_commit(self, tmp_path):
        shas = _build_merge_repo(tmp_path)
        result = _run_gate(tmp_path, **_pr_env(shas, GITHUB_SHA=shas["head"]))
        assert result.returncode == 1
        assert "CHECKED_OUT_NOT_EVENT_MERGE_COMMIT" in result.stdout

    def test_shallow_checkout_still_sees_both_parents(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        shas = _build_merge_repo(source)
        clone = tmp_path / "shallow"
        _git(tmp_path, "clone", "-q", "--depth", "1", f"file://{source}", str(clone))
        result = _run_gate(clone, **_pr_env(shas))
        assert result.returncode == 0, result.stdout + result.stderr

    def test_dispatch_is_sha_certification_never_pr_certification(self, tmp_path):
        shas = _build_merge_repo(tmp_path)
        result = _run_gate(tmp_path, CERT_EVENT="workflow_dispatch", TARGET_REF=shas["merge"])
        assert result.returncode == 0
        assert "PR_IDENTITY_GATE=NOT_APPLICABLE" in result.stdout
        assert "PR_MERGE_REF_CERTIFIED=NO" in result.stdout
        assert "PR_IDENTITY_GATE=PASS" not in result.stdout

    def test_dispatch_with_wrong_target_sha_fails(self, tmp_path):
        shas = _build_merge_repo(tmp_path)
        result = _run_gate(tmp_path, CERT_EVENT="workflow_dispatch", TARGET_REF=shas["head"])
        assert result.returncode == 1
        assert "DISPATCH_TARGET_SHA_MISMATCH" in result.stdout

    def test_unknown_event_fails(self, tmp_path):
        _build_merge_repo(tmp_path)
        result = _run_gate(tmp_path, CERT_EVENT="push")
        assert result.returncode == 1
