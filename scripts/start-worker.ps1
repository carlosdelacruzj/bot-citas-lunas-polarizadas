param(
    [int]$DockerTimeoutSeconds = 180,
    [int]$PostgresTimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$LogDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$BootstrapLog = Join-Path $LogDir ("worker-bootstrap-{0}.log" -f (Get-Date -Format "yyyyMMdd"))

function Write-BootstrapLog {
    param([string]$Message)
    $line = "{0} | {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $BootstrapLog -Value $line -Encoding UTF8
}

function Test-CommandAvailable {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Wait-Until {
    param(
        [scriptblock]$Condition,
        [int]$TimeoutSeconds,
        [string]$WaitingMessage,
        [string]$TimeoutMessage
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Condition) {
            return
        }
        Write-BootstrapLog $WaitingMessage
        Start-Sleep -Seconds 5
    }

    throw $TimeoutMessage
}

Write-BootstrapLog "Bootstrap started."

$dockerDesktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
if (Test-Path $dockerDesktop) {
    $dockerProcesses = Get-Process -Name "Docker Desktop", "com.docker.backend" -ErrorAction SilentlyContinue
    if (-not $dockerProcesses) {
        Write-BootstrapLog "Starting Docker Desktop."
        Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
    }
}

if (-not (Test-CommandAvailable "docker")) {
    throw "docker command is not available in PATH."
}

Wait-Until `
    -TimeoutSeconds $DockerTimeoutSeconds `
    -WaitingMessage "Waiting for Docker engine." `
    -TimeoutMessage "Docker engine did not become ready." `
    -Condition {
        try {
            docker info *> $null
            return $LASTEXITCODE -eq 0
        } catch {
            return $false
        }
    }

Write-BootstrapLog "Docker engine is ready. Starting compose services."
docker compose up -d *> $null
if ($LASTEXITCODE -ne 0) {
    throw "docker compose up -d failed."
}

Wait-Until `
    -TimeoutSeconds $PostgresTimeoutSeconds `
    -WaitingMessage "Waiting for appointment-bot-postgres health." `
    -TimeoutMessage "appointment-bot-postgres did not become healthy." `
    -Condition {
        try {
            $health = docker inspect appointment-bot-postgres --format "{{.State.Health.Status}}" 2>$null
            return $LASTEXITCODE -eq 0 -and $health.Trim() -eq "healthy"
        } catch {
            return $false
        }
    }

Write-BootstrapLog "Postgres is healthy. Starting continuous worker."
$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python virtual environment was not found at $python."
}

& $python -m appointment_bot.services.continuous_host
$exitCode = $LASTEXITCODE
Write-BootstrapLog "Continuous worker exited with code $exitCode."
exit $exitCode
