param(
    [ValidateRange(1, 3600)]
    [int]$SupervisorCheckIntervalSeconds = 15
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PowerShellExecutable = Join-Path $PSHOME "powershell.exe"
$LogDir = Join-Path $ProjectRoot "logs"
$BootstrapLog = Join-Path $LogDir ("runtime-bootstrap-{0}.log" -f (Get-Date -Format "yyyyMMdd"))
$EnvPath = Join-Path $ProjectRoot ".env"

Set-Location $ProjectRoot
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-BootstrapLog {
    param([string]$Message)

    $line = "{0} | {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $BootstrapLog -Value $line -Encoding UTF8
}

function Test-BootstrapRunning {
    param([string]$ScriptPath)

    $currentProcessId = $PID
    $running = Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe' OR Name = 'pwsh.exe'" |
        Where-Object {
            $_.ProcessId -ne $currentProcessId -and
            $_.CommandLine -and
            $_.CommandLine.IndexOf(
                $ScriptPath,
                [System.StringComparison]::OrdinalIgnoreCase
            ) -ge 0
        }
    return $null -ne $running
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

function Start-Bootstrap {
    param(
        [string]$Name,
        [string]$ScriptPath
    )

    if (Test-BootstrapRunning -ScriptPath $ScriptPath) {
        return
    }

    Write-BootstrapLog "$Name supervisor is not running. Starting it."
    $process = Start-Process `
        -FilePath $PowerShellExecutable `
        -ArgumentList @(
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-File",
            ('"{0}"' -f $ScriptPath)
        ) `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -PassThru
    Write-BootstrapLog "$Name supervisor started with PID $($process.Id)."
}

$bootstrapDefinitions = @(
    @{
        Name = "admin dashboard"
        ScriptPath = Join-Path $PSScriptRoot "start-admin-dashboard.ps1"
    },
    @{
        Name = "Telegram control"
        ScriptPath = Join-Path $PSScriptRoot "start-telegram-control.ps1"
    },
    @{
        Name = "worker"
        ScriptPath = Join-Path $PSScriptRoot "start-worker.ps1"
    }
)

$captchaShadowServiceEnabled = Test-LocalBooleanSetting `
    -Name "CAPTCHA_SHADOW_SERVICE_ENABLED"
if ($captchaShadowServiceEnabled) {
    $bootstrapDefinitions = @(
        $bootstrapDefinitions[0],
        $bootstrapDefinitions[1],
        @{
            Name = "CAPTCHA shadow"
            ScriptPath = Join-Path $PSScriptRoot "start-captcha-shadow.ps1"
        },
        $bootstrapDefinitions[2]
    )
} else {
    Write-BootstrapLog "CAPTCHA shadow is in cold standby; supervisor will not be started."
}

try {
    foreach ($definition in $bootstrapDefinitions) {
        if (-not (Test-Path -LiteralPath $definition.ScriptPath)) {
            throw "$($definition.Name) supervisor was not found at $($definition.ScriptPath)."
        }
    }

    Write-BootstrapLog (
        "Runtime root supervisor started. Checking child supervisors every {0} seconds." -f
        $SupervisorCheckIntervalSeconds
    )

    while ($true) {
        foreach ($definition in $bootstrapDefinitions) {
            try {
                Start-Bootstrap `
                    -Name $definition.Name `
                    -ScriptPath $definition.ScriptPath
            } catch {
                Write-BootstrapLog (
                    "Could not supervise {0}: {1}" -f
                    $definition.Name,
                    $_.Exception.Message
                )
            }
        }
        Start-Sleep -Seconds $SupervisorCheckIntervalSeconds
    }
} catch {
    Write-BootstrapLog ("Runtime root supervisor failed: {0}" -f $_.Exception.Message)
    exit 1
}
