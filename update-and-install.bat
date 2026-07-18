@echo off
setlocal EnableExtensions EnableDelayedExpansion
title QEOS - Update and Install

REM Run from TEMP so git stash cannot replace this file mid-run.
set "RUNNER=%TEMP%\qeos-update-and-install.bat"
if /i not "%~f0"=="%RUNNER%" (
  set "REPO_ROOT=%~dp0"
  if "!REPO_ROOT:~-1!"=="\" set "REPO_ROOT=!REPO_ROOT:~0,-1!"
  copy /y "%~f0" "%RUNNER%" >nul
  if "%~1"=="" (
    call "%RUNNER%" "!REPO_ROOT!"
  ) else (
    call "%RUNNER%" %*
  )
  exit /b !ERRORLEVEL!
)

set "AUTO=0"
if /i "%~1"=="/auto" (
  set "AUTO=1"
  shift
)

set "ROOT=%~1"
if not defined ROOT (
  set "ROOT=%~dp0"
  if "!ROOT:~-1!"=="\" set "ROOT=!ROOT:~0,-1!"
)
set "BACKEND=%ROOT%\backend"
set "FRONTEND=%ROOT%\frontend"
set "PYTHON_CMD="
set "NPM_CMD=npm"
set "DID_STASH=0"

if "%AUTO%"=="0" (
  echo.
  echo ============================================================
  echo   QEOS - Update from GitHub and Install Dependencies
  echo ============================================================
  echo.
  echo   Pulls latest code, then installs Python, Node, DB, and runners.
  echo   Your data is preserved:
  echo     - .env and settings
  echo     - SQLite database (projects, test cases, discovery)
  echo     - data\ folder (Cursor credentials, backups)
  echo     - execution_artifacts
  echo.
) else (
  echo QEOS auto-update: preserving .env, database, and data folder...
)

REM Snapshot critical user data before pull (never overwrite on restore failure)
if not exist "%ROOT%\data\update_backups" mkdir "%ROOT%\data\update_backups" >nul 2>&1
for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "BK=%%T"
set "BKDIR=%ROOT%\data\update_backups\!BK!"
mkdir "!BKDIR!" >nul 2>&1
if exist "%ROOT%\.env" copy /Y "%ROOT%\.env" "!BKDIR!\root.env" >nul 2>&1
if exist "%BACKEND%\.env" copy /Y "%BACKEND%\.env" "!BKDIR!\backend.env" >nul 2>&1
if exist "%BACKEND%\qeos.db" copy /Y "%BACKEND%\qeos.db" "!BKDIR!\backend.qeos.db" >nul 2>&1
if exist "%ROOT%\qeos.db" copy /Y "%ROOT%\qeos.db" "!BKDIR!\qeos.db" >nul 2>&1
if exist "%ROOT%\data\cursor_credentials.json" copy /Y "%ROOT%\data\cursor_credentials.json" "!BKDIR!\cursor_credentials.json" >nul 2>&1


cd /d "%ROOT%"

where git >nul 2>&1
if errorlevel 1 goto :no_git

if exist "%ROOT%\.git" (
  for /f "delims=" %%B in ('git branch --show-current 2^>nul') do set "BRANCH=%%B"
  if not defined BRANCH set "BRANCH=main"
  if "%AUTO%"=="0" (
    echo Git branch: !BRANCH!
    echo Folder: !ROOT!
    echo.
  )

  call "%ROOT%\stop.bat" /quiet >nul 2>&1

  git diff --quiet 2>nul
  if errorlevel 1 goto :stash_changes
  git diff --cached --quiet 2>nul
  if errorlevel 1 goto :stash_changes
  goto :pull

  :stash_changes
  if "%AUTO%"=="0" echo [NOTE] Saving local changes before update...
  git stash push -u -m "QEOS auto-stash before update" >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Could not stash local changes. Close the app and try again.
    goto :fail
  )
  set "DID_STASH=1"

  :pull
  if "%AUTO%"=="0" echo Downloading latest code from GitHub...
  git fetch origin !BRANCH!
  if errorlevel 1 goto :fetch_failed
  git pull origin !BRANCH!
  if errorlevel 1 goto :pull_failed
  if "!DID_STASH!"=="1" (
    if "%AUTO%"=="0" echo Restoring your saved local changes...
    git stash pop >nul 2>&1
  )
  if "%AUTO%"=="0" echo Code update complete.
  if "%AUTO%"=="0" echo.
) else (
  if "%AUTO%"=="0" (
    echo [NOTE] Not a git repo - skipping pull, installing dependencies only.
    echo.
  )
)

