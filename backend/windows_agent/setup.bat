@echo off
REM GHOST · one-click setup for Windows
REM Run: just double-click this .bat
REM (or right-click in folder → "Open PowerShell window here" → setup.bat)

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

echo Installing core dependencies (this takes ~2 min) ...
python -m pip install -r requirements-core.txt
if errorlevel 1 (
  echo.
  echo *** Core install failed. See error above. ***
  pause
  exit /b 1
)

echo.
echo Installing optional Emergent integration (skipped on failure) ...
python -m pip install --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ emergentintegrations
if errorlevel 1 (
  echo.
  echo NOTE: emergentintegrations could not be installed.
  echo That is OK — you can still run GHOST with your own Anthropic + OpenAI keys.
  echo Edit .env and use Option B (ANTHROPIC_API_KEY + OPENAI_API_KEY).
  echo.
)

if not exist ".env" (
  echo.
  echo Copying .env.example -^> .env ...
  copy /Y ".env.example" ".env" >nul
  echo IMPORTANT: open .env and choose ONE option:
  echo   Option A: leave EMERGENT_LLM_KEY as-is (easiest)
  echo   Option B: comment out EMERGENT_LLM_KEY and fill in ANTHROPIC + OPENAI keys
  notepad .env
)

echo.
echo === Setup complete ===
echo Now double-click run_voice.bat (voice mode) or run_text.bat (text only).
echo.
pause
