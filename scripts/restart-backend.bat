@echo off
setlocal EnableExtensions EnableDelayedExpansion
title QEOS Backend (port 8000)

set "ROOT=%~dp0.."
set "SCRIPTS=%~dp0"
set "PORT=8000"

echo.
echo [%date% %time%] Restarting backend on port %PORT%...
call "%SCRIPTS%stop-servers.bat"

for /L %%R in (1,1,5) do (
  call "%SCRIPTS%lib\kill-port.bat" %PORT%
  call "%SCRIPTS%lib\port-in-use.bat" %PORT%
  if errorlevel 1 (
    ping 127.0.0.1 -n 2 >nul
  ) else (
    goto :port_free
  )
)

:port_free
call "%SCRIPTS%lib\port-in-use.bat" %PORT%
if not errorlevel 1 (
  echo WARNING: Port %PORT% may still be in use. Starting backend anyway...
)

cd /d "%ROOT%\backend"
if not exist ".venv\Scripts\uvicorn.exe" (
  echo ERROR: Backend venv not found. Run setup-and-run.bat first.
  pause
  exit /b 1
)

echo.
echo Starting backend at http://127.0.0.1:%PORT%
echo Press Ctrl+C to stop this window.
echo.

call ".venv\Scripts\uvicorn.exe" app.main:app --host 127.0.0.1 --port %PORT%

endlocal
