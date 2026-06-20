@echo off
setlocal EnableExtensions
title QEOS — Install All Runners

set "ROOT=%~dp0.."
set "BACKEND=%ROOT%\backend"

echo.
echo ============================================================
echo   QEOS — Automation ^& Performance Runner Setup
echo   Playwright, Cypress, WDIO, Robot, k6, JMeter, Locust, …
echo ============================================================
echo.

cd /d "%BACKEND%"
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Backend venv not found. Run setup-and-run.bat first.
  pause
  exit /b 1
)

call ".venv\Scripts\python.exe" scripts\install_all_runners.py
set "RC=%ERRORLEVEL%"

echo.
if %RC% NEQ 0 (
  echo Some critical runners failed. Fix issues above and retry.
) else (
  echo Runner setup complete. Restart backend if it is running:
  echo   scripts\restart-backend.bat
)
echo.
pause
endlocal
exit /b %RC%
