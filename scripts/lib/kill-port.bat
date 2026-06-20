@echo off
REM Kill processes listening on a port (uses Get-NetTCPConnection).
setlocal
set "PORT=%~1"
powershell -NoProfile -Command ^
  "Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue |" ^
  "ForEach-Object { $procId = $_.OwningProcess; if ($procId) { Write-Host ('Killing PID ' + $procId + ' on port %PORT%'); Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue } }"
exit /b 0
