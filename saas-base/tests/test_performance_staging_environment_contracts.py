"""Static safety contracts for the local performance-staging environment."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DEPLOY_ROOT = ROOT / "deploy" / "performance-staging"
FILES = {
    "compose": DEPLOY_ROOT / "compose.yml",
    "dockerfile": DEPLOY_ROOT / "admin.Dockerfile",
    "nginx": DEPLOY_ROOT / "nginx.conf",
    "env": DEPLOY_ROOT / ".env.example",
    "lifecycle": ROOT / "scripts" / "performance-staging.ps1",
}
FROZEN_SHA = "823708c1cbac8ba7c730715afafbecd27d641f09"
EXPECTED_SERVICES = {
    "mysql",
    "redis",
    "migrate",
    "dataset",
    "owner-code",
    "backend",
    "admin",
}


def _read(name: str) -> str:
    return FILES[name].read_text(encoding="utf-8")


def _service_names(compose: str) -> set[str]:
    services_block = compose.split("services:", 1)[1].split("\nvolumes:", 1)[0]
    return set(re.findall(r"^  ([a-z][a-z0-9-]*):\s*$", services_block, re.MULTILINE))


def _service_block(compose: str, service: str) -> str:
    services_block = compose.split("services:\n", 1)[1].split("\nvolumes:", 1)[0]
    match = re.search(
        rf"^  {re.escape(service)}:\s*$\n(?P<body>.*?)(?=^  [a-z][a-z0-9-]*:\s*$|\Z)",
        services_block,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"service block is missing: {service}"
    return match.group("body")


def test_required_environment_files_exist() -> None:
    missing = [str(path.relative_to(ROOT)) for path in FILES.values() if not path.is_file()]
    assert not missing, f"missing performance-staging files: {missing}"


def test_compose_has_only_the_fixed_service_topology() -> None:
    compose = _read("compose")
    assert "name: xiao-performance-staging" in compose
    assert _service_names(compose) == EXPECTED_SERVICES


def test_compose_is_loopback_only_and_data_services_are_private() -> None:
    compose = _read("compose")
    assert '"127.0.0.1:18989:80"' in compose
    assert '"127.0.0.1:19898:8000"' in compose
    assert '"3306:' not in compose
    assert '"6379:' not in compose
    assert "xiao_performance_staging" in compose
    assert 'command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--lifespan", "off"]' in compose


def test_compose_jobs_use_existing_guarded_tools() -> None:
    compose = _read("compose")
    assert "scripts/admin_performance_dataset.py" in compose
    assert "scripts/admin_performance_owner_code.py" in compose
    assert "PERF_DATASET_ACK" in compose
    assert "PERF_DATASET_V1" in compose
    assert "PERF_OWNER_LOGIN_CODE" in compose


def test_job_secrets_are_scoped_to_only_their_consuming_services() -> None:
    compose = _read("compose")
    shared_environment = compose.split(
        "x-backend-environment: &backend-environment\n", 1
    )[1].split("\nservices:", 1)[0]
    assert "PERF_TEST_PASSWORD" not in shared_environment
    assert "PERF_OWNER_LOGIN_CODE" not in shared_environment

    dataset = _service_block(compose, "dataset")
    owner_code = _service_block(compose, "owner-code")
    assert "environment:" in dataset and "<<: *backend-environment" in dataset
    assert "PERF_TEST_PASSWORD: ${PERF_TEST_PASSWORD}" in dataset
    assert "PERF_OWNER_LOGIN_CODE" not in dataset
    assert "environment:" in owner_code and "<<: *backend-environment" in owner_code
    assert "PERF_OWNER_LOGIN_CODE: ${PERF_OWNER_LOGIN_CODE}" in owner_code
    assert "PERF_TEST_PASSWORD" not in owner_code

    for service in ("mysql", "redis", "migrate", "backend", "admin"):
        block = _service_block(compose, service)
        assert "PERF_TEST_PASSWORD" not in block
        assert "PERF_OWNER_LOGIN_CODE" not in block


def test_admin_artifact_freezes_version_and_staging_environment() -> None:
    compose = _read("compose")
    dockerfile = _read("dockerfile")
    assert f"ADMIN_RELEASE_SHA: ${{ADMIN_RELEASE_SHA:-{FROZEN_SHA}}}" in compose
    assert "VITE_ADMIN_ENVIRONMENT: staging" in compose
    assert "VITE_API_BASE_URL: /api" in compose
    assert "FROM node:20-alpine" in dockerfile
    assert "FROM nginx:1.27-alpine" in dockerfile
    assert "npm ci" in dockerfile
    assert "npm run build" in dockerfile
    assert "^[0-9a-f]{40}$" in dockerfile
    assert '"environment":"staging"' in dockerfile
    assert '"builder":"local-docker-performance-staging"' in dockerfile


def test_nginx_preserves_api_prefix_and_supports_spa_fallback() -> None:
    nginx = _read("nginx")
    assert "location /api/" in nginx
    assert "proxy_pass http://backend:8000;" in nginx
    assert "try_files $uri $uri/ /index.html;" in nginx


def test_committed_environment_contains_no_usable_secrets() -> None:
    env = _read("env")
    assert "COMPOSE_PROJECT_NAME=xiao-performance-staging" in env
    assert "APP_ENV=staging" in env
    assert "PERFORMANCE_DB_NAME=xiao_performance_staging" in env
    assert f"ADMIN_RELEASE_SHA={FROZEN_SHA}" in env
    for key in (
        "MYSQL_ROOT_PASSWORD",
        "MYSQL_APP_PASSWORD",
        "JWT_SECRET_KEY",
        "PERF_TEST_PASSWORD",
        "PERF_OWNER_LOGIN_CODE",
    ):
        assert re.search(rf"^{key}=$", env, re.MULTILINE)


def test_environment_contract_has_no_production_endpoint_or_deploy_path() -> None:
    combined = "\n".join(_read(name) for name in FILES)
    lowered = combined.lower()
    assert "saas.zhangbaiyang.com" not in lowered
    assert "api.zhangbaiyang.com" not in lowered
    assert "deploy-production" not in lowered
    assert "docker system prune" not in lowered


def test_lifecycle_exposes_only_the_approved_actions_and_named_gates() -> None:
    lifecycle = _read("lifecycle")
    compact = re.sub(r"\s+", "", lifecycle)
    assert "ValidateSet('Prepare','Start','Verify','Cleanup','Stop','Destroy')" in compact
    assert "[switch]$ConfirmDestroy" in lifecycle
    assert "$ErrorActionPreference = 'Stop'" in lifecycle
    assert "$ProjectName = 'xiao-performance-staging'" in lifecycle
    assert f"$FrozenAdminSha = '{FROZEN_SHA}'" in lifecycle
    for function_name in (
        "Assert-DockerReady",
        "Assert-AdminSourceIdentity",
        "Assert-LoopbackPortsAvailable",
        "Initialize-LocalEnvironment",
        "Assert-ResolvedComposeIsolation",
        "Invoke-MigrationGate",
        "Invoke-DatasetLifecycle",
        "Invoke-OwnerCodePreparation",
        "Wait-HttpHealthy",
        "Invoke-StagingVerify",
        "Invoke-StagingDestroy",
    ):
        assert re.search(rf"function\s+{re.escape(function_name)}\b", lifecycle)


def test_lifecycle_freezes_source_and_uses_argument_array_process_calls() -> None:
    lifecycle = _read("lifecycle")
    assert "git diff --quiet" in lifecycle
    assert "-- admin-h5" in lifecycle
    assert "@Arguments" in lifecycle
    assert "& docker compose" in lifecycle
    assert "$PSScriptRoot" in lifecycle
    assert "Get-Content $LocalEnv" not in lifecycle
    assert "Get-Content -Raw $LocalEnv" not in lifecycle


def test_compose_progress_on_stderr_does_not_become_a_false_failure() -> None:
    lifecycle = _read("lifecycle")
    invoke_compose = lifecycle.split("function Invoke-Compose", 1)[1].split(
        "function Assert-DockerReady", 1
    )[0]
    assert "$ErrorActionPreference = 'Continue'" in invoke_compose
    assert "$composeExitCode = $LASTEXITCODE" in invoke_compose
    assert "$ErrorActionPreference = $previousErrorActionPreference" in invoke_compose
    assert "if ($composeExitCode -ne 0)" in invoke_compose


def test_lifecycle_rejects_untracked_and_ignored_admin_build_inputs() -> None:
    lifecycle = _read("lifecycle")
    assert "git status --porcelain" in lifecycle
    assert "--untracked-files=all" in lifecycle
    assert "--ignored=matching" in lifecycle
    assert "-- admin-h5" in lifecycle


def test_lifecycle_uses_cryptographic_randomness_and_preserves_valid_env() -> None:
    lifecycle = _read("lifecycle")
    assert "RandomNumberGenerator]::Create()" in lifecycle
    assert ".GetBytes(" in lifecycle
    assert "BitConverter]::ToString" in lifecycle
    assert "::Fill(" not in lifecycle
    assert "::GetInt32(" not in lifecycle
    assert "UInt32" in lifecycle
    assert "4294000000" in lifecycle
    assert "Get-Random" not in lifecycle
    assert "git check-ignore" in lifecycle
    assert "PERF_OWNER_LOGIN_CODE" in lifecycle
    assert "PERF_DATASET_V1" in lifecycle


def test_lifecycle_contains_the_exact_dataset_and_health_sequence() -> None:
    lifecycle = _read("lifecycle")
    assert "up', '-d', 'mysql', 'redis" in lifecycle
    assert "run', '--rm', 'migrate" in lifecycle
    assert "PERF_DATASET_V1.json" in lifecycle
    assert "http://127.0.0.1:19898/health" in lifecycle
    assert "http://127.0.0.1:18989/release.json" in lifecycle
    assert "alembic" in lifecycle.lower()
    assert "heads" in lifecycle.lower()


def test_alembic_heads_runs_as_a_python_module_with_the_project_on_sys_path() -> None:
    lifecycle = _read("lifecycle")
    invocation = "run', '--rm', 'migrate', 'python', '-m', 'alembic', 'heads"
    assert lifecycle.count(invocation) == 2
    assert "--entrypoint', 'alembic', 'migrate', 'heads" not in lifecycle


def test_start_builds_every_current_application_image_before_starting() -> None:
    lifecycle = _read("lifecycle")
    assert "build', '--pull', 'migrate', 'dataset', 'owner-code', 'backend', 'admin" in lifecycle
    build_index = lifecycle.index("build', '--pull'")
    first_up_index = lifecycle.index("up', '-d', 'mysql', 'redis")
    assert build_index < first_up_index


def test_missing_compose_ports_are_treated_as_zero_not_one_null_entry() -> None:
    lifecycle = _read("lifecycle")
    assert "Where-Object { $null -ne $_ }" in lifecycle


def test_port_preflight_is_scoped_to_each_corresponding_service() -> None:
    lifecycle = _read("lifecycle")
    assert "function Test-ServiceOwnsPublishedPort" in lifecycle
    assert "-Service 'admin' -Port 18989" in lifecycle
    assert "-Service 'backend' -Port 19898" in lifecycle
    assert "existingContainers" not in lifecycle


def test_saved_evidence_is_parsed_validated_and_whitelisted_json() -> None:
    lifecycle = _read("lifecycle")
    assert "function ConvertTo-SafeDatasetEvidence" in lifecycle
    assert "function ConvertTo-SafeOwnerCodeEvidence" in lifecycle
    assert "ConvertFrom-Json" in lifecycle
    assert "Expected exactly one JSON object" in lifecycle
    for allowed in (
        "status",
        "dataset_version",
        "tenant_id",
        "counts",
        "dataset_scale",
        "semantic_checksum",
        "category_count",
        "order_statuses",
        "member_levels",
        "invalid_print_statuses",
        "orphan_member_accounts",
        "menu_item_spec_count",
        "deleted",
    ):
        assert f"'{allowed}'" in lifecycle
    assert "@('status', 'dataset_version', 'tenant_id', 'phone', 'purpose')" in lifecycle
    assert "ConvertTo-Json" in lifecycle
    assert "Save-SafeEvidence -Name $EvidenceName -Lines $result" not in lifecycle


def test_evidence_sanitizer_avoids_the_windows_powershell_pscustomobject_binder() -> None:
    lifecycle = _read("lifecycle")
    assert "[System.Management.Automation.PSCustomObject]$Report" not in lifecycle
    assert "[psobject]$Report" in lifecycle


def test_dataset_evidence_sanitizer_executes_in_windows_powershell_5() -> None:
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        pytest.skip("Windows PowerShell 5.1 is unavailable")

    lifecycle_path = str(FILES["lifecycle"]).replace("'", "''")
    command = rf"""
