[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Prepare','Start','Verify','Cleanup','Stop','Destroy')]
    [string]$Action,
    [switch]$ConfirmDestroy
)

$ErrorActionPreference = 'Stop'
$ProjectName = 'xiao-performance-staging'
$FrozenAdminSha = '823708c1cbac8ba7c730715afafbecd27d641f09'
$DatasetVersion = 'PERF_DATASET_V1'
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$ComposeFile = Join-Path $RepoRoot 'deploy\performance-staging\compose.yml'
$LocalEnv = Join-Path $RepoRoot 'deploy\performance-staging\.env.local'
$EvidenceRoot = Join-Path ([System.IO.Path]::GetTempPath()) "xiao-performance-staging-$PID"

function Invoke-Compose {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $output = & docker compose --project-name $ProjectName --env-file $LocalEnv -f $ComposeFile @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed for action: $($Arguments[0])"
    }
    return @($output)
}

function Assert-DockerReady {
    $server = & docker info --format '{{.ServerVersion}}' 2>&1
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($server -join ''))) {
        throw 'Docker server is not available'
    }
    $compose = & docker compose version --short 2>&1
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($compose -join ''))) {
        throw 'Docker Compose is not available'
    }
}

function Assert-AdminSourceIdentity {
    Push-Location $RepoRoot
    try {
        & git cat-file -e "$FrozenAdminSha`^{commit}" 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw "Frozen admin SHA is unavailable: $FrozenAdminSha"
        }
        & git diff --quiet $FrozenAdminSha -- admin-h5
        if ($LASTEXITCODE -ne 0) {
            throw 'admin-h5 differs from the frozen source identity'
        }
        $uncommittedBuildInputs = & git status --porcelain --untracked-files=all --ignored=matching -- admin-h5
        if ($LASTEXITCODE -ne 0) {
            throw 'Unable to inspect admin-h5 build inputs'
        }
        if (-not [string]::IsNullOrWhiteSpace(($uncommittedBuildInputs -join ''))) {
            throw 'admin-h5 contains untracked or ignored build inputs'
        }
    }
    finally {
        Pop-Location
    }
}

function Read-EnvironmentFile {
    param([Parameter(Mandatory = $true)][string]$Path)

    $values = @{}
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) {
            continue
        }
        $separator = $trimmed.IndexOf('=')
        if ($separator -le 0) {
            throw "Invalid local environment entry for $ProjectName"
        }
        $key = $trimmed.Substring(0, $separator)
        if ($values.ContainsKey($key)) {
            throw "Duplicate local environment key: $key"
        }
        $values[$key] = $trimmed.Substring($separator + 1)
    }
    return $values
}

function Assert-LocalEnvironmentValues {
    param([Parameter(Mandatory = $true)][hashtable]$Values)

    $fixed = @{
        COMPOSE_PROJECT_NAME = $ProjectName
        APP_ENV = 'staging'
        PERFORMANCE_DB_NAME = 'xiao_performance_staging'
        PERFORMANCE_DB_USER = 'perf_app'
        PERF_DATASET_ACK = $DatasetVersion
        ADMIN_RELEASE_SHA = $FrozenAdminSha
    }
    foreach ($entry in $fixed.GetEnumerator()) {
        if ($Values[$entry.Key] -cne $entry.Value) {
            throw "Local environment has an invalid fixed value: $($entry.Key)"
        }
    }
    foreach ($key in ('MYSQL_ROOT_PASSWORD', 'MYSQL_APP_PASSWORD', 'JWT_SECRET_KEY', 'PERF_TEST_PASSWORD')) {
        if ([string]::IsNullOrWhiteSpace($Values[$key]) -or $Values[$key].Length -lt 24) {
            throw "Local environment secret is missing or too short: $key"
        }
    }
    if ($Values['PERF_OWNER_LOGIN_CODE'] -notmatch '^[0-9]{6}$') {
        throw 'Local environment owner login code must be exactly six digits'
    }
}

