@echo off
title Jericho AI Council
echo.
echo  ================================================
echo   Jericho AI Council — Startup
echo  ================================================
echo.

:: ─── Check Python ────────────────────────────────────────────
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo  [ERROR] Python is not installed or not on PATH.
    echo          Please install Python 3.11+ from https://python.org
    pause
    exit /b 1
)

:: ─── Ensure virtual environment exists ───────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo  [SETUP] Creating virtual environment...
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo  [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  [OK]    Virtual environment created.
)

:: ─── Activate venv ───────────────────────────────────────────
echo  [INFO]  Activating virtual environment...
call venv\Scripts\activate.bat

:: ─── Install / update dependencies ───────────────────────────
echo  [INFO]  Checking dependencies...
pip install -e ".[dev]" --quiet
if %ERRORLEVEL% neq 0 (
    echo  [ERROR] Failed to install dependencies. Check requirements.
    pause
    exit /b 1
)
echo  [OK]    Dependencies up to date.

:: ─── Check for API keys ─────────────────────────────────────
if not exist "config\.env" (
    echo.
    echo  [WARN]  No config\.env found!
    echo          Copying config\.env.example to config\.env
    echo          Please edit config\.env with your API keys before
    echo          running any council sessions.
    copy "config\.env.example" "config\.env" >nul
    echo.
)

:: ─── Show project status ────────────────────────────────────
echo.
echo  ------------------------------------------------
echo   Project Status
echo  ------------------------------------------------
python -m core.cli status
echo.

:: ─── Launch web dashboard ───────────────────────────────────
echo  ------------------------------------------------
echo   Starting Web Dashboard
echo  ------------------------------------------------
echo.
echo  Dashboard:  http://127.0.0.1:8080
echo  API docs:   http://127.0.0.1:8080/docs
echo.
echo  Press Ctrl+C to stop the server.
echo.
python -m uvicorn core.web_api:app --host 127.0.0.1 --port 8080