call :install_deps
if errorlevel 1 goto :fail

if "%AUTO%"=="1" (
  call "%ROOT%\restart.bat" /auto
  endlocal
  exit /b 0
)

echo.
echo ============================================================
echo   SUCCESS - Update and install complete!
echo ============================================================
echo.

set "RESTART=Y"
set /p "RESTART=Start QEOS now? [Y/n]: "
if /i "!RESTART!"=="n" goto :done

call "%ROOT%\restart.bat"
goto :done

:no_git
if "%AUTO%"=="0" (
  echo [WARNING] Git not installed - skipping code update.
  echo Install Git from https://git-scm.com/download/win
  echo.
)
call :install_deps
if errorlevel 1 goto :fail
if "%AUTO%"=="1" (
  call "%ROOT%\restart.bat" /auto
  endlocal
  exit /b 0
)
goto :done

:fetch_failed
echo [ERROR] Could not connect to GitHub.
goto :restore_on_fail

:pull_failed
echo [ERROR] Git pull failed. Check your connection and try again.
goto :restore_on_fail

:restore_on_fail
if "!DID_STASH!"=="1" git stash pop >nul 2>&1
goto :fail

:done
if "%AUTO%"=="0" (
  echo.
  pause
)
endlocal
exit /b 0

:fail
if "%AUTO%"=="0" (
  echo.
  pause
)
endlocal
exit /b 1

REM --- Dependency install (inline) ---

:install_deps
if "%AUTO%"=="0" (
  echo.
  echo ============================================================
  echo   QEOS - Install / update dependencies
  echo ============================================================
  echo.
)

call :banner "Step 1/8 - Python"
call :ensure_python
if errorlevel 1 exit /b 1

call :banner "Step 2/8 - Node.js and npm"
call :ensure_node
if errorlevel 1 exit /b 1

call :banner "Step 3/8 - Environment file"
if not exist "%ROOT%\.env" (
  if exist "%ROOT%\.env.example" (
    copy /Y "%ROOT%\.env.example" "%ROOT%\.env" >nul
    echo Created .env from .env.example
  ) else (
    echo No .env.example found - using built-in defaults.
  )
) else (
  echo .env already exists.
)
if not exist "%BACKEND%\.env" if exist "%ROOT%\.env" (
  copy /Y "%ROOT%\.env" "%BACKEND%\.env" >nul
  echo Synced .env to backend folder.
)

call :banner "Step 4/8 - Backend Python packages"
call :setup_backend
if errorlevel 1 exit /b 1

call :banner "Step 5/8 - Playwright and automation runners"
call :setup_runners
if errorlevel 1 exit /b 1

call :banner "Step 6/8 - Frontend npm packages"
call :setup_frontend
if errorlevel 1 exit /b 1

call :banner "Step 7/8 - Database (SQLite)"
call :setup_database
if errorlevel 1 exit /b 1

call :banner "Step 8/8 - Done"
echo.
echo All dependencies are installed and the database is ready.
exit /b 0

:banner
if "%AUTO%"=="0" (
  echo.
  echo --- %~1 ---
)
exit /b 0

:refresh_path
set "PATH=%PATH%;%LocalAppData%\Programs\Python\Python313;%LocalAppData%\Programs\Python\Python313\Scripts"
set "PATH=%PATH%;%LocalAppData%\Programs\Python\Python312;%LocalAppData%\Programs\Python\Python312\Scripts"
set "PATH=%PATH%;%LocalAppData%\Programs\Python\Python311;%LocalAppData%\Programs\Python\Python311\Scripts"
set "PATH=%PATH%;%ProgramFiles%\Python313;%ProgramFiles%\Python313\Scripts"
set "PATH=%PATH%;%ProgramFiles%\Python312;%ProgramFiles%\Python312\Scripts"
set "PATH=%PATH%;%ProgramFiles%\Python311;%ProgramFiles%\Python311\Scripts"
set "PATH=%PATH%;%ProgramFiles%\nodejs"
exit /b 0

