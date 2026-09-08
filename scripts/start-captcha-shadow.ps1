param(
    [int]$HealthCheckIntervalSeconds = 30,
    [int]$RestartDelaySeconds = 15
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$CaptchaProjectRoot = Join-Path (Split-Path $ProjectRoot -Parent) "test-captcha"
$StartScript = Join-Path $CaptchaProjectRoot "start_shadow_service.ps1"
$StopScript = Join-Path $CaptchaProjectRoot "stop_shadow_service.ps1"
$HealthUrl = "http://127.0.0.1:8787/health"

$LogDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$BootstrapLog = Join-Path $LogDir ("captcha-shadow-bootstrap-{0}.log" -f (Get-Date -Format "yyyyMMdd"))
$EnvPath = Join-Path $ProjectRoot ".env"

function Write-BootstrapLog {
    param([string]$Message)

    $line = "{0} | {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $BootstrapLog -Value $line -Encoding UTF8
}

function Test-LocalBooleanSetting {
    param(
        [string]$Name,
        [bool]$Default = $false
    )

    if (-not (Test-Path -LiteralPath $EnvPath)) {
        return $Default
    }
    $match = Get-Content -LiteralPath $EnvPath |
        Where-Object { $_ -match ("^\s*{0}\s*=" -f [regex]::Escape($Name)) } |
        Select-Object -Last 1
    if (-not $match) {
        return $Default
    }
    $value = ($match -split "=", 2)[1].Trim().Trim('"').Trim("'").ToLowerInvariant()
    return $value -in @("1", "true", "yes", "on")
}

function Test-CaptchaShadowHealthy {
    try {
        $health = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 3
        return $health.status -eq "ok"
    } catch {
        return $false
    }
}

function Stop-UnhealthyCaptchaShadow {
    $matches = Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -in @("python.exe", "pythonw.exe") -and
            $_.CommandLine -and
            $_.CommandLine.Contains("recognizer.src.shadow_service")
        }
    if (-not $matches) {
        return
    }

    Write-BootstrapLog "An unhealthy CAPTCHA shadow process was found. Stopping it before restart."
    if (Test-Path -LiteralPath $StopScript) {
        try {
            & $StopScript *>&1 | ForEach-Object {
                Write-BootstrapLog ("  {0}" -f $_)
            }
            $remaining = Get-CimInstance Win32_Process |
                Where-Object {
                    $_.Name -in @("python.exe", "pythonw.exe") -and
                    $_.CommandLine -and
                    $_.CommandLine.Contains("recognizer.src.shadow_service")
                }
            if (-not $remaining) {
                return
            }
            Write-BootstrapLog "The standard stop script left a CAPTCHA shadow process running."
        } catch {
            Write-BootstrapLog ("The standard stop script failed: {0}" -f $_.Exception.Message)
        }
    }

    foreach ($match in $matches) {
        Stop-Process -Id $match.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

if (-not (Test-LocalBooleanSetting -Name "CAPTCHA_SHADOW_SERVICE_ENABLED")) {
    Write-BootstrapLog "CAPTCHA shadow is in cold standby."
    if (Test-Path -LiteralPath $StopScript) {
        & $StopScript *>&1 | ForEach-Object {
            Write-BootstrapLog ("  {0}" -f $_)
        }
    }
    exit 0
}

Write-BootstrapLog "CAPTCHA shadow supervisor started."

while ($true) {
    if (Test-CaptchaShadowHealthy) {
        Start-Sleep -Seconds $HealthCheckIntervalSeconds
        continue
    }

    try {
        if (-not (Test-Path -LiteralPath $StartScript)) {
            throw "CAPTCHA shadow start script was not found at $StartScript."
        }

        Stop-UnhealthyCaptchaShadow
        Write-BootstrapLog "Starting CAPTCHA shadow service."
        & $StartScript *>&1 | ForEach-Object {
            Write-BootstrapLog ("  {0}" -f $_)
        }

        if (-not (Test-CaptchaShadowHealthy)) {
            throw "CAPTCHA shadow service did not report a healthy state after startup."
        }
        Write-BootstrapLog "CAPTCHA shadow service is healthy at $HealthUrl."
    } catch {
        Write-BootstrapLog ("CAPTCHA shadow startup failed: {0}" -f $_.Exception.Message)
        Write-BootstrapLog "Retrying in $RestartDelaySeconds seconds."
        Start-Sleep -Seconds $RestartDelaySeconds
    }
}
