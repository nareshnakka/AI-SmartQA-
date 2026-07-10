@echo off
REM Non-interactive full stack restart.
setlocal EnableExtensions

set "SCRIPTS=%~dp0"
set "ROOT=%SCRIPTS%.."
set "PORT=3000"

echo.
echo QEOS — auto restart (backend + frontend)
echo.

call "%SCRIPTS%restart-backend-auto.bat"
if errorlevel 1 (
  echo Backend restart failed.
  exit /b 1
)

call "%SCRIPTS%lib\kill-port.bat" %PORT%
ping 127.0.0.1 -n 2 >nul

cd /d "%ROOT%\frontend"
if not exist "node_modules" (
  echo Installing frontend dependencies...
  call npm install
  if errorlevel 1 (
    echo FAILED: npm install
    exit /b 1
  )
)

echo Starting frontend...
start "QEOS Frontend" /MIN cmd /k "cd /d ""%ROOT%\frontend"" && npm run dev -- -p %PORT%"

for /L %%W in (1,1,60) do (
  ping 127.0.0.1 -n 2 >nul
  powershell -NoProfile -Command "try { (Invoke-WebRequest 'http://localhost:%PORT%' -TimeoutSec 3 -UseBasicParsing).StatusCode; exit 0 } catch { exit 1 }" >nul 2>&1
  if not errorlevel 1 (
    echo OK: frontend http://localhost:%PORT%
    echo.
    echo App ready: http://localhost:%PORT%
    echo API health: http://127.0.0.1:8000/health
    echo Opening app in your default browser...
    call "%SCRIPTS%lib\open-app.bat" %PORT%
    exit /b 0
  )
)

echo FAILED: frontend did not respond on http://localhost:%PORT%
echo Check the QEOS Frontend window for errors.
exit /b 1
