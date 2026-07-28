param(
    [int]$RestartDelaySeconds = 15
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogDir = Join-Path $ProjectRoot "logs"
$BootstrapLog = Join-Path $LogDir ("telegram-control-bootstrap-{0}.log" -f (Get-Date -Format "yyyyMMdd"))
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Set-Location $ProjectRoot
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-BootstrapLog {
    param([string]$Message)

    $line = "{0} | {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $BootstrapLog -Value $line -Encoding UTF8
}

function Test-TelegramControlProcessRunning {
    $currentProcessId = $PID
    $matches = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
        Where-Object {
            $_.ProcessId -ne $currentProcessId -and
            $_.CommandLine -and
            $_.CommandLine.Contains("appointment_bot.services.telegram_control")
        }
    return $null -ne $matches
}

if ($RestartDelaySeconds -lt 1) {
    throw "RestartDelaySeconds must be at least 1."
}

if (-not (Test-Path $Python)) {
    throw "Python virtual environment was not found at $Python."
}

if (Test-TelegramControlProcessRunning) {
    Write-BootstrapLog "An existing Telegram control process was found. Supervising it until it exits."
    while (Test-TelegramControlProcessRunning) {
        Start-Sleep -Seconds $RestartDelaySeconds
    }
    Write-BootstrapLog "The adopted Telegram control process exited. Starting its replacement."
}

while ($true) {
    Write-BootstrapLog "Starting Telegram control receiver."
    & $Python -m appointment_bot.services.telegram_control
    $exitCode = $LASTEXITCODE
    Write-BootstrapLog "Telegram control exited with code $exitCode. Restarting in $RestartDelaySeconds seconds."
    Start-Sleep -Seconds $RestartDelaySeconds
}
