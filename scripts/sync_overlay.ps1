param(
    [switch]$Force,
    [switch]$Push
)

$ErrorActionPreference = 'Stop'

function Invoke-Git {
    & git @args
    if ($LASTEXITCODE -ne 0) {
        throw "git $args failed with exit code $LASTEXITCODE"
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$worktreeStatus = @(git status --porcelain)
if ($worktreeStatus.Count -gt 0) {
    throw 'Working tree must be clean before running overlay sync.'
}

Invoke-Git fetch origin

if (-not (git remote | Select-String '^upstream$')) {
    Invoke-Git remote add upstream https://github.com/guoh064/AzurLaneAutoScript.git
}

Invoke-Git fetch upstream

$upstreamAlreadyIncluded = $true
try {
    Invoke-Git merge-base --is-ancestor upstream/main origin/master
}
catch {
    $upstreamAlreadyIncluded = $false
}

if ($upstreamAlreadyIncluded -and -not $Force) {
    Write-Host 'upstream/main is already included in origin/master, skipping sync.'
    exit 0
}

$originalBranch = (Invoke-Git rev-parse --abbrev-ref HEAD).Trim()
$overlayBase = (Invoke-Git merge-base upstream/main origin/master).Trim()
$patchDir = Join-Path ([System.IO.Path]::GetTempPath()) 'alas-overlay-patches'
$patchFile = Join-Path $patchDir 'overlay.patch'

try {
    if (Test-Path -LiteralPath $patchDir) {
        Remove-Item -LiteralPath $patchDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $patchDir | Out-Null

    Write-Host "Overlay base: $overlayBase"
    Invoke-Git diff --binary $overlayBase origin/master --output=$patchFile
    if ((Get-Item -LiteralPath $patchFile).Length -eq 0) {
        Write-Host 'No local overlay diff found, nothing to apply.'
        exit 0
    }

    Invoke-Git checkout -B sync/overlay upstream/main
    Invoke-Git apply --3way --index $patchFile

    $upstreamSha = (Invoke-Git rev-parse --short upstream/main).Trim()
    Invoke-Git commit -m "Apply local overlay on upstream $upstreamSha"

    if ($Push) {
        Invoke-Git push origin HEAD:master --force-with-lease
    }
}
catch {
    Invoke-Git reset --hard upstream/main | Out-Null
    throw
}
finally {
    if (Test-Path -LiteralPath $patchDir) {
        Remove-Item -LiteralPath $patchDir -Recurse -Force
    }

    if ($originalBranch -and $originalBranch -ne 'HEAD') {
        Invoke-Git checkout $originalBranch | Out-Null
    }
}
