@echo off
REM Mythos Local - Web Interface (Windows)
REM Just run: run_web.bat

echo ===============================================================
echo   MYTHOS LOCAL - WEB INTERFACE
echo ===============================================================
echo.

REM Check we're in the right directory
if not exist "config.yaml" (
    echo ERROR: Not in project directory!
    echo Please cd to the Mythos project folder.
    exit /b 1
)

REM Check for venv
if not exist "venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found!
    echo Please run .\setup-windows.ps1 first.
    exit /b 1
)

echo Found project files.
echo.
echo Starting web interface...
echo   URL: http://localhost:7860
echo   The model will auto-download on first run if needed.
echo.

REM Set project root and run
set MYTHOS_PROJECT_ROOT=%~dp0
"%~dp0venv\Scripts\python.exe" main.py --mode web
