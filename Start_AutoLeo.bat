@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [AutoLeo] Creating local Python environment...
    py -3 -m venv .venv 2>nul
    if errorlevel 1 (
        python -m venv .venv
    )
    if errorlevel 1 (
        echo.
        echo [AutoLeo] Python was not found.
        echo Install Python 3.10 or newer, then run this file again.
        pause
        exit /b 1
    )
)

echo [AutoLeo] Installing/updating local dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [AutoLeo] Could not install dependencies.
    echo Check your internet connection and try again.
    pause
    exit /b 1
)

echo [AutoLeo] Starting interface...
start "" ".venv\Scripts\pythonw.exe" AutoLeo_GUI.py
exit /b 0
