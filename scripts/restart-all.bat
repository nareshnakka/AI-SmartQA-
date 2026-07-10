@echo off
setlocal EnableExtensions

set "SCRIPTS=%~dp0"
set "ROOT=%SCRIPTS%.."

echo.
echo QEOS — restarting backend and frontend...
echo.

call "%SCRIPTS%stop-servers.bat"
ping 127.0.0.1 -n 2 >nul

echo Opening backend window...
start "QEOS Backend" cmd /k call "%SCRIPTS%restart-backend.bat"

ping 127.0.0.1 -n 4 >nul

echo Opening frontend window...
start "QEOS Frontend" cmd /k call "%SCRIPTS%restart-frontend.bat"

call "%SCRIPTS%lib\wait-for-servers.bat"
echo Opening app in your default browser...
call "%SCRIPTS%lib\open-app.bat"

echo.
echo Backend:  http://127.0.0.1:8000/health
echo Frontend: http://localhost:3000
echo.
echo Two terminal windows should open. If not, run restart-backend.bat and restart-frontend.bat directly.
echo.

endlocal
exit /b 0
