@echo off
setlocal EnableExtensions EnableDelayedExpansion
title QEOS — Get Latest Update

REM Double-click this file to download the newest version from GitHub.
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "SCRIPTS=%ROOT%\scripts"

echo.
echo ============================================================
echo   QEOS — Get Latest Update from GitHub
echo ============================================================
echo.
echo   This downloads the newest app files for testing.
echo   Your settings file (.env) is NOT removed.
echo.

cd /d "%ROOT%"

where git >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Git is not installed on this PC.
  echo.
  echo Install Git, then run this file again:
  echo   https://git-scm.com/download/win
  echo.
  goto :fail
)

if not exist "%ROOT%\.git" (
  echo [ERROR] This folder is not a Git copy of the project.
  echo.
  echo Ask your team for the full project folder cloned from:
  echo   https://github.com/nareshnakka/AI-SmartQA-
  echo.
  goto :fail
)

for /f "delims=" %%B in ('git branch --show-current 2^>nul') do set "BRANCH=%%B"
if not defined BRANCH set "BRANCH=main"

echo Branch: %BRANCH%
echo Folder: %ROOT%
echo.

set "DID_STASH="
git status --porcelain 2>nul | findstr /R "." >nul 2>&1
if not errorlevel 1 (
  echo [NOTE] Local file changes found — saving them temporarily...
  git stash push -u -m "QEOS auto-stash before update" >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Could not save local changes. Close the app and try again.
    goto :fail
  )
  set "DID_STASH=1"
  echo        Saved. They will be restored after the update.
  echo.
)

if exist "%SCRIPTS%\stop-servers.bat" (
  echo Stopping QEOS (backend + frontend)...
  call "%SCRIPTS%\stop-servers.bat" >nul 2>&1
  echo.
)

echo Downloading latest update from GitHub...
echo Please wait...
echo.

git fetch origin %BRANCH%
if errorlevel 1 (
  echo [ERROR] Could not connect to GitHub.
  echo       Check your internet connection and try again.
  goto :restore_and_fail
)

git pull origin %BRANCH%
if errorlevel 1 (
  echo.
  echo [ERROR] Update failed.
  echo.
  echo Common fixes:
  echo   1. Check internet connection
  echo   2. Run this file again
  echo   3. Ask your team if GitHub login is required
  echo.
  goto :restore_and_fail
)

if defined DID_STASH (
  echo.
  echo Restoring your saved local changes...
  git stash pop >nul 2>&1
  if errorlevel 1 (
    echo [WARNING] Some local changes could not be restored automatically.
    echo           Ask your team for help with: git stash list
  )
)

echo.
echo ============================================================
echo   SUCCESS — You have the latest update!
echo ============================================================
echo.

set "RESTART=Y"
set /p RESTART="Restart the app now so you can test? (Y/n): "
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

:done
echo.
echo Finished. You can close this window.
echo.
pause
exit /b 0

:restore_and_fail
if defined DID_STASH (
  git stash pop >nul 2>&1
)
:fail
echo.
pause
exit /b 1
