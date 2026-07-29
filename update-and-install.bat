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
  echo   Pulls latest code, then installs Python, Node, DB, runners,
  echo   and the Discovery agent ^(Ollama LLM + Playwright e2e^).
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

call :banner "Step 1/9 - Python"
call :ensure_python
if errorlevel 1 exit /b 1

call :banner "Step 2/9 - Node.js and npm"
call :ensure_node
if errorlevel 1 exit /b 1

call :banner "Step 3/9 - Environment file"
if not exist "%ROOT%\.env" (
  if exist "%ROOT%\.env.example" (
    copy /Y "%ROOT%\.env.example" "%ROOT%\.env" >nul
    echo Created .env from .env.example
  ) else (
    echo No .env.example found - using built-in defaults.
  )
) else (
  echo .env already exists.
  call :merge_env_defaults
)
if not exist "%BACKEND%\.env" if exist "%ROOT%\.env" (
  copy /Y "%ROOT%\.env" "%BACKEND%\.env" >nul
  echo Synced .env to backend folder.
)

call :banner "Step 4/9 - Backend Python packages"
call :setup_backend
if errorlevel 1 exit /b 1

call :banner "Step 5/9 - Playwright and automation runners"
call :setup_runners
if errorlevel 1 exit /b 1

call :banner "Step 6/9 - Frontend npm packages"
call :setup_frontend
if errorlevel 1 exit /b 1

call :banner "Step 7/9 - Database (SQLite)"
call :setup_database
if errorlevel 1 exit /b 1

call :banner "Step 8/9 - Discovery agent (Ollama + e2e)"
call :setup_discovery_agent
REM Non-fatal if Ollama needs a reboot / PATH refresh
if errorlevel 1 (
  echo [WARNING] Discovery agent setup had issues — see messages above.
)

call :banner "Step 9/9 - Done"
echo.
echo All dependencies are installed and the database is ready.
echo Discovery agent: Ollama LLM advisor + Playwright e2e GenericSteps.
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
set "PATH=%PATH%;%LocalAppData%\Programs\Ollama;%ProgramFiles%\Ollama"
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

:merge_env_defaults
REM Append new Discovery / Ollama keys from .env.example when missing in .env
if not exist "%ROOT%\.env.example" exit /b 0
findstr /B /C:"DISCOVERY_LLM_ADVISOR_ENABLED=" "%ROOT%\.env" >nul 2>&1
if errorlevel 1 (
  echo.>>"%ROOT%\.env"
  echo # Discovery LLM advisor ^(added by update-and-install^)>>"%ROOT%\.env"
  echo DISCOVERY_LLM_ADVISOR_ENABLED=true>>"%ROOT%\.env"
  echo DISCOVERY_VALIDATE_BEFORE_SCRIPTS=true>>"%ROOT%\.env"
  echo DISCOVERY_STEP_MAX_RETRIES=2>>"%ROOT%\.env"
  echo Merged Discovery advisor settings into .env
)
findstr /B /C:"OLLAMA_MODEL=" "%ROOT%\.env" >nul 2>&1
if errorlevel 1 (
  echo OLLAMA_MODEL=llama3.2>>"%ROOT%\.env"
  echo OLLAMA_BASE_URL=http://localhost:11434>>"%ROOT%\.env"
  echo Merged Ollama settings into .env
)
exit /b 0

:setup_discovery_agent
REM Install / upgrade Ollama (Discovery LLM advisor) and e2e Playwright agent package
set "OLLAMA_MODEL=llama3.2"
if exist "%ROOT%\.env" (
  for /f "usebackq tokens=1,* delims==" %%A in (`findstr /B /I /C:"OLLAMA_MODEL=" "%ROOT%\.env"`) do (
    if /i "%%A"=="OLLAMA_MODEL" set "OLLAMA_MODEL=%%B"
  )
)
REM Trim spaces
for /f "tokens=* delims= " %%M in ("!OLLAMA_MODEL!") do set "OLLAMA_MODEL=%%M"

echo Installing / updating Discovery agent dependencies...
call :ensure_ollama
set "OLLAMA_RC=!ERRORLEVEL!"

call :setup_e2e_agent
set "E2E_RC=!ERRORLEVEL!"

if not "!OLLAMA_RC!"=="0" exit /b 1
if not "!E2E_RC!"=="0" exit /b 1
exit /b 0

:ensure_ollama
call :refresh_path
set "PATH=%PATH%;%LocalAppData%\Programs\Ollama;%ProgramFiles%\Ollama"

where ollama >nul 2>&1
if errorlevel 1 goto :install_ollama

