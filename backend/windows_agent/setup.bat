@echo off
REM GHOST · one-click setup for Windows
REM Run: right-click → "Run with PowerShell" OR just double-click this .bat

setlocal
cd /d "%~dp0"

echo === GHOST setup ===
where python >nul 2>&1
if errorlevel 1 (
  echo Python is not installed or not in PATH. Install Python 3.11+ from https://python.org
  pause
  exit /b 1
)

if not exist ".venv" (
  echo Creating virtualenv .venv ...
  python -m venv .venv
)

call ".venv\Scripts\activate.bat"
echo Installing dependencies (this takes ~2 min) ...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt

if not exist ".env" (
  echo.
  echo Copying .env.example -> .env ...
  copy /Y ".env.example" ".env" >nul
  echo IMPORTANT: open .env and replace placeholder keys, then re-run this script.
  notepad .env
  pause
  exit /b 0
)

echo.
echo === Starting GHOST (voice) ===
python voice_ghost.py
pause
