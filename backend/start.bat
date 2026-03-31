@echo off
REM Token Monitor backend one-click start (Windows). Double-click or run from cmd.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
set EXITCODE=%ERRORLEVEL%
echo.
if %EXITCODE% neq 0 echo Failed, exit code %EXITCODE%
pause
exit /b %EXITCODE%
