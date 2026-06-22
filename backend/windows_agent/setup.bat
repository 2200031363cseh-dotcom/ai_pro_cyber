@echo off
REM GHOST · one-click setup for Windows (no private deps)
setlocal
cd /d "%~dp0"

echo === GHOST setup ===
where python >nul 2>&1
if errorlevel 1 (
  echo Python is not installed or not in PATH. Install Python 3.11+ from https://python.org
  echo Make sure to TICK "Add python.exe to PATH" during install.
  pause
  exit /b 1
)

if not exist ".venv" (
  echo Creating virtualenv .venv ...
  python -m venv .venv
)

call ".venv\Scripts\activate.bat"

echo Upgrading pip ...
python -m pip install --upgrade pip >nul

echo Installing dependencies (this takes ~2 min) ...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo *** Install failed. See error above. ***
  pause
  exit /b 1
)

if not exist ".env" (
  echo.
  echo Copying .env.example -^> .env ...
  copy /Y ".env.example" ".env" >nul
  notepad .env
)

echo.
echo === Setup complete ===
echo Now double-click run_voice.bat (voice mode) or run_text.bat (text only).
echo.
pause
