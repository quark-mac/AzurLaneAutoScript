param(
    [string]$Author = 'quark-mac',
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

if ((git status --porcelain).Trim()) {
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

if ($upstreamAlreadyIncluded) {
    Write-Host 'upstream/main is already included in origin/master, skipping sync.'
    exit 0
}

$originalBranch = (Invoke-Git rev-parse --abbrev-ref HEAD).Trim()
$commits = @(Invoke-Git rev-list --reverse --no-merges --author=$Author 'upstream/main..origin/master')

if ($commits.Count -eq 0) {
    Write-Host "No local overlay commits found for author '$Author', nothing to apply."
    exit 0
}

try {
    Invoke-Git checkout -B sync/overlay upstream/main
    foreach ($commit in $commits) {
        Invoke-Git format-patch -1 --stdout --binary $commit | git am -3
        if ($LASTEXITCODE -ne 0) {
            throw "Applying overlay patch $commit failed."
        }
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
    if ($originalBranch -and $originalBranch -ne 'HEAD') {
        Invoke-Git checkout $originalBranch | Out-Null
    }
}
