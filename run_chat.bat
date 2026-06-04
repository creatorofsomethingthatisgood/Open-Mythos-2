@echo off
REM Mythos Local - Quick Start Chat (Windows)
REM Just run: run_chat.bat

echo ===============================================================
echo   MYTHOS LOCAL - QUICK START
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

REM Check for mythos.bat or mythos CLI
if not exist "mythos.bat" (
    echo ERROR: mythos.bat not found.
    echo Please run .\setup-windows.ps1 first.
    exit /b 1
)

echo.
echo Starting chat...
echo   Model path: %%USERPROFILE%%\.config\mythos\models\
echo   Download once with: mythos.bat model download
echo.

REM Set project root and run
set MYTHOS_PROJECT_ROOT=%~dp0
"%~dp0venv\Scripts\python.exe" -m mythos_cli.main chat
