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


# ---------------------------------------------------------------------------
# Workflow permission / supply-chain audit
# ---------------------------------------------------------------------------

def test_workflow_uses_pinned_actions_and_no_persisted_credentials_or_secrets() -> None:
    import re

    text = _workflow_text()
    uses = re.findall(r"^\s*uses:\s*(\S+)", text, flags=re.MULTILINE)
    assert uses, "workflow must use actions"
    for reference in uses:
        assert re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", reference), reference
    assert text.count("persist-credentials: false") == text.count("uses: actions/checkout@")
    assert "secrets." not in text
    assert "pull_request_target" not in text
    assert "workflow_run" not in text
    assert "contents: read" in text


def test_untrusted_context_values_never_reach_shell_bodies_directly() -> None:
    lines = _workflow_text().splitlines()
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if "${{ inputs." in stripped:
            assert stripped.startswith(("group:", "TARGET_REF:")), (number, stripped)
        if "${{ github.event." in stripped:
            assert stripped.startswith(("group:", "TARGET_REF:", "PR_HEAD_SHA:", "PR_BASE_SHA:")), (number, stripped)
        assert "github.head_ref" not in stripped
        assert "github.event.pull_request.title" not in stripped


# ---------------------------------------------------------------------------
# Summary fail-closed behaviour: run the REAL summary script
# ---------------------------------------------------------------------------

def _summary_script() -> tuple[list[str], str]:
    text = _workflow_text()
    section = text[text.index("  certification-summary:\n"):]
    env_block = section[section.index("        env:\n"): section.index("        run: |\n")]
    names = [line.split(":")[0].strip() for line in env_block.splitlines()[1:] if line.strip()]
    body = section[section.index("        run: |\n") + len("        run: |\n"):]
    script = "\n".join(line[10:] if line.startswith(" " * 10) else line for line in body.splitlines())
    return names, script


SHA = "a" * 40


def _summary_env(event: str = "pull_request", **overrides: str) -> dict:
    is_pr = event == "pull_request"
    env = {
        "CERT_EVENT": event,
        "TARGET_REF": "refs/pull/1/merge" if is_pr else SHA,
        "PR_HEAD_SHA": "b" * 40 if is_pr else "",
        "PR_BASE_SHA": "c" * 40 if is_pr else "",
        "GATE_A_RESULT": "success",
        "GATE_B_RESULT": "success",
        "FULL_RESULT": "success",
        "MYSQL_SCHEMA_RESULT": "success",
        "KEYRING_SYSTEMD_RESULT": "success",
        "GATE_A_CHECKED_OUT_SHA": SHA,
        "GATE_B_CHECKED_OUT_SHA": SHA,
        "FULL_CHECKED_OUT_SHA": SHA,
        "MYSQL_SCHEMA_CHECKED_OUT_SHA": SHA,
        "KEYRING_SYSTEMD_CHECKED_OUT_SHA": SHA,
        "MYSQL_ACTIVATION": "ACTIVE",
        "SYSTEMD_ACTIVATION": "ACTIVE",
        "AUTHORITY_CHANGED_BY_PR": "NO" if is_pr else "",
    }
    identity = "PASS" if is_pr else "NOT_APPLICABLE"
    for job in ("GATE_A", "GATE_B", "FULL", "MYSQL_SCHEMA", "KEYRING_SYSTEMD"):
        env[f"{job}_IDENTITY"] = identity
    env.update(overrides)
    return env