function New-CryptoHex {
    param([int]$ByteCount = 24)

    $bytes = [byte[]]::new($ByteCount)
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return ([System.BitConverter]::ToString($bytes) -replace '-', '').ToLowerInvariant()
}

function New-CryptoSixDigitCode {
    $bytes = [byte[]]::new(4)
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        do {
            $generator.GetBytes($bytes)
            $value = [System.BitConverter]::ToUInt32($bytes, 0)
        } while ($value -ge [UInt64]4294000000)
    }
    finally {
        $generator.Dispose()
    }
    $code = [UInt32]($value % 1000000)
    return $code.ToString('D6', [System.Globalization.CultureInfo]::InvariantCulture)
}

function Initialize-LocalEnvironment {
    Push-Location $RepoRoot
    try {
        & git check-ignore --quiet -- 'deploy/performance-staging/.env.local'
        if ($LASTEXITCODE -ne 0) {
            throw 'The local performance-staging environment file is not ignored by Git'
        }
    }
    finally {
        Pop-Location
    }

    if (Test-Path -LiteralPath $LocalEnv) {
        $existing = Read-EnvironmentFile -Path $LocalEnv
        Assert-LocalEnvironmentValues -Values $existing
        return
    }

    $lines = @(
        "COMPOSE_PROJECT_NAME=$ProjectName",
        'APP_ENV=staging',
        'PERFORMANCE_DB_NAME=xiao_performance_staging',
        'PERFORMANCE_DB_USER=perf_app',
        "MYSQL_ROOT_PASSWORD=$(New-CryptoHex)",
        "MYSQL_APP_PASSWORD=$(New-CryptoHex)",
        "JWT_SECRET_KEY=$(New-CryptoHex -ByteCount 32)",
        "PERF_TEST_PASSWORD=$(New-CryptoHex)",
        "PERF_OWNER_LOGIN_CODE=$(New-CryptoSixDigitCode)",
        "PERF_DATASET_ACK=$DatasetVersion",
        "ADMIN_RELEASE_SHA=$FrozenAdminSha"
    )
    [System.IO.File]::WriteAllLines(
        $LocalEnv,
        $lines,
        [System.Text.UTF8Encoding]::new($false)
    )
    Assert-LocalEnvironmentValues -Values (Read-EnvironmentFile -Path $LocalEnv)
}

function Assert-ResolvedComposeIsolation {
    $resolvedText = (Invoke-Compose @('config', '--format', 'json')) -join "`n"
    $forbiddenDeployPath = 'deploy' + '-' + 'production'
    if (
        $resolvedText -match '(?i)zhangbaiyang\.com|production[_-]deploy' -or
        $resolvedText.Contains($forbiddenDeployPath)
    ) {
        throw 'Resolved Compose configuration references a production endpoint or path'
    }
    try {
        $resolved = $resolvedText | ConvertFrom-Json
    }
    catch {
        throw 'Resolved Compose configuration is not valid JSON'
    }
    if ($resolved.name -ne $ProjectName) {
        throw 'Resolved Compose project name is not the approved staging project'
    }

    foreach ($dataService in ('mysql', 'redis')) {
        $ports = @($resolved.services.$dataService.ports | Where-Object { $null -ne $_ })
        if ($ports.Count -ne 0) {
            throw "$dataService must not publish a host port"
        }
    }
    $expectedPorts = @{ admin = '18989'; backend = '19898' }
    foreach ($entry in $expectedPorts.GetEnumerator()) {
        $ports = @($resolved.services.($entry.Key).ports | Where-Object { $null -ne $_ })
        if ($ports.Count -ne 1) {
            throw "$($entry.Key) must publish exactly one loopback port"
        }
        $port = $ports[0]
        if ($port.host_ip -ne '127.0.0.1' -or [string]$port.published -ne $entry.Value) {
            throw "$($entry.Key) must publish only the approved loopback port"
        }
    }
    if ($resolved.services.backend.environment.APP_ENV -ne 'staging') {
        throw 'Backend must resolve with APP_ENV=staging'
    }
}

