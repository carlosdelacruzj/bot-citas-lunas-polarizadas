param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$DashboardRoot = Join-Path $ProjectRoot "dashboard"
$DashboardIndex = Join-Path $DashboardRoot "dist\dashboard\browser\index.html"

Set-Location $ProjectRoot

if (-not $SkipBuild) {
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
        throw "npm.cmd is required to build the Angular dashboard."
    }
    if (-not (Test-Path (Join-Path $DashboardRoot "node_modules"))) {
        Push-Location $DashboardRoot
        try {
            & npm.cmd ci
            if ($LASTEXITCODE -ne 0) {
                throw "npm ci failed with exit code $LASTEXITCODE."
            }
        } finally {
            Pop-Location
        }
    }
    Push-Location $DashboardRoot
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) {
            throw "Dashboard build failed with exit code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path $DashboardIndex)) {
    throw "Dashboard build not found. Run without -SkipBuild first."
}

Write-Host "Dashboard and admin API: http://127.0.0.1:8766/"
python -m appointment_bot.admin_api.server
