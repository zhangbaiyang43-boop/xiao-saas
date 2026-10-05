<#
Phase 03R: disposable, localhost-only runtime for the Super Admin Phase 03 candidate.

  Prepare   resolve + verify the pinned candidate, extract it OUTSIDE the working tree, write .env.local
  Up        build (inside Docker) and start the runtime. Requires -ConfirmLocalBuildException
  Verify    runtime smoke only: health, pages, build SHA proof, login smoke, fixture presence
  Credentials  copy the generated test super password to the clipboard (never printed)
  Status    show the runtime containers and their bindings
  Down      destroy containers, network, volumes (synthetic DB) and the extracted source + .env.local

Not a test runner and not a deploy tool. It never touches production, never reads saas-base/.env
or /etc/xiao-deploy.env, never pushes, and only ever addresses the Compose project
xiao-super-admin-cert.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Prepare', 'Up', 'Verify', 'Credentials', 'Status', 'Down')]
    [string]$Action,
    [switch]$ConfirmLocalBuildException
)

$ErrorActionPreference = 'Stop'
$ProjectName = 'xiao-super-admin-cert'
$CandidateBranch = 'candidate/super-admin-ia-navigation'
$CandidateSha = '41ca65d86b6697781e7b5dd0f646c873292e44c2'
$RepoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$ToolingDir = Join-Path $RepoRoot 'deploy\super-admin-cert'
$ComposeFile = Join-Path $ToolingDir 'compose.yml'
$EnvFile = Join-Path $ToolingDir '.env.local'
$WorkRoot = Join-Path ([System.IO.Path]::GetTempPath()) 'xiao-super-admin-cert'
$SrcDir = Join-Path $WorkRoot 'src'

function Write-Result([string]$Key, [string]$Value) { Write-Output ("{0}={1}" -f $Key, $Value) }

function Read-EnvFile {
    if (-not (Test-Path $EnvFile)) { throw "missing $EnvFile - run Prepare first" }
    $map = @{}
    foreach ($line in Get-Content -LiteralPath $EnvFile -Encoding UTF8) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $i = $line.IndexOf('=')
        $map[$line.Substring(0, $i).Trim()] = $line.Substring($i + 1).Trim()
    }
    return $map
}

function Invoke-Git {
    param([string[]]$Arguments)
    $out = & git -C $RepoRoot @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "git $($Arguments -join ' ') failed: $($out -join ' ')" }
    return @($out)
}

function Invoke-Compose {
    param([string[]]$Arguments)
    $previous = $ErrorActionPreference
    try {
        # Compose writes progress to stderr; Windows PowerShell 5 would turn that into a terminating error.
        $ErrorActionPreference = 'Continue'
        $out = & docker compose --project-name $ProjectName --env-file $EnvFile -f $ComposeFile @Arguments 2>&1
        $code = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $previous }
    if ($code -ne 0) { throw "docker compose $($Arguments[0]) failed" }
    return @($out)
}

function Assert-DockerReady {
    $v = & docker info --format '{{.ServerVersion}}' 2>&1
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($v -join ''))) { throw 'Docker server is not available' }
}

function New-Secret([int]$Bytes = 24) {
    $b = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($b)
    return (($b | ForEach-Object { $_.ToString('x2') }) -join '')
}

function Get-FreePort([int]$Start) {
    for ($p = $Start; $p -lt ($Start + 50); $p++) {
        $listener = $null
        try {
            $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Parse('127.0.0.1'), $p)
            $listener.Start(); $listener.Stop()
            return $p
        }
        catch { if ($listener) { try { $listener.Stop() } catch {} } }
    }
    throw "no free localhost port from $Start"
}

function To-ComposePath([string]$Path) { return ($Path -replace '\\', '/') }

