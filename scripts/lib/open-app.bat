@echo off
REM Open the QEOS web app in the default browser.
setlocal
set "PORT=%~1"
if "%PORT%"=="" set "PORT=3000"
start "" "http://localhost:%PORT%"
endlocal
exit /b 0
