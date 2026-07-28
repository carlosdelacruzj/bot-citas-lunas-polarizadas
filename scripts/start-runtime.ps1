param(
    [ValidateRange(1, 3600)]
    [int]$SupervisorCheckIntervalSeconds = 15
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PowerShellExecutable = Join-Path $PSHOME "powershell.exe"
$LogDir = Join-Path $ProjectRoot "logs"
$BootstrapLog = Join-Path $LogDir ("runtime-bootstrap-{0}.log" -f (Get-Date -Format "yyyyMMdd"))

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
        Name = "CAPTCHA shadow"
        ScriptPath = Join-Path $PSScriptRoot "start-captcha-shadow.ps1"
    },
    @{
        Name = "worker"
        ScriptPath = Join-Path $PSScriptRoot "start-worker.ps1"
    }
)

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