def _run_summary(event: str = "pull_request", **overrides: str) -> subprocess.CompletedProcess:
    names, script = _summary_script()
    env = _summary_env(event, **overrides)
    assert set(names) <= set(env) | {"CERT_EVENT"}, set(names) - set(env)
    return subprocess.run(
        [BASH, "-eo", "pipefail", "-c", script],
        env={**{k: v for k, v in os.environ.items() if k in {"PATH", "HOME"}}, **env},
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(not BASH or os.name == "nt", reason="needs POSIX bash")
class TestCertificationSummaryFailsClosed:
    def test_all_green_pull_request_passes(self):
        result = _run_summary()
        assert result.returncode == 0, result.stdout + result.stderr
        assert "CERTIFICATION_SUMMARY=PASS" in result.stdout
        assert "PR_IDENTITY_GATE=PASS" in result.stdout
        assert "B1_REQUIRED_TESTS_ACTIVE=YES" in result.stdout

    def test_each_required_job_failing_skipped_or_cancelled_fails_the_summary(self):
        for job in ("GATE_A", "GATE_B", "FULL", "MYSQL_SCHEMA", "KEYRING_SYSTEMD"):
            for state in ("failure", "skipped", "cancelled", ""):
                result = _run_summary(**{f"{job}_RESULT": state})
                assert result.returncode == 1, (job, state)
                assert "CERTIFICATION_SUMMARY=FAIL" in result.stdout, (job, state)

    def test_mysql_and_systemd_failures_are_not_informational(self):
        assert _run_summary(MYSQL_SCHEMA_RESULT="failure").returncode == 1
        assert _run_summary(KEYRING_SYSTEMD_RESULT="failure").returncode == 1

    def test_checkout_identity_mismatch_in_any_job_fails(self):
        for job in ("GATE_B", "FULL", "MYSQL_SCHEMA", "KEYRING_SYSTEMD"):
            result = _run_summary(**{f"{job}_CHECKED_OUT_SHA": "d" * 40})
            assert result.returncode == 1, job
            assert "CERTIFICATION_CHECKOUT_SHA_MISMATCH" in result.stdout
        assert _run_summary(GATE_A_CHECKED_OUT_SHA="").returncode == 1

    def test_identity_gate_output_must_match_the_event_in_every_job(self):
        for job in ("GATE_A", "GATE_B", "FULL", "MYSQL_SCHEMA", "KEYRING_SYSTEMD"):
            for value in ("FAIL", "", "NOT_APPLICABLE"):
                result = _run_summary(**{f"{job}_IDENTITY": value})
                assert result.returncode == 1, (job, value)
                assert "PR_IDENTITY_GATE=FAIL" in result.stdout
            dispatch = _run_summary("workflow_dispatch", **{f"{job}_IDENTITY": "PASS"})
            assert dispatch.returncode == 1, job

    def test_capability_activation_must_be_explicit(self):
        for key in ("MYSQL_ACTIVATION", "SYSTEMD_ACTIVATION"):
            for value in ("", "FAIL", "SKIPPED"):
                assert _run_summary(**{key: value}).returncode == 1, (key, value)

    def test_baseline_not_active_is_reported_and_never_counted_as_verified(self):
        result = _run_summary(MYSQL_ACTIVATION="BASELINE_NOT_ACTIVE", SYSTEMD_ACTIVATION="BASELINE_NOT_ACTIVE")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "B1_REQUIRED_TESTS_ACTIVE=NO" in result.stdout

    def test_pr_changing_ci_authority_files_cannot_self_certify(self):
        for value in ("YES", "", "UNKNOWN"):
            result = _run_summary(AUTHORITY_CHANGED_BY_PR=value)
            assert result.returncode == 1, value
            assert "CI_AUTHORITY_CHANGE_REQUIRES_MANUAL_BOOTSTRAP_REVIEW" in result.stdout

    def test_dispatch_certifies_the_sha_only(self):
        result = _run_summary("workflow_dispatch")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PR_MERGE_REF_CERTIFIED=NO" in result.stdout
        assert "PR_IDENTITY_GATE=NOT_APPLICABLE" in result.stdout


# ---------------------------------------------------------------------------
# Real-git tests: stale merge ref, malformed SHAs, capability activation
# ---------------------------------------------------------------------------

ACTIVATION_SCRIPT = REPO_ROOT / ".github" / "scripts" / "resolve_certification_activation.sh"


@pytest.mark.skipif(not BASH or not GIT or os.name == "nt", reason="needs POSIX bash and git")
class TestStaleMergeRefAndMalformedShas:
    def test_stale_merge_ref_is_rejected(self, tmp_path):
        shas = _build_merge_repo(tmp_path)
        # main moves again and the proposed merge is recomputed: M2 != the event's M1.
        _git(tmp_path, "checkout", "-q", "-b", "recomputed", shas["base"])
        (tmp_path / "d.txt").write_text("main moved again\n")
        _git(tmp_path, "add", "d.txt")
        _git(tmp_path, "commit", "-q", "-m", "main moved again")
        newer_base = _git(tmp_path, "rev-parse", "HEAD")
        _git(tmp_path, "merge", "-q", "--no-ff", "-m", "merge2", shas["head"])
        # Checkout is M2, but the event (and its base) still describe M1.
        stale_event = _run_gate(tmp_path, **_pr_env(shas))
        assert stale_event.returncode == 1
        assert "CHECKED_OUT_NOT_EVENT_MERGE_COMMIT" in stale_event.stdout
        # Even with the event's merge SHA patched through, the stale base is caught.
        patched = _run_gate(tmp_path, **_pr_env(shas, GITHUB_SHA=_git(tmp_path, "rev-parse", "HEAD")))
        assert patched.returncode == 1
        assert "FIRST_PARENT_NOT_PR_BASE_SHA" in patched.stdout
        # The recomputed merge is accepted only when every event field is refreshed.
        fresh = {**shas, "base": newer_base, "merge": _git(tmp_path, "rev-parse", "HEAD")}
        assert _run_gate(tmp_path, **_pr_env(fresh)).returncode == 0

    def test_malformed_shas_fail(self, tmp_path):
        shas = _build_merge_repo(tmp_path)
        for name in ("PR_BASE_SHA", "PR_HEAD_SHA"):
            for bad in ("not-a-sha", shas["base"][:39], shas["base"].upper(), shas["base"] + "0", "; true"):
                result = _run_gate(tmp_path, **_pr_env(shas, **{name: bad}))
                assert result.returncode == 1, (name, bad)
                assert "PR_IDENTITY_GATE=FAIL" in result.stdout


def _activation_repo(tmp_path: Path, *, base_files: dict, candidate_files: dict, delete: tuple = ()) -> str:
    _git(tmp_path, "init", "-q", "-b", "main")
    for name, content in base_files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    (tmp_path / "keep.txt").write_text("keep\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    for name, content in candidate_files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    for name in delete:
        (tmp_path / name).unlink()
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "candidate")
    return base


def _run_activation(cwd: Path, capability: str, base: str) -> subprocess.CompletedProcess:
    env = {key: value for key, value in os.environ.items() if key not in {"GITHUB_OUTPUT", "ACTIVATION_BASE_SHA"}}
    env["ACTIVATION_BASE_SHA"] = base
    return subprocess.run([BASH, str(ACTIVATION_SCRIPT), capability], cwd=cwd, env=env, capture_output=True, text=True)


MIGRATION = "saas-base/alembic/versions/20261009_0001_x.py"
MYSQL_TEST = "saas-base/tests/test_wxpay_secret_schema_mysql.py"
CRYPTO = "saas-base/app/core/wxpay_secret_crypto.py"


@pytest.mark.skipif(not BASH or not GIT or os.name == "nt", reason="needs POSIX bash and git")
class TestCapabilityActivation:
    def test_baseline_without_triggers_or_tests_is_explicitly_not_active(self, tmp_path):
        base = _activation_repo(tmp_path, base_files={}, candidate_files={"docs.md": "x\n"})
        for capability in ("mysql", "systemd"):
            result = _run_activation(tmp_path, capability, base)
            assert result.returncode == 0, result.stdout
            assert f"ACTIVATION_{capability}=BASELINE_NOT_ACTIVE" in result.stdout

    def test_candidate_adding_migration_without_mysql_test_fails_closed(self, tmp_path):
        base = _activation_repo(tmp_path, base_files={}, candidate_files={MIGRATION: "revision = 'x'\n"})
        result = _run_activation(tmp_path, "mysql", base)
        assert result.returncode == 1
        assert "REQUIRED_TEST_MISSING" in result.stdout

    def test_candidate_with_migration_and_mysql_test_is_active(self, tmp_path):
        base = _activation_repo(
            tmp_path, base_files={}, candidate_files={MIGRATION: "revision = 'x'\n", MYSQL_TEST: "def test_x(): pass\n"}
        )
        result = _run_activation(tmp_path, "mysql", base)
        assert result.returncode == 0
        assert "ACTIVATION_mysql=ACTIVE" in result.stdout

    def test_deleting_the_mysql_test_while_changing_migrations_fails(self, tmp_path):
        base = _activation_repo(
            tmp_path,
            base_files={MYSQL_TEST: "def test_x(): pass\n"},
            candidate_files={MIGRATION: "revision = 'y'\n"},
            delete=(MYSQL_TEST,),
        )
        assert _run_activation(tmp_path, "mysql", base).returncode == 1

    def test_removing_the_keyring_module_fails_the_systemd_gate(self, tmp_path):
        base = _activation_repo(tmp_path, base_files={CRYPTO: "x = 1\n"}, candidate_files={}, delete=(CRYPTO,))
        result = _run_activation(tmp_path, "systemd", base)
        assert result.returncode == 1
        assert "REQUIRED_TEST_MISSING" in result.stdout

    def test_present_keyring_module_always_runs_the_systemd_gate(self, tmp_path):
        base = _activation_repo(tmp_path, base_files={CRYPTO: "x = 1\n"}, candidate_files={"docs.md": "x\n"})
        result = _run_activation(tmp_path, "systemd", base)
        assert result.returncode == 0
        assert "ACTIVATION_systemd=ACTIVE" in result.stdout

    def test_invalid_or_unknown_inputs_fail(self, tmp_path):
        base = _activation_repo(tmp_path, base_files={}, candidate_files={"docs.md": "x\n"})
        assert _run_activation(tmp_path, "mysql", "").returncode == 1
        assert _run_activation(tmp_path, "mysql", "f" * 40).returncode == 1
        assert _run_activation(tmp_path, "bogus", base).returncode == 1
