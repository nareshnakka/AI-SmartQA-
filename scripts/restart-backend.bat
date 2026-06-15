@echo off
setlocal EnableExtensions
title QEOS Backend (port 8000)

set "ROOT=%~dp0.."
set "PORT=8000"

echo.
echo [%date% %time%] Stopping processes on port %PORT%...
call "%~dp0stop-servers.bat" >nul 2>&1
for /L %%R in (1,1,2) do (
  for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%P >nul 2>&1
  )
  timeout /t 1 /nobreak >nul
)

cd /d "%ROOT%\backend"
if not exist ".venv\Scripts\uvicorn.exe" (
  echo ERROR: Backend venv not found. Run: cd backend ^& python -m venv .venv ^& .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)

echo Starting backend at http://127.0.0.1:%PORT%
echo Debug flow requires execution_executor=asset_live_v2 on /health
echo Press Ctrl+C to stop.
echo.

call ".venv\Scripts\activate.bat"
uvicorn app.main:app --reload --host 127.0.0.1 --port %PORT%

endlocal
