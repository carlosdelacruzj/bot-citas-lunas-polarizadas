Option Explicit

Dim shell
Dim fso
Dim scriptDir
Dim projectRoot
Dim workerScript
Dim adminDashboardScript
Dim telegramControlScript
Dim captchaShadowScript
Dim workerCommand
Dim adminDashboardCommand
Dim telegramControlCommand
Dim captchaShadowCommand

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
projectRoot = fso.GetParentFolderName(scriptDir)
workerScript = fso.BuildPath(scriptDir, "start-worker.ps1")
adminDashboardScript = fso.BuildPath(scriptDir, "start-admin-dashboard.ps1")
telegramControlScript = fso.BuildPath(scriptDir, "start-telegram-control.ps1")
captchaShadowScript = fso.BuildPath(scriptDir, "start-captcha-shadow.ps1")

shell.CurrentDirectory = projectRoot
adminDashboardCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " _
    & Chr(34) & adminDashboardScript & Chr(34)
workerCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " _
    & Chr(34) & workerScript & Chr(34)
telegramControlCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " _
    & Chr(34) & telegramControlScript & Chr(34)
captchaShadowCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " _
    & Chr(34) & captchaShadowScript & Chr(34)

shell.Run adminDashboardCommand, 0, False
shell.Run telegramControlCommand, 0, False
shell.Run captchaShadowCommand, 0, False
shell.Run workerCommand, 0, True
