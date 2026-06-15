@echo off
setlocal EnableExtensions
title QEOS Frontend (port 3000)

set "ROOT=%~dp0.."
set "PORT=3000"

echo.
echo [%date% %time%] Stopping processes on port %PORT%...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
  taskkill /F /PID %%P >nul 2>&1
)
timeout /t 2 /nobreak >nul

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

echo Starting frontend at http://localhost:%PORT%
echo Press Ctrl+C to stop.
echo.

call npm run dev -- -p %PORT%

endlocal
