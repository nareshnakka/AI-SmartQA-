@echo off
setlocal EnableExtensions EnableDelayedExpansion
title QEOS — Setup, Install, and Run

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "SCRIPTS=%ROOT%\scripts"
set "BACKEND=%ROOT%\backend"
set "FRONTEND=%ROOT%\frontend"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=3000"
set "APP_URL=http://localhost:%FRONTEND_PORT%"
set "PYTHON_CMD="
set "NPM_CMD=npm"

echo.
echo ============================================================
echo   QEOS - Quality Engineering Operating System
echo   One-click setup: install dependencies, start, open app
echo ============================================================
echo.

call :banner "Step 1/7 - Checking Python"
call :ensure_python
if errorlevel 1 goto :fail

call :banner "Step 2/7 - Checking Node.js and npm"
call :ensure_node
if errorlevel 1 goto :fail

call :banner "Step 3/7 - Environment file"
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

call :banner "Step 4/7 - Backend (Python venv + core packages)"
call :setup_backend
if errorlevel 1 goto :fail

call :banner "Step 5/7 - Automation and performance runners"
call :setup_runners
if errorlevel 1 goto :fail

call :banner "Step 6/7 - Frontend (npm packages)"
call :setup_frontend
if errorlevel 1 goto :fail

call :banner "Step 7/7 - Starting servers"
echo.
echo ============================================================
echo   Setup complete. Starting servers...
echo ============================================================
echo.

if exist "%SCRIPTS%\stop-servers.bat" (
  call "%SCRIPTS%\stop-servers.bat"
) else (
  call :kill_port %BACKEND_PORT%
  call :kill_port %FRONTEND_PORT%
)

echo Opening backend and frontend in separate terminal windows...
start "QEOS Backend" cmd /k ""%SCRIPTS%\restart-backend.bat""
timeout /t 4 /nobreak >nul
start "QEOS Frontend" cmd /k ""%SCRIPTS%\restart-frontend.bat""

call "%SCRIPTS%\lib\wait-for-servers.bat" %BACKEND_PORT% %FRONTEND_PORT%
echo Opening app in your default browser...
call "%SCRIPTS%\lib\open-app.bat" %FRONTEND_PORT%

echo.
echo ============================================================
echo   QEOS is starting
echo   App:     %APP_URL%
echo   API:     http://127.0.0.1:%BACKEND_PORT%
echo   API docs: http://127.0.0.1:%BACKEND_PORT%/docs
echo.
echo   Two terminal windows were opened (backend + frontend).
echo   IMPORTANT: Keep the BACKEND window open — closing it causes "Failed to fetch".
echo   Verify API: http://127.0.0.1:%BACKEND_PORT%/health
echo   Close those windows to stop the servers, or run:
echo     scripts\stop-servers.bat
echo ============================================================
echo.
pause
endlocal
exit /b 0

:fail
echo.
echo [ERROR] Setup did not complete. Fix the issue above and run this file again.
echo.
pause
endlocal
exit /b 1

:banner
echo.
echo --- %~1 ---
exit /b 0

:refresh_path
set "PATH=%PATH%;%LocalAppData%\Programs\Python\Python313;%LocalAppData%\Programs\Python\Python313\Scripts"
set "PATH=%PATH%;%LocalAppData%\Programs\Python\Python312;%LocalAppData%\Programs\Python\Python312\Scripts"
set "PATH=%PATH%;%LocalAppData%\Programs\Python\Python311;%LocalAppData%\Programs\Python\Python311\Scripts"
set "PATH=%PATH%;%ProgramFiles%\Python313;%ProgramFiles%\Python313\Scripts"
set "PATH=%PATH%;%ProgramFiles%\Python312;%ProgramFiles%\Python312\Scripts"
set "PATH=%PATH%;%ProgramFiles%\Python311;%ProgramFiles%\Python311\Scripts"
set "PATH=%PATH%;%ProgramFiles%\nodejs"
set "PATH=%PATH%;%ProgramFiles%\k6"
set "PATH=%PATH%;%ProgramFiles%\Apache\maven\bin"
set "PATH=%PATH%;%ProgramFiles%\Microsoft\jdk-17\bin"
set "PATH=%PATH%;%ProgramFiles%\Eclipse Adoptium\jdk-17\bin"
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
  echo Install Python manually from https://www.python.org/downloads/
  echo Enable "Add Python to PATH" during installation.
  exit /b 1
)

echo Installing Python 3.12 via winget (may take a few minutes)...
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
call :refresh_path
call :find_python
if not defined PYTHON_CMD (
  echo Python was installed but is not on PATH in this window.
  echo Close this window, open a new Command Prompt, and run setup-and-run.bat again.
  exit /b 1
)
echo Found after install: %PYTHON_CMD%
%PYTHON_CMD% --version
exit /b 0

:ensure_node
call :refresh_path
call :find_node
where node >nul 2>&1 && (
  echo Found: node
  node --version
  echo Found: %NPM_CMD%
  call %NPM_CMD% --version
  exit /b 0
)

echo Node.js 20+ not found.
where winget >nul 2>&1
if errorlevel 1 (
  echo Install Node.js LTS manually from https://nodejs.org/
  exit /b 1
)

echo Installing Node.js LTS via winget (may take a few minutes)...
winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
call :refresh_path
call :find_node
where node >nul 2>&1 || (
  echo Node.js was installed but is not on PATH in this window.
  echo Close this window, open a new Command Prompt, and run setup-and-run.bat again.
  exit /b 1
)
node --version
call %NPM_CMD% --version
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
  if errorlevel 1 (
    echo Failed to create venv.
    exit /b 1
  )
)

echo Upgrading pip and installing Python packages (this may take several minutes)...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo pip install failed.
  exit /b 1
)
echo Backend core packages installed.

echo.
echo Installing Playwright Chromium browsers ^(required for Discovery and Studio debug^)...
echo This downloads ~300MB on first run — do not skip this step.
call ".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 (
  echo.
  echo ERROR: Playwright browser download failed.
  echo Retry: scripts\install-playwright.bat
  echo Or manually: cd backend ^&^& .venv\Scripts\python.exe -m playwright install chromium
  exit /b 1
)
call ".venv\Scripts\python.exe" scripts\verify_playwright.py
if errorlevel 1 (
  echo Playwright verification failed after browser install.
  exit /b 1
)
echo Playwright Chromium ready.
exit /b 0

:setup_runners
cd /d "%BACKEND%"
echo Installing Playwright, Cypress, WDIO, Robot, k6, Locust, JMeter helpers...
echo This may take 15-30 minutes on first run.
call ".venv\Scripts\python.exe" scripts\install_all_runners.py
if errorlevel 1 (
  echo.
  echo ERROR: Runner setup failed.
  echo Retry: scripts\install-all-runners.bat
  exit /b 1
)
exit /b 0

:setup_frontend
cd /d "%FRONTEND%"
if not exist "package.json" (
  echo ERROR: frontend\package.json not found.
  exit /b 1
)

echo Installing npm packages (this may take several minutes)...
if exist "package-lock.json" (
  call %NPM_CMD% ci
) else (
  call %NPM_CMD% install
)
if errorlevel 1 (
  echo npm install failed.
  exit /b 1
)
echo Frontend packages installed.
exit /b 0

:kill_port
for /L %%R in (1,1,2) do (
  for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr ":%~1" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%P >nul 2>&1
  )
  timeout /t 1 /nobreak >nul
)
exit /b 0