function Test-ServiceOwnsPublishedPort {
    param(
        [Parameter(Mandatory = $true)][string]$Service,
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][int]$ContainerPort
    )

    $published = & docker compose --project-name $ProjectName --env-file $LocalEnv -f $ComposeFile port $Service $ContainerPort 2>$null
    if ($LASTEXITCODE -ne 0) {
        return $false
    }
    return (($published -join '').Trim() -eq "127.0.0.1:$Port")
}

function Assert-LoopbackPortsAvailable {
    $adminListener = Get-NetTCPConnection -State Listen -LocalPort 18989 -ErrorAction SilentlyContinue
    if (
        $null -ne $adminListener -and
        -not (Test-ServiceOwnsPublishedPort -Service 'admin' -Port 18989 -ContainerPort 80)
    ) {
        throw 'Loopback port 18989 is occupied outside the admin staging service'
    }

    $backendListener = Get-NetTCPConnection -State Listen -LocalPort 19898 -ErrorAction SilentlyContinue
    if (
        $null -ne $backendListener -and
        -not (Test-ServiceOwnsPublishedPort -Service 'backend' -Port 19898 -ContainerPort 8000)
    ) {
        throw 'Loopback port 19898 is occupied outside the backend staging service'
    }
}

function Wait-ContainerHealthy {
    param(
        [Parameter(Mandatory = $true)][string]$Service,
        [int]$Attempts = 60
    )

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $containerIds = Invoke-Compose @('ps', '--quiet', $Service)
        $containerId = ($containerIds -join '').Trim()
        if ($containerId) {
            $status = & docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $containerId 2>&1
            if ($LASTEXITCODE -eq 0 -and ($status -join '').Trim() -eq 'healthy') {
                return
            }
        }
        Start-Sleep -Seconds 2
    }
    throw "Container did not become healthy: $Service"
}

function Invoke-MigrationGate {
    [void](Invoke-Compose @('run', '--rm', 'migrate'))
    $heads = Invoke-Compose @('run', '--rm', '--entrypoint', 'alembic', 'migrate', 'heads')
    $headLines = @($heads | Where-Object { $_ -match '\(head\)' })
    if ($headLines.Count -ne 1) {
        throw 'Alembic must resolve to exactly one head'
    }
}