$ErrorActionPreference = 'Stop'
$text = [System.IO.File]::ReadAllText('{lifecycle_path}')
$start = $text.IndexOf('function ConvertFrom-SingleJsonObject')
$end = $text.IndexOf('function Invoke-DatasetCommand')
if ($start -lt 0 -or $end -le $start) {{ throw 'sanitizer extraction failed' }}
Invoke-Expression $text.Substring($start, $end - $start)
$DatasetVersion = 'PERF_DATASET_V1'
$raw = @(
    'compose diagnostic line',
    '{{"status":"PASS","dataset_version":"PERF_DATASET_V1","tenant_id":"perf_test_only_v1","counts":{{"dishes":500}}}}'
)
$safe = ConvertTo-SafeDatasetEvidence -Output $raw
$report = $safe | ConvertFrom-Json
if ($report.status -ne 'PASS' -or $report.counts.dishes -ne 500) {{
    throw 'sanitized evidence mismatch'
}}
Write-Output 'WINDOWS_PS5_SANITIZER=PASS'
"""
    completed = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "WINDOWS_PS5_SANITIZER=PASS" in completed.stdout


def test_destroy_is_exactly_scoped_and_requires_explicit_confirmation() -> None:
    lifecycle = _read("lifecycle")
    destroy = lifecycle.split("function Invoke-StagingDestroy", 1)[1]
    assert "if (-not $ConfirmDestroy)" in destroy
    assert "Destroy requires -ConfirmDestroy" in destroy
    assert "if ($ProjectName -ne 'xiao-performance-staging')" in destroy
    assert "Refusing to destroy an unexpected project" in destroy
    assert "@('down', '--volumes', '--remove-orphans')" in destroy


def test_lifecycle_never_uses_broad_or_production_mutation_commands() -> None:
    lifecycle = _read("lifecycle").lower()
    for forbidden in (
        "docker system prune",
        "docker volume prune",
        "docker network prune",
        "deploy-production",
        "publish-admin-artifact",
        "atomic switch",
        "remove-item *",
        "remove-item -recurse",
    ):
        assert forbidden not in lifecycle
