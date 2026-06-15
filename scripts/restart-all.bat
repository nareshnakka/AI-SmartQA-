@echo off
setlocal EnableExtensions

set "SCRIPTS=%~dp0"

echo.
echo QEOS — restarting backend and frontend in separate windows...
echo.

start "QEOS Backend" cmd /k ""%SCRIPTS%restart-backend.bat""
timeout /t 2 /nobreak >nul
start "QEOS Frontend" cmd /k ""%SCRIPTS%restart-frontend.bat""

echo Backend:  http://127.0.0.1:8000
echo Frontend: http://localhost:3000
echo.
echo Two terminal windows were opened. Close them to stop the servers.
echo.

endlocal