function Save-SafeEvidence {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][object[]]$Lines
    )

    [System.IO.Directory]::CreateDirectory($EvidenceRoot) | Out-Null
    $path = Join-Path $EvidenceRoot $Name
    [System.IO.File]::WriteAllLines(
        $path,
        [string[]]$Lines,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function ConvertFrom-SingleJsonObject {
    param([Parameter(Mandatory = $true)][object[]]$Output)

    $candidates = @()
    foreach ($item in $Output) {
        $line = ([string]$item).Trim()
        if (-not ($line.StartsWith('{') -and $line.EndsWith('}'))) {
            continue
        }
        try {
            $parsed = $line | ConvertFrom-Json
        }
        catch {
            throw 'Performance tool emitted an invalid JSON object'
        }
        if ($null -eq $parsed -or $parsed -isnot [System.Management.Automation.PSCustomObject]) {
            throw 'Performance tool JSON must be an object'
        }
        $candidates += ,$parsed
    }
    if ($candidates.Count -ne 1) {
        throw 'Expected exactly one JSON object from the performance tool'
    }
    return $candidates[0]
}

function ConvertTo-WhitelistedJson {
    param(
        [Parameter(Mandatory = $true)][System.Management.Automation.PSCustomObject]$Report,
        [Parameter(Mandatory = $true)][string[]]$AllowedFields
    )

    $actualFields = @($Report.PSObject.Properties.Name)
    $unexpected = @($actualFields | Where-Object { $_ -notin $AllowedFields })
    if ($unexpected.Count -ne 0) {
        throw 'Performance tool JSON contains a non-whitelisted field'
    }
    $safe = [ordered]@{}
    foreach ($field in $AllowedFields) {
        if ($field -in $actualFields) {
            $safe[$field] = $Report.$field
        }
    }
    return ($safe | ConvertTo-Json -Compress -Depth 8)
}

function ConvertTo-SafeDatasetEvidence {
    param([Parameter(Mandatory = $true)][object[]]$Output)

    $report = ConvertFrom-SingleJsonObject -Output $Output
    if (
        $report.status -ne 'PASS' -or
        $report.dataset_version -ne $DatasetVersion -or
        $report.tenant_id -ne 'perf_test_only_v1'
    ) {
        throw 'Dataset evidence does not match the fixed performance identity'
    }
    $allowed = @(
        'status',
        'dataset_version',
        'tenant_id',
        'counts',
        'dataset_scale',
        'semantic_checksum',
        'category_count',
        'order_statuses',
        'member_levels',
        'invalid_print_statuses',
        'orphan_member_accounts',
        'menu_item_spec_count',
        'deleted'
    )
    return ConvertTo-WhitelistedJson -Report $report -AllowedFields $allowed
}

function ConvertTo-SafeOwnerCodeEvidence {
    param([Parameter(Mandatory = $true)][object[]]$Output)

    $report = ConvertFrom-SingleJsonObject -Output $Output
    if (
        $report.status -ne 'PASS' -or
        $report.dataset_version -ne $DatasetVersion -or
        $report.tenant_id -ne 'perf_test_only_v1' -or
        $report.phone -notmatch '^199\*{4}0000$' -or
        $report.purpose -ne 'login'
    ) {
        throw 'Owner-code evidence does not match the fixed safe identity'
    }
    $allowed = @('status', 'dataset_version', 'tenant_id', 'phone', 'purpose')
    return ConvertTo-WhitelistedJson -Report $report -AllowedFields $allowed
}

function Invoke-DatasetCommand {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('create','verify','cleanup')][string]$DatasetAction,
        [Parameter(Mandatory = $true)][string]$EvidenceName
    )

    $arguments = @('run', '--rm', 'dataset', $DatasetAction, '--dataset-version', $DatasetVersion)
    if ($DatasetAction -eq 'create') {
        $arguments += @('--manifest-out', '/tmp/PERF_DATASET_V1.json')
    }
    $result = Invoke-Compose $arguments
    $safeJson = ConvertTo-SafeDatasetEvidence -Output $result
    Save-SafeEvidence -Name $EvidenceName -Lines @($safeJson)
}

function Invoke-DatasetLifecycle {
    Invoke-DatasetCommand -DatasetAction 'create' -EvidenceName 'dataset-create-first.json'
    Invoke-DatasetCommand -DatasetAction 'verify' -EvidenceName 'dataset-verify-first.json'
    Invoke-DatasetCommand -DatasetAction 'cleanup' -EvidenceName 'dataset-cleanup.json'
    Invoke-DatasetCommand -DatasetAction 'create' -EvidenceName 'dataset-create-final.json'
    Invoke-DatasetCommand -DatasetAction 'verify' -EvidenceName 'dataset-verify-final.json'
}

function Invoke-OwnerCodePreparation {
    $result = Invoke-Compose @('run', '--rm', 'owner-code')
    $safeJson = ConvertTo-SafeOwnerCodeEvidence -Output $result
    Save-SafeEvidence -Name 'owner-code-safe-report.json' -Lines @($safeJson)
}

function Wait-HttpHealthy {
    param(
        [Parameter(Mandatory = $true)][uri]$Uri,
        [int]$Attempts = 60
    )

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                return
            }
        }
        catch {
            if ($attempt -eq $Attempts) {
                throw "HTTP readiness failed: $Uri"
            }
        }
        Start-Sleep -Seconds 2
    }
    throw "HTTP readiness failed: $Uri"
}

function Assert-ServicesHealthy {
    foreach ($service in ('mysql', 'redis', 'backend')) {
        Wait-ContainerHealthy -Service $service
    }
    $runningServices = Invoke-Compose @('ps', '--status', 'running', '--services')
    if (@($runningServices | Where-Object { $_ -eq 'admin' }).Count -ne 1) {
        throw 'Admin service is not running'
    }
}

