@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run install.bat first to create the project environment.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" launch.py
if errorlevel 1 pause
