@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\launch_current_launcher.ps1" -Mode select
if errorlevel 1 pause
