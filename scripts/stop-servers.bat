@echo off
setlocal EnableExtensions

echo.
echo Stopping QEOS servers on ports 8000 and 3000...

call :killport 8000
call :killport 3000

echo Done.
timeout /t 2 /nobreak >nul
endlocal
exit /b 0

:killport
for /L %%R in (1,1,3) do (
  for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%~1" ^| findstr "LISTENING"') do (
    echo Killing PID %%P on port %~1
    taskkill /F /PID %%P >nul 2>&1
  )
  timeout /t 1 /nobreak >nul
)
exit /b 0
