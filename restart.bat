@echo off
setlocal EnableExtensions EnableDelayedExpansion
title QEOS - Restart

set "AUTO=0"
if /i "%~1"=="/auto" set "AUTO=1"

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "BACKEND=%ROOT%\backend"
set "FRONTEND=%ROOT%\frontend"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=3000"
set "APP_URL=http://localhost:%FRONTEND_PORT%"

if "%AUTO%"=="0" (
  echo.
  echo ============================================================
  echo   QEOS - Restart (stop + start backend and frontend)
  echo ============================================================
  echo.
  echo [1/3] Stopping existing servers...
) else (
  echo Stopping existing servers...
)

call "%ROOT%\stop.bat" /quiet
ping 127.0.0.1 -n 2 >nul

if "%AUTO%"=="0" echo.
if "%AUTO%"=="0" echo [2/3] Starting backend and frontend...

if not exist "%BACKEND%\.venv\Scripts\uvicorn.exe" (
  echo ERROR: Backend not installed. Run update-and-install.bat first.
  if "%AUTO%"=="0" pause
  endlocal
  exit /b 1
)

for /L %%R in (1,1,5) do (
  call :kill_port %BACKEND_PORT%
  call :port_in_use %BACKEND_PORT%
  if errorlevel 1 (ping 127.0.0.1 -n 2 >nul) else goto :start_backend
)

:start_backend
start "QEOS Backend" /MIN cmd /k "cd /d ""%BACKEND%"" && .venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port %BACKEND_PORT%"

for /L %%W in (1,1,45) do (
  ping 127.0.0.1 -n 2 >nul
  powershell -NoProfile -Command "try { $r=Invoke-RestMethod 'http://127.0.0.1:%BACKEND_PORT%/health' -TimeoutSec 3; if ($r.status -eq 'healthy') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
  if not errorlevel 1 goto :start_frontend
)
echo ERROR: Backend did not start. Check the QEOS Backend window.
if "%AUTO%"=="0" pause
endlocal
exit /b 1

:start_frontend
call :kill_port %FRONTEND_PORT%
ping 127.0.0.1 -n 2 >nul

if not exist "%FRONTEND%\node_modules" (
  echo Installing frontend packages...
  cd /d "%FRONTEND%"
  call npm install
  if errorlevel 1 (
    echo ERROR: npm install failed.
    if "%AUTO%"=="0" pause
    endlocal
    exit /b 1
  )
)

start "QEOS Frontend" /MIN cmd /k "cd /d ""%FRONTEND%"" && npm run dev -- -p %FRONTEND_PORT%"

for /L %%W in (1,1,60) do (
  ping 127.0.0.1 -n 2 >nul
  powershell -NoProfile -Command "try { (Invoke-WebRequest 'http://localhost:%FRONTEND_PORT%' -TimeoutSec 3 -UseBasicParsing).StatusCode; exit 0 } catch { exit 1 }" >nul 2>&1
  if not errorlevel 1 goto :ready
)
echo ERROR: Frontend did not start. Check the QEOS Frontend window.
if "%AUTO%"=="0" pause
endlocal
exit /b 1

:ready
call :wait_for_servers
start "" "%APP_URL%"

if "%AUTO%"=="0" (
  echo.
  echo [3/3] Ready.
  echo.
  echo ============================================================
  echo   QEOS is running
  echo   App:  %APP_URL%
  echo   API:  http://127.0.0.1:%BACKEND_PORT%/health
  echo.
  echo   Keep the Backend and Frontend windows open while testing.
  echo   To stop everything, run: stop.bat
  echo ============================================================
  echo.
  pause
)
endlocal
exit /b 0

:kill_port
setlocal
set "PORT=%~1"
powershell -NoProfile -Command ^
  "Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue |" ^
  "ForEach-Object { $procId = $_.OwningProcess; if ($procId) { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue } }"
endlocal
exit /b 0

:port_in_use
setlocal
set "PORT=%~1"
powershell -NoProfile -Command ^
  "$c = @(Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue); exit [int]($c.Count -gt 0)"
endlocal
exit /b %ERRORLEVEL%

:wait_for_servers
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
    exit /b 0
  )
)
if "%AUTO%"=="0" echo   ... still starting (!WAIT_COUNT!/45)
timeout /t 2 /nobreak >nul
goto :wait_loop
:wait_done
echo Servers may still be starting - opening browser anyway.
exit /b 0
