param()

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

function Start-Bootstrap {
    param(
        [string]$Name,
        [string]$ScriptName
    )

    $scriptPath = Join-Path $PSScriptRoot $ScriptName
    if (-not (Test-Path -LiteralPath $scriptPath)) {
        throw "$Name bootstrap was not found at $scriptPath."
    }

    $running = Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe' OR Name = 'pwsh.exe'" |
        Where-Object {
            $_.ProcessId -ne $PID -and
            $_.CommandLine -and
            $_.CommandLine.IndexOf(
                $scriptPath,
                [System.StringComparison]::OrdinalIgnoreCase
            ) -ge 0
        }
    if ($running) {
        Write-BootstrapLog "$Name bootstrap is already running. Nothing to start."
        return
    }

    Write-BootstrapLog "Starting $Name bootstrap."
    Start-Process `
        -FilePath $PowerShellExecutable `
        -ArgumentList @(
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-File",
            ('"{0}"' -f $scriptPath)
        ) `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden
}

try {
    Write-BootstrapLog "Runtime bootstrap started."

    Start-Bootstrap -Name "admin dashboard" -ScriptName "start-admin-dashboard.ps1"
    Start-Bootstrap -Name "Telegram control" -ScriptName "start-telegram-control.ps1"
    Start-Bootstrap -Name "CAPTCHA shadow" -ScriptName "start-captcha-shadow.ps1"
    Start-Bootstrap -Name "worker" -ScriptName "start-worker.ps1"

    Write-BootstrapLog "All runtime bootstrap processes were requested."
    exit 0
} catch {
    Write-BootstrapLog ("Runtime bootstrap failed: {0}" -f $_.Exception.Message)
    exit 1
}
