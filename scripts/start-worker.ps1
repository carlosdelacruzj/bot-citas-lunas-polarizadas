param(
    [int]$DockerTimeoutSeconds = 180,
    [int]$PostgresTimeoutSeconds = 180,
    [int]$WorkerRestartDelaySeconds = 30,
    [int]$LeaseUnavailableDelaySeconds = 300,
    [string]$DailyResumeTime = "07:30"
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

function Invoke-LoggedCommand {
    param(
        [string]$Description,
        [scriptblock]$Command
    )

    Write-BootstrapLog $Description
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $Command *>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($output) {
        foreach ($line in $output) {
            Write-BootstrapLog ("  {0}" -f $line)
        }
    }
    if ($exitCode -ne 0) {
        throw "$Description failed with exit code $exitCode."
    }
}

function Test-WorkerProcessRunning {
    $currentProcessId = $PID
    $matches = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
        Where-Object {
            $_.ProcessId -ne $currentProcessId -and
            $_.CommandLine -and
            $_.CommandLine.Contains("appointment_bot.services.continuous_host")
        }
    return $null -ne $matches
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

function Get-SecondsUntilDailyResume {
    param([string]$ResumeTime)

    try {
        $parts = $ResumeTime.Split(":", 2)
        if ($parts.Count -ne 2) {
            throw "invalid"
        }
        $hour = [int]$parts[0]
        $minute = [int]$parts[1]
        if ($hour -lt 0 -or $hour -gt 23 -or $minute -lt 0 -or $minute -gt 59) {
            throw "invalid"
        }
    } catch {
        throw "DailyResumeTime must use HH:mm format. Current value: $ResumeTime"
    }

    $now = Get-Date
    $resumeAt = Get-Date -Hour $hour -Minute $minute -Second 0
    if ($resumeAt -le $now) {
        $resumeAt = $resumeAt.AddDays(1)
    }
    return [int][Math]::Ceiling(($resumeAt - $now).TotalSeconds)
}

try {
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

    $composeStarted = $false
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Invoke-LoggedCommand `
                -Description "Docker engine is ready. Starting compose services. Attempt $attempt." `
                -Command { docker compose up -d }
            $composeStarted = $true
            break
        } catch {
            Write-BootstrapLog ("Compose start failed: {0}" -f $_.Exception.Message)
            if ($attempt -ge 3) {
                throw
            }
            Start-Sleep -Seconds 10
        }
    }

    if (-not $composeStarted) {
        throw "docker compose up -d did not complete."
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

    while ($true) {
        if (Test-WorkerProcessRunning) {
            Write-BootstrapLog "Another local continuous worker process is already running. Waiting $WorkerRestartDelaySeconds seconds."
            Start-Sleep -Seconds $WorkerRestartDelaySeconds
            continue
        }
        & $python -m appointment_bot.services.continuous_host
        $exitCode = $LASTEXITCODE
        Write-BootstrapLog "Continuous worker exited with code $exitCode."
        if ($exitCode -eq 0) {
            $restartDelay = Get-SecondsUntilDailyResume -ResumeTime $DailyResumeTime
            Write-BootstrapLog "Daily cutoff reached. Restarting continuous worker at $DailyResumeTime in $restartDelay seconds unless the PC restarts first."
            Start-Sleep -Seconds $restartDelay
            continue
        }
        if ($exitCode -eq 76) {
            $restartDelay = $LeaseUnavailableDelaySeconds
            Write-BootstrapLog "Another host owns the worker lease. Retrying in $restartDelay seconds."
        } else {
            $restartDelay = if ($exitCode -eq 75) { 1 } else { $WorkerRestartDelaySeconds }
            Write-BootstrapLog "Restarting continuous worker in $restartDelay seconds."
        }
        Start-Sleep -Seconds $restartDelay
    }
} catch {
    Write-BootstrapLog ("Bootstrap failed: {0}" -f $_.Exception.Message)
    exit 1
}
