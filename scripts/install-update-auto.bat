@echo off
REM Non-interactive app update: stash, pull, restart, open browser. No prompts.
setlocal EnableExtensions EnableDelayedExpansion

set "RUNNER=%TEMP%\qeos-install-update-auto.bat"
if /i not "%~f0"=="%RUNNER%" (
  set "REPO_ROOT=%~1"
  if not defined REPO_ROOT (
    set "REPO_ROOT=%~dp0.."
    if "!REPO_ROOT:~-1!"=="\" set "REPO_ROOT=!REPO_ROOT:~0,-1!"
  )
  copy /y "%~f0" "%RUNNER%" >nul
  call "%RUNNER%" "!REPO_ROOT!"
  exit /b !ERRORLEVEL!
)

set "ROOT=%~1"
if not defined ROOT (
  set "ROOT=%~dp0.."
  if "!ROOT:~-1!"=="\" set "ROOT=!ROOT:~0,-1!"
)

set "SCRIPTS=%ROOT%\scripts"
set "DID_STASH=0"

cd /d "%ROOT%"

where git >nul 2>&1
if errorlevel 1 exit /b 1

if not exist "%ROOT%\.git" exit /b 1

for /f "delims=" %%B in ('git branch --show-current 2^>nul') do set "BRANCH=%%B"
if not defined BRANCH set "BRANCH=main"

git diff --quiet 2>nul
if errorlevel 1 goto :stash_changes
git diff --cached --quiet 2>nul
if errorlevel 1 goto :stash_changes
goto :after_stash

:stash_changes
git stash push -u -m "QEOS auto-stash before update" >nul 2>&1
if errorlevel 1 exit /b 1
set "DID_STASH=1"

:after_stash
if exist "%SCRIPTS%\stop-servers.bat" (
  call "%SCRIPTS%\stop-servers.bat" >nul 2>&1
)

git fetch origin !BRANCH!
if errorlevel 1 goto :restore_on_fail

git pull origin !BRANCH!
if errorlevel 1 goto :restore_on_fail

if "!DID_STASH!"=="1" (
  git stash pop >nul 2>&1
)

if exist "%SCRIPTS%\restart-all-auto.bat" (
  call "%SCRIPTS%\restart-all-auto.bat"
)

exit /b 0

:restore_on_fail
if not "!DID_STASH!"=="1" exit /b 1
git stash pop >nul 2>&1
exit /b 1