echo Found Ollama — upgrading to latest...
where winget >nul 2>&1
if not errorlevel 1 (
  "%LocalAppData%\Microsoft\WindowsApps\winget.exe" upgrade -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements >nul 2>&1
  if errorlevel 1 (
    echo Ollama already up to date ^(or upgrade skipped^).
  ) else (
    echo Ollama upgraded to latest.
  )
)
goto :ollama_pull

:install_ollama
echo Ollama not found — installing latest...
call :install_ollama_winget
if errorlevel 1 call :install_ollama_setup_exe
call :refresh_path
set "PATH=%PATH%;%LocalAppData%\Programs\Ollama;%ProgramFiles%\Ollama"
where ollama >nul 2>&1
if errorlevel 1 (
  echo [WARNING] Ollama install finished but ollama.exe is not on PATH yet.
  echo Start the Ollama app from the Start menu, open a new terminal, then run:
  echo   ollama pull !OLLAMA_MODEL!
  exit /b 1
)
goto :ollama_pull

:install_ollama_winget
set "WINGET_EXE="
where winget >nul 2>&1 && set "WINGET_EXE=winget"
if not defined WINGET_EXE if exist "%LocalAppData%\Microsoft\WindowsApps\winget.exe" (
  set "WINGET_EXE=%LocalAppData%\Microsoft\WindowsApps\winget.exe"
)
if not defined WINGET_EXE (
  echo winget not available — will download OllamaSetup.exe instead.
  exit /b 1
)
echo Installing Ollama via winget...
"!WINGET_EXE!" install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements --disable-interactivity
exit /b !ERRORLEVEL!

:install_ollama_setup_exe
set "OLLAMA_SETUP=%TEMP%\OllamaSetup-qeos.exe"
echo Downloading OllamaSetup.exe from ollama.com...
curl.exe -L --retry 3 --retry-delay 2 -o "!OLLAMA_SETUP!" "https://ollama.com/download/OllamaSetup.exe"
if errorlevel 1 (
  echo [ERROR] Failed to download OllamaSetup.exe
  echo Install manually from https://ollama.com/download/windows
  exit /b 1
)
for %%S in ("!OLLAMA_SETUP!") do set "OLLAMA_SIZE=%%~zS"
if not defined OLLAMA_SIZE set "OLLAMA_SIZE=0"
if !OLLAMA_SIZE! LSS 10000000 (
  echo [ERROR] OllamaSetup.exe download looks incomplete ^(!OLLAMA_SIZE! bytes^).
  exit /b 1
)
echo Running silent Ollama install ^(!OLLAMA_SIZE! bytes^)...
"!OLLAMA_SETUP!" /VERYSILENT /NORESTART /SUPPRESSMSGBOXES /SP-
set "RC=!ERRORLEVEL!"
if not "!RC!"=="0" (
  echo [WARNING] Silent install exit code !RC! — trying interactive Start if needed.
)
timeout /t 5 /nobreak >nul
exit /b 0

:ollama_pull
echo Ensuring Ollama service is reachable...
REM Start Ollama app if serve is not up (best-effort)
where ollama >nul 2>&1 || exit /b 1
start "" /B ollama serve >nul 2>&1
timeout /t 3 /nobreak >nul

echo Pulling Discovery model: !OLLAMA_MODEL!
ollama pull !OLLAMA_MODEL!
if errorlevel 1 (
  echo [WARNING] ollama pull failed — start the Ollama app and run: ollama pull !OLLAMA_MODEL!
  exit /b 1
)
ollama list 2>nul
echo Discovery LLM agent ready ^(Ollama / !OLLAMA_MODEL!^).
exit /b 0

:setup_e2e_agent
REM Playwright GenericSteps package used by Discovery / Automation IDE agent
if not exist "%ROOT%\e2e\orangehrm\package.json" (
  echo No e2e\orangehrm package — skipping agent script deps.
  exit /b 0
)
cd /d "%ROOT%\e2e\orangehrm"
echo Installing Discovery e2e agent ^(Playwright GenericSteps^)...
if exist "package-lock.json" (
  call %NPM_CMD% ci
) else (
  call %NPM_CMD% install
)
if errorlevel 1 (
  echo [WARNING] e2e agent npm install failed.
  exit /b 1
)
call %NPM_CMD% exec -- playwright install chromium
if errorlevel 1 (
  echo [WARNING] Playwright Chromium for e2e agent failed — Discovery scripts may still use backend Playwright.
)
echo Discovery e2e agent package ready.
exit /b 0