:find_python
set "PYTHON_CMD="
where python >nul 2>&1 && (
  for /f "delims=" %%P in ('where python 2^>nul ^| findstr /i /v "\\Windows\\"') do (
    set "PYTHON_CMD=%%P"
    goto :find_python_done
  )
)
where py >nul 2>&1 && set "PYTHON_CMD=py -3" && goto :find_python_done
for %%V in (313 312 311) do (
  if exist "%LocalAppData%\Programs\Python\Python%%V\python.exe" (
    set "PYTHON_CMD=%LocalAppData%\Programs\Python\Python%%V\python.exe"
    goto :find_python_done
  )
)
:find_python_done
exit /b 0

:find_node
set "NPM_CMD=npm"
where npm >nul 2>&1 && exit /b 0
if exist "%ProgramFiles%\nodejs\npm.cmd" (
  set "NPM_CMD=%ProgramFiles%\nodejs\npm.cmd"
  set "PATH=%PATH%;%ProgramFiles%\nodejs"
)
exit /b 0

:ensure_python
call :refresh_path
call :find_python
if defined PYTHON_CMD (
  echo Found: %PYTHON_CMD%
  %PYTHON_CMD% --version
  exit /b 0
)
echo Python 3.11+ not found.
where winget >nul 2>&1
if errorlevel 1 (
  echo Install Python from https://www.python.org/downloads/
  exit /b 1
)
echo Installing Python 3.12 via winget...
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
call :refresh_path
call :find_python
if not defined PYTHON_CMD (
  echo Python installed but not on PATH. Open a new terminal and run update-and-install.bat again.
  exit /b 1
)
%PYTHON_CMD% --version
exit /b 0

:ensure_node
call :refresh_path
call :find_node
where node >nul 2>&1 && (
  node --version
  call %NPM_CMD% --version
  exit /b 0
)
echo Node.js not found.
where winget >nul 2>&1
if errorlevel 1 (
  echo Install Node.js LTS from https://nodejs.org/
  exit /b 1
)
echo Installing Node.js LTS via winget...
winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
call :refresh_path
call :find_node
where node >nul 2>&1 || (
  echo Node.js installed but not on PATH. Open a new terminal and run update-and-install.bat again.
  exit /b 1
)
node --version
exit /b 0

:setup_backend
cd /d "%BACKEND%"
if not exist "requirements.txt" (
  echo ERROR: backend\requirements.txt not found.
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating Python virtual environment...
  if /i "!PYTHON_CMD!"=="py -3" (
    py -3 -m venv .venv
  ) else (
    "!PYTHON_CMD!" -m venv .venv
  )
  if errorlevel 1 exit /b 1
)
echo Installing Python packages...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
echo Installing Playwright Chromium...
call ".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 exit /b 1
call ".venv\Scripts\python.exe" scripts\verify_playwright.py
if errorlevel 1 exit /b 1
exit /b 0

:setup_runners
cd /d "%BACKEND%"
echo Installing automation and performance runners...
call ".venv\Scripts\python.exe" scripts\install_all_runners.py
if errorlevel 1 exit /b 1
exit /b 0

:setup_frontend
cd /d "%FRONTEND%"
if not exist "package.json" (
  echo ERROR: frontend\package.json not found.
  exit /b 1
)
if exist "package-lock.json" (
  call %NPM_CMD% ci
) else (
  call %NPM_CMD% install
)
if errorlevel 1 exit /b 1
exit /b 0

:setup_database
cd /d "%BACKEND%"
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Backend venv missing.
  exit /b 1
)
REM init_db creates missing tables only — does not wipe existing project data.
if exist "qeos.db" (
  if "%AUTO%"=="0" echo Existing database found — keeping your projects and test cases.
) else (
  if "%AUTO%"=="0" echo Creating new SQLite database...
)
echo Initializing SQLite database (safe migrate)...
call ".venv\Scripts\python.exe" -c "import asyncio; from app.db.session import init_db; asyncio.run(init_db()); print('Database ready.')"
if errorlevel 1 exit /b 1
exit /b 0
