@echo off
REM Wait until backend health and frontend respond (or timeout).
setlocal EnableExtensions EnableDelayedExpansion

set "BACKEND_PORT=%~1"
set "FRONTEND_PORT=%~2"
if "%BACKEND_PORT%"=="" set "BACKEND_PORT=8000"
if "%FRONTEND_PORT%"=="" set "FRONTEND_PORT=3000"
set "APP_URL=http://localhost:%FRONTEND_PORT%"

echo Waiting for servers to respond (up to 90 seconds)...
set /a WAIT_COUNT=0
:wait_loop
set /a WAIT_COUNT+=1
if !WAIT_COUNT! GTR 45 goto :wait_done
powershell -NoProfile -Command "try { $h = Invoke-WebRequest -Uri 'http://127.0.0.1:%BACKEND_PORT%/health' -TimeoutSec 2 -UseBasicParsing; if ($h.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
  powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%APP_URL%' -TimeoutSec 2 -UseBasicParsing | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
  if not errorlevel 1 (
    echo Both backend and frontend are up.
    endlocal
    exit /b 0
  )
)
echo   ... still starting (!WAIT_COUNT!/45)
timeout /t 2 /nobreak >nul
goto :wait_loop

:wait_done
echo Servers may still be starting - opening browser anyway.
endlocal
exit /b 0
