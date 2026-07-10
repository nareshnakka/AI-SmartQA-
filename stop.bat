@echo off
setlocal EnableExtensions EnableDelayedExpansion
title QEOS - Stop All

set "QUIET=0"
if /i "%~1"=="/quiet" set "QUIET=1"

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=3000"

if "%QUIET%"=="0" (
  echo.
  echo ============================================================
  echo   QEOS - Stop All Servers
  echo ============================================================
  echo.
)

echo Stopping QEOS backend and frontend...

for %%P in (%BACKEND_PORT% %FRONTEND_PORT%) do call :kill_port %%P

powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |" ^
  "Where-Object { $_.Name -match 'python|uvicorn|node' -and $_.CommandLine -match 'app\.main:app|uvicorn|next dev' } |" ^
  "ForEach-Object { Write-Host ('Stopping ' + $_.ProcessId + ' ' + $_.Name); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

for /L %%N in (1,1,3) do (
  set "BUSY=0"
  for %%P in (%BACKEND_PORT% %FRONTEND_PORT%) do (
    call :port_in_use %%P
    if not errorlevel 1 set "BUSY=1"
  )
  if "!BUSY!"=="0" goto :done
  for %%P in (%BACKEND_PORT% %FRONTEND_PORT%) do call :kill_port %%P
  ping 127.0.0.1 -n 2 >nul
)

:done
echo All QEOS servers stopped.

if "%QUIET%"=="0" (
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
  "ForEach-Object { $procId = $_.OwningProcess; if ($procId) { Write-Host ('Killing PID ' + $procId + ' on port %PORT%'); Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue } }"
endlocal
exit /b 0

:port_in_use
setlocal
set "PORT=%~1"
powershell -NoProfile -Command ^
  "$c = @(Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue); exit [int]($c.Count -gt 0)"
endlocal
exit /b %ERRORLEVEL%
