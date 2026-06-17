param(
    [string]$Author = 'quark-mac',
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
$commits = @(Invoke-Git rev-list --reverse --no-merges --author=$Author 'upstream/main..origin/master')
$patchDir = Join-Path ([System.IO.Path]::GetTempPath()) 'alas-overlay-patches'

if ($commits.Count -eq 0) {
    Write-Host "No local overlay commits found for author '$Author', nothing to apply."
    exit 0
}

try {
    if (Test-Path -LiteralPath $patchDir) {
        Remove-Item -LiteralPath $patchDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $patchDir | Out-Null

    Invoke-Git checkout -B sync/overlay upstream/main
    foreach ($commit in $commits) {
        $patchPath = (Invoke-Git format-patch -1 --binary --output-directory $patchDir $commit | Select-Object -Last 1).Trim()
        Invoke-Git am -3 $patchPath
    }

    if ($Push) {
        Invoke-Git push origin HEAD:master --force-with-lease
    }
}
catch {
    if (Test-Path .git\rebase-apply) {
        git am --abort | Out-Null
    }
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
