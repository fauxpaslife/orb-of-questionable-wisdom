@echo off
setlocal
cd /d "%~dp0"
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 (
    py -3 install.py %*
    if errorlevel 1 goto failed
    exit /b 0
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 (
    python install.py %*
    if errorlevel 1 goto failed
    exit /b 0
)
echo Python 3.11 or later is required.
echo Install Python from https://www.python.org/downloads/windows/ and enable Add Python to PATH.
:failed
echo Installation did not finish. Fix the message above and run install.bat again.
pause
exit /b 1
