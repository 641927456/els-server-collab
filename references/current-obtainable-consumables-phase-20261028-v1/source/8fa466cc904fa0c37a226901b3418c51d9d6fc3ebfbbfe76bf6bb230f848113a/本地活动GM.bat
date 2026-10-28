@echo off
"%~dp0python\python.exe" -B -X utf8 "%~dp0tools\open_local_activity_gm.py"
if errorlevel 1 pause
