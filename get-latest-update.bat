@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Run from TEMP so "git stash" cannot replace this file while it is executing.
set "RUNNER=%TEMP%\qeos-get-latest-update.bat"
if /i not "%~f0"=="%RUNNER%" (
  set "REPO_ROOT=%~dp0"
  if "!REPO_ROOT:~-1!"=="\" set "REPO_ROOT=!REPO_ROOT:~0,-1!"
  copy /y "%~f0" "%RUNNER%" >nul
  call "%RUNNER%" "!REPO_ROOT!"
  exit /b !ERRORLEVEL!
)

title QEOS - Get Latest Update

set "ROOT=%~1"
if not defined ROOT (
  set "ROOT=%~dp0"
  if "!ROOT:~-1!"=="\" set "ROOT=!ROOT:~0,-1!"
)

set "SCRIPTS=%ROOT%\scripts"
set "DID_STASH=0"

echo.
echo ============================================================
echo   QEOS - Get Latest Update from GitHub
echo ============================================================
echo.
echo   Downloads the newest app files for testing.
echo   Your settings file (.env) is NOT removed.
echo.

cd /d "%ROOT%"

where git >nul 2>&1
if errorlevel 1 goto :no_git

if not exist "%ROOT%\.git" goto :not_repo

for /f "delims=" %%B in ('git branch --show-current 2^>nul') do set "BRANCH=%%B"
if not defined BRANCH set "BRANCH=main"

echo Branch: !BRANCH!
echo Folder: !ROOT!
echo.

git diff --quiet 2>nul
if errorlevel 1 goto :stash_changes
git diff --cached --quiet 2>nul
if errorlevel 1 goto :stash_changes
goto :after_stash

:stash_changes
echo [NOTE] Local file changes found - saving them temporarily...
git stash push -u -m "QEOS auto-stash before update" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Could not save local changes. Close the app and try again.
  goto :fail
)
set "DID_STASH=1"
echo        Saved. They will be restored after the update.
echo.

:after_stash
if exist "%SCRIPTS%\stop-servers.bat" (
  echo Stopping QEOS backend and frontend...
  call "%SCRIPTS%\stop-servers.bat" >nul 2>&1
  echo.
)

echo Downloading latest update from GitHub...
echo Please wait...
echo.

git fetch origin !BRANCH!
if errorlevel 1 goto :fetch_failed

git pull origin !BRANCH!
if errorlevel 1 goto :pull_failed

if "!DID_STASH!"=="1" goto :restore_stash_ok
goto :success

:restore_stash_ok
echo.
echo Restoring your saved local changes...
git stash pop >nul 2>&1
if errorlevel 1 (
  echo [WARNING] Some local changes could not be restored automatically.
  echo           Ask your team for help with: git stash list
)

:success
echo.
echo ============================================================
echo   SUCCESS - You have the latest update!
echo ============================================================
echo.

set "RESTART=Y"
set /p "RESTART=Restart the app now so you can test? [Y/n]: "
if /i "!RESTART!"=="n" goto :done

if exist "%SCRIPTS%\restart-all-auto.bat" (
  echo.
  echo Restarting QEOS...
  call "%SCRIPTS%\restart-all-auto.bat"
  if errorlevel 1 (
    echo [WARNING] Restart had a problem. Try running setup-and-run.bat
  ) else (
    echo.
    echo App is ready: http://localhost:3000
  )
) else (
  echo Run setup-and-run.bat to start the app.
)
goto :done

:fetch_failed
echo [ERROR] Could not connect to GitHub.
echo       Check your internet connection and try again.
goto :restore_on_fail

:pull_failed
echo.
echo [ERROR] Update failed.
echo.
echo Common fixes:
echo   1. Check internet connection
echo   2. Run this file again
echo   3. Ask your team if GitHub login is required
echo.
goto :restore_on_fail

:restore_on_fail
if not "!DID_STASH!"=="1" goto :fail
echo Restoring your saved local changes...
git stash pop >nul 2>&1
goto :fail

:no_git
echo [ERROR] Git is not installed on this PC.
echo.
echo Install Git, then run this file again:
echo   https://git-scm.com/download/win
echo.
goto :fail

:not_repo
echo [ERROR] This folder is not a Git copy of the project.
echo.
echo Ask your team for the full project folder cloned from:
echo   https://github.com/nareshnakka/AI-SmartQA-
echo.
goto :fail

:done
echo.
echo Finished. You can close this window.
echo.
pause
exit /b 0

:fail
echo.
pause
exit /b 1
