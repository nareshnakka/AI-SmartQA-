@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo.
echo Stopping QEOS servers on ports 8000 and 3000...

for %%P in (8000 3000) do call "%~dp0lib\kill-port.bat" %%P

powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |" ^
  "Where-Object { $_.Name -match 'python|uvicorn' -and $_.CommandLine -match 'app\.main:app|uvicorn' } |" ^
  "ForEach-Object { Write-Host ('Stopping ' + $_.ProcessId + ' ' + $_.Name); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

for /L %%N in (1,1,3) do (
  set "BUSY=0"
  for %%P in (8000 3000) do (
    call "%~dp0lib\port-in-use.bat" %%P
    if not errorlevel 1 set "BUSY=1"
  )
  if "!BUSY!"=="0" goto :done
  for %%P in (8000 3000) do call "%~dp0lib\kill-port.bat" %%P
  ping 127.0.0.1 -n 2 >nul
)

:done
echo Done.
endlocal
exit /b 0
