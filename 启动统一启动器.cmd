@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start_unified_launcher.ps1" -RepositoryRoot "%~dp0."
if errorlevel 1 pause
endlocal