function Assert-AdminReleaseIdentity {
    $release = Invoke-RestMethod -Uri 'http://127.0.0.1:18989/release.json' -TimeoutSec 5
    if (
        $release.sha -ne $FrozenAdminSha -or
        $release.environment -ne 'staging' -or
        $release.builder -ne 'local-docker-performance-staging'
    ) {
        throw 'Admin release identity does not match the frozen staging contract'
    }
}

function Invoke-StagingVerify {
    Assert-DockerReady
    Assert-AdminSourceIdentity
    Initialize-LocalEnvironment
    Assert-ResolvedComposeIsolation
    Assert-ServicesHealthy
    $heads = Invoke-Compose @('run', '--rm', '--entrypoint', 'alembic', 'migrate', 'heads')
    if (@($heads | Where-Object { $_ -match '\(head\)' }).Count -ne 1) {
        throw 'Alembic must resolve to exactly one head'
    }
    Invoke-DatasetCommand -DatasetAction 'verify' -EvidenceName 'dataset-verify-current.json'
    Wait-HttpHealthy -Uri 'http://127.0.0.1:19898/health'
    Wait-HttpHealthy -Uri 'http://127.0.0.1:18989/release.json'
    Assert-AdminReleaseIdentity
    Write-Output "VERIFY PASS: project=$ProjectName environment=staging version=$FrozenAdminSha"
}

function Invoke-Prepare {
    Assert-DockerReady
    Assert-AdminSourceIdentity
    Initialize-LocalEnvironment
    Assert-ResolvedComposeIsolation
    Assert-LoopbackPortsAvailable
    Write-Output "PREPARE PASS: project=$ProjectName environment=staging version=$FrozenAdminSha"
}

function Invoke-StagingStart {
    Invoke-Prepare
    [void](Invoke-Compose @('build', '--pull', 'migrate', 'dataset', 'owner-code', 'backend', 'admin'))
    [void](Invoke-Compose @('up', '-d', 'mysql', 'redis'))
    Wait-ContainerHealthy -Service 'mysql'
    Wait-ContainerHealthy -Service 'redis'
    Invoke-MigrationGate
    Invoke-DatasetLifecycle
    Invoke-OwnerCodePreparation
    [void](Invoke-Compose @('up', '-d', 'backend', 'admin'))
    Wait-HttpHealthy -Uri 'http://127.0.0.1:19898/health'
    Wait-HttpHealthy -Uri 'http://127.0.0.1:18989/release.json'
    Invoke-StagingVerify
}

function Invoke-StagingCleanup {
    Assert-DockerReady
    Assert-AdminSourceIdentity
    Initialize-LocalEnvironment
    Assert-ResolvedComposeIsolation
    Invoke-DatasetCommand -DatasetAction 'cleanup' -EvidenceName 'dataset-cleanup-manual.json'
    Write-Output "CLEANUP PASS: project=$ProjectName dataset=$DatasetVersion"
}

function Invoke-StagingStop {
    Assert-DockerReady
    Initialize-LocalEnvironment
    Assert-ResolvedComposeIsolation
    [void](Invoke-Compose @('stop'))
    Write-Output "STOP PASS: project=$ProjectName volumes=preserved"
}

function Invoke-StagingDestroy {
    if (-not $ConfirmDestroy) {
        throw 'Destroy requires -ConfirmDestroy'
    }
    if ($ProjectName -ne 'xiao-performance-staging') {
        throw 'Refusing to destroy an unexpected project'
    }
    Assert-DockerReady
    Initialize-LocalEnvironment
    Assert-ResolvedComposeIsolation
    [void](Invoke-Compose @('down', '--volumes', '--remove-orphans'))
    Write-Output "DESTROY PASS: project=$ProjectName"
}

switch ($Action) {
    'Prepare' { Invoke-Prepare }
    'Start' { Invoke-StagingStart }
    'Verify' { Invoke-StagingVerify }
    'Cleanup' { Invoke-StagingCleanup }
    'Stop' { Invoke-StagingStop }
    'Destroy' { Invoke-StagingDestroy }
}
