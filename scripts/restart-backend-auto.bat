@echo off
REM Non-interactive backend restart — no pause, starts minimized window.
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPTS=%~dp0"
set "ROOT=%SCRIPTS%.."
set "PORT=8000"

call "%SCRIPTS%stop-servers.bat"

for /L %%R in (1,1,5) do (
  call "%SCRIPTS%lib\kill-port.bat" %PORT%
  call "%SCRIPTS%lib\port-in-use.bat" %PORT%
  if errorlevel 1 (ping 127.0.0.1 -n 2 >nul) else goto :start
)

:start
cd /d "%ROOT%\backend"
if not exist ".venv\Scripts\uvicorn.exe" (
  echo FAILED: backend venv missing — run setup-and-run.bat
  exit /b 1
)

echo Starting backend...
start "QEOS Backend" /MIN cmd /k "cd /d ""%ROOT%\backend"" && .venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port %PORT%"

for /L %%W in (1,1,45) do (
  ping 127.0.0.1 -n 2 >nul
  powershell -NoProfile -Command "try { $r=Invoke-RestMethod 'http://127.0.0.1:%PORT%/health' -TimeoutSec 3; if ($r.status -eq 'healthy') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
  if not errorlevel 1 (
    echo OK: backend http://127.0.0.1:%PORT%/health
    exit /b 0
  )
)

echo FAILED: backend did not respond on http://127.0.0.1:%PORT%/health
echo Check the QEOS Backend window for errors.
exit /b 1
