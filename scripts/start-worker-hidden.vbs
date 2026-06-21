Option Explicit

Dim shell
Dim fso
Dim scriptDir
Dim projectRoot
Dim workerScript
Dim command

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
projectRoot = fso.GetParentFolderName(scriptDir)
workerScript = fso.BuildPath(scriptDir, "start-worker.ps1")

shell.CurrentDirectory = projectRoot
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " _
    & Chr(34) & workerScript & Chr(34)

shell.Run command, 0, True
