@echo off
REM Token Monitor backend one-click stop (Windows). Double-click or run from cmd.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
pause
