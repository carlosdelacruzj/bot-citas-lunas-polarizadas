param(
    [string]$TaskName = "AppointmentBotContinuousWorker"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$RuntimeLauncher = Join-Path $PSScriptRoot "start-runtime.pyw"
$PythonWindowed = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
$UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

if (-not (Test-Path -LiteralPath $RuntimeLauncher)) {
    throw "Windowless runtime launcher was not found at $RuntimeLauncher."
}
if (-not (Test-Path -LiteralPath $PythonWindowed)) {
    throw "Windowed Python executable was not found at $PythonWindowed."
}

$action = New-ScheduledTaskAction `
    -Execute $PythonWindowed `
    -Argument ('"{0}"' -f $RuntimeLauncher) `
    -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $UserId
$principal = New-ScheduledTaskPrincipal `
    -UserId $UserId `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable

$task = New-ScheduledTask `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Supervises the appointment bot runtime without opening a console window."

Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
Write-Output "Scheduled task '$TaskName' registered for $UserId."