function Invoke-Prepare {
    # Gate 00: the candidate must exist on the remote at the exact frozen SHA.
    Invoke-Git @('fetch', 'origin', $CandidateBranch) | Out-Null
    $remote = (Invoke-Git @('ls-remote', '--heads', 'origin', $CandidateBranch) | Select-Object -First 1)
    $remoteSha = ($remote -split '\s+')[0]
    Write-Result 'CANDIDATE_REMOTE_HEAD' $remoteSha
    Write-Result 'CANDIDATE_SHA_MATCH' $(if ($remoteSha -eq $CandidateSha) { 'YES' } else { 'NO' })
    if ($remoteSha -ne $CandidateSha) { throw 'candidate remote SHA does not match the frozen SHA' }
    Invoke-Git @('cat-file', '-e', "$CandidateSha^{commit}") | Out-Null

    # Extract exactly that commit outside the working tree (no .git, no .env, no node_modules).
    if (-not $SrcDir.StartsWith([System.IO.Path]::GetTempPath())) { throw 'refusing to clean a path outside the temp directory' }
    if (Test-Path $WorkRoot) { Remove-Item -LiteralPath $WorkRoot -Recurse -Force }
    New-Item -ItemType Directory -Path $SrcDir -Force | Out-Null
    $tar = Join-Path $WorkRoot 'candidate.tar'
    Invoke-Git @('archive', '--format=tar', '-o', $tar, $CandidateSha) | Out-Null
    & tar -xf $tar -C $SrcDir
    if ($LASTEXITCODE -ne 0) { throw 'tar extraction failed' }
    Remove-Item -LiteralPath $tar -Force
    if (-not (Test-Path (Join-Path $SrcDir 'admin-h5\src\views\super\SuperAdminShell.vue'))) { throw 'extracted source lacks SuperAdminShell.vue' }
    if (Test-Path (Join-Path $SrcDir '.git')) { throw 'extracted source unexpectedly contains .git' }
    if (Test-Path (Join-Path $SrcDir 'saas-base\.env')) { throw 'extracted source unexpectedly contains saas-base/.env' }
    New-Item -ItemType Directory -Path (Join-Path $SrcDir '_cert') -Force | Out-Null
    Copy-Item (Join-Path $ToolingDir 'admin.Dockerfile') (Join-Path $SrcDir '_cert\admin.Dockerfile')
    Copy-Item (Join-Path $ToolingDir 'nginx.conf') (Join-Path $SrcDir '_cert\nginx.conf')

    $adminPort = Get-FreePort 28989
    $backendPort = Get-FreePort 29898
    $lines = @(
        '# Generated by scripts/super-admin-cert.ps1 Prepare. Git-ignored. Test-only secrets for a disposable runtime.',
        "CERT_SRC_DIR=$(To-ComposePath $SrcDir)",
        "CERT_TOOLING_DIR=$(To-ComposePath $ToolingDir)",
        "CERT_ADMIN_SHA=$CandidateSha",
        "CERT_ADMIN_PORT=$adminPort",
        "CERT_BACKEND_PORT=$backendPort",
        "CERT_DB_ROOT_PASSWORD=$(New-Secret)",
        "CERT_DB_APP_PASSWORD=$(New-Secret)",
        "CERT_JWT_SECRET_KEY=$(New-Secret 32)",
        "CERT_SUPER_ADMIN_PASSWORD=$(New-Secret 12)"
    )
    [System.IO.File]::WriteAllText($EnvFile, (($lines -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
    Write-Result 'ADMIN_SHA_PINNED' 'YES'
    Write-Result 'BACKEND_SHA_PINNED' 'YES'
    Write-Result 'ADMIN_SHA' $CandidateSha
    Write-Result 'BACKEND_SHA' $CandidateSha
    Write-Result 'ADMIN_BIND' "127.0.0.1:$adminPort"
    Write-Result 'BACKEND_BIND' "127.0.0.1:$backendPort"
    Write-Result 'SUPER_SECRET_COMMITTED' 'NO'
    Write-Result 'PREPARED' 'YES'
}

function Invoke-Up {
    if (-not $ConfirmLocalBuildException) {
        throw 'Up builds the candidate inside Docker (LOCAL_BUILD_EXCEPTION, Phase 03R only). Re-run with -ConfirmLocalBuildException to confirm you authorise it.'
    }
    Assert-DockerReady
    $cfg = Read-EnvFile
    if ($cfg['CERT_ADMIN_SHA'] -ne $CandidateSha) { throw 'env file is not pinned to the frozen candidate SHA' }
    Invoke-Compose @('up', '-d', '--build') | Out-Null
    $deadline = (Get-Date).AddMinutes(10)
    do {
        Start-Sleep -Seconds 5
        $running = Invoke-Compose @('ps', '--format', '{{.Service}}={{.Health}}') | Out-String
        $ready = ($running -match 'backend=healthy') -and ($running -match 'admin=')
    } while (-not $ready -and (Get-Date) -lt $deadline)
    if (-not $ready) { throw 'runtime did not become healthy within 10 minutes' }
    Write-Result 'RUNTIME_UP' 'YES'
    Write-Result 'LOCAL_BUILD_RUN' 'YES'
    Write-Result 'LOCAL_BUILD_SCOPE' 'ISOLATED_DOCKER_ADMIN_RUNTIME_ONLY'
    Write-Result 'SUPER_RUNTIME_URL' ("http://127.0.0.1:{0}/super" -f $cfg['CERT_ADMIN_PORT'])
}

function Get-StatusCode([string]$Url) {
    try { return [int](Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10).StatusCode }
    catch { if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode } else { return 0 } }
}

function Invoke-Verify {
    $cfg = Read-EnvFile
    $admin = "http://127.0.0.1:$($cfg['CERT_ADMIN_PORT'])"
    $backend = "http://127.0.0.1:$($cfg['CERT_BACKEND_PORT'])"
    $services = Invoke-Compose @('ps', '--format', '{{.Service}}={{.Health}}') | Out-String
    Write-Result 'MYSQL_HEALTH' $(if ($services -match 'mysql=healthy') { 'PASS' } else { 'FAIL' })
    Write-Result 'REDIS_HEALTH' $(if ($services -match 'redis=healthy') { 'PASS' } else { 'FAIL' })
    Write-Result 'BACKEND_HEALTH' $(if ((Get-StatusCode "$backend/health") -eq 200) { 'PASS' } else { 'FAIL' })
    $adminCodes = @{ '/' = (Get-StatusCode "$admin/"); '/super' = (Get-StatusCode "$admin/super"); '/super/merchants' = (Get-StatusCode "$admin/super/merchants") }
    $adminOk = ($adminCodes.Values | Where-Object { $_ -ne 200 }).Count -eq 0
    Write-Result 'ADMIN_HTTP' $(if ($adminOk) { 'PASS' } else { 'FAIL' })
    # Evidence A: build metadata beside the artifact.
    $metaSha = ''
    try { $metaSha = (Invoke-RestMethod -Uri "$admin/build-meta.json" -TimeoutSec 10).git_sha } catch { $metaSha = '' }
    Write-Result 'RUNTIME_ADMIN_SHA_PROOF' $(if ($metaSha -eq $CandidateSha) { "PASS $metaSha" } else { "FAIL '$metaSha'" })
    # Evidence B: the Phase 03 shell is in the served bundle (global navigation labels).
    $html = (Invoke-WebRequest -Uri "$admin/" -UseBasicParsing -TimeoutSec 10).Content
    $assets = [regex]::Matches($html, '/assets/[^"''\s]+\.js') | ForEach-Object { $_.Value } | Select-Object -Unique
    $uiProof = $false
    foreach ($asset in $assets) {
        $js = (Invoke-WebRequest -Uri "$admin$asset" -UseBasicParsing -TimeoutSec 20).Content
        if ($js -match '/super/system/performance' -and $js -match '/super/billing/pending') { $uiProof = $true; break }
    }
    Write-Result 'RUNTIME_PHASE03_UI_PROOF' $(if ($uiProof) { 'PASS (route table + nav targets present in bundle; confirm the SuperAdminShell in the browser)' } else { 'FAIL' })
    # Login smoke: password goes to the API only, token is used once and never printed.
    $login = 'FAIL'; $fixtures = 'FAIL'
    try {
        $body = @{ password = $cfg['CERT_SUPER_ADMIN_PASSWORD'] } | ConvertTo-Json
        $r = Invoke-RestMethod -Uri "$backend/api/super/login" -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 15
        if ($r.code -eq 200 -and $r.data.token) {
            $login = 'PASS'
            $list = Invoke-RestMethod -Uri "$backend/api/super/merchants" -Headers @{ 'X-Super-Token' = $r.data.token } -TimeoutSec 15
            $json = $list | ConvertTo-Json -Depth 8
            $found = @('cert-merchant-a', 'cert-merchant-b', 'cert-merchant-c' | Where-Object { $json -match $_ }).Count
            if ($found -eq 3) { $fixtures = 'PASS 3/3 fixture merchants' } else { $fixtures = "FAIL $found/3" }
        }
    }
    catch { $login = 'FAIL' }
    Write-Result 'SUPER_LOGIN_SMOKE' $login
    Write-Result 'FIXTURE_MERCHANTS_VISIBLE_VIA_API' $fixtures
    Write-Result 'SUPER_LOGIN_READY' $(if ($login -eq 'PASS') { 'YES' } else { 'NO' })
    Write-Result 'SUPER_LOGIN_MODE' 'PASSWORD_ONLY'
    foreach ($svc in 'admin', 'backend') {
        $id = (Invoke-Compose @('ps', '-q', $svc) | Select-Object -First 1)
        $ports = (& docker port $id 2>&1) -join ' ; '
        Write-Result ("{0}_PUBLISHED" -f $svc.ToUpper()) $ports
        if ($ports -match '0\.0\.0\.0|\[::\]') { Write-Result 'PUBLICLY_ACCESSIBLE' 'YES - FAIL'; return }
    }
    Write-Result 'PUBLICLY_ACCESSIBLE' 'NO'
    Write-Result 'SUPER_RUNTIME_URL' "$admin/super"
}

function Invoke-Credentials {
    $cfg = Read-EnvFile
    Set-Clipboard -Value $cfg['CERT_SUPER_ADMIN_PASSWORD']
    Write-Output 'Test super password copied to the clipboard (not printed). Paste it into the /super login box.'
}

function Invoke-Status { Assert-DockerReady; Invoke-Compose @('ps') }

function Invoke-Down {
    Assert-DockerReady
    if (Test-Path $EnvFile) { Invoke-Compose @('down', '-v', '--remove-orphans') | Out-Null }
    else { Write-Output 'no .env.local; nothing to bring down for this project' }
    if ((Test-Path $WorkRoot) -and $WorkRoot.StartsWith([System.IO.Path]::GetTempPath())) { Remove-Item -LiteralPath $WorkRoot -Recurse -Force }
    if (Test-Path $EnvFile) { Remove-Item -LiteralPath $EnvFile -Force }
    Write-Result 'TORN_DOWN' 'YES'
}

switch ($Action) {
    'Prepare' { Invoke-Prepare }
    'Up' { Invoke-Up }
    'Verify' { Invoke-Verify }
    'Credentials' { Invoke-Credentials }
    'Status' { Invoke-Status }
    'Down' { Invoke-Down }
}
