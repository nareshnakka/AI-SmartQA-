@echo off
REM Returns exit 0 if nothing is listening on the port (Get-NetTCPConnection).
setlocal
set "PORT=%~1"
powershell -NoProfile -Command ^
  "$c = @(Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue); exit [int]($c.Count -gt 0)"
exit /b %ERRORLEVEL%
