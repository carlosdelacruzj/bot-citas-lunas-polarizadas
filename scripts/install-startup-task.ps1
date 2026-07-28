param(
    [string]$TaskName = "AppointmentBotContinuousWorker"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$RuntimeScript = Join-Path $PSScriptRoot "start-runtime.ps1"
$PowerShellExecutable = Join-Path $PSHOME "powershell.exe"
$UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

if (-not (Test-Path -LiteralPath $RuntimeScript)) {
    throw "Runtime bootstrap was not found at $RuntimeScript."
}

$action = New-ScheduledTaskAction `
    -Execute $PowerShellExecutable `
    -Argument ('-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -File "{0}"' -f $RuntimeScript) `
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
    -Description "Starts the appointment bot runtime after the operator logs on."

Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
Write-Output "Scheduled task '$TaskName' registered for $UserId."
