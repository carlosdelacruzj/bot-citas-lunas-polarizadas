param(
    [switch]$SkipBuild,
    [int]$RestartDelaySeconds = 30
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$DashboardRoot = Join-Path $ProjectRoot "dashboard"
$DashboardIndex = Join-Path $DashboardRoot "dist\dashboard\browser\index.html"
$LogDir = Join-Path $ProjectRoot "logs"
$BootstrapLog = Join-Path $LogDir ("admin-dashboard-bootstrap-{0}.log" -f (Get-Date -Format "yyyyMMdd"))
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Set-Location $ProjectRoot
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-BootstrapLog {
    param([string]$Message)

    $line = "{0} | {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $BootstrapLog -Value $line -Encoding UTF8
}

function Test-AdminApiProcessRunning {
    $matches = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine.Contains("appointment_bot.admin_api.server")
        }
    return $null -ne $matches
}

if ($RestartDelaySeconds -lt 1) {
    throw "RestartDelaySeconds must be at least 1."
}

if (-not (Test-Path $Python)) {
    throw "Python virtual environment was not found at $Python."
}

if (Test-AdminApiProcessRunning) {
    Write-BootstrapLog "Another local admin API process is already running. Nothing to start."
    exit 0
}

$dashboardReady = $false
while (-not $dashboardReady) {
    try {
        if (-not $SkipBuild) {
            if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
                throw "npm.cmd is required to build the Angular dashboard."
            }
            if (-not (Test-Path (Join-Path $DashboardRoot "node_modules"))) {
                Write-BootstrapLog "Dashboard dependencies are missing. Running npm ci."
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
            Write-BootstrapLog "Building the Angular dashboard."
            Push-Location $DashboardRoot
            try {
                $env:CI = "true"
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

        $dashboardReady = $true
        Write-BootstrapLog "Dashboard build is ready."
    } catch {
        Write-BootstrapLog ("Dashboard preparation failed: {0}" -f $_.Exception.Message)
        Write-BootstrapLog "Retrying dashboard preparation in $RestartDelaySeconds seconds."
        Start-Sleep -Seconds $RestartDelaySeconds
    }
}

while ($true) {
    Write-BootstrapLog "Starting dashboard and admin API at http://127.0.0.1:8766/."
    & $Python -m appointment_bot.admin_api.server
    $exitCode = $LASTEXITCODE
    Write-BootstrapLog "Admin API exited with code $exitCode. Restarting in $RestartDelaySeconds seconds."
    Start-Sleep -Seconds $RestartDelaySeconds
}
