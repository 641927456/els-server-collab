@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\launch_current_launcher.ps1" -Mode local
if errorlevel 1 pause
