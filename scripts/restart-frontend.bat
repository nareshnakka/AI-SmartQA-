@echo off
setlocal EnableExtensions
title QEOS Frontend (port 3000)

set "ROOT=%~dp0.."
set "SCRIPTS=%~dp0"
set "PORT=3000"

echo.
echo [%date% %time%] Restarting frontend on port %PORT%...
call "%SCRIPTS%lib\kill-port.bat" %PORT%
ping 127.0.0.1 -n 2 >nul

cd /d "%ROOT%\frontend"
if not exist "package.json" (
  echo ERROR: frontend\package.json not found.
  pause
  exit /b 1
)

if not exist "node_modules" (
  echo Installing npm dependencies...
  call npm install
  if errorlevel 1 (
    echo npm install failed.
    pause
    exit /b 1
  )
)

echo.
echo Starting frontend at http://localhost:%PORT%
echo Press Ctrl+C to stop this window.
echo.

call npm run dev -- -p %PORT%

endlocal
